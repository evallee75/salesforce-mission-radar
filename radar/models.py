"""Modèle d'offre normalisé, commun à toutes les sources."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Offer:
    id: str                                  # "<source>:<id brut>"
    source: str
    title: str
    url: str
    company: Optional[str] = None
    location: Optional[str] = None           # libellé brut (ville, région…)
    country: Optional[str] = None            # pays normalisé en français ("France", "Suisse"…)
    remote: Optional[str] = None             # "Full remote" | "Hybride" | "Sur site"
    tjm_min: Optional[int] = None            # taux journalier converti en €
    tjm_max: Optional[int] = None
    budget: Optional[str] = None             # forfait (places de marché) : "500–750 USD"
    budget_eur: Optional[int] = None         # borne haute du forfait convertie en €
    duration: Optional[str] = None           # libellé brut ("3 mois", "2 weeks")
    duration_days: Optional[int] = None      # durée estimée en jours calendaires
    part_time: Optional[str] = None          # "2 j/sem", "Temps partiel"…
    published: Optional[str] = None          # date ISO YYYY-MM-DD
    published_at: Optional[str] = None       # horodatage UTC si la source donne l'heure
    skills: List[str] = field(default_factory=list)
    snippet: Optional[str] = None            # extrait court (affiché)
    contract: Optional[str] = None           # "Freelance" | "Contrat" | "Projet"
    confirmed_freelance: bool = False
    # Texte complet servant à la classification. Jamais écrit dans les JSON publiés.
    text: Optional[str] = None
