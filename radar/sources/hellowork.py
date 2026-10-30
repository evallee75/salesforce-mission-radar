"""Hellowork — job board national FR, filtre contrat Freelance natif.

Recherche HTML publique (cartes `data-cy`). Pas de TJM dans la liste : il est lu
sur la page détail, uniquement pour les NOUVELLES offres.
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

from bs4 import BeautifulSoup

from ..models import Offer
from ..text import clean_html
from .base import Source

_BASE = "https://www.hellowork.com"
_SEARCH = f"{_BASE}/fr-fr/emploi/recherche.html"
_REL_DATE = re.compile(r"il y a\s+(\d+)\s+(minute|heure|jour|semaine|mois)", re.I)
_TJM_LABEL = re.compile(r"Taux journalier\s*:?\s*(.{0,60})", re.I)
_MODE = re.compile(r"(Hybride|Full remote|T[ée]l[ée]travail complet|100\s*%\s*t[ée]l[ée]travail|Sur site|Pr[ée]sentiel)", re.I)
_DETAIL_WORKERS = 8


class HelloworkSource(Source):
    name = "hellowork"
    label = "Hellowork"

    def search(self, keyword: str, cfg: Dict, known_ids) -> List[Offer]:
        resp = self.get(_SEARCH, params={"k": keyword, "c": "Freelance", "l": "France"})
        if resp is None:
            return []
        cards = BeautifulSoup(resp.text, "lxml").select('[data-cy="serpCard"]')
        out = [o for o in map(self._parse, cards) if o]
        todo = [o for o in out if o.id not in known_ids]
        with ThreadPoolExecutor(max_workers=_DETAIL_WORKERS) as pool:
            list(pool.map(self._enrich, todo))
        return out

    def _parse(self, card) -> Optional[Offer]:
        a = card.select_one('a[data-cy="offerTitle"]')
        if not a or not a.get("href"):
            return None
        href = a["href"].split("?")[0]
        m = re.search(r"/emplois/(\d+)", href)
        aria = a.get("aria-label", "")
        mc = re.search(r",\s*chez\s+(.+?),\s*pour", aria)
        company = mc.group(1).strip() if mc else None
        title = (a.get("title") or a.get_text(strip=True) or "").strip()
        if company and title.endswith(f"- {company}"):
            title = title[: -len(f"- {company}")].strip()
        loc_el = card.select_one('[data-cy="localisationCard"]')
        text = card.get_text(" ", strip=True)
        return Offer(
            id=f"hellowork:{m.group(1) if m else href}",
            source=self.name,
            title=title or "(sans titre)",
            url=href if href.startswith("http") else _BASE + href,
            company=company,
            location=loc_el.get_text(strip=True) if loc_el else None,
            country="France",
            remote="Full remote" if re.search(r"t[ée]l[ée]travail complet", text, re.I) else None,
            published=_rel_to_date(text),
            contract="Freelance",
            confirmed_freelance=True,
            text=text,
        )

    def _enrich(self, offer: Offer) -> None:
        resp = self.get(offer.url, timeout=15)
        if resp is None:
            return
        txt = BeautifulSoup(resp.text, "lxml").get_text(" ", strip=True)
        lo, hi = _parse_tjm(txt)
        if lo:
            offer.tjm_min, offer.tjm_max = lo, hi
        mode = _MODE.search(txt)
        if mode:
            k = mode.group(1).lower()
            offer.remote = ("Hybride" if "hybride" in k else
                            "Sur site" if ("site" in k or "sentiel" in k) else "Full remote")
        offer.text = txt[:8000]
        if not offer.snippet:
            i = txt.find("Le poste")
            offer.snippet = clean_html(txt[i:i + 600] if i >= 0 else "", 280) or None


def _parse_tjm(text: str) -> Tuple[Optional[int], Optional[int]]:
    """'Taux journalier : 450 - 550 €' -> (450, 550). (None, None) si 'Selon profil'."""
    m = _TJM_LABEL.search(text)
    if not m:
        return None, None
    nums = [int(n) for n in re.findall(r"\d{3,4}", m.group(1)) if 150 <= int(n) <= 3000]
    if not nums:
        return None, None
    return min(nums[:2]), max(nums[:2])


def _rel_to_date(text: str) -> Optional[str]:
    m = _REL_DATE.search(text)
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2).lower()
    days = {"minute": 0, "heure": 0, "jour": n, "semaine": n * 7, "mois": n * 30}[unit]
    return (date.today() - timedelta(days=days)).isoformat()
