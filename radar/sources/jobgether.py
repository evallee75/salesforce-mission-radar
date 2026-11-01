"""Jobgether — agrégateur 100 % remote (API Astro non documentée du site).

`contractType=freelance` uniquement. Les offres géo-restreintes hors Europe/monde
(Inde, USA, Brésil…) sont écartées : non exploitables depuis la France.
Description + TJM lus sur la fiche détail (JSON-LD), pour les NOUVELLES offres.
"""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional

from bs4 import BeautifulSoup

from ..models import Offer
from ..text import EUROPE, clean_html, detect_country, strip_accents_lower, to_utc_timestamp
from .base import Source

_API = "https://jobgether.com/astroapi/offer/search"
_OFFER_URL = "https://jobgether.com/offer/{slug}"
_MAX_PAGES = 3
_DETAIL_WORKERS = 4
_OPEN_TERMS = ("europe", "emea", "worldwide", "anywhere", "global", "remote")


class JobgetherSource(Source):
    name = "jobgether"
    label = "Jobgether"

    def __init__(self) -> None:
        super().__init__()
        self.session.headers.update({"Accept": "application/json",
                                     "Referer": "https://jobgether.com/remote-jobs/search-offers"})

    def search(self, keyword: str, cfg: Dict, known_ids) -> List[Offer]:
        out: List[Offer] = []
        for page in range(1, _MAX_PAGES + 1):
            resp = self.get(_API, params={"keyword": keyword, "contractType": "freelance",
                                          "page": str(page), "$count": "true"})
            if resp is None:
                break
            payload = resp.json()
            for m in payload.get("data", []):
                if _location_ok(m.get("requiredLocations")):
                    offer = self._parse(m)
                    if offer:
                        out.append(offer)
            if page >= payload.get("maxPages", page):
                break
        todo = [o for o in out if o.id not in known_ids]
        with ThreadPoolExecutor(max_workers=_DETAIL_WORKERS) as pool:
            list(pool.map(self._enrich, todo))
        return out

    def _parse(self, m: dict) -> Optional[Offer]:
        raw_id, slug = m.get("_id") or m.get("id"), m.get("slug")
        if not raw_id or not slug:
            return None
        skills = list(dict.fromkeys(s.get("name") for s in (m.get("skills") or [])
                                    if isinstance(s, dict) and s.get("name")))
        location = (m.get("requiredLocations") or "").strip() or "Remote"
        return Offer(
            id=f"jobgether:{raw_id}",
            source=self.name,
            title=m.get("title") or "(sans titre)",
            url=_OFFER_URL.format(slug=slug),
            company=(m.get("companyData") or {}).get("name") or m.get("company"),
            location=location,
            country=detect_country(location),
            remote="Full remote",
            published=(m.get("createdAt") or "")[:10] or None,
            published_at=to_utc_timestamp(m.get("createdAt")),
            skills=skills[:8],
            contract="Freelance",
            confirmed_freelance=True,
            text=m.get("title"),
        )

    def _enrich(self, offer: Offer) -> None:
        resp = self.get(offer.url, timeout=15)
        if resp is None:
            return
        resp.encoding = "utf-8"
        desc = _job_posting_description(resp.text)
        if desc:
            text = clean_html(desc)
            offer.text = f"{offer.title} {text}"
            offer.snippet = clean_html(text, 280)


def _location_ok(required: Optional[str]) -> bool:
    if not required or not required.strip():
        return True
    hay = strip_accents_lower(required)
    return any(t in hay for t in _OPEN_TERMS) or detect_country(required) in EUROPE


def _job_posting_description(page: str) -> Optional[str]:
    soup = BeautifulSoup(page, "lxml")
    for tag in soup.find_all("script", attrs={"type": re.compile("ld\\+json")}):
        try:
            data = json.loads(tag.string or "")
        except (ValueError, TypeError):
            continue
        for node in (data if isinstance(data, list) else [data]):
            if isinstance(node, dict) and node.get("@type") == "JobPosting":
                return node.get("description")
    return None
