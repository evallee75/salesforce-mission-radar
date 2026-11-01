"""Freelancer.com — API publique des projets actifs (sans authentification).

Petits projets au forfait ou à l'heure, du monde entier. La recherche est floue :
on ne garde que les projets dont le titre parle de Salesforce ou qui demandent
explicitement une compétence Salesforce (champ `jobs`).
Les taux horaires sont convertis en TJM (8 h), les forfaits gardés en « budget ».
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from ..models import Offer
from ..text import clean_html, is_salesforce, to_eur, to_utc_timestamp
from .base import Source

_API = "https://www.freelancer.com/api/projects/0.1/projects/active/"
_BASE = "https://www.freelancer.com/projects/"


class FreelancerSource(Source):
    name = "freelancer"
    label = "Freelancer.com"

    def search(self, keyword: str, cfg: Dict, known_ids) -> List[Offer]:
        resp = self.get(_API, params={"query": keyword, "limit": "100",
                                      "full_description": "true", "job_details": "true",
                                      "sort_field": "time_updated"})
        if resp is None:
            return []
        projects = (resp.json().get("result") or {}).get("projects") or []
        return [o for o in map(self._parse, projects) if o]

    def _parse(self, p: dict) -> Optional[Offer]:
        title = p.get("title") or ""
        desc = p.get("description") or p.get("preview_description") or ""
        skills = [j.get("name") or "" for j in (p.get("jobs") or [])]
        if not p.get("seo_url") or not (is_salesforce(title) or any(map(is_salesforce, skills))):
            return None
        budget = p.get("budget") or {}
        currency = (p.get("currency") or {}).get("code") or "USD"
        lo, hi = budget.get("minimum"), budget.get("maximum")
        tjm_min = tjm_max = None
        budget_label = budget_eur = None
        if p.get("type") == "hourly":
            day_lo, day_hi = to_eur((lo or 0) * 8, currency), to_eur((hi or lo or 0) * 8, currency)
            if day_lo and day_lo >= 150:
                tjm_min, tjm_max = int(round(day_lo, -1)), int(round(day_hi, -1))
        elif lo:
            budget_label = f"Forfait {int(lo)}–{int(hi or lo)} {currency}"
            budget_eur = int(to_eur(hi or lo, currency))
        submitted = p.get("submitdate") or p.get("time_submitted")
        published = (datetime.fromtimestamp(submitted, tz=timezone.utc).date().isoformat()
                     if isinstance(submitted, (int, float)) else None)
        return Offer(
            id=f"freelancer:{p['id']}",
            source=self.name,
            title=title,
            url=_BASE + p["seo_url"],
            location="Remote",
            remote="Full remote",
            tjm_min=tjm_min,
            tjm_max=tjm_max,
            budget=budget_label,
            budget_eur=budget_eur,
            published=published,
            published_at=to_utc_timestamp(submitted if isinstance(submitted, (int, float)) else None),
            skills=skills[:8],
            snippet=clean_html(desc, 280),
            contract="Projet",
            confirmed_freelance=True,
            text=f"{title} {desc} " + ("" if p.get("type") == "hourly" else "fixed-price"),
        )
