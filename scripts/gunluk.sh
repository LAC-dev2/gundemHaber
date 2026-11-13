#!/usr/bin/env bash
# Gunluk kosu: tarama -> ceviri -> analiz -> (pazar) sentez -> uyari -> yayin.
#
# GitHub Actions'taki is akisinin kendi bilgisayarinda calisan karsiligi.
# Model cagrilari GUNDEM_LLM=cli ile Claude Code uzerinden yapilir: Claude
# aboneligi kullanilir, API harcamasi olmaz.
#
#   scripts/gunluk.sh            # tam kosu
#   scripts/gunluk.sh --tarama   # yalnizca haber topla + cevir, analiz yok
#
# Kurulum ve zamanlama icin: KURULUM.md
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1
DAL="$(git rev-parse --abbrev-ref HEAD)"
KUTUK="data/kosu-log.txt"
: "${GUNDEM_LLM:=cli}"
export GUNDEM_LLM

yaz() { printf '%s  %s\n' "$(date -u '+%Y-%m-%d %H:%M:%SZ')" "$*" | tee -a "$KUTUK"; }

yaz "=== kosu basladi (dal: $DAL, arka uc: $GUNDEM_LLM) ==="

if [ "$GUNDEM_LLM" = "cli" ] && ! command -v claude >/dev/null 2>&1; then
  yaz "HATA: 'claude' komutu yok. Claude Code kurulu olmali (bkz. KURULUM.md)."
  exit 1
fi

# Araya baska bir kosu girdiyse once onu al; yoksa push reddediliyor.
git pull --rebase --autostash origin "$DAL" >>"$KUTUK" 2>&1 \
  || yaz "uyari: git pull basarisiz, yerel halle devam ediliyor"

yaz "1/6 kaynaklar taraniyor"
python3 scripts/collect.py --discover 120 --news 140 --images 90 --workers 16 2>&1 | tee -a "$KUTUK"

yaz "2/6 ceviri"
# Sayfadaki her kayit Turkce olmali; cevrilemeyen kayit listeye girmiyor.
python3 scripts/ceviri.py --adet 200 2>&1 | tee -a "$KUTUK"

if [ "${1:-}" = "--tarama" ]; then
  yaz "yalnizca tarama istendi; analiz atlandi"
else
  yaz "3/6 analiz girdileri (tam metin + AIHM karar metinleri)"
  python3 scripts/tam_metin.py --adet 18 2>&1 | tee -a "$KUTUK" || true
  python3 scripts/birincil.py --gun-sayisi 21 --adet 8 2>&1 | tee -a "$KUTUK" || true

  yaz "4/6 gunluk analiz"
  python3 scripts/analiz.py 2>&1 | tee -a "$KUTUK"

  # Sentez pazar gunleri, en az uc gunluk analiz birikmisse uretiliyor.
  if [ "$(date -u +%u)" = "7" ]; then
    yaz "5/6 haftalik sentez"
    python3 scripts/sentez.py 2>&1 | tee -a "$KUTUK" || true
  else
    yaz "5/6 haftalik sentez yalnizca pazar gunu; atlandi"
  fi
fi

yaz "6/6 uyari esikleri"
python3 scripts/uyari.py 2>&1 | tee -a "$KUTUK" || true

# Yayin: GitHub Pages depodaki dosyalari okuyor, yani push = yayin.
git add --ignore-removal data
if git diff --cached --quiet; then
  yaz "degisiklik yok, push edilmedi"
else
  git commit -q -m "veri: tarama $(date -u '+%Y-%m-%d %H:%M') UTC"
  for deneme in 1 2 3 4; do
    if git push origin "$DAL" >>"$KUTUK" 2>&1; then
      yaz "push tamam"
      break
    fi
    yaz "push basarisiz ($deneme/4), yeniden deneniyor"
    git pull --rebase -X theirs origin "$DAL" >>"$KUTUK" 2>&1 || true
    sleep $((2 ** deneme))
  done
fi

yaz "=== kosu bitti ==="
