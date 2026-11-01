// Salesforce Mission Radar — front 100 % statique.
// Les données sont pré-calculées chaque jour (data/offers.json) : aucun appel
// serveur au chargement, tout le filtrage se fait ici, dans le navigateur.
// Le suivi (pipeline) et les modèles de message vivent dans le localStorage.
'use strict';

const $ = (id) => document.getElementById(id);
const PAGE_SIZE = 60;

const STATUSES = [
  { key: 'to_contact', label: 'À contacter', icon: '🎯' },
  { key: 'applied', label: 'Candidaté', icon: '📨' },
  { key: 'interview', label: 'Entretien', icon: '🗣️' },
  { key: 'won', label: 'Gagné', icon: '🏆' },
  { key: 'lost', label: 'Perdu', icon: '🫥' },
];
const DISMISSED = 'dismissed';

const FLAGS = {
  'France': '🇫🇷', 'Belgique': '🇧🇪', 'Suisse': '🇨🇭', 'Luxembourg': '🇱🇺', 'Royaume-Uni': '🇬🇧',
  'Irlande': '🇮🇪', 'Allemagne': '🇩🇪', 'Autriche': '🇦🇹', 'Pays-Bas': '🇳🇱', 'Espagne': '🇪🇸',
  'Portugal': '🇵🇹', 'Italie': '🇮🇹', 'Pologne': '🇵🇱', 'Roumanie': '🇷🇴', 'Croatie': '🇭🇷',
  'Rép. tchèque': '🇨🇿', 'Danemark': '🇩🇰', 'Suède': '🇸🇪', 'Norvège': '🇳🇴', 'Finlande': '🇫🇮',
  'Grèce': '🇬🇷', 'Maroc': '🇲🇦', 'Tunisie': '🇹🇳', 'Émirats arabes unis': '🇦🇪',
  'Arabie saoudite': '🇸🇦', 'Qatar': '🇶🇦', 'Canada': '🇨🇦', 'États-Unis': '🇺🇸', 'Inde': '🇮🇳',
  'Singapour': '🇸🇬', 'Australie': '🇦🇺',
};

const DEFAULT_TEMPLATES = {
  fr: `Bonjour,

Votre mission « {titre} » chez {entreprise} a retenu mon attention. Consultant freelance Salesforce, je peux intervenir rapidement, y compris sur un format court ou à temps partiel.

Quelques références récentes : [à compléter]

Seriez-vous disponible pour un court échange cette semaine ?

Bien cordialement,
{nom}`,
  en: `Hello,

Your "{titre}" assignment at {entreprise} caught my attention. I am a freelance Salesforce consultant and can start quickly, including on a short-term or part-time basis.

A few recent references: [to complete]

Would you have time for a quick call this week?

Best regards,
{nom}`,
};

// ---------- État ----------
const state = {
  offers: [],
  meta: {},
  companies: null,
  tab: 'top',
  zone: '',
  limit: PAGE_SIZE,
  companySort: { key: 'last_seen', dir: -1 },
};
const store = {
  get(key, fallback) {
    try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; }
  },
  set(key, value) { localStorage.setItem(key, JSON.stringify(value)); },
};
let pipeline = store.get('radar.pipeline', {});
const previousVisit = rememberVisit();

// « Nouveau » = apparu depuis la visite précédente. Une visite dure tant que
// l'onglet est ouvert : on fige la date dans sessionStorage pour que les badges
// ne disparaissent pas au premier rechargement.
function rememberVisit() {
  let prev = sessionStorage.getItem('radar.previousVisit');
  if (!prev) {
    prev = localStorage.getItem('radar.lastVisit') || new Date(Date.now() - 864e5).toISOString();
    sessionStorage.setItem('radar.previousVisit', prev);
  }
  localStorage.setItem('radar.lastVisit', new Date().toISOString());
  return new Date(prev);
}

// ---------- Utilitaires ----------
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => (
  { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const norm = (s) => String(s ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
const isNew = (o) => new Date(o.first_seen) > previousVisit;
const isShortLike = (o) => o.short || o.part_time || o.tma;
const rateOf = (o) => o.tjm_max || o.tjm_min || 0;

function formatRate(o) {
  const lo = o.tjm_min, hi = o.tjm_max;
  if (lo && hi && lo !== hi) return `${lo}–${hi} €/j`;
  if (lo || hi) return `${hi || lo} €/j`;
  return o.budget || '';
}

function formatDuration(days) {
  if (!days) return '';
  if (days < 14) return `${days} j`;
  if (days < 60) return `${Math.round(days / 7)} sem.`;
  if (days < 365) return `${Math.round(days / 30)} mois`;
  return `${Math.round(days / 365)} an${days >= 730 ? 's' : ''}`;
}

function ago(iso) {
  if (!iso) return '';
  const days = Math.floor((Date.now() - new Date(iso.slice(0, 10))) / 864e5);
  if (days <= 0) return "aujourd'hui";
  if (days === 1) return 'hier';
  if (days < 30) return `il y a ${days} j`;
  return `il y a ${Math.floor(days / 30)} mois`;
}

function median(values) {
  const v = values.filter(Boolean).sort((a, b) => a - b);
  if (!v.length) return null;
  const m = Math.floor(v.length / 2);
  return v.length % 2 ? v[m] : Math.round((v[m - 1] + v[m]) / 2);
}

function toast(message) {
  const t = $('toast');
  t.textContent = message;
  t.classList.add('show');
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => t.classList.remove('show'), 2200);
}

const sourceLabel = (s) => (state.meta.source_labels || {})[s] || s;

// ---------- Chargement ----------
async function load() {
  try {
    const resp = await fetch('data/offers.json', { cache: 'no-cache' });
    const data = await resp.json();
    state.offers = data.offers;
    state.meta = data.meta;
  } catch (err) {
    $('grid').innerHTML = `<div class="empty"><b>😵</b>Impossible de charger les données (${esc(err.message)}).</div>`;
    return;
  }
  renderHeader();
  renderSourceFilter();
  renderZones();
  renderCounts();
  render();
}

// ---------- En-tête ----------
function renderHeader() {
  const active = state.offers.filter((o) => o.active);
  const generated = new Date(state.meta.generated_at);
  const dayAgo = new Date(generated - 864e5);
  const fresh = active.filter((o) => new Date(o.first_seen) >= dayAgo);
  const short = active.filter(isShortLike);
  const intl = active.filter((o) => o.zone === 'Europe' || o.zone === 'Monde');
  const frRate = median(active.filter((o) => o.zone === 'France').map(rateOf));

  $('updated').innerHTML = `Mis à jour le <b>${generated.toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long' })}</b>
    à ${generated.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}<br>
    <a href="feed-courtes.xml" title="S'abonner aux missions courtes">📡 Alertes RSS</a>`;

  const kpis = [
    { value: active.length, label: 'missions actives', tab: 'top' },
    { value: fresh.length, label: 'nouvelles en 24 h', tab: 'all', onlyFresh: true },
    { value: short.length, label: 'courtes / temps partiel', tab: 'short' },
    { value: intl.length, label: 'à l\'international', tab: 'intl' },
    { value: frRate ? `${frRate} €` : '—', label: 'TJM médian France', tab: 'all' },
  ];
  $('kpis').innerHTML = kpis.map((k, i) =>
    `<button class="kpi" data-i="${i}"><b>${k.value}</b><span>${k.label}</span></button>`).join('');
  $('kpis').querySelectorAll('.kpi').forEach((el) => {
    el.onclick = () => {
      const k = kpis[+el.dataset.i];
      $('onlyNew').checked = !!k.onlyFresh;
      showTab(k.tab);
      $('tabs').scrollIntoView({ behavior: 'smooth' });
    };
  });

  const sources = state.meta.sources || {};
  $('srcStatus').innerHTML = Object.entries(sources).map(([name, s]) =>
    `<span class="tag ${s.error ? 'off' : ''}" title="${esc(s.error || '')}">${esc(sourceLabel(name))} · ${s.count}</span>`).join('');
}

function renderSourceFilter() {
  const names = [...new Set(state.offers.map((o) => o.source))].sort();
  $('source').innerHTML = '<option value="">Toutes les sources</option>' +
    names.map((n) => `<option value="${esc(n)}">${esc(sourceLabel(n))}</option>`).join('');
}

function renderZones() {
  const zones = [['', 'Toutes'], ['France', '🇫🇷 France'], ['Europe', '🇪🇺 Europe'], ['Monde', '🌎 Monde'], ['Remote', '🏠 Remote']];
  $('zones').innerHTML = zones.map(([z, label]) =>
    `<button class="chip ${state.zone === z ? 'on' : ''}" data-z="${z}">${label}</button>`).join('');
  $('zones').querySelectorAll('.chip').forEach((el) => {
    el.onclick = () => { state.zone = el.dataset.z; renderZones(); resetAndRender(); };
  });
}

function renderCounts() {
  const active = state.offers.filter((o) => o.active && !isDismissed(o));
  $('c-short').textContent = active.filter(isShortLike).length;
  $('c-intl').textContent = active.filter((o) => o.zone !== 'France').length;
  $('c-all').textContent = active.length;
  $('c-pipe').textContent = Object.values(pipeline).filter((p) => p.status !== DISMISSED).length || '';
}

// ---------- Offres ----------
const isDismissed = (o) => pipeline[o.id]?.status === DISMISSED;

function filteredOffers() {
  const q = norm($('q').value).split(/\s+/).filter(Boolean);
  const minRate = +$('tjm').value;
  const source = $('source').value;
  const remoteOnly = $('remote').checked;
  const noEsn = $('noEsn').checked;
  const onlyNew = $('onlyNew').checked;
  const hideDone = $('hideDone').checked;

  let rows = state.offers.filter((o) => {
    if (!o.active && state.tab !== 'all') return false;
    if (state.tab === 'short' && !isShortLike(o)) return false;
    if (state.tab === 'intl' && o.zone === 'France') return false;
    if (state.zone && o.zone !== state.zone) return false;
    if (minRate && rateOf(o) < minRate) return false;
    if (source && o.source !== source && !(o.also_on || []).some((a) => a.source === source)) return false;
    if (remoteOnly && o.remote !== 'Full remote') return false;
    if (noEsn && o.is_esn) return false;
    if (onlyNew && !isNew(o)) return false;
    if (hideDone && pipeline[o.id]) return false;
    if (q.length) {
      const hay = norm([o.title, o.company, o.location, o.country, o.snippet, (o.skills || []).join(' ')].join(' '));
      if (!q.every((w) => hay.includes(w))) return false;
    }
    return true;
  });

  // Tri chronologique, toutes sources confondues : date de publication, puis première détection, puis score
  const cmp = (x, y) => (x > y ? 1 : x < y ? -1 : 0);
  rows.sort((a, b) => cmp(b.published || b.first_seen.slice(0, 10), a.published || a.first_seen.slice(0, 10))
    || cmp(b.first_seen, a.first_seen) || b.score - a.score);
  return rows;
}

function resetAndRender() { state.limit = PAGE_SIZE; render(); }

function render() {
  if (state.tab === 'pipeline') return renderPipeline();
  if (state.tab === 'companies') return renderCompanies();
  const rows = filteredOffers();
  const shown = rows.slice(0, state.limit);
  const newCount = rows.filter(isNew).length;
  $('resultLine').textContent = `${rows.length} mission(s)` +
    (newCount ? ` · ${newCount} nouvelle(s) depuis ta dernière visite` : '');
  $('grid').innerHTML = shown.length ? shown.map(cardHtml).join('') :
    '<div class="empty"><b>🔭</b>Aucune mission avec ces filtres. Élargis la recherche ou repasse demain : le radar tourne chaque jour.</div>';
  $('more').hidden = rows.length <= state.limit;
}

function scoreColor(score) {
  if (score >= 70) return '#059669';
  if (score >= 55) return '#0284c7';
  if (score >= 40) return '#1d4ed8';
  return '#94a3b8';
}

function cardHtml(o) {
  const kind = o.short ? 'k-short' : o.part_time ? 'k-part' : (o.zone === 'Europe' || o.zone === 'Monde') ? 'k-intl' : '';
  const status = pipeline[o.id]?.status;
  const rate = formatRate(o);
  const tags = [];
  if (isNew(o)) tags.push('<span class="tag new">Nouveau</span>');
  if (!o.active) tags.push('<span class="tag off">Plus en ligne</span>');
  if (rate) tags.push(`<span class="tag money">💶 ${esc(rate)}</span>`);
  if (o.short) tags.push(`<span class="tag short">⚡ ${esc(o.short_reason || 'courte')}</span>`);
  if (o.part_time) tags.push(`<span class="tag part">⏱ ${esc(o.part_time)}</span>`);
  if (o.tma) tags.push('<span class="tag part">🔧 TMA / run</span>');
  if (o.duration_days && !o.short) tags.push(`<span class="tag">⏳ ${formatDuration(o.duration_days)}</span>`);
  if (o.remote) tags.push(`<span class="tag remote">🏠 ${esc(o.remote)}</span>`);
  if (o.zone !== 'France' && o.country) tags.push(`<span class="tag intl">${FLAGS[o.country] || '🌍'} ${esc(o.country)}</span>`);
  if (o.ai?.seniority) tags.push(`<span class="tag">🎓 ${esc(o.ai.seniority)}</span>`);
  (o.ai?.clouds || []).slice(0, 4).forEach((c) => tags.push(`<span class="tag cloud">${esc(c)}</span>`));
  if (o.client_final) tags.push('<span class="tag final">Client final</span>');
  else if (o.is_esn) tags.push('<span class="tag esn">ESN / cabinet</span>');

  const where = o.location || '';
  const also = (o.also_on || []).map((a) =>
    `<a href="${esc(a.url)}" target="_blank" rel="noopener">${esc(sourceLabel(a.source))}</a>`).join(', ');
  const reasons = (o.reasons || []).map((r) => `• ${r}`).join('\n');

  return `<article class="card ${kind} ${o.active ? '' : 'inactive'} ${status ? 'st-' + status : ''}">
    <div class="card-head">
      <div class="score" style="--v:${o.score};--sc:${scoreColor(o.score)}" data-v="${o.score}"
           title="Score d'opportunité ${o.score}/100\n${esc(reasons)}"></div>
      <div>
        <h3 class="title"><a href="${esc(o.url)}" target="_blank" rel="noopener">${esc(o.title)}</a></h3>
        <div class="sub"><b>${esc(o.company || 'Société non précisée')}</b>${where ? ' · ' + esc(where) : ''} · ${ago(o.published || o.first_seen)}</div>
      </div>
    </div>
    <div class="tags">${tags.join('')}</div>
    ${o.ai?.summary ? `<p class="snippet ai" title="Résumé rédigé par Claude">✨ ${esc(o.ai.summary)}</p>`
      : o.snippet ? `<p class="snippet">${esc(o.snippet)}</p>` : ''}
    <div class="card-foot">
      <span class="src">${esc(sourceLabel(o.source))}${also ? ' · aussi sur ' + also : ''}</span>
      <span class="spacer"></span>
      <select class="status" data-id="${esc(o.id)}" title="Suivi">
        <option value="">📌 Suivre…</option>
        ${STATUSES.map((s) => `<option value="${s.key}" ${status === s.key ? 'selected' : ''}>${s.icon} ${s.label}</option>`).join('')}
        <option value="${DISMISSED}" ${status === DISMISSED ? 'selected' : ''}>🙈 Écarter</option>
      </select>
      <button class="btn" data-pitch="${esc(o.id)}" title="${o.ai?.pitch ? 'Copier le message rédigé par Claude pour cette annonce' : 'Copier un message d\'approche personnalisé'}">${o.ai?.pitch ? '✨' : '✉️'} Pitch</button>
      <a class="btn primary" href="${esc(o.url)}" target="_blank" rel="noopener">Voir ↗</a>
    </div>
  </article>`;
}

// Délégation d'événements : un seul écouteur pour toutes les cartes.
$('grid').addEventListener('change', (e) => {
  if (e.target.matches('.status')) setStatus(e.target.dataset.id, e.target.value);
});
$('grid').addEventListener('click', (e) => {
  const btn = e.target.closest('[data-pitch]');
  if (btn) copyPitch(btn.dataset.pitch);
});

// ---------- Pipeline ----------
function offerById(id) { return state.offers.find((o) => o.id === id); }

function setStatus(id, status) {
  if (!status) {
    delete pipeline[id];
  } else {
    const o = offerById(id) || pipeline[id]?.offer || {};
    pipeline[id] = {
      ...(pipeline[id] || {}),
      status,
      updated: new Date().toISOString(),
      // Instantané de l'offre : le pipeline survit à l'expiration de l'annonce.
      offer: { title: o.title, url: o.url, company: o.company, source: o.source, rate: formatRate(o), country: o.country, lang: o.lang, location: o.location, pitch: o.ai?.pitch || o.pitch },
    };
  }
  store.set('radar.pipeline', pipeline);
  const label = status === DISMISSED ? 'Offre écartée' : status ? `Ajoutée au pipeline : ${STATUSES.find((s) => s.key === status).label}` : 'Retirée du pipeline';
  toast(label);
  renderCounts();
  render();
}

function renderPipeline() {
  const items = Object.entries(pipeline).filter(([, p]) => p.status !== DISMISSED);
  const byStatus = (key) => items.filter(([, p]) => p.status === key)
    .sort((a, b) => (b[1].updated > a[1].updated ? 1 : -1));
  const applied = items.filter(([, p]) => ['applied', 'interview', 'won', 'lost'].includes(p.status)).length;
  const won = byStatus('won').length;
  $('funnel').innerHTML = `
    <div><b>${items.length}</b> missions suivies</div>
    <div><b>${applied}</b> candidatures</div>
    <div><b>${byStatus('interview').length}</b> entretiens en cours</div>
    <div><b>${won}</b> gagnées${applied ? ` · ${Math.round((won / applied) * 100)} % de conversion` : ''}</div>`;
  $('board').innerHTML = STATUSES.map((s) => {
    const list = byStatus(s.key);
    return `<div class="col" data-s="${s.key}">
      <h3><span>${s.icon} ${s.label}</span><span>${list.length}</span></h3>
      ${list.map(([id, p]) => pipelineCardHtml(id, p)).join('') || '<div class="src">—</div>'}
    </div>`;
  }).join('');
}

function pipelineCardHtml(id, p) {
  const o = p.offer || {};
  return `<div class="pcard">
    <a href="${esc(o.url)}" target="_blank" rel="noopener">${esc(o.title || id)}</a>
    <div class="src">${esc(o.company || '')}${o.rate ? ' · ' + esc(o.rate) : ''} · ${ago(p.updated)}</div>
    <textarea data-note="${esc(id)}" placeholder="Notes : contact, relance le…">${esc(p.note || '')}</textarea>
    <div class="row">
      <select data-move="${esc(id)}">
        ${STATUSES.map((s) => `<option value="${s.key}" ${p.status === s.key ? 'selected' : ''}>${s.icon} ${s.label}</option>`).join('')}
        <option value="">🗑 Retirer</option>
      </select>
      <button class="btn" data-pitch="${esc(id)}">✉️</button>
    </div>
  </div>`;
}

$('board').addEventListener('change', (e) => {
  if (e.target.dataset.move !== undefined) setStatus(e.target.dataset.move, e.target.value);
});
$('board').addEventListener('input', (e) => {
  const id = e.target.dataset.note;
  if (id && pipeline[id]) {
    pipeline[id].note = e.target.value;
    store.set('radar.pipeline', pipeline);
  }
});
$('board').addEventListener('click', (e) => {
  const btn = e.target.closest('[data-pitch]');
  if (btn) copyPitch(btn.dataset.pitch);
});

$('exportPipe').onclick = () => {
  download(`pipeline-${new Date().toISOString().slice(0, 10)}.json`,
    JSON.stringify(pipeline, null, 2), 'application/json');
};
$('importPipe').onchange = async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  try {
    const imported = JSON.parse(await file.text());
    pipeline = { ...pipeline, ...imported };
    store.set('radar.pipeline', pipeline);
    toast(`${Object.keys(imported).length} élément(s) importé(s)`);
    renderCounts();
    render();
  } catch {
    toast('Fichier invalide');
  }
};

// ---------- Pitch ----------
function templates() { return { ...DEFAULT_TEMPLATES, ...store.get('radar.templates', {}) }; }

function copyPitch(id) {
  const o = offerById(id) || pipeline[id]?.offer;
  if (!o) return;
  // Pitch rédigé par Claude pour cette annonce s'il existe, sinon le modèle générique.
  const tpl = o.ai?.pitch || o.pitch || templates()[o.lang === 'en' ? 'en' : 'fr'];
  const text = tpl
    .replaceAll('{titre}', o.title || '')
    .replaceAll('{entreprise}', o.company || (o.lang === 'en' ? 'your company' : 'votre structure'))
    .replaceAll('{tjm}', o.rate || formatRate(o) || '')
    .replaceAll('{lieu}', o.location || o.country || '')
    .replaceAll('{nom}', store.get('radar.name', ''));
  navigator.clipboard.writeText(text).then(
    () => toast('✉️ Message copié : colle-le dans ta réponse'),
    () => { prompt('Copie ce message :', text); },
  );
}

function openSettings(e) {
  e?.preventDefault();
  const t = templates();
  $('tplFr').value = t.fr;
  $('tplEn').value = t.en;
  $('myName').value = store.get('radar.name', '');
  $('settings').showModal();
}
$('openSettings').onclick = openSettings;
$('openSettings2').onclick = openSettings;
$('saveTpl').onclick = () => {
  store.set('radar.templates', { fr: $('tplFr').value, en: $('tplEn').value });
  store.set('radar.name', $('myName').value);
  toast('Modèles enregistrés');
};
$('resetTpl').onclick = (e) => {
  e.preventDefault();
  $('tplFr').value = DEFAULT_TEMPLATES.fr;
  $('tplEn').value = DEFAULT_TEMPLATES.en;
};

// ---------- Vivier ----------
async function renderCompanies() {
  if (!state.companies) {
    $('ctable').innerHTML = '<tr><td>Chargement…</td></tr>';
    const resp = await fetch('data/companies.json', { cache: 'no-cache' });
    state.companies = (await resp.json()).companies;
  }
  const q = norm($('cq').value);
  const noEsn = $('cNoEsn').checked;
  const withRate = $('cTjm').checked;
  const min = +$('cMin').value;
  const { key, dir } = state.companySort;
  const rows = state.companies.filter((c) =>
    (!q || norm(c.name).includes(q)) && (!noEsn || !c.is_esn) &&
    (!withRate || c.tjm_median) && c.missions >= min)
    .sort((a, b) => {
      const va = a[key] ?? '', vb = b[key] ?? '';
      return (va > vb ? 1 : va < vb ? -1 : 0) * dir;
    });
  $('cLine').textContent = `${rows.length} entreprise(s) · l'historique est conservé même quand les annonces expirent`;

  const cols = [['name', 'Entreprise'], ['missions', 'Missions'], ['short', 'Courtes'],
    ['tjm_median', 'TJM médian'], ['countries', 'Pays'], ['last_seen', 'Dernière annonce'], ['', 'Prospecter']];
  const head = '<tr>' + cols.map(([k, label]) =>
    `<th data-k="${k}" class="${k === key ? 'sorted' : ''}">${label}${k === key ? (dir > 0 ? ' ↑' : ' ↓') : ''}</th>`).join('') + '</tr>';
  const body = rows.slice(0, 400).map((c) => {
    const last = c.titles?.[0];
    const li = `https://www.linkedin.com/search/results/people/?keywords=${encodeURIComponent(c.name + ' salesforce')}`;
    const google = `https://www.google.com/search?q=${encodeURIComponent(`"${c.name}" salesforce responsable CRM`)}`;
    return `<tr>
      <td><b>${esc(c.name)}</b><br>${c.is_esn ? '<span class="tag esn">ESN / cabinet</span>' : '<span class="tag final">Client final</span>'}</td>
      <td>${c.missions}</td>
      <td>${c.short || ''}</td>
      <td>${c.tjm_median ? c.tjm_median + ' €' : '<small>—</small>'}</td>
      <td>${c.countries.map((p) => FLAGS[p] || p).join(' ')}</td>
      <td>${last ? `<a href="${esc(last.url)}" target="_blank" rel="noopener">${esc(last.title)}</a><br><small>${ago(c.last_seen)} · ${c.sources.map(sourceLabel).join(', ')}</small>` : ''}</td>
      <td class="links"><a href="${li}" target="_blank" rel="noopener">LinkedIn</a><a href="${google}" target="_blank" rel="noopener">Google</a></td>
    </tr>`;
  }).join('');
  $('ctable').innerHTML = head + body;
  $('ctable').querySelectorAll('th[data-k]').forEach((th) => {
    if (!th.dataset.k) return;
    th.onclick = () => {
      const k = th.dataset.k;
      state.companySort = { key: k, dir: state.companySort.key === k ? -state.companySort.dir : (k === 'name' ? 1 : -1) };
      renderCompanies();
    };
  });
}

$('exportCsv').onclick = () => {
  const rows = [['Entreprise', 'Type', 'Missions', 'Courtes', 'TJM médian', 'Pays', 'Sources', 'Première vue', 'Dernière vue', 'Dernière annonce']];
  for (const c of state.companies || []) {
    rows.push([c.name, c.is_esn ? 'ESN' : 'Client final', c.missions, c.short, c.tjm_median || '',
      c.countries.join(' / '), c.sources.join(' / '), c.first_seen.slice(0, 10), c.last_seen, c.titles?.[0]?.title || '']);
  }
  const csv = rows.map((r) => r.map((v) => `"${String(v).replace(/"/g, '""')}"`).join(';')).join('\n');
  download('vivier-salesforce.csv', '﻿' + csv, 'text/csv');
};
['cq', 'cNoEsn', 'cTjm', 'cMin'].forEach((id) => $(id).addEventListener('input', renderCompanies));

function download(name, content, type) {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([content], { type }));
  a.download = name;
  a.click();
  URL.revokeObjectURL(a.href);
}

// ---------- Onglets & filtres ----------
function showTab(tab) {
  state.tab = tab;
  document.querySelectorAll('.tab').forEach((t) => t.classList.toggle('active', t.dataset.tab === tab));
  $('view-offers').hidden = tab === 'pipeline' || tab === 'companies';
  $('view-pipeline').hidden = tab !== 'pipeline';
  $('view-companies').hidden = tab !== 'companies';
  history.replaceState(null, '', `#${tab}`);
  resetAndRender();
}
document.querySelectorAll('.tab').forEach((t) => { t.onclick = () => showTab(t.dataset.tab); });

let searchTimer;
$('q').addEventListener('input', () => { clearTimeout(searchTimer); searchTimer = setTimeout(resetAndRender, 120); });
['tjm', 'source', 'remote', 'noEsn', 'onlyNew', 'hideDone'].forEach((id) => $(id).addEventListener('change', resetAndRender));
$('more').onclick = () => { state.limit += PAGE_SIZE; render(); };

const initialTab = location.hash.slice(1);
if (['top', 'short', 'intl', 'all', 'pipeline', 'companies'].includes(initialTab)) {
  state.tab = initialTab;
  document.querySelectorAll('.tab').forEach((t) => t.classList.toggle('active', t.dataset.tab === initialTab));
  $('view-offers').hidden = initialTab === 'pipeline' || initialTab === 'companies';
  $('view-pipeline').hidden = initialTab !== 'pipeline';
  $('view-companies').hidden = initialTab !== 'companies';
}
load();
