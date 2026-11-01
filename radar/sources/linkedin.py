"""LinkedIn — endpoint public « guest » de recherche d'emploi (HTML, sans login).

Interrogé sur plusieurs pays (config `linkedin_locations`) avec les types
de contrat C (contract), T (temporary) et P (part-time) : c'est là que se trouvent
les missions freelance et les besoins ponctuels à l'étranger.
Pas de TJM dans la liste : la page détail est lue pour les NOUVELLES offres
uniquement, une par une avec une pause, et on s'arrête au 2e refus 429 (LinkedIn
bloque très vite les rafales). Les offres non enrichies le seront au run suivant.
"""
from __future__ import annotations

import re
import time
from typing import Dict, List, Optional

from bs4 import BeautifulSoup

from ..models import Offer
from ..text import clean_html, detect_country, is_salesforce, looks_freelance, to_utc_timestamp
from .base import Source

_SEARCH = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
_DETAIL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/"
_DEFAULT_LOCATIONS = ["France"]
_PAGES_PER_LOCATION = 2
_MAX_DETAILS = 80
_DETAIL_PAUSE = 1.5
# Postes salariés qui passent le filtre « contrat » de LinkedIn.
_PERMANENT_RX = re.compile(r"\bcdi\b|permanent|full[- ]time employee|\bfte\b", re.I)


class LinkedInSource(Source):
    name = "linkedin"
    label = "LinkedIn"

    def search(self, keyword: str, cfg: Dict, known_ids) -> List[Offer]:
        seen, out = set(), []
        for location in cfg.get("linkedin_locations") or _DEFAULT_LOCATIONS:
            for page in range(_PAGES_PER_LOCATION):
                resp = self.get(_SEARCH, params={"keywords": keyword, "location": location,
                                                 "f_JT": "C,T,P", "f_TPR": "r1209600",
                                                 "start": str(page * 25)}, timeout=20)
                cards = BeautifulSoup(resp.text, "lxml").select("li") if resp else []
                for card in cards:
                    offer = self._parse(card, location)
                    if offer and offer.id not in seen:
                        seen.add(offer.id)
                        out.append(offer)
                time.sleep(1.0)   # politesse anti-429
                if len(cards) < 10:
                    break

        refusals = 0
        for offer in [o for o in out if o.id not in known_ids][:_MAX_DETAILS]:
            if not self._enrich(offer):
                refusals += 1
                if refusals >= 2:
                    self.log.warning("LinkedIn limite les pages détail : arrêt de l'enrichissement.")
                    break
                time.sleep(15)
            time.sleep(_DETAIL_PAUSE)
        return out

    def _parse(self, card, searched_location: str) -> Optional[Offer]:
        title_el = card.select_one(".base-search-card__title")
        link_el = card.select_one("a.base-card__full-link") or card.find("a", href=True)
        if not title_el or not link_el:
            return None
        title = title_el.get_text(strip=True)
        if not is_salesforce(title) or _PERMANENT_RX.search(title):
            return None
        href = link_el["href"].split("?")[0]
        m = re.search(r"-(\d+)$", href)
        company_el = card.select_one(".base-search-card__subtitle")
        loc_el = card.select_one(".job-search-card__location")
        time_el = card.select_one("time")
        location = loc_el.get_text(strip=True) if loc_el else None
        return Offer(
            id=f"linkedin:{m.group(1) if m else href}",
            source=self.name,
            title=title,
            url=href,
            company=company_el.get_text(strip=True) if company_el else None,
            location=location,
            country=detect_country(location) or detect_country(searched_location),
            published=(time_el.get("datetime") or "")[:10] or None if time_el else None,
            published_at=to_utc_timestamp(time_el.get("datetime")) if time_el else None,
            contract="Contrat",
            confirmed_freelance=looks_freelance(title),
            text=title,
        )

    def _enrich(self, offer: Offer) -> bool:
        """Lit la page détail. False si LinkedIn a refusé (429…), True sinon."""
        job_id = offer.id.split(":", 1)[1]
        if not job_id.isdigit():
            return True
        resp = self.get(_DETAIL + job_id, timeout=15)
        if resp is None:
            return False
        soup = BeautifulSoup(resp.text, "lxml")
        desc_el = soup.select_one(".show-more-less-html__markup, .description__text")
        if not desc_el:
            return True
        text = desc_el.get_text(" ", strip=True)
        criteria = " ".join(li.get_text(" ", strip=True)
                            for li in soup.select(".description__job-criteria-item"))
        offer.text = f"{offer.title} {text} {criteria}"
        offer.snippet = clean_html(text, 280)
        offer.confirmed_freelance = offer.confirmed_freelance or looks_freelance(offer.text)
        if re.search(r"\bremote\b|t[ée]l[ée]travail", f"{offer.location} {criteria}", re.I):
            offer.remote = "Full remote"
        return True
