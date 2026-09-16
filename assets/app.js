/* BHM Gündem Takip — statik arayüz (bağımlılıksız) */
const RC = { 'Türkiye': 'var(--tr)', 'Belçika': 'var(--be)', 'Avrupa': 'var(--eu)', 'Dünya': 'var(--dn)', 'Kurumsal': 'var(--kr)' };
const PAGE = 60;
const $ = (s, r = document) => r.querySelector(s);
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const slug = (s) => String(s).toLowerCase().replace(/[çğıöşü]/g, (c) => ({ ç: 'c', ğ: 'g', ı: 'i', ö: 'o', ş: 's', ü: 'u' }[c]));

const ic = (it) => it.k ? `haber.html?k=${encodeURIComponent(it.k)}`
  : `${it.url}" target="_blank" rel="noopener noreferrer`;

const state = { items: [], sources: [], feeds: {}, themes: [], stats: {}, shown: PAGE, region: '', lead: new Set() };

const dayFmt = new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'long', year: 'numeric', weekday: 'long' });
const timeFmt = new Intl.DateTimeFormat('tr-TR', { hour: '2-digit', minute: '2-digit' });
const fullFmt = new Intl.DateTimeFormat('tr-TR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });

async function getJSON(path, fallback) {
  try {
    const r = await fetch(path + '?t=' + Date.now(), { cache: 'no-store' });
    if (!r.ok) throw new Error(r.status);
    return await r.json();
  } catch (e) { return fallback; }
}

/* ---------------------------------------------------------------- kartlar */
function thumb(it, cls = 'thumb') {
  return it.gorsel
    ? `<div class="${cls}"><img src="${esc(it.gorsel)}" alt="" loading="lazy" onerror="this.closest('div').remove()"></div>`
    : '';
}

function card(it) {
  const pr = slug(it.oncelik || '');
  const prCls = pr === 'kritik' ? 'kritik' : pr === 'yuksek' ? 'yuksek' : '';
  const d = new Date(it.tarih);
  return `<article class="card${it.gorsel ? ' has-img' : ''}" style="--c:${RC[it.bolge] || 'var(--petrol)'}">
    ${thumb(it)}
    <div class="govde">
    <div class="meta">
      <span class="src">${esc(it.kaynak)}</span>
      <span>${esc(it.bolge)}${it.kategori ? ' · ' + esc(it.kategori) : ''}</span>
      ${it.oncelik ? `<span class="tag ${prCls}">${esc(it.oncelik)}</span>` : ''}
      ${it.kanit ? `<span class="tag${it.kanit.startsWith('Birincil') ? ' birincil' : ''}">${esc(it.kanit)}</span>` : ''}
      ${it.tip === 'arama' ? '<span class="tag arama" title="Kaynağın RSS yayını yok; alan adına kilitli haber aramasıyla bulundu">arama</span>' : ''}
      <span class="mono muted">${isNaN(d) ? '' : timeFmt.format(d)}${it.tahmini ? ' · tarih tahmini' : ''}</span>
    </div>
    <h3><a href="${ic(it)}">${esc(it.baslik)}</a></h3>
    ${it.ozet ? `<p>${esc(it.ozet)}</p>` : ''}
    ${(it.terimler || []).length ? `<div class="terms">${it.terimler.map((t) => `<b>${esc(t)}</b>`).join('')}</div>` : ''}
    </div>
  </article>`;
}

function renderFeed(el, rows, limit) {
  if (!rows.length) { el.innerHTML = `<div class="empty">Bu filtrelerle gelişme bulunamadı.</div>`; return; }
  const list = limit ? rows.slice(0, limit) : rows;
  const groups = [];
  list.forEach((it) => {
    const day = String(it.tarih).slice(0, 10);
    if (!groups.length || groups[groups.length - 1].day !== day) groups.push({ day, rows: [] });
    groups[groups.length - 1].rows.push(it);
  });
  const today = new Date().toISOString().slice(0, 10);
  el.innerHTML = groups.map((g) => {
    const d = new Date(g.day + 'T12:00:00Z');
    const label = g.day === today ? 'Bugün' : dayFmt.format(d);
    return `<div class="daygroup"><div class="dayhead"><h2>${esc(label)}</h2>
      <span>${g.rows.length} gelişme${g.day === today ? '' : ' · ' + dayFmt.format(d)}</span></div>
      <div class="list">${g.rows.map(card).join('')}</div></div>`;
  }).join('') + (limit && rows.length > limit
    ? `<button class="more" id="more">Daha fazla göster (${rows.length - limit} gelişme daha)</button>` : '');
  const more = $('#more', el);
  if (more) more.onclick = () => { state.shown += PAGE * 2; draw(); };
}


/* ------------------------------------------------------- manşet ve özet */
const DAY = 864e5;

function recent(days) {
  const t = Date.now() - days * DAY;
  return state.items.filter((i) => new Date(i.tarih).getTime() >= t);
}

function leadCard(it) {
  const d = new Date(it.tarih);
  return `<article class="manset" style="--c:${RC[it.bolge] || 'var(--petrol)'}">
    ${it.gorsel ? `<a class="manset-img" href="${ic(it)}"><img src="${esc(it.gorsel)}" alt="" onerror="this.closest('a').remove()"></a>` : ''}
    <div class="eyebrow"><span class="pin"></span>${esc(it.bolge)}<span class="sep">/</span>${esc(it.kategori || '')}</div>
    <h2><a href="${ic(it)}">${esc(it.baslik)}</a></h2>
    ${it.ozet ? `<p>${esc(it.ozet)}</p>` : ''}
    <div class="byline"><b>${esc(it.kaynak)}</b><span>${esc(it.kanit || '')}</span>
      <span class="mono">${isNaN(d) ? '' : fullFmt.format(d)}</span>
      <a class="ext" href="${esc(it.url)}" target="_blank" rel="noopener noreferrer">kaynakta oku ↗</a></div>
  </article>`;
}

function secondCard(it) {
  return `<a class="ikincil" style="--c:${RC[it.bolge] || 'var(--petrol)'}" href="${ic(it)}">
    <span class="eyebrow"><span class="pin"></span>${esc(it.bolge)}</span>
    <b>${esc(it.baslik)}</b>
    <span class="src">${esc(it.kaynak)}</span></a>`;
}

function renderLead() {
  const pool = (recent(2).length >= 6 ? recent(2) : recent(5))
    .slice().sort((a, b) => b.puan - a.puan);
  if (!pool.length) { $('#lead').innerHTML = `<div class="empty">Henüz tarama kaydı yok.</div>`; return; }

  const today = new Date().toISOString().slice(0, 10);
  const day = state.items.filter((i) => i.tarih.slice(0, 10) === today);
  const scope = day.length ? day : recent(2);
  const termCount = new Map();
  scope.forEach((i) => (i.terimler || []).forEach((t) => termCount.set(t, (termCount.get(t) || 0) + 1)));
  const topTerms = [...termCount.entries()].sort((a, b) => b[1] - a[1]).slice(0, 7);
  const srcCount = new Map();
  scope.forEach((i) => srcCount.set(i.kaynak, (srcCount.get(i.kaynak) || 0) + 1));
  const topSrc = [...srcCount.entries()].sort((a, b) => b[1] - a[1]).slice(0, 5);
  const critical = scope.filter((i) => i.oncelik === 'Kritik').length;

  $('#lead').innerHTML = `
    <div class="lead-main">
      ${leadCard(pool[0])}
      <div class="lead-second">${pool.slice(1, 4).map(secondCard).join('')}</div>
    </div>
    <aside class="ozet">
      <div class="ozet-head">${day.length ? 'Bugünün özeti' : 'Son iki günün özeti'}
        <span class="mono">${esc(new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'long' }).format(new Date()))}</span></div>
      <div class="ozet-say">
        <div><b>${scope.length}</b><span>başlık</span></div>
        <div><b>${new Set(scope.map((i) => i.id)).size}</b><span>kaynak</span></div>
        <div><b>${new Set(scope.map((i) => i.bolge)).size}</b><span>bölge</span></div>
        <div><b>${critical}</b><span>kritik kaynak</span></div>
      </div>
      ${topTerms.length ? `<div class="ozet-blok"><h4>Öne çıkan konular</h4>
        <div class="terms">${topTerms.map(([t, n]) => `<button class="term-btn" data-term="${esc(t)}"><b>${esc(t)}</b><span class="mono">${n}</span></button>`).join('')}</div></div>` : ''}
      ${topSrc.length ? `<div class="ozet-blok"><h4>En çok kayıt veren kaynaklar</h4>
        <ol class="ozet-list">${topSrc.map(([k, n]) => `<li>${esc(k)}<span class="mono">${n}</span></li>`).join('')}</ol></div>` : ''}
      <p class="ozet-not">Başlıklar kaynağın kendi yayınından alınır; dosyaya girecek gelişme birincil kaynakta doğrulanır.</p>
    </aside>`;

  state.lead = new Set(pool.slice(0, 4).map((i) => i.url));

  $('#lead').querySelectorAll('.term-btn').forEach((b) => b.addEventListener('click', () => {
    $('#q').value = b.dataset.term;
    state.shown = PAGE;
    draw();
    $('#akisBasi').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }));
}

/* -------------------------------------------------------- bölge blokları */
function renderRegions() {
  const order = ['Türkiye', 'Belçika', 'Avrupa', 'Dünya'];
  const html = order.map((r) => {
    const rows = state.items.filter((i) => i.bolge === r && !state.lead.has(i.url))
      .slice().sort((a, b) => b.puan - a.puan).slice(0, 3);
    if (!rows.length) return '';
    return `<section class="bolge" style="--c:${RC[r]}">
      <div class="bolge-head"><h3>${esc(r)}</h3>
        <button class="link" data-region="${esc(r)}">bu bölgenin tamamı →</button></div>
      <div class="bolge-grid">${rows.map((it) => `<article class="card sm${it.gorsel ? ' has-img' : ''}" style="--c:${RC[r]}">
        ${thumb(it, 'thumb wide')}
        <div class="govde">
        <div class="meta"><span class="src">${esc(it.kaynak)}</span>
          <span>${esc(it.kategori || '')}</span>
          ${it.oncelik === 'Kritik' ? '<span class="tag kritik">Kritik</span>' : ''}
          <span class="mono muted">${dayShort(it.tarih)}</span></div>
        <h3><a href="${ic(it)}">${esc(it.baslik)}</a></h3>
        ${it.ozet ? `<p>${esc(it.ozet.slice(0, 150))}${it.ozet.length > 150 ? '…' : ''}</p>` : ''}
        </div>
      </article>`).join('')}</div>
    </section>`;
  }).join('');
  $('#bolgeBloklari').innerHTML = html;
  $('#bolgeBloklari').querySelectorAll('.link').forEach((b) => b.addEventListener('click', () => {
    const chip = $(`#bolgeChips .chip[data-r="${b.dataset.region}"]`);
    if (chip) chip.click();
    $('#akisBasi').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }));
}

function dayShort(iso) {
  const d = new Date(iso);
  return isNaN(d) ? '' : new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'short' }).format(d);
}

/* ---------------------------------------------------------------- gündem */
function filtered() {
  const q = slug($('#q').value.trim());
  const themeId = $('#tema').value;
  const pr = $('#oncelik').value;
  const tip = $('#tip').value;
  const theme = state.themes.find((t) => t.id === themeId);
  let rows = state.items.filter((it) => {
    if (state.region && it.bolge !== state.region) return false;
    if (pr && it.oncelik !== pr) return false;
    if (tip && (it.tip || 'akış') !== tip) return false;
    if (theme && !(theme.kategoriler || []).includes(it.kategori)) return false;
    if (q) {
      const hay = slug(`${it.baslik} ${it.kaynak} ${it.ozet} ${it.kategori} ${(it.terimler || []).join(' ')}`);
      if (!hay.includes(q)) return false;
    }
    return true;
  });
  if ($('#sirala').value === 'puan') rows = rows.slice().sort((a, b) => b.puan - a.puan || (a.tarih < b.tarih ? 1 : -1));
  return rows;
}

function draw() {
  const rows = filtered();
  $('#count').textContent = `${rows.length} gelişme gösteriliyor`;
  renderFeed($('#feed'), rows, state.shown);
}

function statTiles(s) {
  const t = [
    ['bugün', s.bugun ?? 0, 'yeni gelişme'],
    [`son ${s.pencereGun || 21} gün`, s.haber ?? 0, 'toplam kayıt'],
    ['otomatik akış', `${s.akisVeriVeren ?? 0}/${s.akisTaranan ?? 0}`, 'veri veren / taranan RSS'],
    ['haber aramaları', `${s.aramaVeriVeren ?? 0}/${s.aramaKaynak ?? 0}`, 'RSS yayını olmayan kaynak'],
    ['kaynak envanteri', s.kaynak ?? 0, 'izlenen kaynak'],
    ['bölge dağılımı', Object.keys(s.bolge || {}).length, Object.entries(s.bolge || {}).map(([k, v]) => `${k} ${v}`).join(' · ') || '—'],
  ];
  return t.map(([label, value, sub]) => `<div class="stat"><span>${esc(label)}</span><b>${esc(value)}</b><i>${esc(sub)}</i></div>`).join('');
}

/* ------------------------------------------------------------- kaynaklar */
function feedOf(src) {
  for (const u of src.links || []) { const f = state.feeds[u]; if (f && f.feed) return f.feed; }
  return null;
}

function drawSources() {
  const q = slug($('#sq').value.trim());
  const b = $('#sbolge').value, k = $('#skategori').value, s = $('#ssiklik').value, r = $('#srss').value;
  const rows = state.sources.filter((x) => {
    if (b && x.bolge !== b) return false;
    if (k && x.kategori !== k) return false;
    if (s && x.siklik !== s) return false;
    const has = !!feedOf(x);
    if (r === 'var' && !has) return false;
    if (r === 'yok' && has) return false;
    if (q && !slug(`${x.ad} ${x.kategori} ${x.tur} ${x.anahtar || ''} ${x.neden || ''}`).includes(q)) return false;
    return true;
  });
  $('#scount').textContent = `${rows.length} kaynak`;
  $('#srcgrid').innerHTML = rows.map((x) => {
    const f = feedOf(x);
    const rows = state.items.filter((i) => i.id === x.id);
    const n = rows.length;
    const mode = f ? 'RSS' : rows.some((r) => r.tip === 'arama') ? 'arama' : 'elle';
    return `<div class="srccard" style="--c:${RC[x.bolge] || 'var(--petrol)'}">
      <div class="meta"><span>${esc(x.bolge)} · ${esc(x.kategori)}</span>
        <span class="rss${mode === 'RSS' ? '' : mode === 'arama' ? ' ara' : ' no'}">${mode}</span>
        ${n ? `<span class="tag">${n} kayıt</span>` : ''}</div>
      <h3>${esc(x.ad)}</h3>
      <div class="meta"><span class="tag">${esc(x.tur || '')}</span><span class="tag">${esc(x.siklik || '')}</span><span class="tag ${slug(x.oncelik || '') === 'kritik' ? 'kritik' : slug(x.oncelik || '') === 'yuksek' ? 'yuksek' : ''}">${esc(x.oncelik || '')}</span></div>
      ${x.neden ? `<p class="why">${esc(x.neden)}</p>` : ''}
      <div class="links">${(x.links || []).slice(0, 3).map((u, i) => `<a href="${esc(u)}" target="_blank" rel="noopener noreferrer">bağlantı ${i + 1}</a>`).join('')}
        ${f ? `<a href="${esc(f)}" target="_blank" rel="noopener noreferrer">akış</a>` : ''}</div>
    </div>`;
  }).join('') || `<div class="empty">Kaynak bulunamadı.</div>`;
}

function fillSelect(el, values, label) {
  el.innerHTML = `<option value="">${label}</option>` + [...new Set(values)].filter(Boolean).sort((a, b) => a.localeCompare(b, 'tr'))
    .map((v) => `<option>${esc(v)}</option>`).join('');
}

/* ----------------------------------------------------------------- arşiv */
async function drawArchive() {
  const day = $('#gun').value;
  if (!day) { $('#arsivFeed').innerHTML = `<div class="empty">Henüz arşiv kaydı yok.</div>`; return; }
  const d = await getJSON(`data/archive/${day}.json`, { haberler: [] });
  const rows = (d.haberler || []).slice().sort((a, b) => b.puan - a.puan);
  $('#acount').textContent = `${rows.length} kayıt`;
  renderFeed($('#arsivFeed'), rows, 0);
}

/* ------------------------------------------------------------------- init */
(async function init() {
  const [latest, meta, feeds, index] = await Promise.all([
    getJSON('data/latest.json', { haberler: [], istatistik: {}, olusturma: null }),
    getJSON('data/sources.json', { sources: [], themes: [] }),
    getJSON('data/feeds.json', {}),
    getJSON('data/archive-index.json', []),
  ]);
  state.items = latest.haberler || [];
  state.stats = latest.istatistik || {};
  state.sources = meta.sources || [];
  state.themes = meta.themes || [];
  state.feeds = feeds || {};

  // durum
  const ts = latest.olusturma ? new Date(latest.olusturma) : null;
  const hrs = ts ? (Date.now() - ts.getTime()) / 36e5 : 999;
  $('#statusText').textContent = ts ? `son tarama ${fullFmt.format(ts)}` : 'tarama verisi yok';
  if (hrs > 8) $('.dot').classList.add('stale');
  $('#footTime').textContent = ts ? fullFmt.format(ts) : '—';
  $('#footSrc').textContent = state.stats.kaynak ?? state.sources.length;
  $('#footFeed').textContent = state.stats.akisVeriVeren ?? 0;
  $('#stats').innerHTML = statTiles(state.stats);
  $('#pencere').textContent = $('#pencere2').textContent = state.stats.pencereGun || 21;
  renderLead();
  renderRegions();

  // bölge çipleri
  const regions = Object.keys(RC).filter((r) => state.sources.some((s) => s.bolge === r));
  const chips = ['', ...regions].map((r) => `<button class="chip" data-r="${esc(r)}" aria-pressed="${r === '' ? 'true' : 'false'}" style="--c:${RC[r] || 'var(--ink-3)'}">${r ? `<span class="pin"></span>${esc(r)}` : 'Tümü'}<span class="muted mono">${r ? state.items.filter((i) => i.bolge === r).length : state.items.length}</span></button>`).join('');
  $('#bolgeChips').insertAdjacentHTML('afterbegin', chips);
  $('#bolgeChips').addEventListener('click', (e) => {
    const btn = e.target.closest('.chip'); if (!btn) return;
    state.region = btn.dataset.r; state.shown = PAGE;
    $('#bolgeChips').querySelectorAll('.chip').forEach((c) => c.setAttribute('aria-pressed', String(c === btn)));
    draw();
  });

  // seçimler
  $('#tema').innerHTML = '<option value="">Tüm temalar</option>' + state.themes.map((t) => `<option value="${esc(t.id)}">${esc(t.ad)}</option>`).join('');
  fillSelect($('#sbolge'), state.sources.map((s) => s.bolge), 'Tüm bölgeler');
  fillSelect($('#skategori'), state.sources.map((s) => s.kategori), 'Tüm kategoriler');
  fillSelect($('#ssiklik'), state.sources.map((s) => s.siklik), 'Tüm tarama sıklıkları');
  $('#gun').innerHTML = (index || []).slice().reverse().map((d) => `<option>${esc(d)}</option>`).join('');

  ['#q', '#tema', '#oncelik', '#tip', '#sirala'].forEach((s) => $(s).addEventListener('input', () => { state.shown = PAGE; draw(); }));
  ['#sq', '#sbolge', '#skategori', '#ssiklik', '#srss'].forEach((s) => $(s).addEventListener('input', drawSources));
  $('#gun').addEventListener('change', drawArchive);

  // sekmeler
  document.querySelectorAll('nav.tabs button').forEach((b) => b.addEventListener('click', () => {
    document.querySelectorAll('nav.tabs button').forEach((x) => x.setAttribute('aria-selected', String(x === b)));
    ['gundem', 'kaynaklar', 'arsiv', 'hakkinda'].forEach((v) => { $('#view-' + v).hidden = v !== b.dataset.view; });
    if (b.dataset.view === 'kaynaklar') drawSources();
    if (b.dataset.view === 'arsiv') drawArchive();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }));

  const params = new URLSearchParams(location.search);
  if (params.get('q')) $('#q').value = params.get('q');
  const hash = location.hash.replace('#', '');
  if (['kaynaklar', 'arsiv', 'hakkinda'].includes(hash)) {
    const tab = document.querySelector(`nav.tabs button[data-view="${hash}"]`);
    if (tab) tab.click();
  }

  draw();
})();
