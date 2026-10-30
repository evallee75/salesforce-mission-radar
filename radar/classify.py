"""Classification d'une offre et score d'opportunité (0-100).

Le score sert à trier « ce qui vaut le coup de répondre aujourd'hui ». Il favorise :
fraîcheur (répondre parmi les premiers), format court / temps partiel (l'objectif
business), TJM élevé, client final plutôt qu'ESN, remote.
Chaque point est expliqué dans `reasons` pour que le score reste lisible à l'écran.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Dict, List, Optional

from . import companies
from .text import (FRENCH_SPEAKING, detect_country, detect_part_time, find_rate,
                   is_salesforce, is_tma, parse_duration_days, short_signals, zone_of)

# Places de marché de petites missions : tout y est « gig » par nature.
MARKETPLACES = {"peopleperhour", "freelancer", "codeur"}
# Sources françaises : pays par défaut = France quand la localisation est muette.
FRENCH_SOURCES = {"freework", "hellowork", "wttj", "codeur"}
SHORT_MAX_DAYS = 45
# Au-delà, une mission n'est pas « courte », quels que soient les mots employés.
LONG_MIN_DAYS = 90


def classify(o: Dict, previous: Optional[Dict] = None) -> Dict:
    """Complète l'offre `o` (dict) avec pays, zone, durée, signaux et score.

    `previous` = version déjà en base : ses signaux sont conservés quand le run
    courant n'a pas relu la page détail (texte plus pauvre).
    """
    prev = previous or {}
    text = o.get("text") or o.get("title") or ""

    if not o.get("country"):
        o["country"] = detect_country(o.get("location")) or prev.get("country")
        if not o["country"] and o["source"] in FRENCH_SOURCES:
            o["country"] = "France"
    o["zone"] = zone_of(o.get("country"), o.get("remote"))

    if not o.get("tjm_min"):
        lo, hi = find_rate(text)
        o["tjm_min"], o["tjm_max"] = lo or prev.get("tjm_min"), hi or prev.get("tjm_max")
    o["duration_days"] = (parse_duration_days(o.get("duration"), text)
                          or prev.get("duration_days"))
    o["part_time"] = o.get("part_time") or detect_part_time(text) or prev.get("part_time")

    days = o["duration_days"]
    renewable = bool(re.search(r"renouvel|renewable|extension", o.get("duration") or "", re.I))
    short_by_duration = days is not None and days <= SHORT_MAX_DAYS and not renewable
    is_long = days is not None and days > LONG_MIN_DAYS
    reason = None if is_long else short_signals(o.get("title"), text)
    is_gig = o["source"] in MARKETPLACES
    o["short"] = bool(is_gig or short_by_duration or reason or (prev.get("short") and not is_long))
    o["short_reason"] = (
        f"{days} jours" if short_by_duration
        else reason or ("petite mission" if is_gig else None)
        or (prev.get("short_reason") if o["short"] else None)
    )
    o["tma"] = is_tma(text) or bool(prev.get("tma"))
    o["sf_title"] = is_salesforce(o.get("title"))
    o["gig"] = is_gig

    company = o.get("company")
    o["is_esn"] = bool(company) and companies.is_esn(company)
    o["client_final"] = bool(company) and not o["is_esn"] and not companies.is_placeholder(company)
    o["lang"] = "fr" if (o.get("country") in FRENCH_SPEAKING or o["zone"] == "France") else "en"

    o["score"], o["reasons"] = _score(o)
    return o


def _score(o: Dict):
    points: List[tuple] = []
    if o.get("sf_title"):
        points.append((15, "Salesforce dans l'intitulé"))
    age = _age_days(o.get("published") or o.get("first_seen"))
    if age is not None:
        if age <= 1:
            points.append((25, "publiée il y a moins de 48 h"))
        elif age <= 3:
            points.append((20, "publiée cette semaine"))
        elif age <= 7:
            points.append((12, "publiée il y a moins de 8 jours"))
        elif age <= 14:
            points.append((6, "publiée il y a moins de 15 jours"))

    if o.get("short") and o.get("part_time"):
        points.append((25, "courte et à temps partiel"))
    elif o.get("short") and o.get("gig"):
        # Places de marché : courtes par nature, mais budgets souvent modestes.
        points.append((12, "petite mission (place de marché)"))
    elif o.get("short"):
        points.append((20, "mission courte"))
    elif o.get("part_time"):
        points.append((20, "temps partiel"))
    if o.get("tma"):
        points.append((5, "TMA / support récurrent"))

    tjm = o.get("tjm_max") or o.get("tjm_min")
    if tjm:
        if tjm >= 800:
            points.append((20, "TJM ≥ 800 €"))
        elif tjm >= 650:
            points.append((15, "TJM ≥ 650 €"))
        elif tjm >= 500:
            points.append((10, "TJM ≥ 500 €"))
        else:
            points.append((4, "TJM affiché"))
    elif o.get("budget_eur") is not None and o["budget_eur"] < 300:
        points.append((-15, "budget inférieur à 300 €"))
    elif o.get("budget"):
        points.append((4, "budget affiché"))

    if o.get("client_final"):
        points.append((15, "client final (pas une ESN)"))
    elif not o.get("company"):
        points.append((4, "société non précisée"))

    if o.get("remote") == "Full remote":
        points.append((8, "full remote"))
    elif o.get("remote") == "Hybride":
        points.append((4, "hybride"))
    if o.get("confirmed_freelance"):
        points.append((7, "freelance confirmé"))

    return max(0, min(100, sum(p for p, _ in points))), [r for _, r in points]


def _age_days(iso: Optional[str]) -> Optional[int]:
    if not iso:
        return None
    try:
        return (date.today() - date.fromisoformat(iso[:10])).days
    except ValueError:
        return None
