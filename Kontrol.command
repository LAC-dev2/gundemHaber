#!/bin/bash
# Cift tiklanabilir: bugunun analizi yapilmadiysa yapilmasini ister.
# Bu dosyanin bulundugu klasorde calisir.
cd "$(dirname "$0")" || exit 1
echo "Gündem Takip · günün analizi kontrol ediliyor…"
echo
python3 scripts/tetikle.py
KOD=$?
echo
if [ $KOD -ne 0 ]; then
  echo "Bir şeyler ters gitti. Jeton kurulumu için OKUBENI.md'ye bakabilirsin."
fi
echo "Kapatmak için bu pencereyi kapatabilirsin."
read -r -p "" _
