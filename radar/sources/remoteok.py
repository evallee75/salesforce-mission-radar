"""Remote OK — API JSON publique, 100 % remote (souvent international).

On ne garde que les postes dont le TITRE parle de Salesforce (le tag capte sinon
tout job qui cite l'outil). Les CGU demandent un lien vers l'offre : c'est le cas.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from ..models import Offer
from ..text import clean_html, detect_country, is_salesforce, looks_freelance, to_utc_timestamp
from .base import Source

_API = "https://remoteok.com/api"


class RemoteOkSource(Source):
    name = "remoteok"
    label = "Remote OK"

    def search(self, keyword: str, cfg: Dict, known_ids) -> List[Offer]:
        resp = self.get(_API, params={"tags": keyword}, timeout=20)
        if resp is None:
            return []
        resp.encoding = "utf-8"
        data = resp.json()
        return [o for o in (self._parse(m) for m in data if isinstance(m, dict) and "position" in m) if o]

    def _parse(self, m: dict) -> Optional[Offer]:
        title = m.get("position") or ""
        if not is_salesforce(title):
            return None
        desc = clean_html(m.get("description"))
        return Offer(
            id=f"remoteok:{m.get('id') or m.get('slug')}",
            source=self.name,
            title=title,
            url=m.get("url") or m.get("apply_url") or "https://remoteok.com",
            company=m.get("company"),
            location=m.get("location") or "Remote",
            country=detect_country(m.get("location")),
            remote="Full remote",
            published=(m.get("date") or "")[:10] or None,
            published_at=to_utc_timestamp(m.get("date")),
            skills=[t for t in (m.get("tags") or []) if isinstance(t, str)][:8],
            snippet=clean_html(desc, 280),
            contract="Freelance" if looks_freelance(f"{title} {desc}") else "Remote",
            confirmed_freelance=looks_freelance(f"{title} {desc}"),
            text=f"{title} {desc}",
        )
