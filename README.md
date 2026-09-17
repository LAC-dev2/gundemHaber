# Gündem Takip — Brüksel Hukuk Merkezi

BHM'nin izleme envanterindeki **350 hukuki kaynağı** otomatik tarayan, günlük
gelişmeleri tek bir sayfada toplayan statik site.

* Sunucu, veritabanı veya ücretli servis gerektirmez.
* Tarama GitHub Actions üzerinde günde üç kez çalışır; sonuçlar JSON olarak
  depoya yazılır, site bu dosyaları okur.
* Kaynak envanteri, tema tanımları ve uyarı terimleri BHM "Kaynak İzleme
  Merkezi" dosyasından içe aktarılır.

## Dosya düzeni

```
index.html                  yayın sayfası (manşet + günün özeti + bölge blokları,
                            ardından tüm gelişmeler) ve Kaynaklar / Arşiv / Nasıl çalışır
haber.html                  tek kayıt sayfası (?k=<anahtar>): künye, görsel, özet,
                            kaynağa bağlantı, "bu kaynak neden izleniyor", ilgili kayıtlar
assets/haber.js             haber sayfasının görünümü
assets/style.css            BHM görsel kimliğiyle uyumlu stil
assets/app.js               filtreler, akış ve arşiv görünümü
scripts/import_sources.py   BHM HTML dosyasından kaynak envanterini aktarır
scripts/collect.py          RSS/Atom keşfi + tarama + puanlama
data/sources.json           350 kaynak, temalar, sosyal hesaplar, uyarı terimleri
data/feeds.json             keşfedilen akış adresleri (önbellek)
data/images.json            sayfa görselleri (og:image) için önbellek
data/latest.json            son 21 günün gelişmeleri + istatistikler
data/archive/YYYY-AA-GG.json  günlük arşiv kayıtları
.github/workflows/tarama.yml  zamanlanmış tarama ve Pages yayını
scripts/serve.py            yerel uygulama (tara + sun + tarayıcıda aç)
scripts/extract.py          haber sayfasından okunabilir tam metin çıkarma
scripts/paketle.py          paylaşım paketleri (tek dosyalık HTML, zip)
scripts/ikon.py             uygulama ikonları (PNG/SVG üretici)
scripts/analiz.py           günlük analiz üretimi (Claude API)
scripts/ceviri.py           Türkçe olmayan kayıtların başlık/özet çevirisi
scripts/kaynak_ekle.py      envantere yeni kaynak ekleme (form ve komut satırı)
scripts/tam_metin.py        analiz öncesi öne çıkan kayıtların tam metni
scripts/sentez.py           haftalık sentez üretimi (Claude API)
scripts/birincil.py         AİHM karar metinleri (HUDOC) ve Resmî Gazete
scripts/uyari.py            eşik aşıldığında uyarı (API kullanmaz)
data/takip.json             açık takip maddeleri ve seyri
data/sentez/                haftalık sentezler
data/birincil-latest.json   indirilen birincil belgelerin listesi
data/uyari-son.json         güncel eşik uyarıları
data/ceviri.json            çeviri önbelleği (her kayıt bir kez çevrilir)
data/analiz/YYYY-AA-GG.json günlük analiz kayıtları
Baslat.bat / .command / .sh çift tıklamayla çalıştırma
OKUBENI.md                  alıcıya verilecek kurulum anlatımı
manifest.webmanifest        "Ana Ekrana Ekle" için uygulama tanımı
```

## Yayın

Depo şu an **özel**. İki yayın yolu var ve ikisi erişim bakımından farklı:

### A) GitHub Pages — herkese açık

* Depo **genel (public)** yapılırsa ücretsiz çalışır. GitHub Pro ile özel
  depodan da yayınlanabilir, ama **site yine herkese açıktır**; siteye erişim
  denetimi yalnızca GitHub Enterprise Cloud'da var.
* Adres: `https://lac-dev2.github.io/gundemHaber/`
* Açılışı: **Settings → Pages → Build and deployment → Source: GitHub Actions**.
  Bunu depo yöneticisi yapar; iş akışının belirteci Pages'i kendisi açamıyor
  (`Resource not accessible by integration`). Ardından
  **Actions → Kaynak taraması → Run workflow**.
* Sonucu: kaynak envanteri, izleme gerekçeleri, uyarı terimleri ve toplanan
  metinler herkesin görebileceği hâle gelir.

### B) Cloudflare Pages + Access — girişle korumalı

* Depo **özel kalır**. Cloudflare Pages depoyu bağlar (derleme komutu yok,
  çıktı dizini kök), Cloudflare Access ücretsiz katmanda 50 kullanıcıya kadar
  e-posta doğrulamalı giriş koyar. Yani yalnızca izin verdiğin adresler görür.
* Tarama yine GitHub Actions'ta çalışır; her veri işlemesinde Cloudflare
  yeniden yayınlar.
* İzleme masasının kendi envanterini açmak istemiyorsan doğru yol budur.

Her iki durumda `robots.txt` ve `_headers` dosyaları arama motorlarına
"dizinleme" demez (`noindex, nofollow`) — ama bu erişim denetimi değildir,
yalnızca dizinlenmeyi engeller.

Depo ayarlarında gereken diğer şey **Settings → Actions → General → Workflow
permissions: Read and write** (tarama sonucunu depoya işlemek için) — bu
depoda zaten açık.

## Yerel uygulama (tek komut)

```bash
python3 scripts/serve.py
```

Bu komut: veri eskiyse kaynakları tarar, tam metinleri ve görselleri diske
indirir, siteyi `http://127.0.0.1:8000` adresinde sunar ve tarayıcıda açar.
Bağımlılık yoktur — yalnızca Python 3.9+ standart kütüphanesi.

```bash
python3 scripts/serve.py --every 30       # 30 dakikada bir yeniden tara
python3 scripts/serve.py --no-scan        # taramadan yalnızca sun
python3 scripts/serve.py --stale 0        # veri taze olsa da baştan tara
python3 scripts/serve.py --port 9000 --full 100 --mirror 200
```

Yerel kipte iki şey fazladan yapılır:

* **Tam metin** — `--full N` kadar kaydın sayfası indirilip okunabilir metne
  çevrilir (`data/pages/<anahtar>.json`). Haber sayfası özet yerine tam metni,
  kelime sayısını ve okuma süresini gösterir. Bir kez indirilen sayfa bir daha
  çekilmez.
* **Görsel aynası** — `--mirror N` kadar görsel `data/img/` altına indirilir;
  sayfa önce yerel kopyayı, yüklenemezse kaynağın sunucusunu dener. Böylece
  çevrimdışı da çalışır ve sıcak bağlantı engellerine takılmaz.

Bu iki dizin `.gitignore` içindedir: her makinede yeniden üretilir, depoyu
şişirmez. Yayın sürümü (GitHub Pages) yalnızca künye + özet gösterir.

Yalnızca taramayı çalıştırmak için:

```bash
python3 scripts/collect.py --discover 40 --full 40 --mirror 80
```

Kaynak envanteri güncellendiğinde:

```bash
python3 scripts/import_sources.py /yol/bhm-kaynak-izleme-merkezi.html
```

## Kendi alan adında yayınlamak

Site tamamen statiktir; herhangi bir statik barındırmaya konabilir.

**GitHub Pages + kendi alan adı** (en kısa yol, ek maliyet yok):

1. Depo köküne alan adını içeren tek satırlık bir `CNAME` dosyası ekle
   (örnek içerik: `gundem.brukselhukukmerkezi.com`).
2. Alan adı sağlayıcısında DNS kaydı:
   * Alt alan adı için (`gundem.` gibi): `CNAME` → `lac-dev2.github.io`
   * Kök alan adı için: `A` kayıtları → `185.199.108.153`, `185.199.109.153`,
     `185.199.110.153`, `185.199.111.153`
3. **Settings → Pages → Custom domain** alanına aynı adı yaz ve
   *Enforce HTTPS* işaretle (sertifika birkaç dakikada verilir).

**Cloudflare Pages** alternatifi: depoyu bağla, derleme komutu yok, çıktı
dizini kök (`/`). Tarama görevi yine GitHub Actions'ta çalışır; Cloudflare
her veri işlemesinde yeniden yayınlar.

Arama motorları ve paylaşım kartları için `index.html` içindeki
`<meta name="description">` ile başlığı kendi diline göre düzenleyebilirsin.

## Tarama mantığı

1. **Akış keşfi** — her kaynağın adresinde `link rel="alternate"` etiketi ve
   yaygın `/feed`, `/rss`, `/atom.xml` kalıpları denenir. Bulunan akışlar
   önbelleğe yazılır; 30 günde bir yeniden doğrulanır, bulunamayanlar 21 günde
   bir yeniden aranır. Google arama ve X bağlantıları keşfe dahil edilmez.
2. **Tarama** — akışlar paralel çekilir, son 21 günün öğeleri ayrıştırılır,
   bağlantıya göre tekilleştirilir. Bir akıştaki hata taramayı durdurmaz.
3. **Puanlama** — kaynak önceliği (Kritik/Yüksek/Orta/Düşük), birincil kanıt
   değeri, uyarı terimi eşleşmeleri ve tazelik puanlanır. "Önem sırası"
   sıralaması bu puanı kullanır.
4. **Yayın** — `data/latest.json` ve o güne ait arşiv dosyası güncellenir,
   değişiklik varsa işlenir ve Pages yeniden yayınlanır.

## Başkasıyla paylaşmak

Alıcının ne yapacağına göre üç yol var; ayrıntılı, alıcıya verilebilecek
anlatım `OKUBENI.md` içinde.

```bash
python3 scripts/paketle.py           # dist/gundem-takip-<tarih>.html  (tek dosya)
python3 scripts/paketle.py --zip     # dist/gundem-takip-<tarih>.zip   (çalıştırılabilir)
```

1. **Tek dosyalık HTML** — stil, betik, veri, tam metinler ve küçük görseller
   tek bir `.html` dosyasına gömülür. Çift tıkla açılır, kurulum ve internet
   gerektirmez, `#k=<anahtar>` ile kayıt sayfaları da aynı dosyada çalışır.
   iPhone/iPad için en kolay yol: Dosyalar'dan dokun, Safari'de açılır.
   Anlık kopyadır, kendini yenilemez.
2. **Çalıştırılabilir zip** — kod + güncel veri + başlatıcılar. macOS'ta
   **`Gündem Takip.app`** (Terminal penceresi açmadan çalışan sarmalayıcı;
   Python yoksa pencereyle söyler ve kurulum sayfasını açar), ayrıca
   `Baslat.command`; Windows'ta `Baslat.bat`, Linux'ta `baslat.sh`.
   `--tam` ile indirilmiş tam metinler ve görseller de pakete girer, alıcı
   ilk taramayı beklemeden dolu bir ekran görür. iOS'ta çalışmaz.
   macOS 15+ imzasız `.app`/`.command` dosyalarını her indirişte karantinaya
   alır ve "Apple could not verify…" ile engeller; alıcı klasörü bir kez
   `xattr -dr com.apple.quarantine <klasör>` ile karantinadan çıkarır ya da
   uygulamayı `python3 scripts/serve.py` ile başlatır (Terminal'den başlatılan
   betik Gatekeeper'a takılmaz). Bu engel her alıcıda çıkacağı için, yaygın
   paylaşım için yayın adresi (3. yol) daha uygundur.
   Paket adları saat damgalıdır (`gundem-takip-<tarih>-<saat>`) ve zip'in kök
   klasörü de damgalı: eski indirmeyle karışmaz, üzerine açılmaz. Arayüzün
   altlığında paketin saati yazar.
3. **Yayın adresi** — GitHub Pages; hiç kurulum gerekmez, telefonda da açılır,
   kendini günde üç kez günceller. `manifest.webmanifest` ve ikonlar eklendiği
   için Safari'de "Ana Ekrana Ekle" ile uygulama gibi durur.

## Veri çakışması

Zamanlanmış tarama da, yerel tarama da aynı veri dosyalarını yazar; ikisi
birbirinden habersiz çalıştığında `git pull` sırasında `data/latest.json` ve
günlük arşiv dosyasında çakışma çıkar. Bu dosyalar türetilmiştir, elle
birleştirilmez:

```bash
git checkout --theirs data/     # kendi taramanı koru
# ya da
git checkout --ours data/ && python3 scripts/collect.py   # uzaktakini al, yeniden tara
```

## Görseller ve haber sayfası

Her kayıt için site içinde bir sayfa üretilir: `haber.html?k=<anahtar>`. Anahtar,
kaydın bağlantısından türetilen kalıcı bir özettir; sayfa `data/latest.json`
içinden o kaydı bulup gösterir. Sayfada başlık, künye (kaynak, kanıt değeri,
öncelik, kaydın akıştan mı aramadan mı geldiği), kaynağın kendi özeti, birincil
kaynağa giden buton, envanterden gelen "bu kaynak neden izleniyor" bloğu ve
ilgili kayıtlar yer alır. Tam metin çoğaltılmaz; okuma kaynakta sürer.

Görseller üç kademede bulunur:

1. Akışın kendi görseli (`enclosure`, `media:content`, `media:thumbnail` veya
   özet içindeki ilk `img`) — ek istek gerektirmez.
2. Yoksa haber sayfasının `og:image` / `twitter:image` etiketi; sonuç
   `data/images.json` önbelleğine yazılır, aynı bağlantı bir daha çekilmez.
   Her turda en fazla `--images` kadar yeni kayıt için denenir (öntanımlı 90).
3. Logo, paylaşım kartı ve yer tutucu dosyaları (`logo`, `meta-facebook`,
   `placeholder`, `favicon`…) görsel sayılmaz.

Görseller kaynağın sunucusundan gösterilir (kopyalanmaz), altına kaynak adı
yazılır ve yüklenemezse kart tipografik hâline döner. Kaynak sıcak bağlantıya
kapalıysa görsel sessizce düşer, yerinde boşluk kalmaz.

## Kaynak ekleme

Siteden **Kaynaklar → + Kaynak ekle** düğmesi, GitHub'da bir form açar
(`.github/ISSUE_TEMPLATE/kaynak.yml`). Form gönderildiğinde `kaynak.yml` iş
akışı devreye girer: kaynağı `data/sources.json` içine ekler, sayfa başlığını
ve RSS/Atom akışını otomatik bulur, taramayı başlatır ve sonucu konuya yorum
olarak yazıp konuyu kapatır. Ekstra bir hesap ya da anahtar gerekmez —
GitHub oturumu yeter.

Güvenlik: depo herkese açık olduğu için iş akışı yalnızca **depo sahibinin**
açtığı konuları işler; başkasının açtığı konu yok sayılır.

Komut satırından:

```bash
python3 scripts/kaynak_ekle.py https://ornek.org/haberler \
    --ad "Örnek Kurum" --bolge Avrupa --kategori "İnsan hakları" \
    --oncelik Yüksek --siklik Günlük --anahtar "iade, INTERPOL"
```

Aynı alan adı zaten izleniyorsa ekleme reddedilir ve hangi kayıtta olduğu
söylenir.

## Çeviri

Kaynakların bir kısmı İngilizce, Fransızca ve Felemenkçe yayın yapıyor. Tarama
sonrası `scripts/ceviri.py` Türkçe olmayan kayıtların başlık ve özetlerini
Türkçeye çevirir; arayüzde "Türkçe" düğmesiyle çeviri ile özgün metin arasında
geçiş yapılır (tercih tarayıcıda saklanır), kayıt sayfasında özgün başlık her
zaman görünür.

Her kayıt **bir kez** çevrilir ve `data/ceviri.json` önbelleğine yazılır;
sonraki turlarda yalnızca yeni kayıtlar için istek atılır. Dil ayrımı ücretsiz
bir sezgiyle yapılır (Türkçeye özgü harfler ve sık sözcükler), böylece Türkçe
kayıtlar için istek atılmaz. Öntanımlı model `claude-haiku-4-5` (toplu, basit
iş); `CEVIRI_MODEL` ile değiştirilebilir.

Maliyet: ilk dolum ≈ $0,27 (300 kayıt), sonrasında tur başına ≈ $0,05.

```bash
python3 scripts/ceviri.py --kuru      # kaç kayıt çevrilecek, tahmini maliyet
python3 scripts/ceviri.py --adet 200  # bu turda en fazla 200 kayıt
```

## Günlük analiz (Claude API)

Tarama ham kayıt üretir; analiz bu kayıtların merkezin dosyaları açısından ne
anlama geldiğini söyler. Her sabah taramasının ardından bir kez çalışır.

**Çalışma alanları** (brusselslawoffice.com'daki hizmet başlıklarıyla hizalı):
AİHM başvuruları ve kararların icrası · BM insan hakları mekanizmaları ·
INTERPOL bildirimleri ve kırmızı bülten · İade, adli yardım ve iltica ·
Yaptırım listeleri ve malvarlığı dondurma · Gülen hareketi/KHK dosyaları ve
sınıraşan baskı · İfade ve basın özgürlüğü · Belçika ve AB mevzuatı.

**Hafıza ve takip listesi:** Analiz her gün sıfırdan başlamaz. Son 7 günün
başlıkları ve **açık takip maddeleri** girdiye eklenir; model her açık madde
için "hareket var / hareket yok / kapandı" der ve hareket varsa notunu yazar.
Yeni izlenmesi gereken konular takip listesine eklenir (`data/takip.json`).
45 gün hareket görmeyen madde kendiliğinden kapanır. Böylece "bu operasyon
12 Eylül'den beri sürüyor, bugün 32 kişi daha" türü süreklilik kurulur.

**Tam metin:** Analizden hemen önce `scripts/tam_metin.py` en yüksek puanlı 18
kaydın tam metnini indirir; analiz bu kayıtlarda başlıktan fazlasını görür
(ilk 15 kayıt için ~2.600, diğerleri için ~700 karakter).

**Üretilen brifing:** günün başlığı, 3-5 cümlelik değerlendirme, en fazla 6
"öne çıkan gelişme" (alan etiketi, neden önemli olduğu, dayandığı kayıtlar ve
güven düzeyi), alan alan durum notları, izlenecekler listesi.

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python3 scripts/analiz.py                 # bugünün analizini üret
python3 scripts/analiz.py --kuru          # istek atmadan istemi ve maliyeti gör
python3 scripts/analiz.py --model claude-sonnet-5
python3 scripts/analiz.py --kisa          # tam metinleri gönderme (daha ucuz)
python3 scripts/analiz.py --gun 2026-09-16 --zorla
```

**Yayında çalıştırmak için** tek gereken, depoya bir sır eklemek:
**Settings → Secrets and variables → Actions → New repository secret**,
ad `ANTHROPIC_API_KEY`. Model değiştirmek istersen aynı ekranda *Variables*
sekmesinde `ANALIZ_MODEL` tanımlanabilir. Anahtar tanımlı değilse analiz adımı
sessizce atlanır, tarama normal çalışır.

**Maliyet — ölçülen değerler** (45 kayıt, tam metinler ve 6 birincil belge ile
≈ 15 bin girdi token; çıktı, zenginleşen şema yüzünden uzun):

| Adım | Model | Günlük |
|---|---|---|
| Günlük analiz | `claude-opus-5` (öntanımlı) | ≈ $0,51 |
| Öz-denetim | `claude-sonnet-5` | ≈ $0,17 |
| Çeviri | `claude-haiku-4-5` | ≈ $0,02 |
| Haftalık sentez | `claude-opus-5` | ≈ $0,12 (haftada bir) |
| **Toplam** | | **≈ $0,70/gün · $21/ay** |

Kısmak istersen: `ANALIZ_MODEL=claude-sonnet-5` ana analizi beşte bire indirir;
`--kisa` tam metinleri göndermez; `--birincil-yok` karar metinlerini,
`--denetim-yok` ikinci geçişi kapatır; `--adet 30` analize giren kayıt sayısını
azaltır. Her analiz kullandığı token sayısını ve maliyeti hem ekrana yazar hem
de üretilen dosyaya (`maliyet_usd`) kaydeder.
Her analiz, kullandığı token sayısını ve maliyeti hem ekrana yazar hem de
üretilen dosyaya (`maliyet_usd`) kaydeder.

### Birincil belgeler

Analizin en büyük eksiği şuydu: kararları *anlatan haberleri* okuyor, kararın
kendisini okumuyordu. `scripts/birincil.py` bunu kapatır.

* **HUDOC (AİHM)** — Türkiye aleyhine kararlar, kabul edilebilirlik kararları ve
  Bakanlar Komitesi icra kararları; başvuru numarası, incelenen maddeler ve
  HUDOC'un kendi "sonuç" alanıyla birlikte **tam metin** olarak indirilir.
  Analize kararın olay özeti ve **hüküm kısmı** verilir (ortadaki usul bölümleri
  atlanır) — hükümde ihlal bulunup bulunmadığı ve hükmedilen tutar yazar.
* **Resmî Gazete** — günün sayısının başlıkları. Sitenin sertifika zinciri eksik
  olduğu için erişilemeyebilir; o durumda adım sessizce atlanır.

Sistem istemi birincil belgeyi haber kaydından **üstün** sayar: bir haber kararı
yanlış aktarıyorsa analiz kararın metnine uyar ve farkı açıkça yazar. Arayüzde
"Birincil belgeler" bloğu her karar için üç şey gösterir — mahkeme ne dedi,
merkezin dosyaları için ne anlama geliyor, haber kayıtlarıyla fark nerede.

```bash
python3 scripts/birincil.py --liste            # indirmeden neler var, gör
python3 scripts/birincil.py --gun-sayisi 21 --adet 8
```

### Öz-denetim

Analiz üretildikten sonra ikinci bir geçiş, **her iddiayı kendi dayanaklarına
karşı** denetler (öntanımlı `claude-sonnet-5`, ölçülen maliyet ≈ $0,17/gün;
`DENETIM_MODEL` ile `claude-haiku-4-5` seçilirse yarısına iner). İddianın
gösterdiği kayıtlar, birincil belgeler ve önceki günlerin başlıkları isteme
yeniden konur; model üç hükümden birini verir: "dayanaklı", "kısmen" (ana olgu
var ama kayıtlarda olmayan başka bir olgu eklenmiş) ya da "dayanaksız".
İşaretlenen iddia **silinmez**; arayüzde gerekçesiyle görünür.

Denetim yalnızca **olgu** iddialarını inceler: sayı, tarih, isim, tutar, ne
olduğu. "Merkezin dosyaları için ne anlama geliyor", önem sırası ve hangi
mekanizmanın devrede olduğu analistin değerlendirmesidir, denetlenmez — yoksa
her madde "kısmen" işaretlenir ve işaret hiçbir şey ifade etmez.

Ölçülen ilk sonuç: 13 iddiadan 12'si dayanaklı, biri işaretli — *"28 kişilik
gözaltı kararı kayıtla doğrulanıyor, ancak 'dün 28-72 arası rakam bandı'
iddiası önceki gün başlıklarında yer almıyor."*

### Zenginleşen günlük çıktı

Öne çıkan her gelişme artık şunları da taşır:

* **ayrıntılar** — kayıtlarda geçen somut veriler (sayı, tarih, dosya numarası,
  tutar), her biri kendi dipnotuyla
* **mekanizma** — devrede olan hukuki yol (AİHM maddesi, BM usulü, INTERPOL
  kuralı). Tavsiye değil, konumlandırma
* **karşı okuma** — bu kayıtların *göstermediği* şey; hangi çıkarım yapılamaz
* **kronoloji** — günün ana dosyasında adım adım seyir

### Haftalık sentez

Günlük brifing günü anlatır; **haftalık sentez** yedi güne birden bakar ve
günlük analizlerin kendisini girdi alır (yeniden tarama yapmaz, kaynakları
tekrar okumaz). Pazar sabahı taramasından sonra bir kez çalışır.

Çıkardığı şey gün tekrarı değil: hafta boyunca birden fazla gün karşılığı olan
**eğilimler** (güçleniyor / sabit / zayıflıyor), açık takip **dosyalarının
haftalık seyri** (ilerledi / yerinde / sessiz), bir gün görünüp devamı gelmeyen
**tek seferlik** gelişmeler ve —en çok işe yarayanı— günlük brifinglerde
"izlenecek" denip hafta içinde **karşılığı gelmeyen beklentiler**.
Her madde dayandığı günleri taşır; arayüzdeki tarih rozetine tıklayınca o günün
analizi açılır.

```bash
python3 scripts/sentez.py                 # son 7 günün sentezi
python3 scripts/sentez.py --kuru          # istek atmadan istemi ve maliyeti gör
python3 scripts/sentez.py --pencere 14    # iki haftalık pencere
python3 scripts/sentez.py --gun 2026-09-21 --zorla
```

En az üç günlük analiz birikmeden sentez üretilmez. Maliyeti haftada bir kez
≈ $0,10–0,15'tir (`claude-opus-5`); model `SENTEZ_MODEL` değişkeniyle
değiştirilebilir.

**Sınırlar — bilerek konulmuş:** Model yalnızca verilen kayıtlardaki bilgiyi
kullanır, kayıt dışı olay/isim/tarih uyduramaz; her değerlendirme dayandığı
kayıt anahtarlarını taşır; her maddede güven düzeyi belirtilir; hukuki tavsiye
veya dava stratejisi üretmesi yasaklanmıştır. Çıktı JSON şemasıyla
kısıtlanmıştır. Her analiz sayfasında, değerlendirmenin yapay zekâ ile
üretildiğini ve birincil kaynakta doğrulanmadan dosyaya esas alınamayacağını
söyleyen uyarı görünür.

## Uyarılar — ne zaman bakmam gerekir

Site gün boyu sessizce dolar. `scripts/uyari.py` her taramadan sonra çalışır ve
yalnızca aşağıdaki eşiklerden biri aşılırsa haber verir. Model çağırmaz, ek
maliyeti yoktur.

| Kural | Eşik |
|---|---|
| **Acil alan** | INTERPOL, iade/adli yardım ya da yaptırım alanında öne çıkan bir gelişme (bu alanlarda kayıt nadirdir, tek gelişme bile bakmayı hak eder) |
| **Dosya hareketi** | Açık takip dosyalarından biri kımıldadıysa |
| **Çok kaynaklı** | Aynı gelişmeyi 4 ya da daha fazla kaynak verdiyse |
| **Kritik kayıt yoğunluğu** | Gün içinde birincil kaynaktan 3+ "Kritik" öncelikli kayıt |
| **İzleme bozuldu** | 8 ya da daha fazla kaynağın akışı hata veriyorsa |

Aynı uyarı iki kez gönderilmez (`data/uyari-gecmis.json`). Kanallar:

* **GitHub konusu** — kurulum gerektirmez; depo sahibine GitHub kendisi e-posta
  gönderir. Uyarı, `uyari` etiketli bir konu olarak açılır.
* **Telegram** (isteğe bağlı) — `TELEGRAM_TOKEN` ve `TELEGRAM_CHAT_ID` sırları
  tanımlıysa aynı özet Telegram'a da düşer; tanımlı değilse adım sessizce atlanır.
* **Site** — güncel uyarılar Gündem sayfasının en üstünde şerit olarak görünür;
  "×" ile o güne kapatılabilir (tercih tarayıcıda saklanır).

```bash
python3 scripts/uyari.py               # bugünü değerlendir
python3 scripts/uyari.py --kuru        # geçmişe yazma, yalnızca göster
python3 scripts/uyari.py --hepsi       # daha önce gönderilmişleri de listele
```

## İzleme masası özellikleri

* **Doğrulama kümeleri** — başlık sözcüklerinin örtüşmesine göre (Jaccard ≥ 0,6 ve en az
  3 ortak sözcük, 5 günlük pencere) aynı gelişmeyi anlatan kayıtlar eşleştirilir. Küme
  imzası ilk kaydın sözcükleridir, genişletilmez; böylece zincirlenip alakasız kayıtları
  toplamaz. Akışta küme tek satıra iner, kayıt sayfasında kaynaklar karşılaştırılır.
* **Kaynak sağlığı** (`data/health.json`) — kaynak başına son kayıt tarihi ve akış hatası.
  Arayüz, kaynağın kendi tarama sıklığına göre (günlük 4, haftalık 14, aylık 45 gün)
  gecikenleri "sessiz", akışı kırılanları "akış hatası" olarak işaretler. İzlemenin
  kendisini izlemek için: sessizleşen bir kaynak, çoğu zaman kırılmış bir akıştır.
* **Dosyam** — ☆ ile toplanan kayıtlar tarayıcıda saklanır (`localStorage`, hiçbir yere
  gönderilmez) ve Markdown/CSV olarak indirilebilir. Tarama penceresinden düşen kayıtlar
  da dosyada kalır.
* **Son ziyaretten beri** — özet panelinde, en son bakıştan sonra gelen kayıt sayısı;
  akışta bu kayıtlar "yeni" işaretli.
* **Kendi RSS akışımız** — `data/gundem.xml`, puana göre seçilmiş 80 kayıt. Kendi okuyucuna
  ya da bir Slack/Telegram kanalına bağlanabilir.
* **Yazdırma** — sayfa altındaki "yazdır", o an süzülmüş listeyi künye ve bağlantılarla
  birlikte yazdırmaya uygun biçimde çıkarır (gezinme, görseller ve panel düşer).

## Kanıt standardı

Akış başlıkları yalnızca işarettir. Dosyaya girecek her gelişme **birincil
kaynakta** (karar metni, resmî yayın, tebliğ) doğrulanmalıdır. Tarih bilgisi
vermeyen akışlarda öğe tarihi tarama anına göre alınır ve kartta
"tarih tahmini" olarak işaretlenir. RSS yayını olmayan kaynaklar arayüzde
"elle" etiketiyle görünür ve izleme planındaki sıklığa göre elle kontrol
edilir.
