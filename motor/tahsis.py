"""
Personel tahsisi — darboğazı en aza indiren kesin (optimal) dağıtım.

Her makine ve her istasyon tam 1 personel gerektirir. Tahsis birimi u'ya w_u
personel verildiğinde birimin çevrim süresi f_u(w_u) olur:

    parça grubu   f(w) = C_max( P || Cmax, w makine )     (bkz. dengeleme.py)
    varyant grubu f(w) = τ / w ,  w ≤ min(makine, talep edilen varyantların takım toplamı)
    hücre / hat   f(w) = τ / w ,  w ≤ azami istasyon

Sistem çevrim süresi (takt kapasitesi) en yavaş birimdir:

    C(w) = max_u f_u(w_u)          kapasite = 3600 / C  [adet/saat]

PROBLEM (min-max kaynak tahsisi):
    min_w  C(w)   öyle ki   Σ_u w_u ≤ N ,   1 ≤ w_u ≤ ü_u ,  w_u ∈ ℤ

KESİN ÇÖZÜM — candidate cycle sweep:
    Optimal C* mutlaka {f_u(k)} kümesinin bir elemanıdır. Aday değerler küçükten
    büyüğe taranır; her aday C için her birimin ihtiyacı
        n_u(C) = min{ k : f_u(k) ≤ C }
    hesaplanır. Σ n_u(C) ≤ N sağlayan İLK aday optimaldir; çünkü çevrimi C'yi
    aşmayan her tahsiste w_u ≥ n_u(C) olmak zorundadır. Aynı C için kullanılan
    personel de en azdır (eşitlik bozucu). Karmaşıklık O(A · U · ü) — tam sayım
    (Π ü_u kombinasyon) yerine aday sayısıyla doğrusal.

ARTIK PERSONEL: Optimum çoğu zaman bütün kadroyu kullanmaz. Artanlar önce makine
gruplarına verilir (paralel makine sayısı arttıkça parti/ayar yükü bölüşülür),
sonra çevrimi en yüksek birime — böylece darboğaz dışındaki birimlerde emniyet
payı oluşur.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from motor.dengeleme import Dengeleme, dengele
from motor.model import Fabrika

_EPS = 1e-9


@dataclass(frozen=True)
class TahsisBirimi:
    kod: str
    ad: str
    atolye: str
    tip: str                         # "parca" | "varyant" | "hucre" | "hat"
    cevrimler: Tuple[float, ...]     # cevrimler[w-1] = f(w)

    @property
    def ust(self) -> int:
        return len(self.cevrimler)

    def cevrim(self, w: int) -> float:
        return self.cevrimler[max(1, min(w, self.ust)) - 1]

    def ihtiyac(self, c: float) -> Optional[int]:
        """f(k) ≤ c sağlayan en küçük k (yoksa None)."""
        for k, f in enumerate(self.cevrimler, start=1):
            if f <= c + _EPS:
                return k
        return None


@dataclass
class Dagilim:
    personel: Dict[str, int]                 # birim -> personel (= istasyon/makine)
    cevrimler: Dict[str, float]              # birim -> çevrim (sn/adet)
    cevrim: float
    darbogaz: str
    kadro: int
    birimler: Dict[str, TahsisBirimi]
    dengelemeler: Dict[str, Dengeleme] = field(default_factory=dict)
    optimum_personel: int = 0                # artık dağıtımdan önceki asgari kullanım

    @property
    def kullanilan(self) -> int:
        return sum(self.personel.values())

    @property
    def bosta(self) -> int:
        return self.kadro - self.kullanilan

    @property
    def kapasite_saat(self) -> float:
        return 3600.0 / self.cevrim if self.cevrim > 0 else 0.0


@dataclass(frozen=True)
class KaynakKaydi:
    """Tek bir makine veya istasyon. Her kaynak bir personel gerektirir."""
    ad: str
    atolye: str
    birim: str
    tip: str
    no: int


# ==============================================================================
# BİRİMLERİN KURULMASI
# ==============================================================================

def tahsis_birimleri(fabrika: Fabrika, talep_varyantlari: Sequence[str]
                     ) -> Tuple[List[TahsisBirimi], Dict[str, Dict[int, Dengeleme]]]:
    birimler: List[TahsisBirimi] = []
    dengelemeler: Dict[str, Dict[int, Dengeleme]] = {}
    for g in fabrika.parca_gruplari:
        sureler = g.sureler()
        tablo = {w: dengele(sureler, w) for w in range(1, g.makine_sayisi + 1)}
        dengelemeler[g.kod] = tablo
        birimler.append(TahsisBirimi(g.kod, g.ad, g.ad, "parca",
                                     tuple(tablo[w].cmax for w in sorted(tablo))))
    vg = fabrika.varyant_grubu
    if vg:
        ust = max(1, vg.kullanilabilir_makine(talep_varyantlari or fabrika.varyantlar))
        birimler.append(TahsisBirimi(vg.kod, vg.ad, vg.ad, "varyant",
                                     tuple(vg.sure_sn / w for w in range(1, ust + 1))))
    for h in fabrika.hucreler:
        birimler.append(TahsisBirimi(h.kod, h.ad, fabrika.hucre_atolyesi, "hucre",
                                     tuple(h.sure_sn / w
                                           for w in range(1, h.azami_istasyon + 1))))
    for i in fabrika.istasyonlar:
        birimler.append(TahsisBirimi(i.kod, i.ad, fabrika.hat_atolyesi, "hat",
                                     tuple(i.sure_sn / w
                                           for w in range(1, i.azami_istasyon + 1))))
    return birimler, dengelemeler


# ==============================================================================
# KESİN MİN-MAKS TAHSİS
# ==============================================================================

def min_max_tahsis(birimler: Sequence[TahsisBirimi], butce: int
                   ) -> Optional[Tuple[Dict[str, int], float]]:
    """Candidate cycle sweep. Dönüş: ({birim: personel}, C*) ya da None."""
    if butce < len(birimler):
        return None
    adaylar = sorted({round(f, 9) for b in birimler for f in b.cevrimler})
    for c in adaylar:
        ihtiyac: Dict[str, int] = {}
        for b in birimler:
            k = b.ihtiyac(c)
            if k is None:
                break
            ihtiyac[b.kod] = k
        else:
            if sum(ihtiyac.values()) <= butce:
                gercek = max(b.cevrim(ihtiyac[b.kod]) for b in birimler)
                return ihtiyac, gercek
    return None


def _artik_dagit(birimler: Sequence[TahsisBirimi], w: Dict[str, int], bos: int) -> None:
    makine = [b for b in birimler if b.tip in ("parca", "varyant")]
    diger = [b for b in birimler if b.tip not in ("parca", "varyant")]
    while bos > 0:
        adaylar = [b for b in makine
                   if w[b.kod] < b.ust and b.cevrim(w[b.kod] + 1) <= b.cevrim(w[b.kod]) + _EPS]
        if not adaylar:
            adaylar = [b for b in diger if w[b.kod] < b.ust]
        if not adaylar:
            return
        hedef = max(adaylar, key=lambda b: (b.cevrim(w[b.kod]), b.kod))
        w[hedef.kod] += 1
        bos -= 1


def en_iyi_dagilim(fabrika: Fabrika, kadro: int,
                   talep_varyantlari: Sequence[str] = ()) -> Optional[Dagilim]:
    birimler, tablolar = tahsis_birimleri(fabrika, talep_varyantlari)
    sonuc = min_max_tahsis(birimler, kadro)
    if sonuc is None:
        return None
    w, _ = sonuc
    optimum = sum(w.values())
    _artik_dagit(birimler, w, kadro - optimum)
    cevrimler = {b.kod: b.cevrim(w[b.kod]) for b in birimler}
    darbogaz = max(cevrimler, key=lambda k: (cevrimler[k], k))
    return Dagilim(
        personel=w, cevrimler=cevrimler, cevrim=cevrimler[darbogaz], darbogaz=darbogaz,
        kadro=kadro, birimler={b.kod: b for b in birimler},
        dengelemeler={g: tablo[w[g]] for g, tablo in tablolar.items()},
        optimum_personel=optimum)


def yapisal_alt_sinir(fabrika: Fabrika, talep_varyantlari: Sequence[str] = ()
                      ) -> Tuple[float, str]:
    """Sınırsız personelle bile aşılamayan çevrim (sn/adet) ve sebebi."""
    birimler, _ = tahsis_birimleri(fabrika, talep_varyantlari)
    en = max(birimler, key=lambda b: min(b.cevrimler))
    return min(en.cevrimler), en.kod


# ==============================================================================
# KAYNAK LİSTESİ
# ==============================================================================

def kaynak_adi(birim_kodu: str, no: int, fabrika: Fabrika) -> str:
    for g in fabrika.parca_gruplari:
        if g.kod == birim_kodu:
            return f"{g.kaynak_oneki}-{no}"
    vg = fabrika.varyant_grubu
    if vg and vg.kod == birim_kodu:
        return f"{vg.kaynak_oneki}-{no}"
    return f"{birim_kodu}.{no}"


def kaynaklari_olustur(fabrika: Fabrika, tahsis: Dagilim) -> List[KaynakKaydi]:
    out: List[KaynakKaydi] = []
    for kod, b in tahsis.birimler.items():
        for no in range(1, tahsis.personel[kod] + 1):
            out.append(KaynakKaydi(kaynak_adi(kod, no, fabrika), b.atolye, kod, b.tip, no))
    return out
