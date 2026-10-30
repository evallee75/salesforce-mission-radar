# Routine d'analyse IA des missions

Consignes suivies par la routine Claude Code planifiée (2×/jour, ~30 min après
chaque scan). Elle lit les nouvelles annonces, les analyse et pousse le résultat ;
le push déclenche la republication du site (workflow `radar.yml`, mode `--publish-only`).

## Étapes

1. Lire `data/ai_queue.json` : liste d'annonces `{id, title, company, location,
   country, source, lang, rate, duration, text}`. Si la liste est vide, s'arrêter
   sans rien committer.
2. Lire `data/ai.json` (objet `{id: analyse}`, `{}` s'il n'existe pas).
3. Pour **chaque** annonce de la file, produire une analyse au format ci-dessous en
   se fondant uniquement sur `title` + `text` (ne pas ouvrir les URLs), puis l'ajouter
   dans `data/ai.json` sous la clé `id`. Ne jamais modifier ni supprimer les entrées
   déjà présentes.
4. Écrire `data/ai.json` en JSON valide (UTF-8, `ensure_ascii=False`), le valider avec
   `python3 -c "import json; json.load(open('data/ai.json'))"`.
5. `git add data/ai.json`, commit `Analyse IA : N mission(s)` et `git push` sur `main`
   (en cas de rejet : `git pull --rebase` puis push). Ne toucher à aucun autre fichier.

## Format d'une analyse

```json
{
  "summary": "Une phrase en français (≤ 160 caractères) : le besoin réel, le contexte, ce qui compte.",
  "format": "courte | temps_partiel | longue | inconnu",
  "days_per_week": 2,
  "duration_days": 20,
  "end_client": true,
  "seniority": "junior | confirmé | senior | expert",
  "clouds": ["Sales Cloud", "CPQ"],
  "salesforce_relevant": true,
  "pitch": "…",
  "analyzed_at": "YYYY-MM-DD"
}
```

- `format` : `courte` = mission de quelques jours à ~6 semaines, ponctuelle, renfort,
  audit, forfait ; `temps_partiel` = moins de 5 j/semaine sur la durée ; `longue` =
  temps plein de plus de 2 mois ; `inconnu` si l'annonce ne permet pas de trancher.
  **« 2 jours de télétravail par semaine » n'est PAS du temps partiel.**
- `days_per_week` : nombre de jours travaillés par semaine si indiqué (5 = temps plein), sinon `null`.
- `duration_days` : durée initiale en jours calendaires si indiquée (1 mois = 30), sinon `null`.
- `end_client` : `true` si l'annonceur est le client final, `false` si c'est une ESN,
  un cabinet, un recruteur ou une plateforme qui place un consultant chez un client,
  `null` si impossible à dire.
- `seniority` : niveau attendu, `null` si non précisé.
- `clouds` : produits Salesforce demandés (Sales Cloud, Service Cloud, Marketing Cloud,
  Experience Cloud, CPQ / Revenue Cloud, Field Service, Data Cloud, Agentforce,
  MuleSoft, Tableau, Pardot / Account Engagement, Commerce Cloud, Industries / OmniStudio,
  Platform / Apex / LWC…). Liste vide si rien de précis.
- `salesforce_relevant` : `false` si Salesforce n'est qu'accessoire (ex. Data Engineer
  qui extrait des données de Salesforce).
- `pitch` : message de candidature **dans la langue de l'annonce** (`lang` : `fr` ou
  `en`), 70 à 110 mots, ton professionnel et direct, à la première personne, écrit par
  un consultant freelance Salesforce indépendant. Il reprend 2 ou 3 éléments précis de
  l'annonce (produits, contexte, enjeu) pour montrer qu'elle a été lue, met en avant la
  disponibilité rapide et la souplesse (format court ou partiel bienvenu), propose un
  court échange. Ne pas inventer de références, de clients ni d'années d'expérience :
  utiliser `[référence à compléter]` si besoin. Commencer par « Bonjour, » ou
  « Hello, » et terminer par une formule de politesse suivie de `{nom}` seul sur la
  dernière ligne.
- `analyzed_at` : date du jour.
