"""Analyse de texte : normalisation, pertinence Salesforce, TJM multi-devises,
durée, temps partiel, signaux « mission courte » et détection du pays.

Tout est en best-effort par regex : les annonces sont rédigées en français ou en
anglais, avec des formats très variables. Chaque fonction renvoie None quand
elle ne trouve rien de fiable plutôt que de deviner.
"""
from __future__ import annotations

import html
import re
import unicodedata
from datetime import datetime, timezone
from typing import Optional, Tuple, Union

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def strip_accents_lower(text) -> str:
    t = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode()
    return t.lower()


def clean_html(text: Optional[str], limit: Optional[int] = None) -> str:
    if not text:
        return ""
    t = re.sub(r"<[^>]+>", " ", text)
    t = html.unescape(t)
    t = re.sub(r"\s+", " ", t).strip()
    if limit and len(t) > limit:
        return t[:limit].rsplit(" ", 1)[0] + "…"
    return t


# Le repo et le site sont publics : aucun contact personnel ne doit être republié.
_EMAIL_RX = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_PHONE_RX = re.compile(r"(?<!\w)(?:\+\d{2,3}|00\d{2,3}|0)\s?[1-9](?:[\s.\-]?\d{2}){4}(?!\w)")


def scrub_contacts(text: Optional[str]) -> Optional[str]:
    if not text:
        return text
    return _PHONE_RX.sub("[tél. masqué]", _EMAIL_RX.sub("[email masqué]", text))


# --- Pertinence Salesforce ----------------------------------------------------
# Les places de marché (Freelancer, PeoplePerHour…) font une recherche floue : on
# revérifie que l'annonce parle vraiment de l'écosystème Salesforce.
_SALESFORCE_RX = re.compile(
    r"salesforce|\bsfdc\b|\bapex\b|pardot|account engagement|agentforce|"
    r"sales\s?cloud|service\s?cloud|marketing\s?cloud|experience\s?cloud|"
    r"commerce\s?cloud|data\s?cloud|health\s?cloud|financial services cloud|"
    r"field service lightning|\blwc\b|lightning web component|omnistudio|vlocity|"
    r"mulesoft|\bcpq\b|tableau crm|slack connect",
    re.I,
)


def is_salesforce(text: Optional[str]) -> bool:
    return bool(text and _SALESFORCE_RX.search(text))


def is_salesforce_offer(title: Optional[str], description: Optional[str]) -> bool:
    """Titre Salesforce, ou description qui en parle vraiment (≥ 3 mentions) :
    écarte les annonces qui citent l'outil en passant (source de données, logo…)."""
    if is_salesforce(title):
        return True
    return len(_SALESFORCE_RX.findall(description or "")) >= 3


# --- Freelance ------------------------------------------------------------------
_FREELANCE_TERMS = (
    "freelance", "free-lance", "freelancing", "independant", "mission", "tjm",
    "portage", "contractor", "contract", "sous-traitance", "regie", "prestation",
    "day rate", "daily rate", "outside ir35", "inside ir35", "interim",
)


def looks_freelance(text) -> bool:
    hay = strip_accents_lower(text)
    return any(term in hay for term in _FREELANCE_TERMS)


# --- Postes salariés -------------------------------------------------------------
# Les filtres « contrat » de LinkedIn laissent passer des CDI : on les repère dans
# le texte complet (type de poste explicite ou salaire annuel).
_PERMANENT_RX = re.compile(
    r"job type\s*:?\s*permanent|employment type\s*:?\s*(?:permanent|full[- ]time)|"
    r"permanent\s*[-–,]?\s*full[- ]time|type de contrat\s*:?\s*cdi|\bcdi\b\s*[-–]?\s*temps plein|"
    r"per annum|salaire annuel|brut annuel|annual salary|"
    r"\bsalary\b[^.]{0,30}?[£$€]\s?\d{2},?\d{3}",
    re.I,
)


def is_permanent(text: Optional[str]) -> bool:
    return bool(text and _PERMANENT_RX.search(text))


# --- Temps partiel ----------------------------------------------------------------
_PART_TIME_PATTERNS = [
    (re.compile(r"\b([1-4](?:[.,]5)?)\s*(?:j|jours?)\s*(?:/|par|a la|à la)\s*sem", re.I),
     lambda m: f"{m.group(1)} j/sem"),
    (re.compile(r"\b([1-4](?:[.,]5)?)\s*jours?\s*hebdo", re.I), lambda m: f"{m.group(1)} j/sem"),
    (re.compile(r"\b([1-4](?:[.,]5)?)\s*days?\s*(?:/|per|a)\s*week", re.I),
     lambda m: f"{m.group(1)} j/sem"),
    (re.compile(r"\b([1-9]|1\d)\s*(?:j|jours?|days?)\s*(?:/|par|per|a)\s*(?:mois|month)", re.I),
     lambda m: f"{m.group(1)} j/mois"),
    (re.compile(r"\b([1-3]?\d)\s*(?:h|hrs?|hours?|heures?)\s*(?:/|per|par|a)\s*(?:sem|week)", re.I),
     lambda m: f"{m.group(1)} h/sem"),
    (re.compile(r"temps\s*partiel|part[\s-]?time", re.I), lambda m: "Temps partiel"),
    (re.compile(r"mi[\s-]?temps|half[\s-]?time", re.I), lambda m: "Mi-temps"),
]


# « 2 jours par semaine » désigne très souvent le télétravail ou la présence sur
# site, pas un temps partiel : on ignore le motif si ce vocabulaire l'entoure.
_ONSITE_CONTEXT = re.compile(
    r"t[ée]l[ée]travail|remote|sur site|on[\s-]?site|pr[ée]sentiel|in[\s-]?office|"
    r"\boffice\b|bureau|\btt\b|hybrid|locaux|client site|d[ée]placement|travel",
    re.I,
)


def detect_part_time(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    for pattern, fmt in _PART_TIME_PATTERNS:
        for m in pattern.finditer(text):
            context = text[max(0, m.start() - 45): m.end() + 30]
            if _ONSITE_CONTEXT.search(context):
                continue
            label = fmt(m)
            # « 35 h/sem » ou plus = temps plein, pas un signal.
            if label.endswith("h/sem") and int(label.split()[0]) >= 32:
                continue
            return label
    return None


# --- Durée ------------------------------------------------------------------------
_UNIT_DAYS = {
    "jour": 1, "jours": 1, "j": 1, "day": 1, "days": 1,
    "semaine": 7, "semaines": 7, "sem": 7, "week": 7, "weeks": 7, "wk": 7, "wks": 7,
    "mois": 30, "month": 30, "months": 30, "mth": 30, "mths": 30,
    "an": 365, "ans": 365, "year": 365, "years": 365,
}
_UNIT = r"(jours?|j|days?|semaines?|sem|weeks?|wks?|mois|months?|mths?|ans?|years?)"
# Durée dans un champ dédié (« 3 mois », « 2-3 weeks ») : on prend la borne haute.
_FIELD_DURATION = re.compile(r"(\d{1,3})(?:\s*(?:-|–|à|to)\s*(\d{1,3}))?\s*" + _UNIT + r"\b", re.I)
# Durée dans un texte libre : exige un contexte (« durée : », « mission de »,
# « 3-month contract »…) pour ne pas confondre avec « 5 ans d'expérience ».
_TEXT_DURATION = [
    re.compile(r"(?:dur[ée]e|duration|length|period)\s*(?:de la mission|of the (?:mission|project|contract))?"
               r"\s*[:=\-]?\s*(?:de\s*|of\s*|:\s*)?(?:~|env\.?\s*)?(\d{1,3})(?:\s*(?:-|–|à|to)\s*(\d{1,3}))?\s*"
               + _UNIT + r"\b", re.I),
    re.compile(r"(?:mission|contrat|projet|prestation)\s+(?:courte\s+)?(?:de|d'une durée de)\s+(\d{1,3})"
               r"(?:\s*(?:-|–|à)\s*(\d{1,3}))?\s*" + _UNIT + r"\b", re.I),
    re.compile(r"\b(\d{1,2})(?:\s*(?:-|–|to)\s*(\d{1,2}))?[\s-]*" + _UNIT +
               r"[\s-]+(?:contract|engagement|project|assignment|mission|role)\b", re.I),
    re.compile(r"\bfor\s+(?:about\s+|approx\.?\s+)?(\d{1,2})(?:\s*(?:-|–|to)\s*(\d{1,2}))?\s*" + _UNIT + r"\b", re.I),
]


def _to_days(n1: str, n2: Optional[str], unit: str) -> Optional[int]:
    unit = unit.lower()
    factor = _UNIT_DAYS.get(unit) or _UNIT_DAYS.get(unit.rstrip("s"))
    if not factor:
        return None
    n = max(int(n1), int(n2 or 0))
    days = n * factor
    return days if 0 < days <= 3 * 365 else None


def parse_duration_days(duration_field: Optional[str], text: Optional[str] = None) -> Optional[int]:
    """Durée estimée (jours calendaires) depuis le champ durée, sinon le texte."""
    if duration_field:
        m = _FIELD_DURATION.search(duration_field)
        if m:
            return _to_days(m.group(1), m.group(2), m.group(3))
    if text:
        for rx in _TEXT_DURATION:
            m = rx.search(text)
            if m:
                return _to_days(m.group(1), m.group(2), m.group(3))
    return None


# --- Signaux « mission courte / ponctuelle » --------------------------------------
# Signaux forts : comptent où qu'ils soient dans l'annonce.
_SHORT_RX = re.compile(
    r"quelques jours|quelques semaines|courte dur[ée]e|mission courte|tr[eè]s court|"
    r"ponctuel(?:le)?|renfort|coup de main|"
    r"short[\s-]?term|short mission|short project|few days|couple of (?:days|weeks)|"
    r"one[\s-]?off|quick (?:fix|task|project)|small (?:project|task|job)",
    re.I,
)
# Signaux faibles : banals dans une description (« projets au forfait », « audit
# de l'existant »…), ils ne comptent que dans le TITRE.
_SHORT_TITLE_RX = re.compile(
    r"\baudit\b|\bpoc\b|proof of concept|health ?check|\bforfait\b|ad[\s-]?hoc|"
    r"d[ée]pannage|fixed[\s-]?price|\bexpertise ponctuelle\b",
    re.I,
)
# TMA / run / support : souvent récurrent et à temps partiel, intéressant en complément.
_TMA_RX = re.compile(
    r"\btma\b|tierce maintenance|maintenance applicative|\bmco\b|astreinte|"
    r"support (?:n[12]|niveau|level)|ongoing support|retainer|maintenance contract",
    re.I,
)


def short_signals(title: Optional[str], text: Optional[str]) -> Optional[str]:
    """Premier signal « mission courte » trouvé (pour l'expliquer à l'écran)."""
    m = _SHORT_RX.search(f"{title or ''} {text or ''}") or _SHORT_TITLE_RX.search(title or "")
    return m.group(0).strip().lower() if m else None


def is_tma(text: Optional[str]) -> bool:
    return bool(text and _TMA_RX.search(text))


# --- TJM (multi-devises, converti en € / jour) ------------------------------------
# Taux approximatifs, suffisants pour comparer des TJM (pas de la compta).
_TO_EUR = {"eur": 1.0, "gbp": 1.17, "usd": 0.92, "chf": 1.05, "cad": 0.67,
           "aud": 0.60, "inr": 0.011, "pln": 0.23, "sek": 0.087, "dkk": 0.134}
_CUR_SYMBOLS = {"€": "eur", "£": "gbp", "$": "usd", "eur": "eur", "euro": "eur",
                "euros": "eur", "gbp": "gbp", "usd": "usd", "chf": "chf", "cad": "cad",
                "k€": "eur"}
_CUR = r"(€|£|\$|eur(?:os?)?|gbp|usd|chf|cad)"
_NUM = r"(\d{1,3}(?:[ .,]\d{3})?|\d{2,4})"
_PER = r"(?:\s*(?:ht|hors taxes?|excl\.? vat|\+ ?vat))?\s*(?:/|par|per|a|p\.?|an?)?\s*"
_DAY = r"(jour|day|j\b|d\b|jr|diem|daily)"
_HOUR = r"(heure|hour|hr|h\b)"
_RATE_PATTERNS = [
    # 450-550 €/jour, 500 £ per day
    (re.compile(_NUM + r"\s*(?:-|–|à|to)\s*" + _NUM + r"\s*" + _CUR + _PER + r"(?:" + _DAY + r"|" + _HOUR + r")", re.I), "num_num_cur"),
    # £450-£550 per day, $80-95/hr
    (re.compile(_CUR + r"\s?" + _NUM + r"\s*(?:-|–|à|to)\s*" + _CUR + r"?\s?" + _NUM + _PER + r"(?:" + _DAY + r"|" + _HOUR + r")", re.I), "cur_num_num"),
    # 600 € HT / jour, 85 $/h
    (re.compile(_NUM + r"\s*" + _CUR + _PER + r"(?:" + _DAY + r"|" + _HOUR + r")", re.I), "num_cur"),
    # £600 per day, €75/h
    (re.compile(_CUR + r"\s?" + _NUM + _PER + r"(?:" + _DAY + r"|" + _HOUR + r")", re.I), "cur_num"),
    # TJM 500 / day rate: 550 (devise implicite = €, ou celle qui suit)
    (re.compile(r"(?:\btjm\b|day rate|daily rate|taux journalier)[^\d]{0,20}" + _NUM +
                r"(?:\s*(?:-|–|à|to|et)\s*" + _NUM + r")?\s*" + _CUR + r"?", re.I), "label"),
]


def _num(s: str) -> int:
    return int(re.sub(r"[ .,]", "", s))


def find_rate(text: Optional[str]) -> Tuple[Optional[int], Optional[int]]:
    """Cherche un TJM dans un texte libre. Renvoie (min, max) en €/jour, ou (None, None).

    Les taux horaires sont convertis sur une base de 8 h/jour.
    """
    if not text:
        return None, None
    for rx, kind in _RATE_PATTERNS:
        for m in rx.finditer(text):
            g = m.groups()
            if kind == "num_num_cur":
                nums, cur, hourly = [g[0], g[1]], g[2], bool(g[4])
            elif kind == "cur_num_num":
                nums, cur, hourly = [g[1], g[3]], g[0], bool(g[5])
            elif kind == "num_cur":
                nums, cur, hourly = [g[0]], g[1], bool(g[3])
            elif kind == "cur_num":
                nums, cur, hourly = [g[1]], g[0], bool(g[3])
            else:
                nums, cur, hourly = [g[0], g[1]], g[2] or "eur", False
            rate = _TO_EUR.get(_CUR_SYMBOLS.get(cur.lower(), "eur"), 1.0)
            values = [_num(n) * rate * (8 if hourly else 1) for n in nums if n]
            values = [int(round(v, -1)) for v in values if 150 <= v <= 3000]
            if values:
                return min(values), max(values)
    return None, None


def to_eur(amount: Optional[float], currency: Optional[str]) -> Optional[float]:
    if amount is None:
        return None
    return amount * _TO_EUR.get((currency or "eur").lower(), 1.0)


# --- Pays -------------------------------------------------------------------------
# Libellé français -> termes (sans accents, minuscules) recherchés dans la localisation.
_COUNTRIES = {
    "France": ["france", "ile-de-france", "ile de france", "paris", "lyon", "marseille",
               "toulouse", "bordeaux", "lille", "nantes", "rennes", "nice", "strasbourg",
               "montpellier", "grenoble", "sophia", "hauts-de-seine", "seine", "yvelines",
               "essonne", "val-de-marne", "val-d'oise", "auvergne", "occitanie", "bretagne",
               "normandie", "nouvelle-aquitaine", "grand est", "hauts-de-france",
               "pays de la loire", "provence", "bourgogne", "centre-val", "la defense",
               "courbevoie", "puteaux", "boulogne", "nanterre", "issy", "levallois",
               "saint-denis", "neuilly", "rueil", "massy", "velizy", "guyancourt"],
    "Belgique": ["belgium", "belgique", "belgie", "bruxelles", "brussels", "brussel",
                 "antwerp", "anvers", "gent", "ghent", "gand", "liege", "namur", "leuven",
                 "mechelen", "wallonie", "flanders", "vlaanderen"],
    "Suisse": ["switzerland", "suisse", "schweiz", "svizzera", "geneve", "geneva", "genf",
               "zurich", "lausanne", "basel", "bale", "bern", "berne", "lugano", "zug"],
    "Luxembourg": ["luxembourg", "luxemburg"],
    "Royaume-Uni": ["united kingdom", "royaume-uni", "england", "london", "londres",
                    "manchester", "scotland", "edinburgh", "glasgow", "birmingham",
                    "leeds", "bristol", "essex", "reading", "cambridge", "oxford",
                    "wales", "cardiff", "belfast", "uk"],
    "Irlande": ["ireland", "irlande", "dublin", "cork"],
    "Allemagne": ["germany", "deutschland", "allemagne", "berlin", "munich", "munchen",
                  "hamburg", "frankfurt", "koln", "cologne", "dusseldorf", "stuttgart"],
    "Autriche": ["austria", "autriche", "osterreich", "vienna", "wien", "vienne"],
    "Pays-Bas": ["netherlands", "pays-bas", "nederland", "holland", "amsterdam",
                 "rotterdam", "utrecht", "eindhoven", "den haag", "the hague"],
    "Espagne": ["spain", "espagne", "espana", "madrid", "barcelona", "barcelone",
                "valencia", "malaga", "sevilla"],
    "Portugal": ["portugal", "lisbon", "lisbonne", "lisboa", "porto"],
    "Italie": ["italy", "italie", "italia", "milan", "milano", "rome", "roma", "turin", "torino"],
    "Pologne": ["poland", "pologne", "polska", "warsaw", "varsovie", "krakow", "wroclaw"],
    "Roumanie": ["romania", "roumanie", "bucharest", "bucarest", "cluj"],
    "Croatie": ["croatia", "croatie", "zagreb"],
    "Rép. tchèque": ["czech", "tcheque", "prague", "praha", "brno"],
    "Danemark": ["denmark", "danemark", "copenhagen", "copenhague"],
    "Suède": ["sweden", "suede", "stockholm", "gothenburg"],
    "Norvège": ["norway", "norvege", "oslo"],
    "Finlande": ["finland", "finlande", "helsinki"],
    "Grèce": ["greece", "grece", "athens", "athenes"],
    "Maroc": ["morocco", "maroc", "casablanca", "rabat", "marrakech", "tanger"],
    "Tunisie": ["tunisia", "tunisie", "tunis"],
    "Émirats arabes unis": ["dubai", "dubaï", "abu dhabi", "united arab emirates", "uae", "emirats"],
    "Arabie saoudite": ["saudi", "riyadh", "jeddah"],
    "Qatar": ["qatar", "doha"],
    "Canada": ["canada", "montreal", "quebec", "toronto", "vancouver", "ottawa", "calgary"],
    "États-Unis": ["united states", "etats-unis", "usa", "new york", "california",
                   "san francisco", "texas", "chicago", "boston", "seattle", "florida",
                   "atlanta", "remote-usa", "remote usa", "u.s."],
    "Inde": ["india", "inde", "bangalore", "bengaluru", "hyderabad", "pune", "chennai",
             "mumbai", "delhi", "noida", "gurgaon"],
    "Singapour": ["singapore", "singapour"],
    "Australie": ["australia", "australie", "sydney", "melbourne", "brisbane"],
}
_COUNTRY_RX = [
    (name, re.compile(r"(?<![a-z])(?:" + "|".join(re.escape(t) for t in terms) + r")(?![a-z])"))
    for name, terms in _COUNTRIES.items()
]
_ISO2 = {"FR": "France", "BE": "Belgique", "CH": "Suisse", "LU": "Luxembourg",
         "GB": "Royaume-Uni", "UK": "Royaume-Uni", "IE": "Irlande", "DE": "Allemagne",
         "AT": "Autriche", "NL": "Pays-Bas", "ES": "Espagne", "PT": "Portugal",
         "IT": "Italie", "PL": "Pologne", "RO": "Roumanie", "HR": "Croatie",
         "CZ": "Rép. tchèque", "DK": "Danemark", "SE": "Suède", "NO": "Norvège",
         "FI": "Finlande", "GR": "Grèce", "MA": "Maroc", "TN": "Tunisie",
         "AE": "Émirats arabes unis", "SA": "Arabie saoudite", "QA": "Qatar",
         "CA": "Canada", "US": "États-Unis", "IN": "Inde", "SG": "Singapour",
         "AU": "Australie"}

EUROPE = {"France", "Belgique", "Suisse", "Luxembourg", "Royaume-Uni", "Irlande",
          "Allemagne", "Autriche", "Pays-Bas", "Espagne", "Portugal", "Italie",
          "Pologne", "Roumanie", "Croatie", "Rép. tchèque", "Danemark", "Suède",
          "Norvège", "Finlande", "Grèce"}
# Pays où l'on travaille en français : utile pour choisir la langue du pitch.
FRENCH_SPEAKING = {"France", "Belgique", "Suisse", "Luxembourg", "Maroc", "Tunisie", "Canada"}


def country_from_iso(code: Optional[str]) -> Optional[str]:
    return _ISO2.get((code or "").upper())


def detect_country(location: Optional[str]) -> Optional[str]:
    """Pays (libellé FR) déduit d'une localisation en texte libre. None si inconnu."""
    if not location:
        return None
    hay = strip_accents_lower(location)
    for name, rx in _COUNTRY_RX:
        if rx.search(hay):
            return name
    return None


def zone_of(country: Optional[str], remote: Optional[str]) -> str:
    """Zone d'affichage : France | Europe | Monde | Remote (pays inconnu, 100 % remote)."""
    if country == "France":
        return "France"
    if country in EUROPE:
        return "Europe"
    if country:
        return "Monde"
    return "Remote" if remote == "Full remote" else "France"


def to_utc_timestamp(value: Union[str, int, float, datetime, None]) -> Optional[str]:
    """Horodatage de publication normalisé en UTC (« 2026-11-01T09:30:00Z »).

    Accepte un ISO 8601 avec heure (offset, « Z », millisecondes), un timestamp Unix
    ou un datetime. Renvoie None si la valeur n'a pas d'heure : une simple date ne
    permet pas de trier à l'intérieur d'une journée. Une heure sans fuseau est lue en UTC.
    """
    if value is None or value == "":
        return None
    try:
        if isinstance(value, datetime):
            dt = value
        elif isinstance(value, (int, float)):
            dt = datetime.fromtimestamp(value / 1000 if value > 1e11 else value, tz=timezone.utc)
        else:
            raw = str(value).strip()
            if not re.match(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}", raw):
                return None
            raw = raw.replace(" ", "T", 1).replace("Z", "+00:00")
            raw = re.sub(r"(\.\d+)", "", raw)                       # millisecondes
            raw = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", raw)     # +0100 → +01:00
            dt = datetime.fromisoformat(raw)
    except (ValueError, OverflowError, OSError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
