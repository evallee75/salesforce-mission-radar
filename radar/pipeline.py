"""Orchestration d'un scan : sources en parallèle → classification → fusion avec
l'historique → dédoublonnage → fichiers statiques du site.

Pas de base de données : l'état vit dans `data/` (JSON versionné par le workflow
GitHub Actions) et le site lit des JSON pré-calculés dans `site/data/`. C'est ce
qui rend l'interface instantanée : aucun calcul ni scrape à l'ouverture de la page.
"""
from __future__ import annotations

import json
import logging
import os
import re
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Set, Tuple

import yaml

from . import companies
from .classify import apply_ai, classify
from .feed import format_rate, write_feed
from .sources import REGISTRY, get_source
from .text import is_permanent, is_salesforce_offer, scrub_contacts, strip_accents_lower

log = logging.getLogger("radar.pipeline")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_PATH = os.path.join(ROOT, "data", "state.json")
COMPANIES_PATH = os.path.join(ROOT, "data", "companies.json")
# Analyse IA (routine Claude Code planifiée, voir ROUTINE.md) :
#  - TEXTS_PATH : texte complet des annonces récentes, matière première de l'analyse ;
#  - AI_QUEUE_PATH : annonces à analyser, régénéré à chaque publication ;
#  - AI_PATH : résultats écrits par la routine, fusionnés à la publication.
TEXTS_PATH = os.path.join(ROOT, "data", "texts.json")
AI_QUEUE_PATH = os.path.join(ROOT, "data", "ai_queue.json")
AI_PATH = os.path.join(ROOT, "data", "ai.json")
AI_QUEUE_MAX = 60
AI_QUEUE_DAYS = 10
_TEXT_MAX = 5000
SITE_DATA = os.path.join(ROOT, "site", "data")

# En cas de doublon, on garde la source la plus riche (plus petit = prioritaire).
SOURCE_PRIORITY = {"freework": 0, "wttj": 1, "freelancermap": 2, "hellowork": 3,
                   "linkedin": 4, "codeur": 5, "peopleperhour": 6, "freelancer": 7,
                   "jobgether": 8, "remoteok": 9}
# Une offre non revue depuis N jours est considérée comme pourvue / retirée.
ACTIVE_DAYS = 3
# Champs internes non publiés dans le JSON du site.
_PRIVATE_FIELDS = {"text", "enriched"}


def load_config() -> dict:
    with open(os.path.join(ROOT, "config.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def run(publish_only: bool = False) -> dict:
    """Scan complet, ou seulement republication (`publish_only`) : utilisé après
    que la routine IA a poussé de nouvelles analyses, sans re-scraper les sites."""
    cfg = load_config()
    started = time.time()
    state: Dict[str, dict] = _read_json(STATE_PATH, {})
    texts: Dict[str, str] = _read_json(TEXTS_PATH, {})
    known = {oid for oid, o in state.items() if o.get("enriched")}

    if publish_only:
        previous_meta = _read_json(os.path.join(SITE_DATA, "offers.json"), {}).get("meta", {})
        scraped, stats = [], previous_meta.get("sources", {})
    else:
        scraped, stats = _scrape(cfg, known)
    today = date.today().isoformat()
    # first_seen est horodaté (le front marque « Nouveau » à l'heure près) ;
    # last_seen reste une date (purge et statut « actif » au jour près).
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    new_ids = []
    for o in scraped:
        prev = state.get(o["id"])
        if not prev and not is_salesforce_offer(o["title"], f"{o.get('text')} {' '.join(o['skills'])}"):
            stats[o["source"]]["off_topic"] = stats[o["source"]].get("off_topic", 0) + 1
            continue
        # Le freelance natif (FreeWork, WTTJ…) est fiable ; ailleurs on écarte les CDI.
        if not prev and o["contract"] != "Freelance" and is_permanent(o.get("text")):
            stats[o["source"]]["permanent"] = stats[o["source"]].get("permanent", 0) + 1
            continue
        o["enriched"] = bool(prev and prev.get("enriched")) or _is_enriched(o)
        o["first_seen"] = prev["first_seen"] if prev else now
        o["last_seen"] = today
        if prev:
            for k in ("snippet", "remote", "duration", "company", "published", "skills"):
                o[k] = o.get(k) or prev.get(k)
        else:
            new_ids.append(o["id"])
        classify(o, prev)
        text = scrub_contacts(o.pop("text", None) or "")
        if len(text) > len(texts.get(o["id"], "")):
            texts[o["id"]] = text[:_TEXT_MAX]
        o["snippet"] = scrub_contacts(o.get("snippet"))
        state[o["id"]] = o

    retention = int(cfg.get("retention_days", 45))
    cutoff = (date.today() - timedelta(days=retention)).isoformat()
    state = {k: v for k, v in state.items() if v.get("last_seen", "") >= cutoff}
    # Re-score les offres non revues aujourd'hui : la fraîcheur évolue chaque jour.
    for o in state.values():
        if o["last_seen"] != today or publish_only:
            classify(o, dict(o))

    company_db = _update_companies(_read_json(COMPANIES_PATH, {}), state.values())
    offers = _publishable(state.values())
    # L'analyse IA ne s'applique qu'aux copies publiées : l'état persistant reste
    # celui des regex, et une analyse retirée de ai.json ne laisse aucune trace.
    ai = _read_json(AI_PATH, {})
    for o in offers:
        apply_ai(o, ai.get(o["id"]))
    offers.sort(key=lambda o: (o["active"], o["score"], o.get("published") or ""), reverse=True)
    texts = {k: v for k, v in texts.items() if k in state}
    _write_json(AI_QUEUE_PATH, _ai_queue(offers, ai, texts))
    meta = {
        "generated_at": (previous_meta.get("generated_at") if publish_only else None)
        or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "ai_analyzed": sum(1 for o in offers if o.get("ai")),
        "duration_s": round(time.time() - started, 1),
        "sources": stats,
        "source_labels": {name: cls.label for name, cls in REGISTRY.items()},
        "new_today": len(new_ids),
        "count": len(offers),
    }

    _write_json(STATE_PATH, state)
    _write_json(TEXTS_PATH, texts)
    _write_json(COMPANIES_PATH, company_db)
    _write_json(os.path.join(SITE_DATA, "offers.json"), {"meta": meta, "offers": offers})
    _write_json(os.path.join(SITE_DATA, "companies.json"),
                {"generated_at": meta["generated_at"], "companies": _public_companies(company_db)})
    site_url = cfg.get("site_url") or ""
    write_feed(os.path.join(ROOT, "site", "feed.xml"), offers, site_url,
               "Salesforce Mission Radar — nouvelles missions", lambda o: True)
    write_feed(os.path.join(ROOT, "site", "feed-courtes.xml"), offers, site_url,
               "Salesforce Mission Radar — missions courtes & temps partiel",
               lambda o: o.get("short") or o.get("part_time"))

    log.info("%s en %.0fs : %d offres publiées (%d analysées par l'IA), %d nouvelles, %d entreprises.",
             "Publication" if publish_only else "Scan terminé", meta["duration_s"], len(offers),
             meta["ai_analyzed"], len(new_ids), len(company_db))
    for name, s in stats.items():
        log.info("  %-14s %4d offres%s", name, s["count"], f"  ⚠ {s['error']}" if s.get("error") else "")
    return {"meta": meta, "offers": offers, "new_ids": set(new_ids)}


# --- Analyse IA ---------------------------------------------------------------------------
def _ai_queue(offers: List[dict], ai: Dict[str, dict], texts: Dict[str, str]) -> List[dict]:
    """Annonces récentes et actives pas encore analysées, les plus prometteuses d'abord."""
    cutoff = (date.today() - timedelta(days=AI_QUEUE_DAYS)).isoformat()
    todo = [o for o in offers if o["active"] and o["id"] not in ai and o["first_seen"] >= cutoff]
    todo.sort(key=lambda o: o["score"], reverse=True)
    return [{
        "id": o["id"], "title": o["title"], "company": o.get("company"),
        "location": o.get("location"), "country": o.get("country"), "source": o["source"],
        "lang": o.get("lang"), "rate": format_rate(o) or None, "duration": o.get("duration"),
        "text": texts.get(o["id"]) or o.get("snippet") or "",
    } for o in todo[:AI_QUEUE_MAX]]


# --- Scrape ------------------------------------------------------------------------
def _scrape(cfg: dict, known: Set[str]) -> Tuple[List[dict], Dict[str, dict]]:
    names = [s for s in (cfg.get("sources") or REGISTRY) if s in REGISTRY]
    keywords = cfg.get("keywords") or ["salesforce"]
    tasks = [(s, kw) for s in names for kw in keywords]
    stats = {s: {"count": 0, "error": None} for s in names}
    seen, out = set(), []

    def job(source_name, keyword):
        return [asdict(o) for o in get_source(source_name).search(keyword, cfg, known)]

    with ThreadPoolExecutor(max_workers=len(tasks) or 1) as pool:
        futures = {pool.submit(job, s, kw): s for s, kw in tasks}
        for fut in as_completed(futures):
            s = futures[fut]
            try:
                for o in fut.result():
                    if o["id"] not in seen:
                        seen.add(o["id"])
                        out.append(o)
                        stats[s]["count"] += 1
            except Exception as exc:   # une source cassée ne doit jamais bloquer le scan
                log.exception("Source %s en erreur", s)
                stats[s]["error"] = f"{type(exc).__name__}: {exc}"[:200]
    return out, stats


def _is_enriched(o: dict) -> bool:
    """Vrai si l'offre a un vrai texte (pas juste son titre) : inutile de relire la page détail."""
    return len(o.get("text") or "") > len(o.get("title") or "") + 80


# --- Dédoublonnage & publication ------------------------------------------------------
def _dedupe_key(o: dict) -> str:
    title = strip_accents_lower(o.get("title") or "")
    title = re.sub(r"\(?\b[hfmwx]\s*/\s*[hfmwx](?:\s*/\s*[dx])?\b\)?", " ", title)   # H/F, m/w/d…
    title = re.sub(r"[^a-z0-9]+", " ", title).strip()
    company = companies.normalize_company(o.get("company"))
    if companies.is_placeholder(o.get("company")):
        company = ""
    return f"{title}|{company}"


def _publishable(offers) -> List[dict]:
    today = date.today()
    groups: Dict[str, List[dict]] = {}
    for o in offers:
        groups.setdefault(_dedupe_key(o), []).append(o)
    out = []
    for group in groups.values():
        group.sort(key=lambda x: SOURCE_PRIORITY.get(x["source"], 99))
        best = {k: v for k, v in group[0].items() if k not in _PRIVATE_FIELDS}
        best["also_on"] = [{"source": g["source"], "url": g["url"]} for g in group[1:]
                           if g["source"] != best["source"]]
        # Une info manquante sur la source prioritaire peut venir d'un doublon.
        for k in ("tjm_min", "tjm_max", "company", "remote", "duration_days", "part_time"):
            if not best.get(k):
                best[k] = next((g[k] for g in group[1:] if g.get(k)), best.get(k))
        best["first_seen"] = min(g["first_seen"] for g in group)
        last_seen = max(g["last_seen"] for g in group)
        best["active"] = (today - date.fromisoformat(last_seen)).days <= ACTIVE_DAYS
        out.append(best)
    out.sort(key=lambda o: (o["active"], o["score"], o.get("published") or ""), reverse=True)
    return out


# --- Vivier entreprises (jamais purgé) -------------------------------------------------
def _update_companies(db: Dict[str, dict], offers) -> Dict[str, dict]:
    for o in offers:
        name = o.get("company")
        key = companies.normalize_company(name)
        if not key or companies.is_placeholder(name):
            continue
        c = db.setdefault(key, {"name": name, "offer_ids": [], "tjm": [], "sources": [],
                                "countries": [], "titles": [], "short": 0,
                                "first_seen": o["first_seen"], "last_seen": o["last_seen"]})
        c["is_esn"] = companies.is_esn(name)
        c["last_seen"] = max(c["last_seen"], o["last_seen"])
        if o["id"] in c["offer_ids"]:
            continue
        c["offer_ids"].append(o["id"])
        tjm = o.get("tjm_max") or o.get("tjm_min")
        if tjm:
            c["tjm"] = (c["tjm"] + [tjm])[-50:]
        for field, value in (("sources", o["source"]), ("countries", o.get("country"))):
            if value and value not in c[field]:
                c[field].append(value)
        c["titles"] = ([{"title": o["title"], "url": o["url"], "date": o["first_seen"]}]
                       + c["titles"])[:5]
        c["short"] += 1 if (o.get("short") or o.get("part_time")) else 0
    return db


def _public_companies(db: Dict[str, dict]) -> List[dict]:
    rows = []
    for c in db.values():
        rows.append({
            "name": c["name"], "is_esn": c.get("is_esn", False),
            "missions": len(c["offer_ids"]), "short": c.get("short", 0),
            "tjm_median": int(statistics.median(c["tjm"])) if c["tjm"] else None,
            "sources": c["sources"], "countries": c["countries"], "titles": c["titles"],
            "first_seen": c["first_seen"], "last_seen": c["last_seen"],
        })
    rows.sort(key=lambda r: (r["last_seen"], r["missions"]), reverse=True)
    return rows


# --- JSON ------------------------------------------------------------------------------
def _read_json(path: str, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return default


def _write_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)
