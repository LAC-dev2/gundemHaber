/* Gündem Takip — tek kayıt (haber) görünümü.
   Hem haber.html sayfası hem de tek dosyalık paket bunu kullanır. */
(function () {
const RC = { 'Türkiye': 'var(--tr)', 'Belçika': 'var(--be)', 'Avrupa': 'var(--eu)', 'Dünya': 'var(--dn)', 'Kurumsal': 'var(--kr)' };
const $ = (s, r = document) => r.querySelector(s);
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fullFmt = new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit' });
const dayFmt = new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'short' });

async function getJSON(path, fallback) {
  if (window.__VERI__) return window.__VERI__[path] ?? fallback;   // paket kipi
  try {
    const r = await fetch(path + '?t=' + Date.now(), { cache: 'no-store' });
    if (!r.ok) throw new Error(r.status);
    return await r.json();
  } catch (e) { return fallback; }
}

window.gorselHata = window.gorselHata || function (img) {
  if (img.dataset.remote && img.src !== img.dataset.remote) { img.src = img.dataset.remote; return; }
  img.closest('figure')?.remove();
};

function imgTag(it, extra = '') {
  // yerel aynayı dene, yoksa kaynağın sunucusuna düş, o da olmazsa kaldır
  const local = it.yerel ? esc(it.yerel) : '';
  const remote = it.gorsel ? esc(it.gorsel) : '';
  return `<img src="${local || remote}" alt="" loading="lazy" ${extra}
    data-remote="${remote}" onerror="window.gorselHata(this)">`;
}

function picture(it) {
  if (!it.gorsel && !it.yerel) return '';
  return `<figure class="hero-img">${imgTag(it)}
    <figcaption>Görsel: ${esc(it.kaynak)} yayınından</figcaption></figure>`;
}

function fullText(page) {
  if (!page) return '';
  const body = page.paragraflar.map((x) => x.startsWith('## ')
    ? `<h3>${esc(x.slice(3))}</h3>` : `<p>${esc(x)}</p>`).join('');
  const min = Math.max(1, Math.round(page.kelime / 190));
  return `<div class="tam-metin">
    <div class="tam-head"><span class="tag">tam metin</span>
      <span class="mono">${page.kelime.toLocaleString('tr-TR')} kelime · ~${min} dk okuma</span></div>
    ${body}</div>`;
}

/* dosyam: ana sayfayla aynı yerde saklanır, her yazmada yeniden okunur */
function dosyaOku() {
  try { return JSON.parse(localStorage.getItem('bhm.dosya')) || {}; } catch (e) { return {}; }
}
function dosyaCevir(it) {
  const hepsi = dosyaOku();
  if (hepsi[it.k]) delete hepsi[it.k];
  else hepsi[it.k] = { k: it.k, baslik: it.baslik, kaynak: it.kaynak, url: it.url,
    tarih: it.tarih, bolge: it.bolge, kategori: it.kategori, eklendi: new Date().toISOString() };
  try { localStorage.setItem('bhm.dosya', JSON.stringify(hepsi)); } catch (e) { /* özel pencere */ }
  return !!hepsi[it.k];
}

const haberLink = (k) => window.__VERI__ ? `#k=${encodeURIComponent(k)}`
  : `haber.html?k=${encodeURIComponent(k)}`;

function relatedCard(it) {
  return `<a class="ikincil" style="--c:${RC[it.bolge] || 'var(--petrol)'}" href="${haberLink(it.k)}">
    <span class="eyebrow"><span class="pin"></span>${esc(it.bolge)}<span class="sep">/</span>${esc(dayFmt.format(new Date(it.tarih)))}</span>
    <b>${esc(it.baslik)}</b><span class="src">${esc(it.kaynak)}</span></a>`;
}

async function renderHaber(box, key) {
  const [latest, meta, page] = await Promise.all([
    getJSON('data/latest.json', { haberler: [] }),
    getJSON('data/sources.json', { sources: [] }),
    key ? getJSON(`data/pages/${encodeURIComponent(key)}.json`, null) : null,
  ]);
  const items = latest.haberler || [];
  const it = items.find((x) => x.k === key);

  if (!it) {
    box.innerHTML = `<div class="empty">Bu kayıt güncel tarama penceresinde bulunamadı.
      Kayıtlar son ${latest.istatistik ? latest.istatistik.pencereGun : 21} günü kapsar; daha eskisi için
      <a href="index.html">arşive</a> bakabilirsin.</div>`;
    return;
  }

  const src = (meta.sources || []).find((s) => s.id === it.id) || {};
  const d = new Date(it.tarih);
  document.title = `${it.baslik} — Gündem Takip`;
  const st = $('#statusText');
  if (st) st.textContent = `${it.kaynak} · ${isNaN(d) ? '' : dayFmt.format(d)}`;

  const kume = it.kume != null
    ? items.filter((x) => x.kume === it.kume && x.k !== it.k) : [];
  const kumeKeys = new Set(kume.map((x) => x.k));
  const sameSource = items.filter((x) => x.id === it.id && x.k !== it.k && !kumeKeys.has(x.k)).slice(0, 3);
  const sameTerm = items.filter((x) => x.k !== it.k && x.id !== it.id && !kumeKeys.has(x.k)
    && (x.terimler || []).some((t) => (it.terimler || []).includes(t))).slice(0, 3);

  box.innerHTML = `
  <article class="yazi" style="--c:${RC[it.bolge] || 'var(--petrol)'}">
    <div class="eyebrow"><span class="pin"></span>${esc(it.bolge)}${it.kategori ? `<span class="sep">/</span>${esc(it.kategori)}` : ''}</div>
    <h1>${esc(it.baslik)}</h1>
    <div class="kunye">
      <b>${esc(it.kaynak)}</b>
      ${it.kanit ? `<span class="tag${it.kanit.startsWith('Birincil') ? ' birincil' : ''}">${esc(it.kanit)}</span>` : ''}
      ${it.oncelik ? `<span class="tag ${it.oncelik === 'Kritik' ? 'kritik' : it.oncelik === 'Yüksek' ? 'yuksek' : ''}">${esc(it.oncelik)} öncelik</span>` : ''}
      ${it.tip === 'arama' ? '<span class="tag arama">haber aramasıyla bulundu</span>' : '<span class="tag">RSS akışı</span>'}
      ${it.tam ? '<span class="tag birincil">tam metin indirildi</span>' : ''}
      <span class="mono">${isNaN(d) ? '' : fullFmt.format(d)}${it.tahmini ? ' · tarih tahmini' : ''}</span>
    </div>
    ${picture(it)}
    ${!page && it.ozet ? `<p class="ozet-metin">${esc(it.ozet)}</p>` : ''}
    ${fullText(page)}
    <p class="kaynak-not">${page
      ? 'Metin, yerel tarama sırasında kaynağın sayfasından alınmıştır. Belge ve doğrulama için kaynağa bakılmalıdır.'
      : 'Başlık ve özet kaynağın kendi yayınından alınmıştır. Metnin tamamı, belge ve doğrulama kaynaktadır.'}</p>
    <div class="eylem">
      <a class="git" href="${esc(it.url)}" target="_blank" rel="noopener noreferrer">Kaynakta oku ↗</a>
      <button class="git ikincil-buton" id="dosyaEkle" aria-pressed="${!!dosyaOku()[it.k]}">
        ${dosyaOku()[it.k] ? '★ Dosyamda' : '☆ Dosyama ekle'}</button>
    </div>

    ${(it.terimler || []).length ? `<div class="terms yazi-terms">${it.terimler.map((t) => `<a href="index.html?q=${encodeURIComponent(t)}"><b>${esc(t)}</b></a>`).join('')}</div>` : ''}

    ${src.neden ? `<section class="neden"><h3>Bu kaynak neden izleniyor?</h3>
      <p>${esc(src.neden)}</p>
      <dl>
        ${src.tur ? `<div><dt>Kaynak türü</dt><dd>${esc(src.tur)}</dd></div>` : ''}
        ${src.siklik ? `<div><dt>Tarama sıklığı</dt><dd>${esc(src.siklik)}</dd></div>` : ''}
        ${src.anahtar ? `<div><dt>Anahtar terimler</dt><dd>${esc(src.anahtar)}</dd></div>` : ''}
      </dl>
      ${(src.links || []).length ? `<div class="links">${src.links.slice(0, 3).map((u, i) => `<a href="${esc(u)}" target="_blank" rel="noopener noreferrer">kaynak adresi ${i + 1} ↗</a>`).join('')}</div>` : ''}
    </section>` : ''}

    ${kume.length ? `<section class="ilgili dogrulama"><h3>Bu gelişmeyi veren diğer kaynaklar
      <span class="mono">${kume.length + 1} kaynak</span></h3>
      <div class="lead-second" style="border:0;margin:0;padding:0">${kume.slice(0, 4).map(relatedCard).join('')}</div>
      <p class="ozet-not">Başlıklar benzerliğe göre eşleştirilmiştir; aynı olayın farklı
        kaynaklardaki anlatımını karşılaştırmak için kullanılır.</p></section>` : ''}
    ${sameSource.length ? `<section class="ilgili"><h3>Aynı kaynaktan</h3>
      <div class="lead-second" style="border:0;margin:0;padding:0">${sameSource.map(relatedCard).join('')}</div></section>` : ''}
    ${sameTerm.length ? `<section class="ilgili"><h3>Aynı konuda diğer kaynaklar</h3>
      <div class="lead-second" style="border:0;margin:0;padding:0">${sameTerm.map(relatedCard).join('')}</div></section>` : ''}
  </article>`;

  const ekle = box.querySelector('#dosyaEkle');
  if (ekle) ekle.addEventListener('click', () => {
    const on = dosyaCevir(it);
    ekle.setAttribute('aria-pressed', String(on));
    ekle.textContent = on ? '★ Dosyamda' : '☆ Dosyama ekle';
  });
}

window.renderHaber = renderHaber;

// Kendi sayfası (haber.html) olarak açıldıysa doğrudan çiz
const own = document.getElementById('haber');
if (own) renderHaber(own, new URLSearchParams(location.search).get('k'));
})();
