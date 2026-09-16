#!/bin/sh
# macOS: bu dosyaya cift tiklayin (ilk seferde: sag tik > Ac).
cd "$(dirname "$0")" || exit 1

if command -v python3 >/dev/null 2>&1; then
  echo "Gündem Takip başlatılıyor. Tarayıcı kendiliğinden açılır."
  echo "Kapatmak için bu pencerede Ctrl+C."
  exec python3 scripts/serve.py "$@"
fi

cat <<'MSG'

  Python 3 bulunamadı. Bir kez kurmak yeterli:

    Terminal'de:  xcode-select --install
    ya da:        https://www.python.org/downloads/macos/

  Kurduktan sonra bu dosyaya yeniden çift tıklayın.

MSG
printf "Kapatmak için Enter'a basın: "
read -r _
