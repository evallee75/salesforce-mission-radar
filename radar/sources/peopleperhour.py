"""PeoplePerHour — place de marché de petites missions (UK/Europe), en HTML public.

Typiquement des missions courtes au forfait : exactement ce que l'on cherche
pour du « quelques jours par-ci par-là ». Budget affiché en devise locale.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Dict, List, Optional

from bs4 import BeautifulSoup

from ..models import Offer
from ..text import clean_html, is_salesforce_offer
from .base import Source

_SEARCH = "https://www.peopleperhour.com/freelance-{kw}-jobs"
_AGO = re.compile(r"(\d+)\s+(minute|hour|day|week|month)s?\s+ago", re.I)
_BUDGET = re.compile(r"^[€£$][\d.,]+K?$")


class PeoplePerHourSource(Source):
    name = "peopleperhour"
    label = "PeoplePerHour"

    def search(self, keyword: str, cfg: Dict, known_ids) -> List[Offer]:
        resp = self.get(_SEARCH.format(kw=re.sub(r"\W+", "-", keyword.lower())))
        if resp is None:
            return []
        soup = BeautifulSoup(resp.text, "lxml")
        seen, out = set(), []
        for h6 in soup.find_all("h6"):
            a = h6.find("a", href=re.compile(r"/freelance-jobs/.+-\d+$"))
            li = h6.find_parent("li")
            if not a or not li or a["href"] in seen:
                continue
            seen.add(a["href"])
            offer = self._parse(a, li)
            if offer:
                out.append(offer)
        return out

    def _parse(self, a, li) -> Optional[Offer]:
        title = a.get_text(strip=True)
        desc = " ".join(p.get_text(" ", strip=True) for p in li.find_all("p"))
        if not is_salesforce_offer(title, desc):
            return None
        spans = [s.get_text(strip=True) for s in li.find_all("span")]
        budget = next((s for s in spans if _BUDGET.match(s)), None)
        ago = next((m for m in (_AGO.search(s) for s in spans) if m), None)
        remote = any(s == "Remote" for s in spans)
        return Offer(
            id=f"peopleperhour:{a['href'].rsplit('-', 1)[-1]}",
            source=self.name,
            title=title,
            url=a["href"],
            location="Remote" if remote else None,
            remote="Full remote" if remote else None,
            budget=f"Forfait {budget}" if budget else None,
            published=_ago_to_date(ago),
            snippet=clean_html(desc, 280),
            contract="Projet",
            confirmed_freelance=True,
            text=f"{title} {desc} forfait",
        )


def _ago_to_date(m) -> Optional[str]:
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2).lower()
    days = {"minute": 0, "hour": 0, "day": n, "week": 7 * n, "month": 30 * n}[unit]
    return (date.today() - timedelta(days=days)).isoformat()
