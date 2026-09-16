#!/bin/sh
# Linux: ./baslat.sh
cd "$(dirname "$0")" || exit 1
if command -v python3 >/dev/null 2>&1; then
  exec python3 scripts/serve.py "$@"
fi
echo "Python 3 kurulu değil. Örnek: sudo apt install python3"
exit 1
