#!/usr/bin/env python3
"""Model cagrisi icin tek giris noktasi: API anahtari ya da Claude aboneligi.

Iki arka uc var, ayni imzayi veriyorlar:

  api  (varsayilan)  anthropic SDK + ANTHROPIC_API_KEY. Token basina odeme.
  cli                Claude Code komut satiri (`claude -p`). Abonelikle
                     calisir, ayrica API harcamasi olmaz.

Secim GUNDEM_LLM ortam degiskeniyle yapilir:

  GUNDEM_LLM=cli python3 scripts/analiz.py

Arka uclar arasindaki tek gercek fark cikti bicimi: API tarafinda JSON sema
sunucuda zorlanir (output_config/json_schema), komut satirinda boyle bir
ozellik yok. Orada sema sistem istemine yaziliyor, yanit ayristirilip
dogrulaniyor ve tutmazsa duzeltme notuyla yeniden soruluyor.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile

ARKA_UC = (os.environ.get("GUNDEM_LLM") or "api").strip().lower()

# 1M token basina USD (girdi, cikti). Abonelikte gercek fatura bu degil;
# kayitlara yine yaziliyor ki iki arka ucun yuku karsilastirilabilsin.
FIYAT = {
    "claude-opus-5": (5.0, 25.0),
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-fable-5-1": (10.0, 50.0),
    "claude-fable-5": (10.0, 50.0),
}

CLI_SURE = int(os.environ.get("GUNDEM_CLI_SURE") or 1800)   # saniye
CLI_DENEME = 3                      # sema tutmazsa kac kez yeniden sorulur


class LLMHata(Exception):
    """hesap=True: kredi/limit/yetki sorunu — yeniden denemenin anlami yok."""

    def __init__(self, mesaj: str, *, hesap: bool = False, kod=None):
        super().__init__(mesaj)
        self.mesaj = mesaj
        self.hesap = hesap
        self.kod = kod


def maliyet(model: str, girdi: int, cikti: int) -> float:
    g, c = FIYAT.get(model, FIYAT["claude-opus-5"])
    return girdi / 1e6 * g + cikti / 1e6 * c


def _hesap_hatasi(mesaj: str, kod=None) -> bool:
    """Yeniden denemenin anlamsiz oldugu hatalar: kredi, limit, yetki.

    Hiz siniri (429) bilerek disarida: o gecici bir durum, cagri yeniden
    denenebilir."""
    dusuk = (mesaj or "").lower()
    return (kod in (400, 401, 402, 403)
            or "credit balance" in dusuk
            or "usage limit" in dusuk)


# --------------------------------------------------------------- api arka uc
def _api(model, sistem, istem, sema, max_tokens, dusun, efor):
    try:
        import anthropic
    except ImportError as hata:
        raise LLMHata("anthropic paketi kurulu değil:  pip install anthropic",
                      hesap=True) from hata

    istemci = anthropic.Anthropic()
    bicim = {"type": "json_schema", "schema": sema}
    try:
        if dusun:
            # Akis: uzun cikti ve dusunme token'lari icin yer birak, HTTP
            # zaman asimindan da korunmus ol.
            with istemci.messages.stream(
                model=model, max_tokens=max_tokens, system=sistem,
                messages=[{"role": "user", "content": istem}],
                thinking={"type": "adaptive"},
                output_config={"format": bicim},
            ) as akis:
                yanit = akis.get_final_message()
        else:
            cikti_ayar = {"format": bicim}
            if efor:
                cikti_ayar["effort"] = efor
            yanit = istemci.messages.create(
                model=model, max_tokens=max_tokens, system=sistem,
                messages=[{"role": "user", "content": istem}],
                output_config=cikti_ayar,
            )
    except Exception as hata:
        mesaj = getattr(hata, "message", None) or str(hata)
        kod = getattr(hata, "status_code", None)
        raise LLMHata(f"{kod}: {mesaj}" if kod else f"{type(hata).__name__}: {mesaj}",
                      hesap=_hesap_hatasi(mesaj, kod), kod=kod) from hata

    if yanit.stop_reason == "refusal":
        raise LLMHata("model yanıtlamayı reddetti")
    if yanit.stop_reason == "max_tokens":
        raise LLMHata("yanıt çıktı sınırına takıldı")
    try:
        veri = json.loads(next(b.text for b in yanit.content if b.type == "text"))
    except Exception as hata:
        raise LLMHata(f"yanıt ayrıştırılamadı: {type(hata).__name__}") from hata
    k = yanit.usage
    return veri, {"girdi": k.input_tokens, "cikti": k.output_tokens,
                  "maliyet": maliyet(model, k.input_tokens, k.output_tokens),
                  "model": model, "arka_uc": "api"}


# --------------------------------------------------------------- cli arka uc
def _cli_model(model: str) -> str:
    """Tam model adini komut satirinin takma adina cevirir.

    Abonelikte hangi tam surumun acik oldugu degisebiliyor; takma ad
    ('opus', 'sonnet', 'haiku') her zaman o ailenin guncelini veriyor.
    """
    ozel = os.environ.get("GUNDEM_CLI_MODEL")
    if ozel:
        return ozel
    for aile in ("opus", "sonnet", "haiku", "fable"):
        if aile in model:
            return aile
    return "sonnet"


def _sema_talimati(sema: dict) -> str:
    return (
        "\n\n--- ÇIKTI BİÇİMİ (ZORUNLU) ---\n"
        "Yanıtın TEK bir JSON nesnesi olacak. Nesnenin önüne ya da arkasına\n"
        "hiçbir şey yazma: açıklama yok, selamlama yok, ```json çiti yok.\n"
        "Nesne şu JSON Şemasına birebir uyacak:\n"
        + json.dumps(sema, ensure_ascii=False)
    )


def _json_ayikla(metin: str):
    """Modelin yanitindan JSON nesnesini cikarir.

    Sistem istemi ciplak JSON istiyor, ama kod citi ya da tek satirlik bir
    giris yazisi gelebiliyor; ilk '{' ile son '}' arasini da deniyoruz.
    """
    metin = (metin or "").strip()
    if not metin:
        raise ValueError("boş yanıt")
    cit = re.match(r"^```(?:json)?\s*(.*?)\s*```$", metin, re.S)
    if cit:
        metin = cit.group(1).strip()
    try:
        return json.loads(metin)
    except ValueError:
        pass
    bas, son = metin.find("{"), metin.rfind("}")
    if bas == -1 or son <= bas:
        raise ValueError("yanıtta JSON nesnesi yok")
    return json.loads(metin[bas:son + 1])


def _sema_dogrula(veri, sema: dict) -> None:
    """Yalnizca ust duzey sozlesmeyi denetler: tur ve zorunlu alanlar.

    Tam JSON Sema dogrulamasi icin bagimlilik eklemiyoruz; buradaki amac
    sessizce bos/yanlis sekilli bir analizin yayina gitmesini engellemek.
    """
    if sema.get("type") == "object" and not isinstance(veri, dict):
        raise ValueError("JSON nesnesi bekleniyordu")
    eksik = [a for a in sema.get("required", []) if a not in (veri or {})]
    if eksik:
        raise ValueError("eksik alan: " + ", ".join(eksik))


def _cli(model, sistem, istem, sema, max_tokens, dusun, efor):
    exe = shutil.which("claude")
    if not exe:
        raise LLMHata("`claude` komutu bulunamadı — Claude Code kurulu değil",
                      hesap=True)
    seviye = efor or ("high" if dusun else "low")
    sistem_tam = sistem + _sema_talimati(sema)
    girdi_toplam = cikti_toplam = 0
    son_hata = ""

    for deneme in range(CLI_DENEME):
        istek = istem if deneme == 0 else (
            istem + f"\n\n--- ÖNCEKİ DENEME GEÇERSİZDİ ---\n{son_hata}\n"
            "Bu kez yalnızca şemaya uyan tek bir JSON nesnesi döndür.")
        # Calisma dizini olarak bos bir klasor: depodaki CLAUDE.md ve proje
        # ayarlari isteme karismasin, dosya araclari da zaten kapali.
        with tempfile.TemporaryDirectory() as bos:
            try:
                kosu = subprocess.run(
                    [exe, "-p", "--output-format", "json",
                     "--model", _cli_model(model),
                     "--system-prompt", sistem_tam,
                     "--effort", seviye,
                     "--tools", "",            # salt uretim: arac yok
                     "--strict-mcp-config",
                     "--setting-sources", ""],
                    input=istek, capture_output=True, text=True,
                    timeout=CLI_SURE, cwd=bos, check=False)
            except subprocess.TimeoutExpired as hata:
                raise LLMHata(f"claude {CLI_SURE} sn içinde yanıt vermedi") from hata

        if kosu.returncode != 0:
            hata_metni = (kosu.stderr or kosu.stdout or "").strip()[:400]
            raise LLMHata(f"claude çıkış kodu {kosu.returncode}: {hata_metni}",
                          hesap=_hesap_hatasi(hata_metni))
        try:
            kabuk = json.loads(kosu.stdout)
        except ValueError as hata:
            raise LLMHata("claude çıktısı okunamadı (JSON değil)") from hata

        k = kabuk.get("usage") or {}
        girdi_toplam += int(k.get("input_tokens") or 0) + int(
            k.get("cache_creation_input_tokens") or 0) + int(
            k.get("cache_read_input_tokens") or 0)
        cikti_toplam += int(k.get("output_tokens") or 0)

        if kabuk.get("is_error"):
            mesaj = str(kabuk.get("result") or kabuk.get("subtype") or "bilinmeyen")[:400]
            raise LLMHata(f"claude hata döndürdü: {mesaj}",
                          hesap=_hesap_hatasi(mesaj))
        try:
            veri = _json_ayikla(kabuk.get("result", ""))
            _sema_dogrula(veri, sema)
        except ValueError as hata:
            son_hata = str(hata)
            print(f"cli yanıtı şemaya uymadı ({son_hata}); yeniden soruluyor "
                  f"[{deneme + 1}/{CLI_DENEME}]")
            continue
        return veri, {"girdi": girdi_toplam, "cikti": cikti_toplam,
                      "maliyet": maliyet(model, girdi_toplam, cikti_toplam),
                      "model": model, "arka_uc": "cli"}

    raise LLMHata(f"cli yanıtı {CLI_DENEME} denemede şemaya uymadı: {son_hata}")


# ------------------------------------------------------------------ giris
def sor(*, model: str, sistem: str, istem: str, sema: dict,
        max_tokens: int = 16000, dusun: bool = False, efor: str | None = None):
    """Modele sorar, (veri, kullanim) dondurur. Hata halinde LLMHata atar.

    kullanim: {"girdi", "cikti", "maliyet", "model", "arka_uc"}
    """
    if ARKA_UC == "cli":
        return _cli(model, sistem, istem, sema, max_tokens, dusun, efor)
    if ARKA_UC == "api":
        return _api(model, sistem, istem, sema, max_tokens, dusun, efor)
    raise LLMHata(f"bilinmeyen arka uç: {ARKA_UC} (api ya da cli olmalı)",
                  hesap=True)
