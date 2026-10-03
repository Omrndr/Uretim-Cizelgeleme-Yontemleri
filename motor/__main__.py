"""
Komut satırı.

    python -m motor                              örnek senaryoyu çözer, raporu yazar
    python -m motor senaryo.json                 kendi senaryonuz
    python -m motor senaryo.json --fabrika f.json --paket Ciktilar
    python -m motor --duzenler                   bütün çalışma düzenlerini karşılaştırır
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from motor import analiz
from motor.cozucu import duzen_karsilastir, plan_olustur
from motor.model import (fabrika_yukle, senaryo_oku, varsayilan_personel,
                         veri_dizini)


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(prog="python -m motor",
                                 description="Üretim çizelgeleme motoru (komut satırı)")
    ap.add_argument("senaryo", nargs="?", default=str(veri_dizini() / "ornek_senaryo.json"))
    ap.add_argument("--fabrika", default="", help="fabrika tanımı (JSON)")
    ap.add_argument("--paket", default="", help="çıktı paketinin yazılacağı klasör")
    ap.add_argument("--pdf-yok", action="store_true", help="PDF yerine HTML bırak")
    ap.add_argument("--duzenler", action="store_true", help="düzen karşılaştırması")
    a = ap.parse_args(argv)

    sen = senaryo_oku(a.senaryo)
    fabrika = fabrika_yukle(a.fabrika or sen.fabrika_dosyasi or None)
    personel = sen.personel or varsayilan_personel(fabrika.personel_sayisi)
    if a.duzenler:
        for satir in duzen_karsilastir(fabrika, sen.siparisler, sen.baslangic,
                                       sen.ek_mesailer, sen.ayarlar, personel):
            print(" | ".join(f"{k}: {v}" for k, v in satir.items()))
        return 0

    def ilerleme(oran: float, mesaj: str) -> None:
        print(f"\r[{oran * 100:5.1f}%] {mesaj:<60}", end="", file=sys.stderr, flush=True)

    plan = plan_olustur(fabrika, sen.siparisler, sen.baslangic, sen.ek_mesailer, sen.ayarlar,
                        personel, ilerleme=ilerleme)
    print(file=sys.stderr)
    print(analiz.duz_metin_rapor(plan))
    if a.paket:
        from rapor.paket import paket_olustur
        klasor, ozet = paket_olustur(plan, Path(a.paket), pdf=not a.pdf_yok,
                                     ilerleme=ilerleme)
        print(file=sys.stderr)
        print(f"\nÇıktı paketi: {klasor}\n  {ozet['belge']} belge "
              f"({ozet['pdf']} PDF, {ozet['html']} HTML)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
