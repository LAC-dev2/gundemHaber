# Görev: Gündem Takip'i bu bilgisayarda günlük çalışır hâle getir

Bu dosya, **başka bir bilgisayardaki Claude oturumuna** verilmek üzere
hazırlanmıştır. O oturumun bu projeyle ilgili hiçbir önbilgisi yok; ihtiyaç
duyulan her şey aşağıda.

---

## Claude: önce bunu oku

Sen bir hukuk bürosunun izleme sistemini kurmakla görevlisin. İş, bu
bilgisayarda her sabah kendi kendine çalışacak bir boru hattı kurmak.

**Proje:** Gündem Takip — Brüksel Hukuk Merkezi için otomatik hukuki gelişme
izleme. 420 kaynağı tarar, haberleri Türkçeye çevirir, günün hukuki
brifingini üretir ve GitHub Pages'te yayımlar.

- Depo: `https://github.com/LAC-dev2/gundemHaber`
- Çalışma dalı: `claude/trusting-ritchie-qqutwf` (ana dal değil, **bu dal**)
- Canlı site: `https://lac-dev2.github.io/gundemHaber/`

**Amaç:** Bu iş şimdiye kadar GitHub Actions üzerinde, Anthropic API'sine
token başına ödeyerek koşuyordu (~0,57 $/gün). Artık **bu bilgisayarda,
kullanıcının Claude aboneliğiyle, ek API harcaması olmadan** koşacak.

Kod bunun için zaten hazır: model çağrıları `scripts/llm.py` adlı bir
katmanın arkasında ve iki arka ucu var.

| | `GUNDEM_LLM=api` | `GUNDEM_LLM=cli` |
|---|---|---|
| Nasıl bağlanır | `ANTHROPIC_API_KEY` | Claude Code komut satırı (`claude -p`) |
| Ödeme | token başına fatura | **Claude aboneliği**, ek harcama yok |

**Senin kuracağın `cli` olanı.** Kod yazmana gerek yok; kurulum, doğrulama ve
zamanlama yapacaksın.

---

## Adım 1 — Ortamı kontrol et

```bash
python3 --version      # 3.11+ olmalı
git --version
node --version         # 18+ olmalı
claude --version       # yoksa bir sonraki komut
```

Claude Code kurulu değilse:

```bash
npm install -g @anthropic-ai/claude-code
```

Eksik bir şey varsa kullanıcıya **ne eksik olduğunu söyle ve kurmasını iste**;
kendi başına sistem paketi kurmaya çalışma.

## Adım 2 — Aboneliği bağla

Zamanlanmış görev tarayıcı açamayacağı için uzun ömürlü bir belirteç gerekir.
Bu komutu **kullanıcı kendisi çalıştırmalı** (tarayıcı açılır, hesabıyla
giriş yapar):

```bash
claude setup-token
```

Çıkan değeri kabuk profiline yazmasını iste (`~/.zshrc` ya da `~/.bashrc`):

```bash
export CLAUDE_CODE_OAUTH_TOKEN="sk-ant-oat01-..."
```

> **Bu bir kimlik bilgisidir.** Değerini sohbete yazdırma, dosyaya kaydetme,
> depoya işleme. Yalnızca tanımlı olup olmadığını kontrol et:
> `[ -n "$CLAUDE_CODE_OAUTH_TOKEN" ] && echo tanımlı`

## Adım 3 — Depoyu al

```bash
git clone https://github.com/LAC-dev2/gundemHaber.git
cd gundemHaber
git checkout claude/trusting-ritchie-qqutwf
```

`git push` zamanlanmış görevden de çalışacak, yani parola sormadan geçmeli.
Kullanıcıya sor: SSH anahtarı mı var, yoksa kimlik yardımcısı mı kuralım?

```bash
git config --global credential.helper store    # Linux/Windows
git config --global credential.helper osxkeychain   # macOS
```

Sonra bir kez elle `git push` denemesi yaptır ki kimlik kaydedilsin.

## Adım 4 — Kısa deneme (analiz yok)

```bash
scripts/gunluk.sh --tarama
```

Bu yalnızca tarar ve çevirir; 2–3 dakika sürer. Çıktıda şunu görmelisin:

```
akis veri veren: 1xx/277 ... | haber 6xx | gorselli 4xx
çeviri bitti: ... token · ≈ $0.0xx
```

Sorun çıkarsa aşağıdaki **Sorun giderme** tablosuna bak.

## Adım 5 — Tam koşu

```bash
scripts/gunluk.sh
```

**5–8 dakika sürer** — analiz adımı uzun, sabırlı ol, iptal etme. Başarılı
koşunun sonu şuna benzer:

```
analiz: 2026-11-13 · 5 öne çıkan · 8 alan notu · takip: 192 açık
token: 41.119 girdi / 34.890 çıktı · model claude-opus-5 · arka uç cli
```

### Doğrulama (bunu mutlaka yap)

```bash
python3 -c "import json;d=json.load(open('data/analiz-latest.json'));print(d['arka_uc'], d['model'], d['girdi_token'], d['cikti_token'])"
```

`arka_uc` **`cli`** yazmalı. `api` yazıyorsa `GUNDEM_LLM` ayarı geçmemiş
demektir — `scripts/gunluk.sh` içinde varsayılan `cli`, dışarıdan
`GUNDEM_LLM=api` geliyorsa onu bul ve kaldır.

Sonra sitenin güncellendiğini doğrula: push geçtiyse birkaç dakika içinde
`https://lac-dev2.github.io/gundemHaber/` üzerinde o günün tarihi görünür.

## Adım 6 — Her sabah çalışsın

Önce işletim sistemini tespit et (`uname -s`), sonra uygun olanı kur.

### macOS / Linux

`crontab -e` ile aç:

```cron
# cron'un PATH'i dardır; node, claude ve python3 bulunamazsa koşu SESSİZCE düşer.
# Aşağıdaki yolları `which claude`, `which python3` çıktısına göre düzelt.
PATH=/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin
CLAUDE_CODE_OAUTH_TOKEN=sk-ant-oat01-...

47 8 * * * cd /TAM/YOL/gundemHaber && ./scripts/gunluk.sh >> data/cron.log 2>&1
```

Saat 08:47: koşu birkaç dakika sürdüğü için ofis 09:00'da masaya oturduğunda
haber ve analiz hazır olsun diye biraz önceden başlıyor. Kullanıcı Brüksel'de
(UTC+2), cron yerel saatle çalışır — ayrıca ayar gerekmez.

**macOS uyarısı:** bilgisayar uykudaysa cron ateşlenmez ve o iş *kaçar*.
Kullanıcıya iki seçeneği anlat: ya `System Settings → Energy Saver`'dan o
saatte uyanmasını ayarlasın, ya da cron yerine `launchd` kuralım — `launchd`
kaçırılan işi uyanınca çalıştırır. İkincisini istiyorsa
`~/Library/LaunchAgents/com.bhm.gundem.plist` dosyasını sen yaz.

### Windows

Kullanıcıya sor, iki yol var:

1. **WSL** (önerilen): Ubuntu içinde yukarıdaki cron adımlarını uygula.
2. **Görev Zamanlayıcı**: Günlük 08:47 tetikleyici, eylem
   `C:\Program Files\Git\bin\bash.exe`, argüman
   `-lc "cd /c/Users/<kullanıcı>/gundemHaber && ./scripts/gunluk.sh"`.
   "Kullanıcı oturum açmış olsun olmasın" seçeneğini işaretlet.

### Kurduktan sonra

Zamanlamayı **gerçekten doğrula**: cron satırını geçici olarak 2–3 dakika
sonraya ayarla, çalıştığını `data/cron.log` dosyasından gör, sonra asıl saate
çek. "Kurdum" deyip geçme — cron'un PATH sorunu tam olarak böyle yakalanır.

---

## Yapma

- **`--bare` bayrağını `claude` komutuna ekleme.** Kimlik doğrulamasını
  yalnızca `ANTHROPIC_API_KEY`'e sabitler, yani aboneliği devre dışı bırakır
  ve kullanıcı farkında olmadan API'ye ödemeye başlar.
- **`GUNDEM_LLM=api` yapma.** İşin tamamı bunun tersi için.
- **Belirteci dosyaya/depoya yazma.** Yalnızca kabuk profilinde ve crontab'da
  dursun.
- **`scripts/llm.py`, `analiz.py`, `ceviri.py`, `sentez.py` dosyalarını
  değiştirme.** Çalışıyorlar ve uçtan uca doğrulandılar. Gerçek bir hata
  bulursan önce kullanıcıya söyle.
- **Veri dosyalarını elle düzeltme.** `data/` altındakileri boru hattı üretir.

---

## Sorun giderme

| Belirti | Sebep ve çözüm |
|---|---|
| `'claude' komutu yok` | Claude Code kurulu değil ya da cron'un PATH'inde değil. `which claude` çıktısını crontab'daki `PATH=` satırına ekle. |
| `claude çıkış kodu 1: ... authentication` | Belirteç süresi dolmuş. Kullanıcıdan `claude setup-token` ile yenilemesini iste. |
| `cli yanıtı 3 denemede şemaya uymadı` | Model şemaya uymayan çıktı verdi. `GUNDEM_CLI_SURE=3600` ile süreyi uzat; sürerse kullanıcıya bildir. |
| `claude 1800 sn içinde yanıt vermedi` | `GUNDEM_CLI_SURE=3600` ile sınırı yükselt. |
| `git push` parola soruyor | Kimlik yardımcısı kurulu değil (Adım 3). |
| Analiz üretilmiyor, hata da yok | `data/analiz-durum.json` son denemenin nedenini yazar; onu oku. |
| `analizi zaten var` | O gün için analiz üretilmiş. Yeniden üretmek için `python3 scripts/analiz.py --zorla`. |
| Koşu sınıra takıldı | Abonelik kullanım sınırı kullanıcının diğer Claude işleriyle ortak. Günlük yük ~37 bin girdi / ~15 bin çıktı token; yoğun bir günün ardından takılabilir. Birkaç saat sonra tekrar dene. |

## Ayar değişkenleri

| Değişken | Varsayılan | Ne yapar |
|---|---|---|
| `GUNDEM_LLM` | `api` (ama `gunluk.sh` içinde `cli`) | arka uç seçimi |
| `GUNDEM_CLI_SURE` | `1800` | tek model çağrısı için saniye sınırı |
| `GUNDEM_CLI_MODEL` | (yok) | komut satırına geçecek model adını elle sabitler |
| `ANALIZ_MODEL` | `claude-opus-5` | günlük analizin modeli |
| `CEVIRI_MODEL` | `claude-haiku-4-5` | çevirinin modeli |

---

## Bilinmesi gerekenler

**Bilgisayar açık olmalı.** İş artık bulutta değil bu makinede. Kapalıysa o
gün analiz üretilmez. GitHub Actions iş akışı dosyası depoda duruyor; yedek
olarak GitHub'dan elle tetiklenebilir (o yol API anahtarı kullanır).

**JSON şeması artık sunucuda zorlanmıyor.** API tarafında şema
`output_config` ile garanti altındaydı; komut satırında böyle bir özellik yok.
`scripts/llm.py` şemayı sistem istemine yazıyor, yanıtı ayrıştırıp zorunlu
alanları doğruluyor, tutmazsa düzeltme notuyla üç kez yeniden soruyor. Gerçek
boyutlu bir analizde test edildi ve API'nin ürettiğiyle alan alan aynı çıktı —
ama API yolundaki kadar kesin bir garanti değil.

**`maliyet_usd` alanı abonelikte gerçek fatura değil**, liste fiyatı
karşılığı; iki arka ucun yükünü karşılaştırmak için yazılıyor. Kaydın
`arka_uc` alanı hangisinin kullanıldığını söyler.

---

## Bitti sayılma ölçütü

Hepsi sağlandığında işin tamam:

1. `scripts/gunluk.sh` elle çalıştırıldığında hatasız bitiyor.
2. `data/analiz-latest.json` içindeki `arka_uc` alanı **`cli`**.
3. Canlı sitede o günün tarihi görünüyor (push geçmiş).
4. Zamanlanmış görev kurulu ve **gerçekten ateşlendiği görüldü**
   (`data/cron.log` içinde bir koşu kaydı var).

Dördünü de tek tek doğrula ve kullanıcıya hangisinin nasıl doğrulandığını
söyle. Depoda `KURULUM.md` daha ayrıntılı bir sürümünü taşıyor.
