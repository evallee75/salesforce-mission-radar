"""Registre des sources. Ajouter une source = un module + une entrée ici + config.yaml."""
from __future__ import annotations

from typing import Dict, Type

from .base import Source
from .codeur import CodeurSource
from .freelancer import FreelancerSource
from .freelancermap import FreelancermapSource
from .freework import FreeWorkSource
from .hellowork import HelloworkSource
from .jobgether import JobgetherSource
from .linkedin import LinkedInSource
from .peopleperhour import PeoplePerHourSource
from .remoteok import RemoteOkSource
from .wttj import WttjSource

REGISTRY: Dict[str, Type[Source]] = {cls.name: cls for cls in (
    FreeWorkSource, WttjSource, HelloworkSource, LinkedInSource, FreelancermapSource,
    PeoplePerHourSource, FreelancerSource, CodeurSource, RemoteOkSource, JobgetherSource,
)}


def get_source(name: str) -> Source:
    return REGISTRY[name]()
