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
index.html                  arayüz (Gündem / Kaynaklar / Arşiv / Nasıl çalışır)
assets/style.css            BHM görsel kimliğiyle uyumlu stil
assets/app.js               filtreler, akış ve arşiv görünümü
scripts/import_sources.py   BHM HTML dosyasından kaynak envanterini aktarır
scripts/collect.py          RSS/Atom keşfi + tarama + puanlama
data/sources.json           350 kaynak, temalar, sosyal hesaplar, uyarı terimleri
data/feeds.json             keşfedilen akış adresleri (önbellek)
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

## Yerel çalıştırma

```bash
python3 scripts/collect.py --discover 40      # tarama (stdlib, bağımlılık yok)
python3 -m http.server 8000                   # http://localhost:8000
```

Kaynak envanteri güncellendiğinde:

```bash
python3 scripts/import_sources.py /yol/bhm-kaynak-izleme-merkezi.html
```

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

## Kanıt standardı

Akış başlıkları yalnızca işarettir. Dosyaya girecek her gelişme **birincil
kaynakta** (karar metni, resmî yayın, tebliğ) doğrulanmalıdır. Tarih bilgisi
vermeyen akışlarda öğe tarihi tarama anına göre alınır ve kartta
"tarih tahmini" olarak işaretlenir. RSS yayını olmayan kaynaklar arayüzde
"elle" etiketiyle görünür ve izleme planındaki sıklığa göre elle kontrol
edilir.
