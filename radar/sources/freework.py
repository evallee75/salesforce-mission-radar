"""FreeWork — API JSON publique (api.free-work.com). Source la plus riche :
freelance natif, TJM, durée, compétences, description complète.

Pas de filtre de localisation : on prend toute la France + l'étranger (FreeWork
publie aussi Belgique, Suisse, Luxembourg…), le tri se fait côté interface.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from ..models import Offer
from ..text import clean_html, country_from_iso, to_utc_timestamp
from .base import Source

_API = "https://api.free-work.com/job_postings"
_REMOTE = {"full": "Full remote", "partial": "Hybride", "none": "Sur site"}
_PERIOD = {"month": "mois", "day": "jours", "year": "ans", "week": "semaines"}
_PAGE_SIZE = 50
_MAX_PAGES = 6


class FreeWorkSource(Source):
    name = "freework"
    label = "Free-Work"

    def __init__(self) -> None:
        super().__init__()
        self.session.headers["Accept"] = "application/ld+json"

    def search(self, keyword: str, cfg: Dict, known_ids) -> List[Offer]:
        out: List[Offer] = []
        for page in range(1, _MAX_PAGES + 1):
            resp = self.get(_API, params={"searchKeywords": keyword, "contracts": "contractor",
                                          "itemsPerPage": str(_PAGE_SIZE), "page": str(page)})
            if resp is None:
                break
            members = resp.json().get("hydra:member", [])
            out += [o for o in map(self._parse, members) if o]
            if len(members) < _PAGE_SIZE:
                break
        return out

    def _parse(self, m: dict) -> Optional[Offer]:
        if m.get("id") is None:
            return None
        job_slug, slug = (m.get("job") or {}).get("slug"), m.get("slug")
        url = (f"https://www.free-work.com/fr/tech-it/{job_slug}/job-mission/{slug}"
               if job_slug and slug else "https://www.free-work.com" + (m.get("@id") or ""))
        loc = m.get("location") or {}
        duration = None
        if m.get("durationValue"):
            period = _PERIOD.get(m.get("durationPeriod"), m.get("durationPeriod") or "")
            duration = f"{m['durationValue']} {period}".strip()
            if m.get("renewable"):
                duration += " (renouvelable)"
        text = clean_html(f"{m.get('description') or ''} {m.get('candidateProfile') or ''}")
        return Offer(
            id=f"freework:{m['id']}",
            source=self.name,
            title=m.get("title") or "(sans titre)",
            url=url,
            company=(m.get("company") or {}).get("name"),
            location=loc.get("locality") or loc.get("adminLevel2") or loc.get("adminLevel1"),
            country=country_from_iso(loc.get("countryCode")),
            remote=_REMOTE.get(m.get("remoteMode")),
            tjm_min=_int(m.get("minDailySalary")),
            tjm_max=_int(m.get("maxDailySalary")),
            duration=duration,
            published=(m.get("publishedAt") or "")[:10] or None,
            published_at=to_utc_timestamp(m.get("publishedAt")),
            skills=[s["name"] for s in (m.get("skills") or []) if s.get("name")][:10],
            snippet=clean_html(m.get("description"), 280),
            contract="Freelance",
            confirmed_freelance=True,
            text=text,
        )


def _int(v) -> Optional[int]:
    try:
        return int(round(float(v))) if v is not None else None
    except (TypeError, ValueError):
        return None
