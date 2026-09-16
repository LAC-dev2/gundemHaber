# Gündem Takip — nasıl açılır?

Brüksel Hukuk Merkezi'nin izlediği 350 hukuki kaynağı tarayıp günlük
gelişmeleri tek sayfada toplayan uygulama. Aşağıdaki üç yoldan biri yeter;
hangisinin sana uygun olduğu **ne kullandığına** bağlı.

---

## 1) Sadece bakacaksan: tek dosya (hiçbir şey kurmadan)

Sana `gundem-takip-<tarih>.html` diye **tek bir dosya** geldiyse:

* **Windows / macOS:** dosyaya çift tıkla — tarayıcıda açılır.
* **iPhone / iPad:** dosyayı Dosyalar (Files) uygulamasına kaydet, üzerine
  dokun. Safari'de açılır. Paylaş menüsünden **"Ana Ekrana Ekle"** ile
  uygulama gibi de durabilir.
* **Android:** Dosyalar'dan dokun, "Tarayıcıyla aç" seç.

İnternet bile gerekmez: metinler ve görsellerin çoğu dosyanın içine gömülüdür.
Bu bir **anlık kopyadır** — dosya hazırlandığı andaki gelişmeleri gösterir,
kendi kendine yenilenmez. Yeni gelişmeler için yeni dosya istemen gerekir.

---

## 2) Kendi taramasını yapsın istiyorsan: uygulamayı çalıştır

`gundem-takip-<tarih>.zip` dosyasını bir klasöre çıkar, sonra:

* **Windows:** `Baslat.bat` dosyasına çift tıkla.
  Python kurulu değilse pencere bunu söyler ve tek satırlık kurulum komutunu
  verir (`winget install -e --id Python.Python.3.12`). Kurduktan sonra yeniden
  çift tıkla.
* **macOS — ilk seferde karantinayı kaldır (önerilen).** macOS 15 ve sonrasında,
  internetten inen `.app` ve `.command` dosyaları imzalı olmadıkları için her açılışta
  "Apple could not verify…" penceresiyle engellenir. Klasörü bir kez karantinadan
  çıkarırsan bu bir daha sorulmaz. Terminal'i aç (Spotlight'ta "Terminal"), şunu yapıştır
  — `<klasör>` yerine paketi çıkardığın klasörü Finder'dan sürükleyip bırakabilirsin:

  ```
  xattr -dr com.apple.quarantine <klasör>
  ```

  Sonrasında klasördeki **`Gündem Takip.app`** simgesine çift tıklamak yeterli: Terminal
  açılmaz, tarama arkada çalışır, tarayıcı hazır olunca kendiliğinden gelir. Kapatmak için
  Dock'taki simgede sağ tık → Çık.

* **macOS — hiç uğraşmadan tek satır.** Karantinayı kaldırmak istemiyorsan uygulamayı
  Terminal'den başlatmak da Gatekeeper'a takılmaz:

  ```
  cd <klasör> && python3 scripts/serve.py
  ```
* **macOS (seçenek):** `Baslat.command` — aynı işi Terminal penceresiyle yapar. Karantina
  kaldırılmadıysa bu da her açılışta sorar. Üç ayrıntı:
  1. İlk açılışta macOS "internetten indirildi / tanınmayan geliştirici"
     diyebilir. Çözüm: dosyaya **sağ tık → Aç**, sonra **Aç**'ı onayla. Bir kez
     yeter. (İnatçı durumda Terminal'de:
     `xattr -d com.apple.quarantine Baslat.command`)
  2. Zip'i **Finder ile** açmak yeterlidir; başlatıcının çalıştırma izni
     pakette saklıdır. Başka bir araçla açtıysan izin düşebilir, o zaman
     Terminal'de: `chmod +x Baslat.command`
  3. macOS'ta hazır Python 3 gelmez. İlk çalıştırmada sistem
     "komut satırı geliştirici araçlarını yükle" penceresi açarsa **Yükle**'ye
     bas — Python bununla gelir. Açmazsa
     [python.org/downloads/macos](https://www.python.org/downloads/macos/)
     üzerinden kurup yeniden çift tıkla.

  Terminal penceresi açık kalır; kapatmak için **Ctrl+C**.
* **Linux:** `./baslat.sh`

Ne olur: kaynaklar taranır (ilk tarama birkaç dakika sürer), haber metinleri ve
görseller bilgisayara indirilir, tarayıcı kendiliğinden açılır. Kapatmak için
açılan siyah pencerede **Ctrl+C**.

Python 3.9 veya üstü gerekir; başka hiçbir kurulum, hesap veya anahtar yok.

Sık kullanacaksan taramayı kendi kendine yenilesin:

```
Windows:  Baslat.bat --every 30
macOS:    ./Baslat.command --every 30
```

**iPhone / iPad'de bu yol çalışmaz** — iOS'ta bu tür bir uygulama
çalıştırılamaz (macOS'ta çalışır, ikisi farklı). Telefon/tablet için 1. veya
3. yolu kullan.

---

## 3) Herkes her yerden görsün istiyorsan: yayın adresi

Uygulama bir web adresinde de durabilir (GitHub Pages, ücretsiz). O zaman
kimsenin hiçbir şey kurması gerekmez: bağlantıyı açarlar, telefonda da
bilgisayarda da çalışır ve günde üç kez kendini günceller. iPhone'da Safari'nin
Paylaş menüsünden "Ana Ekrana Ekle" denirse uygulama gibi görünür.

Kurulum adımları `README.md` içindeki "Kendi alan adında yayınlamak" bölümünde.

---

## Hangisi?

| Durum | Yol |
|---|---|
| "Hiçbir şey kurmak istemiyorum" | 1 — tek dosya |
| "Bir bakayım" | 1 — tek dosya |
| iPhone / iPad | 1 veya 3 |
| "Güncel kalsın, benim makinemde çalışsın" | 2 — Baslat |
| "Ekipteki herkes görsün" | 3 — yayın adresi |

---

## Paketi hazırlayan için

```bash
python3 scripts/paketle.py           # tek dosyalık HTML (dist/ altına)
python3 scripts/paketle.py --zip     # çalıştırılabilir zip de üret
```

Tek dosyalık sürüm, o anda indirilmiş tam metinleri ve 250 KB altındaki
görselleri (toplam 14 MB'a kadar) içine gömer; sınırları
`--gorsel` ve `--gorsel-limit` ile değiştirebilirsin.
