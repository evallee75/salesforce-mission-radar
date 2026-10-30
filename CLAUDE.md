# CLAUDE.md — Salesforce Mission Radar

Successeur public de `~/Documents/FreelanceSearch` (privé, FastAPI + Neon + Render).
Ici : **site statique** sur GitHub Pages, données pré-calculées par GitHub Actions.

## Règles

- Code nommé en anglais ; commentaires, UI, commits et README en français.
- ⚠️ `python3` local = 3.9 : garder la compatibilité (`from __future__ import annotations`,
  `Optional[...]`). Actions tourne en 3.12. Toujours utiliser `.venv/bin/python`.
- Aucune donnée personnelle dans les JSON publiés (repo et site publics) : pas d'email ni
  de téléphone de recruteur.
- Une source cassée ne doit jamais faire échouer le scan : `Source.get()` logue et
  renvoie None, `pipeline._scrape` isole chaque source.
- Tester une source en réel avant de committer :
  `.venv/bin/python -c "from radar.sources import get_source; print([o.title for o in get_source('freework').search('salesforce', {}, set())])"`

## Flux

`python -m radar` → `pipeline.run()` : sources en parallèle → filtre pertinence
(`is_salesforce_offer`) + exclusion CDI (`is_permanent`, hors sources freelance natives)
→ `classify()` (pays, zone, durée, temps partiel, courte, TMA, ESN, score) → fusion avec
`data/state.json` (first_seen horodaté, last_seen = date) → purge `retention_days` →
`data/companies.json` (vivier, jamais purgé) → `site/data/*.json` + flux RSS.

`known_ids` = offres déjà enrichies (`enriched`) : les pages détail (coûteuses) ne sont
lues que pour les nouvelles. Sur LinkedIn, l'enrichissement s'arrête au 2e refus 429 et
reprend au run suivant.

## Analyse IA

Routine Claude Code planifiée (abonnement, pas l'API) ~30 min après chaque scan : lit
`data/ai_queue.json`, écrit `data/ai.json`, pousse → le workflow republie en
`--publish-only`. Consignes : `ROUTINE.md`. `apply_ai` ne s'applique qu'aux copies
publiées (`_publishable`), jamais à `data/state.json`. Textes complets dans
`data/texts.json` (contacts masqués, purgés avec les offres).

## Pièges

- Clé Algolia WTTJ publique mais susceptible d'être tournée (voir docstring de `wttj.py`).
- Codeur.com : le RSS ignore `search`, on filtre nous-mêmes (rendement faible, c'est normal).
- Liste ESN (`companies._ESN_KNOWN`) curatée : à enrichir quand une ESN passe en « client final ».
