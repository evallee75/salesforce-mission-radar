# 🎯 Salesforce Mission Radar

**Les missions freelance Salesforce du jour, au même endroit, triées par intérêt business.**
France, Europe, international, et surtout les **missions courtes et à temps partiel**
(quelques jours par-ci par-là, TMA, renfort ponctuel), qui sont noyées dans les job
boards classiques.

👉 **Site : https://evallee75.github.io/salesforce-mission-radar/**

## Ce que fait le radar

- **Scanne 10 sources** deux fois par jour (GitHub Actions) et dédoublonne les annonces
  publiées sur plusieurs sites.
- **Détecte les formats qui rapportent** : missions courtes (durée ≤ 45 j, « quelques
  jours », « ponctuel », « short-term »…), temps partiel (« 2 j/sem », « part-time »…),
  TMA / run. Le télétravail (« 2 jours de TT par semaine ») n'est pas confondu avec du
  temps partiel.
- **Attribue un score d'opportunité (0-100)**, expliqué au survol : fraîcheur, format
  court ou partiel, TJM, client final plutôt qu'ESN, remote, Salesforce dans l'intitulé.
- **Convertit les TJM** de toutes les devises (€, £, $, CHF…) et les taux horaires en €/jour.
- **Pipeline de prospection** : suivi À contacter → Candidaté → Entretien → Gagné/Perdu,
  avec notes, export et import. Les données restent dans ton navigateur.
- **Pitch en un clic** : un message d'approche personnalisé (FR ou EN selon le pays) est
  copié dans le presse-papiers.
- **Vivier entreprises** : qui publie, combien, à quel TJM médian, client final ou ESN,
  avec des liens directs pour trouver les décideurs sur LinkedIn. Export CSV. L'historique
  n'est jamais purgé.
- **Alertes** : flux RSS ([toutes](https://evallee75.github.io/salesforce-mission-radar/feed.xml),
  [courtes et partielles](https://evallee75.github.io/salesforce-mission-radar/feed-courtes.xml))
  et email optionnel.

## Pourquoi c'est rapide

Il n'y a ni serveur ni base de données. Le scan tourne dans GitHub Actions et écrit des
fichiers JSON pré-calculés. GitHub Pages les sert depuis un CDN, et le navigateur filtre
tout en local. À l'ouverture, il n'y a ni démarrage à froid, ni scrape, ni requête lente.

```
GitHub Actions (2×/jour)                         GitHub Pages (CDN)
┌──────────────────────────────┐                 ┌──────────────────────────┐
│ 10 sources en parallèle      │                 │ index.html + app.js      │
│ → pertinence Salesforce      │   data/*.json   │ data/offers.json  ← 1 fetch
│ → classification + score     │ ──────────────► │ data/companies.json      │
│ → fusion avec l'historique   │   commit + push │ feed.xml, feed-courtes   │
│ → dédoublonnage              │                 └──────────────────────────┘
└──────────────────────────────┘
```

## Sources

| Source | Type | Apport |
|---|---|---|
| Free-Work | API JSON | Source principale FR : freelance natif, TJM, durée |
| Welcome to the Jungle | API Algolia | Freelance FR, TJM |
| Hellowork | HTML | Freelance FR, TJM sur la page détail |
| LinkedIn | HTML (guest) | 9 pays, contrats, missions temporaires, temps partiel |
| freelancermap | JSON embarqué | Projets IT Europe (DE/CH/UK/Benelux) |
| PeoplePerHour | HTML | Petites missions au forfait (UK/Europe) |
| Freelancer.com | API publique | Petites missions, monde entier |
| Codeur.com | RSS | Petites missions FR, souvent en direct client |
| Jobgether | API | Remote freelance, Europe et monde |
| Remote OK | API | Remote international |

Non scrapables sans navigateur headless ni login : Malt, Indeed, LeHibou, Comet,
Upwork, Crème de la Crème.

## Lancer en local

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m radar                      # scan complet (~3 min)
cd site && python3 -m http.server 8000         # http://localhost:8000
```

Les paramètres (mots-clés, pays LinkedIn, sources, rétention) sont dans `config.yaml`.

## Email quotidien (optionnel)

Définir dans **Settings → Secrets and variables → Actions** : `SMTP_USER`,
`SMTP_PASSWORD` (mot de passe d'application Gmail) et `ALERT_TO`. Le mail ne
reprend que les nouvelles missions avec un score ≥ 40.

## Structure

```
radar/
  sources/        un module par site (interface Source.search)
  text.py         pertinence Salesforce, TJM multi-devises, durée, temps partiel, pays, CDI
  classify.py     signaux (courte, partiel, TMA, client final) + score d'opportunité
  companies.py    normalisation des noms + détection ESN / cabinets
  pipeline.py     orchestration, fusion avec l'historique, dédoublonnage, écriture
  feed.py         flux RSS
  digest.py       email optionnel
data/             état persistant (offres vues, vivier) — versionné par le bot
site/             front statique publié sur GitHub Pages
```

## Bon usage

Le radar ne collecte que des annonces publiques, renvoie toujours vers l'annonce
d'origine et ne republie **aucune donnée personnelle** : pas d'email ni de téléphone
de recruteur. Le rythme des requêtes reste modeste (2 scans par jour, pauses entre les
pages).
