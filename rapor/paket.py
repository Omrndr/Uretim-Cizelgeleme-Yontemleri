"""
Çıktı paketi — planı yazıcıya hazır dosyalar hâlinde diske yazar.

    Ciktilar/
      Plan_2026-11-02_(oluşturma 2026-10-03 14-05)/
        BENIOKU.txt
        00_Genel_Bakis.pdf
        01_Plan_Raporu.txt
        02_Plan_Tablolari.xlsx
        03_Is_Emirleri.csv
        Hafta 01 (02.11-08.11)/
          CNC Torna Atolyesi/
            _Haftalik_Plan.pdf          (A3, panoya asılır)
            Gun_2026-11-02_Pzt.pdf      (A4, vardiya başında dağıtılır)
            ...
          Montaj ve Test Hatti/
          ...
        Personel Kartlari/
          P01.pdf                       (personelin bütün görevleri)

Hafta numarası plan içinde sıralıdır (ilk hafta daima "Hafta 01"); yıl dönümünde
klasör sırası bozulmaz. Bir haftanın bütün belgeleri aynı klasördedir: o hafta
gelince klasör açılır, hepsi seçilip yazdırılır.

PDF ÜRETİMİ: Ek kütüphane kurulmaz. Bilgisayarda bulunan Chromium tabanlı bir
tarayıcı (Edge / Chrome / Chromium) "headless" kipte çağrılır ve HTML → PDF
çevrilir. Tarayıcı yoksa dosyalar HTML olarak kalır; tarayıcıda açılıp Ctrl+P ile
aynı sayfa düzeninde yazdırılabilir.
"""
from __future__ import annotations

import concurrent.futures as cf
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from motor import analiz as an
from motor.cozucu import Plan
from rapor import cizim as cz
from rapor import genel_bakis as gb
from rapor import semalar as sm
from rapor import tablolar as tb
from rapor.is_emirleri import GUN_KISALTMA, BASLIKLAR, IsEmri, is_emirleri, personel_karti, tablo

_TR = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
_YASAK = re.compile(r'[<>:"/\\|?*]')

_TARAYICILAR = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
)
_KOMUTLAR = ("msedge", "chrome", "google-chrome", "chromium", "chromium-browser")


def guvenli_ad(metin: str) -> str:
    return _YASAK.sub("-", metin.translate(_TR)).strip(" .")


def pdf_tarayicisi() -> Optional[str]:
    ortam = os.environ.get("CIZELGE_TARAYICI")
    if ortam and Path(ortam).exists():
        return ortam
    for yol in _TARAYICILAR:
        if Path(yol).exists():
            return yol
    for komut in _KOMUTLAR:
        bulunan = shutil.which(komut)
        if bulunan:
            return bulunan
    return None


def html_pdf(html: Path, pdf: Path, tarayici: str, zaman_asimi: int = 90) -> bool:
    profil = tempfile.mkdtemp(prefix="cizelge_")
    try:
        komut = [tarayici, "--headless=new", "--disable-gpu", "--no-sandbox",
                 "--no-first-run", "--no-pdf-header-footer", f"--user-data-dir={profil}",
                 f"--print-to-pdf={pdf}", html.resolve().as_uri()]
        bayrak = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.run(komut, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=zaman_asimi, creationflags=bayrak)
        return pdf.exists() and pdf.stat().st_size > 0
    except (OSError, subprocess.SubprocessError):
        return False
    finally:
        shutil.rmtree(profil, ignore_errors=True)


def _personel_html(plan: Plan, emirler: List[IsEmri], kisi: str) -> str:
    satirlar = [[r["Tarih"], r["Gün"], r["Başlangıç"], r["Bitiş"], r["Kaynak"], r["Görev"],
                 r["Sipariş"], r["Adet"]] for r in tablo(plan, personel_karti(emirler, kisi))]
    govde = cz.tablo_html(["Tarih", "Gün", "Başlangıç", "Bitiş", "Kaynak", "Görev",
                           "Sipariş", "Adet"], satirlar, f"Personel kartı — {kisi}",
                          f"{plan.fabrika.ad} · plan başlangıcı {plan.baslangic:%d.%m.%Y}")
    return cz.html_belgesi([], f"Personel {kisi}", "A4", govde).replace(
        "landscape", "portrait")


def paket_olustur(plan: Plan, kok: Path, pdf: bool = True,
                  ilerleme: Optional[Callable[[float, str], None]] = None) -> Tuple[Path, dict]:
    """Paketi oluşturur. Dönüş: (paket klasörü, özet sözlüğü)."""
    def bildir(oran: float, mesaj: str) -> None:
        if ilerleme:
            ilerleme(oran, mesaj)

    damga = datetime.now().strftime("%Y-%m-%d %H-%M")
    hedef = Path(kok) / f"Plan_{plan.baslangic:%Y-%m-%d} (olusturma {damga})"
    hedef.mkdir(parents=True, exist_ok=True)
    bildir(0.02, "İş emirleri hazırlanıyor...")
    emirler = is_emirleri(plan)

    gorevler: List[Tuple[Path, str]] = []        # (html yolu, kağıt)

    def html_yaz(yol: Path, icerik: str) -> None:
        yol.parent.mkdir(parents=True, exist_ok=True)
        yol.write_text(icerik, encoding="utf-8")
        gorevler.append((yol, icerik))

    html_yaz(hedef / "00_Genel_Bakis.html",
             cz.html_belgesi([gb.genel_bakis(plan)], "Genel bakış", "A4"))
    (hedef / "01_Plan_Raporu.txt").write_text(an.duz_metin_rapor(plan), encoding="utf-8")
    tb.plan_calisma_kitabi(plan, hedef / "02_Plan_Tablolari.xlsx", emirler)
    tb.csv_yaz(hedef / "03_Is_Emirleri.csv", tablo(plan, emirler), BASLIKLAR)

    haftalar = sm.haftalar(emirler)
    atolyeler = plan.fabrika.atolyeler
    toplam = max(1, len(haftalar) * len(atolyeler))
    for hi, pzt in enumerate(haftalar, start=1):
        klasor = hedef / f"Hafta {hi:02d} ({pzt:%d.%m}-{pzt + timedelta(days=6):%d.%m})"
        for ai, atolye in enumerate(atolyeler):
            bildir(0.05 + 0.35 * ((hi - 1) * len(atolyeler) + ai) / toplam,
                   f"Hafta {hi:02d} · {atolye}")
            alt = klasor / guvenli_ad(atolye)
            hafta_emir = [r for r in emirler if r.atolye == atolye
                          and pzt <= r.tarih <= pzt + timedelta(days=6)]
            if not hafta_emir:
                continue
            html_yaz(alt / "_Haftalik_Plan.html",
                     cz.html_belgesi([sm.hafta_plani(plan, emirler, atolye, pzt)],
                                     f"{atolye} haftalık", "A3"))
            for g in sorted({r.tarih for r in hafta_emir}):
                html_yaz(alt / f"Gun_{g:%Y-%m-%d}_{guvenli_ad(GUN_KISALTMA[g.weekday()])}.html",
                         cz.html_belgesi([sm.gun_plani(plan, emirler, atolye, g)],
                                         f"{atolye} {g:%d.%m.%Y}", "A4"))
    kisiler = sorted({r.personel for r in emirler if r.personel not in ("-", "ATANAMADI")})
    for kisi in kisiler:
        html_yaz(hedef / "Personel Kartlari" / f"{guvenli_ad(kisi)}.html",
                 _personel_html(plan, emirler, kisi))

    ozet = {"klasor": str(hedef), "belge": len(gorevler), "pdf": 0, "html": 0,
            "tarayici": None}
    tarayici = pdf_tarayicisi() if pdf else None
    ozet["tarayici"] = tarayici
    if tarayici:
        tamam = 0

        def pdfe_cevir(gorev: Tuple[Path, str]) -> bool:
            yol, _ = gorev
            hedef_pdf = yol.with_suffix(".pdf")
            if html_pdf(yol, hedef_pdf, tarayici):
                yol.unlink(missing_ok=True)
                return True
            return False

        with cf.ThreadPoolExecutor(max_workers=min(4, os.cpu_count() or 2)) as havuz:
            for i, sonuc in enumerate(havuz.map(pdfe_cevir, gorevler), start=1):
                tamam += sonuc
                bildir(0.40 + 0.58 * i / len(gorevler), f"PDF {i}/{len(gorevler)}")
        ozet["pdf"] = tamam
        ozet["html"] = len(gorevler) - tamam
    else:
        ozet["html"] = len(gorevler)
    (hedef / "BENIOKU.txt").write_text(_benioku(plan, ozet, len(haftalar)), encoding="utf-8")
    bildir(1.0, "Paket hazır.")
    return hedef, ozet


def _benioku(plan: Plan, ozet: dict, hafta: int) -> str:
    bicim = "PDF" if ozet["pdf"] else "HTML"
    return f"""ÜRETİM PLANI ÇIKTI PAKETİ
==========================
Fabrika        : {plan.fabrika.ad}
Plan başlangıcı: {plan.baslangic:%d.%m.%Y}
Bitiş          : {plan.bitis_tarihi:%d.%m.%Y %H:%M}
Toplam adet    : {plan.urun_sayisi}
Termine uygun  : {"EVET" if plan.termine_uygun else "HAYIR"}
Hafta sayısı   : {hafta}
Belge          : {ozet["belge"]} ({ozet["pdf"]} PDF, {ozet["html"]} HTML)

İÇİNDEKİLER
  00_Genel_Bakis      termin çizelgesi ve hafta × atölye kullanım ısı haritası
  01_Plan_Raporu.txt  kapasite, dengeleme, parti araması, uyarı panoları
  02_Plan_Tablolari   bütün tablolar (Excel / LibreOffice ile açılır)
  03_Is_Emirleri.csv  zaman · kaynak · personel · iş emri satırları
  Hafta NN/<atölye>/  _Haftalik_Plan (A3) + her gün için Gun_... (A4)
  Personel Kartlari/  her personelin görev listesi

YAZDIRMA
  Belgeler {bicim} biçimindedir. Haftalık planlar A3 yatay, günlük planlar A4
  yatay basılır. HTML dosyaları tarayıcıda açılıp Ctrl+P ile yazdırılabilir.
"""
