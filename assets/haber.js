/* Gündem Takip — tek kayıt (haber) sayfası */
const RC = { 'Türkiye': 'var(--tr)', 'Belçika': 'var(--be)', 'Avrupa': 'var(--eu)', 'Dünya': 'var(--dn)', 'Kurumsal': 'var(--kr)' };
const $ = (s, r = document) => r.querySelector(s);
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fullFmt = new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit' });
const dayFmt = new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'short' });

async function getJSON(path, fallback) {
  try {
    const r = await fetch(path + '?t=' + Date.now(), { cache: 'no-store' });
    if (!r.ok) throw new Error(r.status);
    return await r.json();
  } catch (e) { return fallback; }
}

function picture(it) {
  if (!it.gorsel) return '';
  return `<figure class="hero-img"><img src="${esc(it.gorsel)}" alt="" loading="lazy"
    onerror="this.closest('figure').remove()">
    <figcaption>Görsel: ${esc(it.kaynak)} yayınından</figcaption></figure>`;
}

function relatedCard(it) {
  return `<a class="ikincil" style="--c:${RC[it.bolge] || 'var(--petrol)'}" href="haber.html?k=${esc(it.k)}">
    <span class="eyebrow"><span class="pin"></span>${esc(it.bolge)}<span class="sep">/</span>${esc(dayFmt.format(new Date(it.tarih)))}</span>
    <b>${esc(it.baslik)}</b><span class="src">${esc(it.kaynak)}</span></a>`;
}

(async function init() {
  const key = new URLSearchParams(location.search).get('k');
  const [latest, meta] = await Promise.all([
    getJSON('data/latest.json', { haberler: [] }),
    getJSON('data/sources.json', { sources: [] }),
  ]);
  const items = latest.haberler || [];
  const it = items.find((x) => x.k === key);

  if (!it) {
    $('#haber').innerHTML = `<div class="empty">Bu kayıt güncel tarama penceresinde bulunamadı.
      Kayıtlar son ${latest.istatistik ? latest.istatistik.pencereGun : 21} günü kapsar; daha eskisi için
      <a href="index.html">arşive</a> bakabilirsin.</div>`;
    return;
  }

  const src = (meta.sources || []).find((s) => s.id === it.id) || {};
  const d = new Date(it.tarih);
  document.title = `${it.baslik} — Gündem Takip`;
  $('#statusText').textContent = `${it.kaynak} · ${isNaN(d) ? '' : dayFmt.format(d)}`;

  const sameSource = items.filter((x) => x.id === it.id && x.k !== it.k).slice(0, 3);
  const sameTerm = items.filter((x) => x.k !== it.k && x.id !== it.id
    && (x.terimler || []).some((t) => (it.terimler || []).includes(t))).slice(0, 3);

  $('#haber').innerHTML = `
  <article class="yazi" style="--c:${RC[it.bolge] || 'var(--petrol)'}">
    <div class="eyebrow"><span class="pin"></span>${esc(it.bolge)}${it.kategori ? `<span class="sep">/</span>${esc(it.kategori)}` : ''}</div>
    <h1>${esc(it.baslik)}</h1>
    <div class="kunye">
      <b>${esc(it.kaynak)}</b>
      ${it.kanit ? `<span class="tag${it.kanit.startsWith('Birincil') ? ' birincil' : ''}">${esc(it.kanit)}</span>` : ''}
      ${it.oncelik ? `<span class="tag ${it.oncelik === 'Kritik' ? 'kritik' : it.oncelik === 'Yüksek' ? 'yuksek' : ''}">${esc(it.oncelik)} öncelik</span>` : ''}
      ${it.tip === 'arama' ? '<span class="tag arama">haber aramasıyla bulundu</span>' : '<span class="tag">RSS akışı</span>'}
      <span class="mono">${isNaN(d) ? '' : fullFmt.format(d)}${it.tahmini ? ' · tarih tahmini' : ''}</span>
    </div>
    ${picture(it)}
    ${it.ozet ? `<p class="ozet-metin">${esc(it.ozet)}</p>` : ''}
    <p class="kaynak-not">Yukarıdaki başlık ve özet kaynağın kendi yayınından alınmıştır. Metnin tamamı, belge ve doğrulama kaynaktadır.</p>
    <a class="git" href="${esc(it.url)}" target="_blank" rel="noopener noreferrer">Kaynakta oku ↗</a>

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

    ${sameSource.length ? `<section class="ilgili"><h3>Aynı kaynaktan</h3>
      <div class="lead-second" style="border:0;margin:0;padding:0">${sameSource.map(relatedCard).join('')}</div></section>` : ''}
    ${sameTerm.length ? `<section class="ilgili"><h3>Aynı konuda diğer kaynaklar</h3>
      <div class="lead-second" style="border:0;margin:0;padding:0">${sameTerm.map(relatedCard).join('')}</div></section>` : ''}
  </article>`;
})();
