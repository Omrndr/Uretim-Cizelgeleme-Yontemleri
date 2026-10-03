"""
Overview — planlamacı için iki panel (sahaya inmez).

    PANEL 1 · TERMİN ÇİZELGESİ   satır = sipariş; üretim aralığı, termin işareti,
                                 erken/geç gün sayısı → "yetişiyor muyum?"
    PANEL 2 · HAFTA × ATÖLYE     hücre = o hafta atölyenin utilization (heatmap),
                                 alt satırlar: çalışan personel ve ayar sayısı
                                 → "nerede sıkışıyorum?"

Utilization çalışma saniyesiyle hesaplanır: haftalık meşgul çalışma süresi /
haftalık açık çalışma süresi (atölyedeki bütün kaynaklar toplamı).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Dict, List, Tuple

from motor import cubuklar as cb
from motor.cozucu import Plan
from motor.takvim import GUN
from rapor import cizim as cz
from rapor.semalar import hafta_basi

AY = ("Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara")


def _isi_rengi(oran: float) -> str:
    """0 → açık gri, 1 → koyu turuncu (tek renk tonlu sıralı ölçek)."""
    oran = max(0.0, min(1.0, oran))
    a = (245, 245, 244)
    b = (194, 65, 12)
    r, g, bb = (round(a[i] + (b[i] - a[i]) * oran) for i in range(3))
    return f"#{r:02x}{g:02x}{bb:02x}"


def hafta_atolye_kullanimi(plan: Plan) -> Tuple[List[date], Dict[Tuple[str, date], float],
                                                Dict[date, int], Dict[date, int]]:
    tk = plan.takvim
    mesgul = cb.mesgul_araliklar(plan)
    son_gun = tk.hangi_gun(plan.makespan)
    haftalar_ = []
    h = hafta_basi(plan.baslangic)
    while h <= son_gun:
        haftalar_.append(h)
        h += timedelta(days=7)
    dolu: Dict[Tuple[str, date], float] = defaultdict(float)
    acik: Dict[Tuple[str, date], float] = defaultdict(float)
    for k in plan.kaynaklar:
        takvim = tk.takvim(k.ad)
        for h in haftalar_:
            a = max(0.0, (h - plan.baslangic).days * GUN)
            b = (h - plan.baslangic).days * GUN + 7 * GUN
            acik[(k.atolye, h)] += takvim.calisma(a, b)
            dolu[(k.atolye, h)] += sum(takvim.calisma(max(a, x), min(b, y))
                                       for x, y in mesgul.get(k.ad, []) if y > a and x < b)
    oran = {anahtar: (dolu[anahtar] / acik[anahtar]) if acik[anahtar] > 0 else 0.0
            for anahtar in acik}
    kisi: Dict[date, set] = defaultdict(set)
    if plan.atama:
        for g in plan.atama.gorevler:
            kisi[hafta_basi(g.tarih)].add(g.personel)
    ayar: Dict[date, int] = defaultdict(int)
    for p in (*plan.parca_partileri, *plan.varyant.partiler):
        if p.ayar_var:
            ayar[hafta_basi(tk.hangi_gun(p.ayar_bas))] += 1
    return haftalar_, oran, {h: len(v) for h, v in kisi.items()}, dict(ayar)


def genel_bakis(plan: Plan) -> cz.Sahne:
    W, H = cz.A4_YATAY
    s = cz.Sahne(W, H, baslik="Overview")
    tk = plan.takvim
    s.dik(0, 0, W, 6, dolgu=cz.ATOLYE_RENKLERI[0])
    s.yazi(28, 40, "Overview — Termin ve Doluluk", 20, kalin=True)
    durum = "bütün siparişler zamanında" if plan.termine_uygun else \
        f"en büyük gecikme {plan.en_buyuk_gecikme:.1f} gün"
    s.yazi(28, 62, f"{plan.urun_sayisi} adet · bitiş {plan.bitis_tarihi:%d.%m.%Y} · {durum}",
           12, cz.IYI if plan.termine_uygun else cz.KOTU)
    s.yazi(W - 28, 40, plan.fabrika.ad, 11, cz.GRI, hiza="end")

    # ---------------------------------------------------------------- panel 1
    siparisler = sorted(plan.siparisler, key=lambda x: (x.termin, x.kod))
    bas = plan.baslangic
    son = max([tk.hangi_gun(plan.makespan)] + [x.termin for x in siparisler]) + timedelta(days=2)
    sol, sag, ust = 160.0, W - 40.0, 100.0
    gun_say = max(1, (son - bas).days)

    def x(g) -> float:
        return sol + (sag - sol) * g / gun_say

    s.yazi(28, ust, "1 · Termin çizelgesi", 13, kalin=True)
    y0 = ust + 26
    # ay ve hafta çizgileri
    g = bas
    while g <= son:
        if g.weekday() == 0:
            s.cizgi(x((g - bas).days), y0, x((g - bas).days), y0 + 26 * len(siparisler) + 4,
                    cz.IZGARA, 0.6)
            s.yazi(x((g - bas).days), y0 - 4, f"{g.day} {AY[g.month - 1]}", 8.5, cz.GRI,
                   hiza="middle")
        g += timedelta(days=1)
    son_ist = plan.fabrika.istasyonlar[-1].kod
    ilk_bitis: Dict[str, float] = {}
    for (kod, _), t in zip(plan.sira, plan.akis.bit[son_ist]):
        ilk_bitis[kod] = min(ilk_bitis.get(kod, t), t)
    for i, sp in enumerate(siparisler):
        y = y0 + 6 + i * 26
        gecikme = plan.gecikme_gun.get(sp.kod, 0.0)
        renk = cz.IYI if gecikme <= 1e-9 else cz.KOTU
        s.yazi(28, y + 13, sp.kod, 12, kalin=True)
        s.yazi(92, y + 13, f"{sp.toplam} ad", 10, cz.GRI)
        a = ilk_bitis.get(sp.kod, 0.0) / GUN
        b = plan.siparis_bitis.get(sp.kod, 0.0) / GUN
        s.dik(x(a), y + 3, max(2.0, x(b) - x(a)), 14, dolgu=renk,
              ipucu=f"{sp.kod}: {tk.zamana(a * GUN):%d.%m} – {tk.zamana(b * GUN):%d.%m.%Y}")
        xt = x((sp.termin - bas).days + 1)
        s.cizgi(xt, y - 1, xt, y + 21, cz.KOYU, 2.0)
        etiket = f"{abs(gecikme):.1f} gün {'erken' if gecikme <= 0 else 'GEÇ'}"
        xe = max(x(b), xt) + 4
        if xe + 90 > W:                       # sağ kenara taşmasın: çizginin soluna yaz
            s.yazi(xt - 4, y + 8, f"termin {sp.termin:%d.%m}", 8.5, cz.GRI, hiza="end")
            s.yazi(xt - 4, y + 19, etiket, 9, renk, hiza="end", kalin=True)
        else:
            s.yazi(xt + 4, y + 8, f"termin {sp.termin:%d.%m}", 8.5, cz.GRI)
            s.yazi(xe, y + 19, etiket, 9, renk, kalin=True)

    # ---------------------------------------------------------------- panel 2
    haftalar_, oran, kisi, ayar = hafta_atolye_kullanimi(plan)
    ust2 = y0 + 26 * len(siparisler) + 50
    s.yazi(28, ust2, "2 · Hafta × atölye utilization", 13, kalin=True)
    atolyeler = plan.fabrika.atolyeler
    hucre_w = min(70.0, (sag - sol) / max(1, len(haftalar_)))
    hucre_h = 26.0
    yb = ust2 + 30
    for j, h in enumerate(haftalar_):
        s.yazi(sol + j * hucre_w + hucre_w / 2, yb - 6, f"{h:%d.%m}", 9, cz.GRI, hiza="middle")
    for i, a in enumerate(atolyeler):
        y = yb + i * hucre_h
        s.yazi(28, y + 17, cz.uydur(a, sol - 36, 10.5), 10.5)
        for j, h in enumerate(haftalar_):
            o = oran.get((a, h), 0.0)
            s.dik(sol + j * hucre_w, y, hucre_w - 2, hucre_h - 2, dolgu=_isi_rengi(o),
                  ipucu=f"{a} · {h:%d.%m}: %{100 * o:.0f}")
            if hucre_w >= 34:
                s.yazi(sol + j * hucre_w + hucre_w / 2 - 1, y + 16, f"{100 * o:.0f}", 9.5,
                       "#ffffff" if o > 0.55 else cz.KOYU, hiza="middle")
    y = yb + len(atolyeler) * hucre_h + 8
    for etiket, veri in (("Çalışan personel", kisi), ("Ayar sayısı", ayar)):
        s.yazi(28, y + 14, etiket, 10, cz.GRI)
        for j, h in enumerate(haftalar_):
            if hucre_w >= 26:
                s.yazi(sol + j * hucre_w + hucre_w / 2 - 1, y + 14, str(veri.get(h, 0)), 9.5,
                       cz.KOYU, hiza="middle")
        y += 20
    # ölçek
    for k in range(11):
        s.dik(W - 260 + k * 20, H - 46, 20, 10, dolgu=_isi_rengi(k / 10))
    s.yazi(W - 260, H - 52, "kullanım %0", 8.5, cz.GRI)
    s.yazi(W - 40, H - 52, "%100", 8.5, cz.GRI, hiza="end")
    s.yazi(28, H - 22, "Kullanım = meşgul çalışma süresi / açık çalışma süresi (molalar ve "
           "kapalı günler hariç).", 9, cz.GRI)
    return s
