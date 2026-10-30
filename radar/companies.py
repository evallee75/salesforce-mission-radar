"""Vivier entreprises — normalisation des noms + détection ESN / cabinets.

Sert à constituer une base d'entreprises qui publient des missions (pour la
prospection), en distinguant les **ESN / cabinets / plateformes intermédiaires**
des **clients finaux** (cible privilégiée d'une prospection freelance).
"""
from __future__ import annotations

import re
from typing import Optional

from .text import strip_accents_lower

# Noms génériques / anonymisés : pas de vraie entreprise => exclus du vivier.
_PLACEHOLDERS = {
    "", "confidentiel", "client final", "esn", "collectivite", "n/a", "na",
    "anonyme", "non communique", "non renseigne", "entreprise",
}

# Formes juridiques / suffixes retirés pour normaliser la clé de regroupement.
_LEGAL = {
    "sas", "sasu", "sa", "sarl", "eurl", "sl", "gmbh", "ltd", "llc", "inc",
    "bv", "ag", "spa", "srl", "plc", "co", "company",
}

# ESN / cabinets de conseil / intégrateurs / recruteurs / plateformes connus
# (clé normalisée, sans accents, en minuscules). Liste indicative, extensible.
_ESN_KNOWN = {
    # Intégrateurs & ESN
    "accenture", "capgemini", "sopra steria", "sopra", "steria", "devoteam",
    "atos", "cgi", "wavestone", "keyrus", "hardis", "hardis group", "valtech",
    "cognizant", "infosys", "tcs", "tata consultancy services", "wipro", "ibm",
    "deloitte", "pwc", "kpmg", "ey", "mc2i", "micropole", "umanis", "sii",
    "alten", "akka", "akka technologies", "expleo", "inetum", "gfi", "sqli",
    "smile", "emakina", "synolia", "texei", "easyteam", "saletis", "vivansa",
    "astrea", "brillio", "neoxia", "cellenza", "talan", "niji", "magellan",
    "magellan consulting", "onepoint", "octo", "octo technology", "sfeir",
    "zenika", "ippon", "ippon technologies", "xebia", "klanik", "davidson",
    "nexio", "vneuron", "businessdecision", "business decision", "soft computing",
    "ekino", "publicis sapient", "publicis", "sage", "ausy", "amaris",
    "mantu", "vmf", "open", "groupe open", "scalian", "vinci", "modis", "akkodis",
    # Recruteurs / staffing / portage / plateformes
    "hays", "michael page", "page personnel", "robert walters", "robert half",
    "computer futures", "urban linker", "mobiskill", "free-work", "freework",
    "fed it", "fed", "approach people", "harvey nash", "nigel frank",
    "mason frank", "revolent", "talent.io", "talent io", "comet", "malt",
    "lehibou", "le hibou", "freelance.com", "crème de la crème", "creme de la creme",
    "externatic", "seyos", "skillval", "huxley", "darwin recruitment",
    # Staffing / intérim spécialisé
    "adecco", "randstad", "manpower", "expectra", "sthree", "hanson regan",
    "mindquest", "cat amania", "catamania", "gentis", "lincoln", "lhh",
    "freelancerepublik", "odhcom", "sthree",
    # Intégrateurs / staffing internationaux (offres hors France)
    "ntt data", "nttdata", "hcl", "hcltech", "tech mahindra", "ltimindtree", "mindtree",
    "persistent", "persistent systems", "globant", "epam", "experis", "teksystems",
    "tek systems", "jefferson frank", "salt", "eames consulting", "nicoll curtin",
    "montash", "la fosse", "harnham", "spectrum it", "trust in soda", "akkodis",
    "infoplus technologies", "jobgate", "yochana", "coforge", "virtusa", "slalom",
    "pwc", "ey", "kpmg", "bluewolf", "silverline", "appirio", "coastal cloud",
    # Plateformes / réseaux de freelances FR
    "mon consultant independant", "valtao", "crème de la crème", "littlebig connection",
    "freelance informatique", "kicklox", "silkhom", "storm group",
    "craftman data", "nicholson", "ebmc", "squadra", "xpertiz",
}

# Indices (heuristique conservatrice) qu'un nom inconnu est une ESN/cabinet.
_ESN_HINTS = (
    "esn", "ssii", "consulting", "consultants", "conseil", "recrutement",
    "staffing", "interim", "portage", "freelance", "consfirmcorp",
    "recruitment", "recruiting", "talent solutions", "resourcing", "consult",
    "solutions", "partners", "services", "technologies", "digital", "informatique",
)


def normalize_company(name: Optional[str]) -> str:
    """Clé de regroupement d'une entreprise (sans accents, sans forme juridique)."""
    if not name:
        return ""
    base = strip_accents_lower(name)
    base = base.replace(".", "")                   # S.A.S. -> SAS (forme juridique pointée)
    base = re.sub(r"\(.*?\)", " ", base)          # retire (H/F), (Paris)…
    base = re.sub(r"[^a-z0-9]+", " ", base).strip()
    tokens = [t for t in base.split() if t not in _LEGAL]
    return " ".join(tokens)


def is_placeholder(name: Optional[str]) -> bool:
    return normalize_company(name) in _PLACEHOLDERS


def is_esn(name: Optional[str]) -> bool:
    """True si l'entreprise est (probablement) une ESN/cabinet/intermédiaire."""
    key = normalize_company(name)
    if not key:
        return False
    if key in _ESN_KNOWN:
        return True
    words = set(key.split())
    for known in _ESN_KNOWN:
        if " " in known:
            if known in key:               # raison sociale multi-mots
                return True
        elif len(known) >= 4 and known in words:   # nom mono-mot (+ pays/suffixe)
            return True
    return any(h in key for h in _ESN_HINTS)
