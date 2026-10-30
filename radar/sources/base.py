"""Interface commune aux sources + session HTTP partagée."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Set

import requests

from ..models import Offer
from ..text import USER_AGENT


class Source(ABC):
    name: str = "base"
    # Libellé affiché dans l'interface.
    label: str = "base"

    def __init__(self) -> None:
        self.log = logging.getLogger(f"radar.{self.name}")
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT,
                                     "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8"})

    @abstractmethod
    def search(self, keyword: str, cfg: Dict, known_ids: Set[str]) -> List[Offer]:
        """Offres pour `keyword`. `known_ids` = ids déjà en base : les sources qui
        enrichissent via une page détail (coûteux) SAUTENT ces ids."""
        raise NotImplementedError

    def get(self, url: str, **kwargs) -> Optional[requests.Response]:
        """GET tolérant : logue et renvoie None plutôt que de planter le scan global."""
        kwargs.setdefault("timeout", 25)
        try:
            resp = self.session.get(url, **kwargs)
        except requests.RequestException as exc:
            self.log.warning("Erreur réseau %s : %s", url, exc)
            return None
        if resp.status_code != 200:
            self.log.warning("%s a renvoyé %s", url, resp.status_code)
            return None
        return resp
