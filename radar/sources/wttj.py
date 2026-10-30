"""Welcome to the Jungle — index Algolia public utilisé par le site.

Clé search-only publique ; l'en-tête `Referer` est OBLIGATOIRE (sinon 403).
Si la clé est tournée (403 persistant), la ré-extraire via
`GET https://www.welcometothejungle.com/api/env` avec un User-Agent Googlebot.
Filtre `contract_type:freelance` ; TJM présent quand `salary_period` = daily.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import requests

from ..models import Offer
from ..text import clean_html, country_from_iso
from .base import Source

_APP_ID = "CSEKHVMS53"
_API_KEY = "4bd8f6215d0cc52b26430765769e65a0"   # clé publique search-only
_API = f"https://{_APP_ID}-dsn.algolia.net/1/indexes/wttj_jobs_production_fr/query"
_OFFER_URL = "https://www.welcometothejungle.com/fr/companies/{org}/jobs/{slug}"
_REMOTE = {"fulltime": "Full remote", "partial": "Hybride", "punctual": "Hybride", "no": "Sur site"}
_MAX_PAGES = 3


class WttjSource(Source):
    name = "wttj"
    label = "Welcome to the Jungle"

    def __init__(self) -> None:
        super().__init__()
        self.session.headers.update({
            "x-algolia-application-id": _APP_ID,
            "x-algolia-api-key": _API_KEY,
            "Referer": "https://www.welcometothejungle.com/",
            "Content-Type": "application/json",
        })

    def search(self, keyword: str, cfg: Dict, known_ids) -> List[Offer]:
        out: List[Offer] = []
        for page in range(_MAX_PAGES):
            body = {"query": keyword, "facetFilters": [["contract_type:freelance"]],
                    "hitsPerPage": 50, "page": page}
            try:
                resp = self.session.post(_API, json=body, timeout=25)
            except requests.RequestException as exc:
                self.log.warning("Erreur réseau WTTJ : %s", exc)
                break
            if resp.status_code != 200:
                self.log.warning("WTTJ a renvoyé %s", resp.status_code)
                break
            data = resp.json()
            out += [o for o in map(self._parse, data.get("hits", [])) if o]
            if page + 1 >= data.get("nbPages", 0):
                break
        return out

    def _parse(self, h: dict) -> Optional[Offer]:
        org = h.get("organization") or {}
        if not (h.get("objectID") and h.get("slug") and org.get("slug")):
            return None
        lo = hi = None
        if h.get("salary_period") in ("daily", "day"):
            lo, hi = _int(h.get("salary_minimum")), _int(h.get("salary_maximum"))
            lo, hi = lo or hi, hi or lo
        office = (h.get("offices") or [{}])[0]
        location = ", ".join(p for p in (office.get("city"), office.get("state")) if p) or None
        summary = h.get("summary") or ""
        return Offer(
            id=f"wttj:{h['objectID']}",
            source=self.name,
            title=h.get("name") or "(sans titre)",
            url=_OFFER_URL.format(org=org["slug"], slug=h["slug"]),
            company=org.get("name"),
            location=location,
            country=country_from_iso(office.get("country_code")),
            remote=_REMOTE.get(h.get("remote")),
            tjm_min=lo,
            tjm_max=hi,
            published=h.get("published_at_date"),
            snippet=clean_html(summary, 280),
            contract="Freelance",
            confirmed_freelance=True,
            text=f"{h.get('name') or ''} {summary} {h.get('profile') or ''}",
        )


def _int(v) -> Optional[int]:
    try:
        return int(round(float(v))) if v is not None else None
    except (TypeError, ValueError):
        return None
