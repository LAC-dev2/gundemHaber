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
                            ardından tüm akış) ve Kaynaklar / Arşiv / Nasıl çalışır
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
```

## Kurulum (tek seferlik)

1. Bu dal `main` içine alındıktan sonra **Settings → Pages → Source: GitHub
   Actions** seçilir. (Zamanlanmış görevler yalnızca varsayılan dalda çalışır.)
2. **Settings → Actions → General → Workflow permissions** altında
   *Read and write permissions* işaretlenir; tarama sonuçlarını depoya işlemek
   için gereklidir.
3. **Actions → Kaynak taraması → Run workflow** ile ilk tarama elle başlatılır.
   İlk turlarda akış keşfi yapılır; `data/feeds.json` doldukça sonraki turlar
   hızlanır.

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

## Kanıt standardı

Akış başlıkları yalnızca işarettir. Dosyaya girecek her gelişme **birincil
kaynakta** (karar metni, resmî yayın, tebliğ) doğrulanmalıdır. Tarih bilgisi
vermeyen akışlarda öğe tarihi tarama anına göre alınır ve kartta
"tarih tahmini" olarak işaretlenir. RSS yayını olmayan kaynaklar arayüzde
"elle" etiketiyle görünür ve izleme planındaki sıklığa göre elle kontrol
edilir.
