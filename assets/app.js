/* BHM Gündem Takip — statik arayüz (bağımlılıksız) */
const RC = { 'Türkiye': 'var(--tr)', 'Belçika': 'var(--be)', 'Avrupa': 'var(--eu)', 'Dünya': 'var(--dn)', 'Kurumsal': 'var(--kr)' };
const PAGE = 60;
const SURUM = 'sürüm 5 · dosya düzeni';   // arayüz sürümü: eski kopyayı ayırt etmek için
const $ = (s, r = document) => r.querySelector(s);
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const slug = (s) => String(s).toLowerCase().replace(/[çğıöşü]/g, (c) => ({ ç: 'c', ğ: 'g', ı: 'i', ö: 'o', ş: 's', ü: 'u' }[c]));

const ic = (it) => !it.k ? `${it.url}" target="_blank" rel="noopener noreferrer`
  : window.__VERI__ ? `#k=${encodeURIComponent(it.k)}`
  : `haber.html?k=${encodeURIComponent(it.k)}`;

const state = { items: [], sources: [], feeds: {}, themes: [], stats: {}, shown: PAGE,
  region: '', lead: new Set(), kumeler: {}, health: {}, dosya: {}, sonZiyaret: 0, yeni: 0 };

/* --------------------------------------------------- tarayıcıda saklananlar */
const LS = {
  get(key, fallback) {
    try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch (e) { return fallback; }
  },
  set(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) { /* özel pencere */ }
  },
};

function dosyaKaydet(it, on) {
  if (on) {
    state.dosya[it.k] = { k: it.k, baslik: it.baslik, kaynak: it.kaynak, url: it.url,
      tarih: it.tarih, bolge: it.bolge, kategori: it.kategori, eklendi: new Date().toISOString() };
  } else {
    delete state.dosya[it.k];
  }
  LS.set('bhm.dosya', state.dosya);
  const n = Object.keys(state.dosya).length;
  const tab = document.querySelector('nav.tabs button[data-view="dosyam"]');
  if (tab) tab.textContent = n ? `Dosyam (${n})` : 'Dosyam';
  document.querySelectorAll(`.yildiz[data-k="${it.k}"]`).forEach((b) => {
    b.setAttribute('aria-pressed', String(!!state.dosya[it.k]));
    b.textContent = state.dosya[it.k] ? '★' : '☆';
  });
  if (!$('#view-dosyam').hidden) drawDosyam();
}

function yildiz(it, dugme) {
  const on = !!state.dosya[it.k];
  if (dugme) {
    return `<button class="btn yildiz yildiz-btn" data-k="${esc(it.k)}" aria-pressed="${on}"
      title="${on ? 'Dosyamdan çıkar' : 'Dosyama ekle'}">${on ? '★ Dosyamda' : '☆ Dosyama ekle'}</button>`;
  }
  return `<button class="yildiz" data-k="${esc(it.k)}" aria-pressed="${on}"
    title="${on ? 'Dosyamdan çıkar' : 'Dosyama ekle'}">${on ? '★' : '☆'}</button>`;
}

function indir(name, text, type) {
  const blob = new Blob([text], { type: `${type};charset=utf-8` });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 4000);
}

const dayFmt = new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'long', year: 'numeric', weekday: 'long' });
const timeFmt = new Intl.DateTimeFormat('tr-TR', { hour: '2-digit', minute: '2-digit' });
const fullFmt = new Intl.DateTimeFormat('tr-TR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });

async function getJSON(path, fallback) {
  if (window.__VERI__) return window.__VERI__[path] ?? fallback;   // paket kipi
  try {
    const r = await fetch(path + '?t=' + Date.now(), { cache: 'no-store' });
    if (!r.ok) throw new Error(r.status);
    return await r.json();
  } catch (e) { return fallback; }
}

/* ---------------------------------------------------------------- kartlar */
/* Görsel yüklenemezse: önce kaynağın sunucusu, o da olmazsa kaynak amblemi.
   Böylece ızgarada boş sütun kalmaz. */
window.gorselHata = function (img) {
  if (img.dataset.remote && img.src !== img.dataset.remote) { img.src = img.dataset.remote; return; }
  const box = img.closest('.gorsel, .manset-img');
  if (box) {
    box.classList.add('plaka');
    box.innerHTML = `<span>${img.dataset.plaka || '·'}</span>`;
    return;
  }
  img.closest('figure')?.remove();
};

function imgTag(it) {
  const local = it.yerel ? esc(it.yerel) : '';
  const remote = it.gorsel ? esc(it.gorsel) : '';
  return `<img src="${local || remote}" alt="" loading="lazy" data-remote="${remote}"
    data-plaka="${esc(bashafler(it.kaynak))}" onerror="window.gorselHata(this)">`;
}

/* Kaynak amblemi: adın baş harfleri, bölge renginde. Görseli olmayan
   kayıtlarda ızgaranın ritmi korunur ve kaynak uzaktan tanınır. */
function bashafler(ad) {
  const atla = new Set(['the', 'for', 'and', 'of', 'de', 'la', 'le', 'van', 'von', 've']);
  const sozler = String(ad).split(/[\s\-—–·/(),.]+/)
    .filter((w) => w && !atla.has(w.toLocaleLowerCase('tr')));
  const harfler = sozler.slice(0, 2).map((w) => w[0]).join('');
  return (harfler || String(ad).slice(0, 2)).toLocaleUpperCase('tr');
}

function gorselAlani(it, cls = 'gorsel') {
  if (it.gorsel || it.yerel) return `<div class="${cls}">${imgTag(it)}</div>`;
  return `<div class="${cls} plaka" aria-hidden="true"><span>${esc(bashafler(it.kaynak))}</span></div>`;
}

function card(it) {
  const pr = slug(it.oncelik || '');
  const prCls = pr === 'kritik' ? 'kritik' : pr === 'yuksek' ? 'yuksek' : '';
  const d = new Date(it.tarih);
  return `<article class="card" style="--c:${RC[it.bolge] || 'var(--petrol)'}">
    <a class="gorsel-bag" href="${ic(it)}" tabindex="-1" aria-hidden="true">${gorselAlani(it)}</a>
    <div class="govde">
    <div class="meta">
      <span class="src">${esc(it.kaynak)}</span>
      <span>${esc(it.bolge)}${it.kategori ? ' · ' + esc(it.kategori) : ''}</span>
      ${prCls ? `<span class="tag ${prCls}">${esc(it.oncelik.toLocaleLowerCase('tr'))}</span>` : ''}
      ${it.kanit && it.kanit.startsWith('Birincil') ? '<span class="tag birincil">birincil</span>' : ''}
      ${it.tip === 'arama' ? '<span class="tag arama" title="Kaynağın RSS yayını yok; alan adına kilitli haber aramasıyla bulundu">arama</span>' : ''}
      ${it.tam ? '<span class="tag" title="Tam metin yerel olarak indirildi">tam metin</span>' : ''}
      <span class="mono muted">${isNaN(d) ? '' : timeFmt.format(d)}${it.tahmini ? ' · tarih tahmini' : ''}</span>
      ${yeniMi(it) ? '<span class="tag yeni">yeni</span>' : ''}
    </div>
    <h3><a href="${ic(it)}">${esc(it.baslik)}</a></h3>
    ${it.ozet ? `<p>${esc(it.ozet)}</p>` : ''}
    ${(it.ek || []).length ? `<p class="ayrica"><span>aynı gelişme</span> ${it.ek.map((x) =>
      `<a href="${ic(x)}">${esc(x.kaynak)}</a>`).join('<i>·</i>')}</p>` : ''}
    ${(it.terimler || []).length ? `<div class="terms">${it.terimler.map((t) => `<b>${esc(t)}</b>`).join('')}</div>` : ''}
    <div class="eylemler">
      <a class="btn ana" href="${ic(it)}">Kaydı aç</a>
      <a class="btn" href="${esc(it.url)}" target="_blank" rel="noopener noreferrer">Kaynakta oku ↗</a>
      ${yildiz(it, true)}
    </div>
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
    ${(it.gorsel || it.yerel) ? `<a class="manset-img" href="${ic(it)}" style="--c:${RC[it.bolge] || 'var(--accent-2)'}">${imgTag(it)}</a>` : ''}
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
        ${state.yeni ? `<div><b>${state.yeni}</b><span>son ziyaretinden beri</span></div>` : ''}
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
      .slice().sort((a, b) => b.puan - a.puan).slice(0, 4);
    if (!rows.length) return '';
    const [first, ...rest] = rows;
    const meta = (it, compact) => `<div class="meta"><span class="src">${esc(it.kaynak)}</span>
      ${!compact && it.kategori ? `<span>${esc(it.kategori)}</span>` : ''}
      ${it.oncelik === 'Kritik' ? '<span class="tag kritik">kritik</span>' : ''}
      <span class="mono">${dayShort(it.tarih)}</span></div>`;
    return `<section class="bolge" style="--c:${RC[r]}">
      <div class="rule-head"><h3>${esc(r)}</h3>
        <span class="mono">${state.items.filter((i) => i.bolge === r).length} kayıt</span>
        <button class="link" data-region="${esc(r)}">bölgenin tamamı →</button></div>
      <div class="bolge-lead">
        <a class="gorsel-bag" href="${ic(first)}" tabindex="-1" aria-hidden="true">${gorselAlani(first, 'gorsel buyuk')}</a>
        <div class="govde">${meta(first)}
          <h3><a href="${ic(first)}">${esc(first.baslik)}</a></h3>
          ${first.ozet ? `<p>${esc(first.ozet.slice(0, 190))}${first.ozet.length > 190 ? '…' : ''}</p>` : ''}
        </div>
      </div>
      <div class="bolge-rest">${rest.map((it) => `<article class="card kucuk" style="--c:${RC[r]}">
        <a class="gorsel-bag" href="${ic(it)}" tabindex="-1" aria-hidden="true">${gorselAlani(it, 'gorsel kucuk')}</a>
        <div class="govde">${meta(it, true)}
          <h3><a href="${ic(it)}">${esc(it.baslik)}</a></h3>
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

  // aynı gelişmeyi veren kayıtları tek satırda topla
  const seen = new Map();
  const out = [];
  rows.forEach((it) => {
    if (it.kume == null) { out.push(it); return; }
    const first = seen.get(it.kume);
    if (!first) { const copy = { ...it, ek: [] }; seen.set(it.kume, copy); out.push(copy); }
    else if (first.ek.length < 5) first.ek.push(it);
  });
  return out;
}

const yeniMi = (it) => state.sonZiyaret && new Date(it.tarih).getTime() > state.sonZiyaret;

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
    ['doğrulanan gelişme', s.kume ?? 0, 'birden çok kaynakta'],
    ['izleme sorunu', state.sources.reduce((n, x) => {
      const sg = saglik(x); return n + (sg && sg.tip !== 'iyi' ? 1 : 0); }, 0), 'sessiz ya da hatalı kaynak'],
    ['bölge dağılımı', Object.keys(s.bolge || {}).length, Object.entries(s.bolge || {}).map(([k, v]) => `${k} ${v}`).join(' · ') || '—'],
  ];
  return t.map(([label, value, sub]) => `<div class="stat"><span>${esc(label)}</span><b>${esc(value)}</b><i>${esc(sub)}</i></div>`).join('');
}

/* ------------------------------------------------------------- kaynaklar */
function feedOf(src) {
  for (const u of src.links || []) { const f = state.feeds[u]; if (f && f.feed) return f.feed; }
  return null;
}

const GUN = 864e5;
const BEKLENEN = { 'Günlük': 4, 'Haftalık': 14, 'Aylık': 45, 'Dönemsel': 120, 'Yıllık': 400 };

function saglik(src) {
  const h = state.health[String(src.id)];
  if (!h) return null;
  if (h.hata) return { tip: 'hata', metin: `akış hatası: ${h.hata}` };
  if (!h.sonKayit) return null;
  const gun = Math.floor((Date.now() - new Date(h.sonKayit).getTime()) / GUN);
  const sinir = BEKLENEN[src.siklik] || 30;
  if (gun > sinir) return { tip: 'sessiz', metin: `${gun} gündür kayıt yok` };
  return { tip: 'iyi', metin: gun < 1 ? 'bugün kayıt geldi' : `${gun} gün önce` };
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
    if (r === 'sorun') { const sg = saglik(x); if (!sg || sg.tip === 'iyi') return false; }
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
      ${(() => { const sg = saglik(x); return sg ? `<p class="saglik ${sg.tip}">${esc(sg.metin)}</p>` : ''; })()}
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

/* ---------------------------------------------------------------- dosyam */
function drawDosyam() {
  const rows = Object.values(state.dosya).sort((a, b) => (a.tarih < b.tarih ? 1 : -1));
  $('#dcount').textContent = `${rows.length} kayıt`;
  if (!rows.length) {
    $('#dosyaListe').innerHTML = `<div class="empty">Dosyan boş. Akıştaki kayıtların
      sağındaki ☆ işaretine basarak buraya ekleyebilirsin; kayıtlar bu tarayıcıda saklanır.</div>`;
    return;
  }
  $('#dosyaListe').innerHTML = `<div class="list">${rows.map((it) => `<article class="card">
    <div class="govde"><div class="meta">
      <span class="src" style="--c:${RC[it.bolge] || 'var(--petrol)'}">${esc(it.kaynak)}</span>
      <span>${esc(it.bolge)}${it.kategori ? ' · ' + esc(it.kategori) : ''}</span>
      <span class="mono">${fullFmt.format(new Date(it.tarih))}</span>
      ${yildiz(it)}</div>
      <h3><a href="${it.k ? `haber.html?k=${encodeURIComponent(it.k)}` : esc(it.url)}">${esc(it.baslik)}</a></h3>
      <p class="kaynak-baglanti"><a href="${esc(it.url)}" target="_blank" rel="noopener noreferrer">${esc(it.url)}</a></p>
    </div></article>`).join('')}</div>`;
}

function dosyaMetni(bicim) {
  const rows = Object.values(state.dosya).sort((a, b) => (a.tarih < b.tarih ? 1 : -1));
  const gun = new Date().toLocaleDateString('tr-TR');
  if (bicim === 'csv') {
    const q = (v) => `"${String(v ?? '').replace(/"/g, '""')}"`;
    return ['tarih,bolge,kategori,kaynak,baslik,url',
      ...rows.map((r) => [r.tarih, r.bolge, r.kategori, r.kaynak, r.baslik, r.url].map(q).join(','))].join('\n');
  }
  return [`# Gündem Takip — dosya (${gun})`, '',
    ...rows.map((r) => `- **${r.baslik}**  \n  ${r.kaynak} · ${r.bolge}${r.kategori ? ' · ' + r.kategori : ''} · ${new Date(r.tarih).toLocaleString('tr-TR')}  \n  ${r.url}`),
    '', `_${rows.length} kayıt · Brüksel Hukuk Merkezi Gündem Takip_`].join('\n');
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
  const [latest, meta, feeds, index, health, surum] = await Promise.all([
    getJSON('data/latest.json', { haberler: [], istatistik: {}, olusturma: null }),
    getJSON('data/sources.json', { sources: [], themes: [] }),
    getJSON('data/feeds.json', {}),
    getJSON('data/archive-index.json', []),
    getJSON('data/health.json', {}),
    getJSON('data/surum.json', null),
  ]);
  state.items = latest.haberler || [];
  state.stats = latest.istatistik || {};
  state.sources = meta.sources || [];
  state.themes = meta.themes || [];
  state.feeds = feeds || {};
  state.kumeler = latest.kumeler || {};
  state.health = health || {};
  state.dosya = LS.get('bhm.dosya', {}) || {};

  // son ziyaretten beri gelen kayıtlar
  state.sonZiyaret = LS.get('bhm.sonZiyaret', 0) || 0;
  state.yeni = state.sonZiyaret
    ? state.items.filter((i) => new Date(i.tarih).getTime() > state.sonZiyaret).length : 0;
  LS.set('bhm.sonZiyaret', Date.now());

  const dn = Object.keys(state.dosya).length;
  const dtab = document.querySelector('nav.tabs button[data-view="dosyam"]');
  if (dtab && dn) dtab.textContent = `Dosyam (${dn})`;

  // durum
  const ts = latest.olusturma ? new Date(latest.olusturma) : null;
  const hrs = ts ? (Date.now() - ts.getTime()) / 36e5 : 999;
  $('#statusText').textContent = ts ? `son tarama ${fullFmt.format(ts)}` : 'tarama verisi yok';
  if (hrs > 8) $('.dot').classList.add('stale');
  $('#footTime').textContent = ts ? fullFmt.format(ts) : '—';
  $('#footSrc').textContent = state.stats.kaynak ?? state.sources.length;
  $('#footFeed').textContent = state.stats.akisVeriVeren ?? 0;
  if (surum && surum.damga) {
    const el = $('#footSurum');
    if (el) el.textContent = ` · paket ${surum.damga}`;
    const ust = $('#statusPaket');
    if (ust) ust.textContent = `paket ${surum.damga}`;
  }
  const s3 = $('#statusSurum');
  if (s3) s3.textContent = SURUM;
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

  // dosyama ekle / çıkar
  document.addEventListener('click', (e) => {
    const btn = e.target.closest('.yildiz');
    if (!btn) return;
    e.preventDefault();
    const key = btn.dataset.k;
    const it = state.items.find((x) => x.k === key) || state.dosya[key];
    if (it) dosyaKaydet(it, !state.dosya[key]);
  });
  $('#dMd').addEventListener('click', () => indir(
    `bhm-dosya-${new Date().toISOString().slice(0, 10)}.md`, dosyaMetni('md'), 'text/markdown'));
  $('#dCsv').addEventListener('click', () => indir(
    `bhm-dosya-${new Date().toISOString().slice(0, 10)}.csv`, dosyaMetni('csv'), 'text/csv'));
  $('#dTemizle').addEventListener('click', () => {
    if (!confirm('Dosyadaki tüm kayıtlar silinsin mi?')) return;
    state.dosya = {};
    LS.set('bhm.dosya', state.dosya);
    const tab = document.querySelector('nav.tabs button[data-view="dosyam"]');
    if (tab) tab.textContent = 'Dosyam';
    drawDosyam();
  });

  // sekmeler
  document.querySelectorAll('nav.tabs button').forEach((b) => b.addEventListener('click', () => {
    document.querySelectorAll('nav.tabs button').forEach((x) => x.setAttribute('aria-selected', String(x === b)));
    VIEWS.forEach((v) => { $('#view-' + v).hidden = v !== b.dataset.view; });
    $('#view-haber').hidden = true;
    if (location.hash.startsWith('#k=')) history.replaceState(null, '', location.pathname);
    if (b.dataset.view === 'kaynaklar') drawSources();
    if (b.dataset.view === 'arsiv') drawArchive();
    if (b.dataset.view === 'dosyam') drawDosyam();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }));

  // paket kipi: #k=<anahtar> ile kayıt sayfası aynı dosyada açılır
  const VIEWS = ['gundem', 'kaynaklar', 'arsiv', 'dosyam', 'hakkinda'];
  function route() {
    const m = location.hash.match(/^#k=(.+)$/);
    const box = $('#view-haber');
    VIEWS.forEach((v) => { $('#view-' + v).hidden = !!m || v !== 'gundem'; });
    box.hidden = !m;
    document.querySelectorAll('nav.tabs button').forEach((b) => b.setAttribute('aria-selected', String(!m && b.dataset.view === 'gundem')));
    if (m) {
      window.renderHaber(box, decodeURIComponent(m[1]));
      window.scrollTo({ top: 0 });
    } else {
      document.title = 'Gündem Takip — Brüksel Hukuk Merkezi';
    }
  }
  window.addEventListener('hashchange', route);

  const params = new URLSearchParams(location.search);
  if (params.get('q')) $('#q').value = params.get('q');
  const hash = location.hash.replace('#', '');
  if (['kaynaklar', 'arsiv', 'hakkinda'].includes(hash)) {
    const tab = document.querySelector(`nav.tabs button[data-view="${hash}"]`);
    if (tab) tab.click();
  }

  draw();
  if (location.hash.startsWith('#k=')) route();
})();
