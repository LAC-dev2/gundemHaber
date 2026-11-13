# API harcaması olmadan çalıştırma

Gündem Takip'in model çağrıları iki ayrı arka uçtan yapılabiliyor:

| | `GUNDEM_LLM=api` | `GUNDEM_LLM=cli` |
|---|---|---|
| Nasıl bağlanır | `ANTHROPIC_API_KEY` | Claude Code komut satırı |
| Ödeme | token başına fatura | **Claude aboneliği** — ek API harcaması yok |
| Nerede çalışır | GitHub Actions ya da yerel | GitHub Actions ya da yerel |

Aboneliği iki yerde kullanabilirsin:

- **GitHub Actions'ta** (Bölüm 0) — bilgisayarının açık olması gerekmez,
  mevcut zamanlama ve yayın düzeni aynen devam eder. **Önerilen.**
- **Kendi bilgisayarında** (Bölüm 1'den itibaren) — her şey yerelde koşar.

---

## 0. En kolay yol: GitHub Actions + abonelik

Bu düzende hiçbir şey taşınmaz. Aynı iş akışı, aynı saatler, aynı uyarılar ve
aynı Pages yayını; yalnızca model çağrıları API yerine aboneliğinden geçer.

**Tek yapman gereken bir secret eklemek.**

1. Kendi bilgisayarında bir kez belirteç üret:

   ```bash
   npm install -g @anthropic-ai/claude-code
   claude setup-token
   ```

2. Çıkan değeri GitHub'a ekle:
   `Settings → Secrets and variables → Actions → Secrets → New repository secret`
   - Ad: `CLAUDE_CODE_OAUTH_TOKEN`
   - Değer: `sk-ant-oat01-...`

Bu kadar. İş akışı belirteci görür görmez `cli` arka ucuna geçer; Claude
Code'u kendisi kurar ve analizi aboneliğinle üretir. `ANTHROPIC_API_KEY`
secret'ını silmene gerek yok — dururken de kullanılmaz.

**Geri dönmek istersen:** `Settings → Secrets and variables → Actions →
Variables` altına `GUNDEM_LLM` = `api` ekle. İş akışı eski davranışına döner.
Secret'ı silmen gerekmez.

**Doğrulama:** ilk koşudan sonra adım kütüğünde
`arka uc: Claude Code ... — abonelik, API harcamasi yok` satırını ara, ayrıca:

```bash
curl -s https://lac-dev2.github.io/gundemHaber/data/analiz-latest.json \
  | python3 -c "import json,sys;d=json.load(sys.stdin);print(d['arka_uc'], d['model'])"
```

`cli` yazmalı.

### Bilmen gereken tek şey

Bu belirteç **aboneliğine bağlı bir kimlik bilgisidir** ve GitHub Secrets'ta
durur. Depoya yazma yetkisi olan biri (ya da iş akışı dosyasını
değiştirebilen biri) onu kullanabilir. Depo senin ve tek yetkili sensen bu
bir sorun değil; ekibe açarsan düşün. İstediğin an `claude setup-token` ile
yenileyip eskisini geçersiz kılabilirsin.

Kullanım sınırı senin diğer Claude işlerinle ortaktır: günlük yük ~37 bin
girdi / ~15 bin çıktı token, normal bir abonelikte küçük bir pay.

---

## Kendi bilgisayarında çalıştırma

Aşağısı ikinci yolu anlatıyor: tarama, çeviri ve analizi her gün **kendi
bilgisayarında** koşturmak.

---

## 1. Gerekenler

- **Python 3.11+** ve **git**
- **Node.js 18+** (Claude Code için)
- **Claude Code** ve bir **Claude aboneliği** (Pro ya da Max)

Claude Code kurulumu:

```bash
npm install -g @anthropic-ai/claude-code
claude --version
```

## 2. Aboneliği bağla

Komut satırında bir kez giriş yap:

```bash
claude
# açılan oturumda /login → tarayıcıdan Claude hesabınla giriş
```

Zamanlanmış görev için **uzun ömürlü bir belirteç** üret — cron'un tarayıcı
açamayacağı için bu şart:

```bash
claude setup-token
```

Verdiği değeri kabuk profiline yaz (`~/.zshrc` ya da `~/.bashrc`):

```bash
export CLAUDE_CODE_OAUTH_TOKEN="sk-ant-oat01-..."
```

> Bu bir aboneliğe bağlı kimlik bilgisidir; paylaşma, depoya koyma.

## 3. Depoyu al

```bash
git clone https://github.com/LAC-dev2/gundemHaber.git
cd gundemHaber
git checkout claude/trusting-ritchie-qqutwf
```

`git push` zamanlanmış görevden de çalışacağı için kimlik doğrulamasının
parola sormadan geçmesi gerekir: ya SSH anahtarı kullan, ya da bir kimlik
yardımcısı kur (`git config --global credential.helper store` ile bir kez
giriş yapmak yeterli; macOS'ta `osxkeychain`).

## 4. Dene

Önce yalnızca tarama ve çeviri — analiz yok, kısa sürer:

```bash
scripts/gunluk.sh --tarama
```

Sonra tam koşu:

```bash
scripts/gunluk.sh
```

Çıktı `data/kosu-log.txt` dosyasına da yazılır. Analizin hangi arka uçtan
üretildiği kaydın içinde durur:

```bash
python3 -c "import json;d=json.load(open('data/analiz-latest.json'));print(d['arka_uc'], d['model'])"
```

## 5. Her sabah çalışsın

### macOS / Linux (cron)

`crontab -e` ile aç ve ekle:

```cron
# cron'un PATH'i dardır: node, claude ve python3 bulunamazsa koşu sessizce düşer.
PATH=/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin
CLAUDE_CODE_OAUTH_TOKEN=sk-ant-oat01-...

# Her sabah 08:47'de (yerel saat). Ofis 09:00'da haberi ve analizi hazır bulur.
47 8 * * * cd /Users/<kullanıcı>/gundemHaber && ./scripts/gunluk.sh >> data/cron.log 2>&1
```

Saat neden 08:47? Tarama ve analiz birkaç dakika sürüyor; 09:00'da masaya
oturulduğunda bitmiş olması için biraz önceden başlıyor.

**macOS'ta uyku sorunu:** bilgisayar uykudaysa cron ateşlenmez. Ya
`System Settings → Energy Saver` içinden o saatte uyanmasını ayarla, ya da
cron yerine `launchd` kullan — `launchd`, kaçırılan bir işi uyanınca
çalıştırır.

### Windows

İki yol var:

1. **WSL** (önerilen): Ubuntu kur, yukarıdaki cron adımlarını onun içinde uygula.
2. **Görev Zamanlayıcı**: Yeni görev → Tetikleyici: Günlük 08:47 → Eylem:
   `C:\Program Files\Git\bin\bash.exe` programı, argüman
   `-lc "cd /c/Users/<kullanıcı>/gundemHaber && ./scripts/gunluk.sh"`.
   Görev özelliklerinde **"Yalnızca kullanıcı oturum açtığında çalıştır"**
   yerine "Kullanıcı oturum açmış olsun olmasın" seçilirse bilgisayar açıkken
   oturum kapalıyken de koşar.

## 6. Bilmen gerekenler

**Bilgisayar açık olmalı.** GitHub Actions bulutta koşuyordu; artık işi senin
makinen yapıyor. Kapalıysa o gün analiz üretilmez. İkisi birlikte de
çalışabilir: iş akışı dosyası duruyor, istersen GitHub'dan elle tetikleyip
yedek olarak kullanabilirsin.

**Abonelik kullanım sınırı ortak.** Günlük koşu senin Claude'la yaptığın diğer
işlerle aynı sınırı paylaşır. Ölçülen yük günde ~37 bin girdi / ~15 bin çıktı
token; normal bir abonelikte bu küçük bir pay, ama yoğun bir günün ardından
koşu sınıra takılırsa `data/analiz-durum.json` nedeni yazar.

**JSON şeması artık sunucuda zorlanmıyor.** API tarafında şema
`output_config` ile garanti altındaydı; komut satırında böyle bir özellik yok.
`scripts/llm.py` şemayı sistem istemine yazıyor, yanıtı ayrıştırıp üst düzey
alanları doğruluyor ve tutmazsa düzeltme notuyla **üç kez** yeniden soruyor.
Pratikte sorun çıkarmıyor, ama API yolundaki kadar kesin bir garanti değil —
bilerek böyle.

**Maliyet kaydı bilgi amaçlı.** `maliyet_usd` alanı abonelikte gerçek bir
fatura değil, liste fiyatı karşılığı; iki arka ucun yükünü karşılaştırmak için
yazılıyor. Kaydın `arka_uc` alanı hangisinin kullanıldığını söyler.

## 7. Sorun giderme

| Belirti | Sebep ve çözüm |
|---|---|
| `'claude' komutu yok` | Claude Code kurulu değil ya da cron'un PATH'inde değil. `which claude` çıktısını crontab'daki PATH'e ekle. |
| `claude çıkış kodu 1: ... authentication` | Belirteç süresi dolmuş. `claude setup-token` ile yenile. |
| `cli yanıtı 3 denemede şemaya uymadı` | Model şemaya uymayan çıktı verdi. `GUNDEM_CLI_SURE` ve model ayarını kontrol et; `GUNDEM_LLM=api` ile bir kez koşup karşılaştır. |
| Koşu çok uzun sürüyor | Varsayılan sınır 1800 sn. `GUNDEM_CLI_SURE=3600` ile uzatılabilir. |
| `git push` parola soruyor | Kimlik yardımcısı kurulu değil; SSH anahtarına geç ya da `credential.helper` ayarla. |
| Analiz üretilmiyor, hata da yok | `data/analiz-durum.json` son denemenin nedenini yazar. |

## 8. Ayar değişkenleri

| Değişken | Varsayılan | Ne yapar |
|---|---|---|
| `GUNDEM_LLM` | `api` | `cli` → Claude Code (abonelik), `api` → API anahtarı |
| `GUNDEM_CLI_SURE` | `1800` | Tek model çağrısı için saniye cinsinden sınır |
| `GUNDEM_CLI_MODEL` | (yok) | Komut satırına geçirilecek model adını elle sabitler |
| `ANALIZ_MODEL` | `claude-opus-5` | Günlük analizin modeli |
| `CEVIRI_MODEL` | `claude-haiku-4-5` | Çevirinin modeli |
