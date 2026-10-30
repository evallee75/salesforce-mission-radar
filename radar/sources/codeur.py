"""Codeur.com — place de marché FR de petits projets (flux RSS public).

Le flux renvoie les derniers projets toutes catégories (le paramètre `search`
est ignoré) : on filtre sur Salesforce nous-mêmes. Rendement faible mais ce
sont presque toujours des missions courtes au forfait, souvent en direct client.
"""
from __future__ import annotations

import re
from email.utils import parsedate_to_datetime
from typing import Dict, List

from bs4 import BeautifulSoup

from ..models import Offer
from ..text import clean_html, is_salesforce_offer
from .base import Source

_RSS = "https://www.codeur.com/projects.rss"
_BUDGET = re.compile(r"Budget\s*:\s*([^-<]+?)\s*(?:-|$)", re.I)


class CodeurSource(Source):
    name = "codeur"
    label = "Codeur.com"

    def search(self, keyword: str, cfg: Dict, known_ids) -> List[Offer]:
        resp = self.get(_RSS)
        if resp is None:
            return []
        out = []
        for item in BeautifulSoup(resp.content, "xml").find_all("item"):
            title = item.title.get_text(strip=True) if item.title else ""
            desc = clean_html(item.description.get_text() if item.description else "")
            if not is_salesforce_offer(title, desc):
                continue
            budget = _BUDGET.search(desc)
            try:
                published = parsedate_to_datetime(item.pubDate.get_text()).date().isoformat()
            except (AttributeError, TypeError, ValueError):
                published = None
            out.append(Offer(
                id=f"codeur:{item.guid.get_text(strip=True) if item.guid else item.link.get_text()}",
                source=self.name,
                title=title,
                url=item.link.get_text(strip=True),
                location="Remote",
                country="France",
                remote="Full remote",
                budget=f"Forfait {budget.group(1).strip()}" if budget else None,
                published=published,
                snippet=clean_html(desc, 280),
                contract="Projet",
                confirmed_freelance=True,
                text=f"{title} {desc} forfait",
            ))
        return out
