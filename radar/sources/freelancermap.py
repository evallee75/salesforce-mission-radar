"""freelancermap — board de projets IT freelance (DE/AT/CH/UK/Benelux…).

La page de recherche embarque l'état initial en JSON (`initialState.result.projects`) :
titre, description, pays, durée, date de début, type de contrat. Une seule requête,
pas de page détail. Excellent pour l'international.
"""
from __future__ import annotations

import json
from typing import Dict, List, Optional

from bs4 import BeautifulSoup

from ..models import Offer
from ..text import clean_html, country_from_iso, detect_country, is_salesforce_offer
from .base import Source

_SEARCH = "https://www.freelancermap.com/projects"
_BASE = "https://www.freelancermap.com/project/"


class FreelancermapSource(Source):
    name = "freelancermap"
    label = "freelancermap"

    def search(self, keyword: str, cfg: Dict, known_ids) -> List[Offer]:
        resp = self.get(_SEARCH, params={"query": keyword})
        if resp is None:
            return []
        projects = _initial_projects(resp.text)
        return [o for o in map(self._parse, projects) if o]

    def _parse(self, p: dict) -> Optional[Offer]:
        desc = clean_html(p.get("description"))
        title = p.get("title") or ""
        if not p.get("slug") or not is_salesforce_offer(title, desc):
            return None
        country = p.get("country") or {}
        contract = p.get("projectContractType") or {}
        remote_pct = contract.get("remoteInPercent")
        location = ", ".join(x for x in (p.get("city"), country.get("nameEn")) if x) or None
        return Offer(
            id=f"freelancermap:{p.get('id')}",
            source=self.name,
            title=title,
            url=_BASE + p["slug"],
            company=None if p.get("company") in (None, "", "Unknown") else p.get("company"),
            location=location,
            country=country_from_iso(country.get("iso2")) or detect_country(location),
            remote=("Full remote" if remote_pct == 100 else
                    "Hybride" if remote_pct else "Sur site" if remote_pct == 0 else None),
            duration=p.get("durationText") or None,
            published=(p.get("created") or "")[:10] or None,
            snippet=clean_html(desc, 280),
            contract="Freelance",
            confirmed_freelance=True,
            text=f"{title} {desc} {p.get('beginningText') or ''} {p.get('durationText') or ''}",
        )


def _initial_projects(page: str) -> List[dict]:
    soup = BeautifulSoup(page, "lxml")
    for tag in soup.find_all("script", type="application/json"):
        raw = tag.string or ""
        if '"initialState"' not in raw[:200] and "initialState" not in raw:
            continue
        try:
            data = json.loads(raw)
        except ValueError:
            continue
        projects = ((data.get("initialState") or {}).get("result") or {}).get("projects")
        if isinstance(projects, list):
            return projects
    return []
