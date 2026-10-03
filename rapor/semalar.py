"""
Atölye şemaları — sahaya basılan saat ölçekli çizelgeler.

    GÜNLÜK  · A4 yatay · 1 sayfa = 1 atölye × 1 üretim günü (vardiya başında dağıtılır)
    HAFTALIK· A3 yatay · 1 sayfa = 1 atölye × 1 hafta      (atölye panosuna asılır)

Her çubuk zaman, kaynak, personel ve iş emri bilgisini birlikte taşır. Molalar
gri, varsayılan vardiya bitişinden sonraki ek mesai bölgesi sarı zeminle
gösterilir; ayar çubukları koyu ve taralıdır.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, timedelta
from typing import Dict, List, Sequence

from motor.cozucu import Plan
from motor.model import saat_yaz
from motor.takvim import GUN, SAAT
from rapor import cizim as cz
from rapor.is_emirleri import KAYNAK_NOTU, GUN_KISALTMA, IsEmri, suz

GUN_ADI = ("Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar")


def _saat(plan: Plan, t: float, gun: date) -> float:
    """Mutlak anı, üretim gününün 00:00'ına göre saate çevirir."""
    return (t - (gun - plan.baslangic).days * GUN) / SAAT


def atolye_kaynaklari(plan: Plan, atolye: str) -> List[str]:
    return [k.ad for k in plan.kaynaklar if k.atolye == atolye]


def _ust_bilgi(s: cz.Sahne, plan: Plan, baslik: str, alt: str, renk: str) -> None:
    s.dik(0, 0, s.genislik, 6, dolgu=renk)
    s.yazi(28, 40, baslik, 20, kalin=True)
    s.yazi(28, 62, alt, 12, cz.GRI)
    s.yazi(s.genislik - 28, 40, plan.fabrika.ad, 11, cz.GRI, hiza="end")
    s.yazi(s.genislik - 28, 58, f"Düzen {plan.takvim.duzen.etiket} · K={plan.parti_sayisi}",
           10, cz.GRI, hiza="end")


def _lejant(s: cz.Sahne, x: float, y: float, renk: str) -> None:
    ogeler = [("Üretim", renk, False), ("Ayar", cz.AYAR_RENGI, True),
              ("Mola", cz.MOLA_RENGI, False), ("Ek mesai bölgesi", cz.MESAI_RENGI, False)]
    for ad, dolgu, tarama in ogeler:
        s.dik(x, y - 9, 14, 10, dolgu=dolgu, renk=cz.IZGARA, tarama=tarama)
        s.yazi(x + 19, y, ad, 10, cz.GRI)
        x += 28 + cz.metin_genisligi(ad, 10)


def _cubuk(s: cz.Sahne, x0: float, x1: float, y: float, h: float, r: IsEmri,
           renk: str, ayrintili: bool) -> None:
    ayar = r.tur == "Ayar"
    dolgu = cz.AYAR_RENGI if ayar else renk
    ipucu = f"{r.kaynak} · {r.personel} · {r.gorev} · {r.siparis} · {r.adet} adet"
    s.dik(x0, y, max(1.5, x1 - x0), h, dolgu=dolgu, renk="#ffffff", kalinlik=0.8,
          tarama=ayar, ipucu=ipucu)
    w = x1 - x0 - 6
    if w < 14:
        return
    ust = f"{r.personel} · {'AYAR' if ayar else r.siparis}"
    s.yazi(x0 + 3, y + min(14, h * 0.55), cz.uydur(ust, w, 10), 10, "#ffffff", kalin=True)
    if ayrintili and h >= 30:
        alt = r.gorev if ayar else f"{r.gorev} · {r.adet} ad"
        s.yazi(x0 + 3, y + h - 7, cz.uydur(alt, w, 9), 9, "#ffffff")


def gun_plani(plan: Plan, emirler: Sequence[IsEmri], atolye: str, gun: date
              ) -> cz.Sahne:
    W, H = cz.A4_YATAY
    s = cz.Sahne(W, H, baslik=f"{atolye} {gun:%d.%m.%Y}")
    renk = cz.atolye_rengi(plan.fabrika.atolyeler, atolye)
    satirlar = [r for r in suz(emirler, atolye=atolye, bas=gun, bit=gun)]
    kaynaklar = atolye_kaynaklari(plan, atolye)
    kural, duzen = plan.fabrika.takvim, plan.takvim.duzen
    _ust_bilgi(s, plan, f"{atolye} — Günlük İş Planı",
               f"{gun:%d.%m.%Y} {GUN_ADI[gun.weekday()]} · {len(satirlar)} iş emri satırı",
               renk)
    _lejant(s, 28, 88, renk)

    t0 = kural.baslangic
    t1 = max([duzen.brut_bitis] + [_saat(plan, r.bit, gun) for r in satirlar])
    t1 = math.ceil(t1)
    sol, sag, ust = 150.0, W - 28.0, 112.0
    satir_h = min(44.0, 300.0 / max(1, len(kaynaklar)))
    alt = ust + 18 + satir_h * len(kaynaklar)

    def x(saat: float) -> float:
        return sol + (sag - sol) * (saat - t0) / max(1e-9, t1 - t0)

    # zemin: ek mesai bölgesi ve molalar
    if t1 > duzen.brut_bitis:
        s.dik(x(duzen.brut_bitis), ust + 18, x(t1) - x(duzen.brut_bitis), alt - ust - 18,
              dolgu=cz.MESAI_RENGI)
    for a, b in kural.gunun_molalari(gun.weekday()):
        if b > t0 and a < t1:
            s.dik(x(max(a, t0)), ust + 18, x(min(b, t1)) - x(max(a, t0)), alt - ust - 18,
                  dolgu=cz.MOLA_RENGI)
    for h in range(int(t0), int(t1) + 1):
        xx = x(h)
        if xx < sol - 1:
            continue
        s.cizgi(xx, ust + 14, xx, alt, cz.IZGARA, 0.6)
        s.yazi(xx, ust + 10, saat_yaz(h)[:5], 9, cz.GRI, hiza="middle")
    yer = {k: ust + 18 + i * satir_h for i, k in enumerate(kaynaklar)}
    kisi: Dict[str, List[str]] = defaultdict(list)
    for r in satirlar:
        if r.personel not in kisi[r.kaynak]:
            kisi[r.kaynak].append(r.personel)
    for k, y in yer.items():
        s.cizgi(28, y + satir_h, sag, y + satir_h, cz.IZGARA, 0.6)
        s.yazi(28, y + satir_h / 2 + 1, k, 12, kalin=True)
        if kisi.get(k):
            s.yazi(28, y + satir_h / 2 + 14, cz.uydur(", ".join(kisi[k]), 115, 9), 9, cz.GRI)
        elif satir_h >= 24:
            s.yazi(28, y + satir_h / 2 + 14, "boşta", 9, cz.GRI)
    for r in satirlar:
        y = yer.get(r.kaynak)
        if y is None:
            continue
        _cubuk(s, x(_saat(plan, r.bas, gun)), x(_saat(plan, r.bit, gun)),
               y + 4, satir_h - 8, r, renk, True)

    # Alt tablo: aynı bilgi, okunur biçimde
    sutun = [("Kaynak", 28), ("V", 108), ("Saat", 130), ("Personel", 222), ("Görev", 300),
             ("İş emri / sipariş", 560), ("Varyant", 760), ("Adet", 1000)]
    yt = alt + 30
    for ad, xx in sutun:
        s.yazi(xx, yt, ad, 10, cz.GRI, kalin=True)
    s.cizgi(28, yt + 5, sag, yt + 5, cz.IZGARA)
    satir_yuk = 15
    sigan = int((H - 40 - (yt + 8)) / satir_yuk)
    tk = plan.takvim
    for i, r in enumerate(sorted(satirlar, key=lambda r: (r.kaynak, r.bas))[:sigan]):
        yy = yt + 20 + i * satir_yuk
        degerler = [r.kaynak, str(r.vardiya),
                    f"{tk.zamana(r.bas):%H:%M}–{tk.zamana(r.bit):%H:%M}", r.personel,
                    r.gorev, "AYAR" if r.tur == "Ayar" else r.siparis, r.varyant,
                    str(r.adet) if r.adet else "-"]
        for (_, xx), (j, v) in zip(sutun, enumerate(degerler)):
            genislik = (sutun[j + 1][1] - xx - 8) if j + 1 < len(sutun) else 80
            s.yazi(xx, yy, cz.uydur(v, genislik, 10), 10)
    if len(satirlar) > sigan:
        s.yazi(28, H - 34, f"… ve {len(satirlar) - sigan} satır daha — tam liste iş emri "
               f"tablosunda.", 9, cz.KOTU)
    s.yazi(28, H - 18, KAYNAK_NOTU, 8.5, cz.GRI)
    s.yazi(sag, H - 18, f"Plan başlangıcı {plan.baslangic:%d.%m.%Y}", 8.5, cz.GRI, hiza="end")
    return s


def hafta_basi(g: date) -> date:
    return g - timedelta(days=g.weekday())


def hafta_plani(plan: Plan, emirler: Sequence[IsEmri], atolye: str,
                pazartesi: date) -> cz.Sahne:
    W, H = cz.A3_YATAY
    s = cz.Sahne(W, H, baslik=f"{atolye} hafta {pazartesi:%d.%m.%Y}")
    renk = cz.atolye_rengi(plan.fabrika.atolyeler, atolye)
    pazar = pazartesi + timedelta(days=6)
    satirlar = suz(emirler, atolye=atolye, bas=pazartesi, bit=pazar)
    calisan = {r.tarih for r in satirlar}
    gunler = [pazartesi + timedelta(days=i) for i in range(7)
              if i < plan.takvim.duzen.gun or (pazartesi + timedelta(days=i)) in calisan]
    kaynaklar = atolye_kaynaklari(plan, atolye)
    kural, duzen = plan.fabrika.takvim, plan.takvim.duzen
    _ust_bilgi(s, plan, f"{atolye} — Haftalık Plan",
               f"{pazartesi:%d.%m.%Y} – {pazar:%d.%m.%Y} · {len(satirlar)} iş emri satırı", renk)
    _lejant(s, 28, 88, renk)

    t0 = kural.baslangic
    t1 = math.ceil(max([duzen.brut_bitis] + [_saat(plan, r.bit, r.tarih) for r in satirlar]))
    sol, sag, ust = 150.0, W - 28.0, 130.0
    sutun_w = (sag - sol) / max(1, len(gunler))
    satir_h = min(64.0, (H - ust - 210) / max(1, len(kaynaklar)))
    alt = ust + 34 + satir_h * len(kaynaklar)

    def x(gi: int, saat: float) -> float:
        return sol + gi * sutun_w + 4 + (sutun_w - 8) * (saat - t0) / max(1e-9, t1 - t0)

    for gi, g in enumerate(gunler):
        x0 = sol + gi * sutun_w
        s.dik(x0, ust, sutun_w, 30, dolgu="#fafaf9", renk=cz.IZGARA, kalinlik=0.6)
        s.yazi(x0 + sutun_w / 2, ust + 19, f"{GUN_KISALTMA[g.weekday()]} {g:%d.%m}", 12,
               hiza="middle", kalin=True)
        if g.weekday() >= duzen.gun:
            s.dik(x0, ust + 30, sutun_w, alt - ust - 30, dolgu=cz.KAPALI_RENGI)
        if t1 > duzen.brut_bitis:
            s.dik(x(gi, duzen.brut_bitis), ust + 34, x(gi, t1) - x(gi, duzen.brut_bitis),
                  alt - ust - 34, dolgu=cz.MESAI_RENGI)
        for a, b in kural.gunun_molalari(g.weekday()):
            s.dik(x(gi, a), ust + 34, x(gi, b) - x(gi, a), alt - ust - 34, dolgu=cz.MOLA_RENGI)
        s.cizgi(x0, ust, x0, alt, "#a8a29e", 1.0)
        adim = 2 if (t1 - t0) > 12 else 1
        for h in range(int(t0), int(t1) + 1, adim):
            s.cizgi(x(gi, h), ust + 30, x(gi, h), ust + 34, cz.GRI, 0.6)
    s.cizgi(sag, ust, sag, alt, "#a8a29e", 1.0)
    yer = {k: ust + 34 + i * satir_h for i, k in enumerate(kaynaklar)}
    for k, y in yer.items():
        s.cizgi(28, y + satir_h, sag, y + satir_h, cz.IZGARA, 0.6)
        s.yazi(28, y + satir_h / 2 + 4, k, 13, kalin=True)
    gun_indeksi = {g: i for i, g in enumerate(gunler)}
    for r in satirlar:
        gi = gun_indeksi.get(r.tarih)
        y = yer.get(r.kaynak)
        if gi is None or y is None:
            continue
        _cubuk(s, x(gi, _saat(plan, r.bas, r.tarih)), x(gi, _saat(plan, r.bit, r.tarih)),
               y + 5, satir_h - 10, r, renk, satir_h >= 40)

    # Günlük özet
    yt = alt + 34
    s.yazi(28, yt, "Gün özeti", 12, kalin=True)
    for gi, g in enumerate(gunler):
        gs = [r for r in satirlar if r.tarih == g]
        kisiler = sorted({r.personel for r in gs if r.personel not in ("-",)})
        uretim = sum(r.adet for r in gs if r.tur != "Ayar")
        ayar = sum(1 for r in gs if r.tur == "Ayar")
        x0 = sol + gi * sutun_w + 6
        s.yazi(x0, yt, f"{len(kisiler)} personel · {uretim} adet", 11)
        s.yazi(x0, yt + 16, f"{ayar} ayar" if ayar else "ayar yok", 10, cz.GRI)
        s.yazi(x0, yt + 32, cz.uydur(", ".join(kisiler), sutun_w - 12, 9), 9, cz.GRI)
    s.yazi(28, H - 22, KAYNAK_NOTU + " Makine satırlarında adet parça sayısıdır.", 9, cz.GRI)
    return s


def haftalar(emirler: Sequence[IsEmri]) -> List[date]:
    return sorted({hafta_basi(r.tarih) for r in emirler})


def gunler(emirler: Sequence[IsEmri], atolye: str) -> List[date]:
    return sorted({r.tarih for r in emirler if r.atolye == atolye})
