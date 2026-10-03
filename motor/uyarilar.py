"""
Uyarı panoları — planı değiştirmeden ölçer: hangi sınır zorlanıyor, hangi grup yetmiyor.

PANO A · YASAL DURUM   — "Sınırları aşıyor muyum?"
    günlük, haftalık, yıllık fazla çalışma ve atanamayan vardiyalar.

PANO B · HAT YETERLİLİĞİ — "Hangi hat yetmiyor, günde kaç saat eksik?"
    Her kaynak grubu için ANALİTİK günlük ihtiyaç (yeniden planlama yapılmaz):

        h_gerekli = N · τ_g / ( c_g · 3600 · D )        [saat / gün / kaynak]
        açık      = h_gerekli − h_mevcut

    N: termine kadar üretilecek adet, τ_g: grubun ürün başına süresi
    (parça makinesinde makinenin yükü L_k), c_g: gruptaki kaynak sayısı,
    D: plan başı ile termin arasındaki iş günü, h_mevcut: grubun ortalama
    günlük net çalışma saati. Açığı en büyük grup kritik hattır.

    Açık ≤ 0 iken sipariş yine gecikiyorsa kararlı durum kapasitesi yeterlidir;
    gecikme geçici etkilerden (ayar kayıpları, hattın dolma süresi, sıra bekleme)
    kaynaklanır.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Tuple

from motor import cubuklar as cb
from motor.cozucu import Plan, _kapasite_gruplari

TAMAM, DIKKAT, IHLAL = "TAMAM", "DİKKAT", "İHLAL"
SEMBOL = {TAMAM: "✔", DIKKAT: "▲", IHLAL: "✖"}


@dataclass
class PanoSatiri:
    durum: str
    baslik: str
    detay: str = ""

    def __str__(self) -> str:
        return f"{SEMBOL[self.durum]} {self.baslik}" + (f" — {self.detay}" if self.detay else "")


@dataclass
class GrupAcigi:
    grup: str
    atolye: str
    kaynaklar: List[str]
    birim_sn: float
    kullanim: float
    mevcut_saat: float
    gerekli_saat: float

    @property
    def acik(self) -> float:
        return self.gerekli_saat - self.mevcut_saat


@dataclass
class GecikmeAnalizi:
    kod: str
    gecikme_gun: float
    termin: date
    kritik: Optional[GrupAcigi] = None
    en_dolu: List[GrupAcigi] = field(default_factory=list)


def mevzuat_panosu(plan: Plan) -> List[PanoSatiri]:
    a, m = plan.atama, plan.fabrika.mevzuat
    if a is None:
        return [PanoSatiri(DIKKAT, "Bireysel personel denetimi kapalı",
                           "Yasal sınırlar denetlenmedi.")]
    out: List[PanoSatiri] = []
    gunluk: Dict[Tuple[str, date], float] = defaultdict(float)
    haftalik: Dict[Tuple[str, Tuple[int, int]], float] = defaultdict(float)
    for g in a.gorevler:
        gunluk[(g.personel, g.tarih)] += g.saat
        haftalik[(g.personel, tuple(g.tarih.isocalendar()[:2]))] += g.saat
    if gunluk:
        (p, gun), en = max(gunluk.items(), key=lambda x: x[1])
        out.append(PanoSatiri(TAMAM if en <= m.gunluk_azami_saat + 1e-6 else IHLAL,
                              f"Günlük {m.gunluk_azami_saat:g} saat",
                              f"en yüksek {en:.2f} sa · {p} · {gun:%d.%m.%Y}"))
    if haftalik:
        (p, hf), en = max(haftalik.items(), key=lambda x: x[1])
        out.append(PanoSatiri(TAMAM if en <= m.haftalik_azami_saat + 1e-6 else IHLAL,
                              f"Haftalık {m.haftalik_azami_saat:g} saat (politika)",
                              f"en yüksek {en:.2f} sa · {p} · {hf[0]}/{hf[1]}. hafta"))
    fm = {p: s for p, s in a.plan_fazla_mesai.items() if s > 1e-6}
    out.append(PanoSatiri(TAMAM if not fm else DIKKAT,
                          f"Haftalık {m.haftalik_normal_saat:g} saat üstü fazla çalışma",
                          "bu planda fazla çalışma yok" if not fm else
                          f"{len(fm)} personelde toplam {sum(fm.values()):.1f} sa"))
    if a.ozet:
        en = max(a.ozet, key=lambda o: o.yil_sonu)
        oran = 100 * en.yil_sonu / m.yillik_fazla_calisma_tavani
        durum = IHLAL if oran > 100 + 1e-6 else (DIKKAT if oran >= 90 else TAMAM)
        out.append(PanoSatiri(durum, f"Yıllık {m.yillik_fazla_calisma_tavani:g} saat tavanı",
                              f"en yüksek {en.personel} %{oran:.0f} ({en.yil_sonu:.1f} sa)"))
    if a.karsilanamayan:
        ornek = "; ".join(f"{k.kaynak} {k.tarih:%d.%m} V{k.vardiya}"
                          for k in a.karsilanamayan[:3])
        out.append(PanoSatiri(IHLAL, f"Atanamayan vardiya: {len(a.karsilanamayan)}",
                              ornek + (" …" if len(a.karsilanamayan) > 3 else "")))
    else:
        out.append(PanoSatiri(TAMAM, "Atanamayan vardiya yok",
                              "her kaynak-günü yasal sınırlar içinde bir personelle karşılandı"))
    return out


def _kullanim(plan: Plan) -> Dict[str, float]:
    tk = plan.takvim
    out: Dict[str, float] = {}
    for k, araliklar in cb.mesgul_araliklar(plan).items():
        takvim = tk.takvim(k)
        acik = takvim.gecen(plan.makespan)
        dolu = sum(takvim.calisma(a, b) for a, b in araliklar)
        out[k] = min(1.0, dolu / acik) if acik > 0 else 0.0
    return out


def grup_aciklari(plan: Plan, termin: Optional[date] = None,
                  adet: Optional[int] = None) -> List[GrupAcigi]:
    tk = plan.takvim
    if termin is None:
        termin = min(s.termin for s in plan.siparisler)
    if adet is None:
        adet = plan.urun_sayisi
    gun = max(1, tk.is_gunu_sayisi(plan.baslangic, termin))
    kullanim = _kullanim(plan)
    out: List[GrupAcigi] = []
    for atolye in plan.fabrika.atolyeler:
        for ad, kaynaklar, tau in _kapasite_gruplari(plan, atolye):
            gerekli = adet * tau / (max(1, len(kaynaklar)) * 3600.0 * gun)
            ort = []
            for k in kaynaklar:
                gunluk = [h for g, h in tk.net.get(k, {}).items()
                          if plan.baslangic <= g <= termin and h > 0]
                ort.append(sum(gunluk) / len(gunluk) if gunluk else 0.0)
            mevcut = sum(ort) / len(ort) if ort else 0.0
            out.append(GrupAcigi(ad, atolye, kaynaklar, tau,
                                 max((kullanim.get(k, 0.0) for k in kaynaklar), default=0.0),
                                 round(mevcut, 3), round(gerekli, 3)))
    out.sort(key=lambda h: (-h.acik, -h.kullanim))
    return out


def geciken_siparisler(plan: Plan) -> List[GecikmeAnalizi]:
    out: List[GecikmeAnalizi] = []
    sirali = sorted(plan.siparisler, key=lambda s: (s.termin, s.kod))
    birikimli = 0
    for s in sirali:
        birikimli += s.toplam                 # EDD: önündeki siparişler de üretilmeli
        g = plan.gecikme_gun.get(s.kod, 0.0)
        if g <= 1e-9:
            continue
        hatlar = grup_aciklari(plan, s.termin, birikimli)
        out.append(GecikmeAnalizi(s.kod, g, s.termin, hatlar[0] if hatlar else None,
                                  sorted(hatlar, key=lambda h: -h.kullanim)[:3]))
    out.sort(key=lambda x: -x.gecikme_gun)
    return out


def panolar_metin(plan: Plan) -> str:
    L = ["PANO A · YASAL DURUM"]
    L += [f"   {x}" for x in mevzuat_panosu(plan)]
    L += ["", "PANO B · HAT YETERLİLİĞİ"]
    gecikenler = geciken_siparisler(plan)
    if not gecikenler:
        en_dolu = sorted(grup_aciklari(plan), key=lambda h: -h.kullanim)[:3]
        L.append(f"   {SEMBOL[TAMAM]} Bütün siparişler termine yetişiyor.")
        L.append("   En dolu gruplar: " + " · ".join(
            f"{h.grup} %{100 * h.kullanim:.0f}" for h in en_dolu))
    for s in gecikenler:
        L.append(f"   {SEMBOL[IHLAL]} {s.kod}: termin {s.termin:%d.%m.%Y}, "
                 f"{s.gecikme_gun:.1f} gün geç")
        if s.kritik:
            k = s.kritik
            if k.acik > 1e-3:
                L.append(f"      Kritik grup {k.grup}: günde +{k.acik:.2f} saat gerekli "
                         f"(gerekli {k.gerekli_saat:.2f} / mevcut {k.mevcut_saat:.2f} sa/gün)")
            else:
                L.append("      Kararlı durum kapasitesi yeterli; gecikme ayar kayıpları ve "
                         "hattın dolma süresinden. Parti sayısını artırmayı ya da sırayı "
                         "değiştirmeyi deneyin.")
        if s.en_dolu:
            L.append("      En dolu: " + " · ".join(
                f"{h.grup} %{100 * h.kullanim:.0f}" for h in s.en_dolu))
    return "\n".join(L)
