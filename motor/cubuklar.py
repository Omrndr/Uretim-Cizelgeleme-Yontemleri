"""
Zaman çubukları ve meşguliyet aralıkları.

* ``Cubuk``: çizelgelerde görünen tek bir iş parçası (ayar ya da üretim).
  Hücre ve hat istasyonlarında ardışık ürünler, aynı siparişe ait olduğu ve
  aynı üretim gününde kaldığı sürece tek çubukta birleştirilir.
* ``mesgul_araliklar``: her kaynağın kesin meşgul olduğu aralıklar (birleşik).
  Personel saatleri çubuklardan değil buradan hesaplanır; çubuk birleştirmesi
  aradaki kısa boşlukları da kapsadığı için saat şişirirdi.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Dict, List, Optional, Sequence, Tuple

from motor.parti import Parti
from motor.tahsis import kaynak_adi
from motor.takvim import FabrikaTakvimi, SAAT

if TYPE_CHECKING:                       # pragma: no cover
    from motor.cozucu import Plan

URETIM, AYAR = "Üretim", "Ayar"


@dataclass
class Cubuk:
    atolye: str
    kaynak: str
    tur: str
    gorev: str
    bas: float
    bit: float
    adet: int = 0
    siparis: str = ""                  # "S-01" ya da "S-01 (120) · S-02 (40)"
    varyant: str = ""                  # "Antrasit" ya da "Antrasit 12 · Krem 4"
    detay: str = ""
    parti: Optional[Parti] = None
    urunler: Tuple[int, ...] = ()      # hücre/hat: kapsanan ürün indeksleri

    @property
    def sure(self) -> float:
        return self.bit - self.bas


def ozet_metni(sayac: Counter, sira: Sequence[str] = ()) -> str:
    if not sayac:
        return ""
    if len(sayac) == 1:
        return next(iter(sayac))
    anahtar = (lambda k: (sira.index(k) if k in sira else 99, k)) if sira else None
    return " · ".join(f"{k} ({sayac[k]})" for k in sorted(sayac, key=anahtar))


def _parti_cubuklari(partiler: Sequence[Parti]) -> List[Cubuk]:
    out: List[Cubuk] = []
    for p in partiler:
        if p.ayar_var:
            out.append(Cubuk(p.atolye, p.kaynak, AYAR, f"{p.ayar_etiketi} → {p.nesne}",
                             p.ayar_bas, p.ayar_bit, 0, "", "", "Kaynak üretim yapmaz",
                             parti=p))
        out.append(Cubuk(p.atolye, p.kaynak, URETIM, p.etiket, p.bas, p.bit, p.adet, "",
                         "", f"{p.adet} adet × {p.birim_sn:g} sn · parti {p.parti_no}",
                         parti=p))
    return out


def tum_cubuklar(plan: "Plan", gune_bol: bool = True,
                 bosluk_sn: float = 1800.0) -> List[Cubuk]:
    f, tk = plan.fabrika, plan.takvim
    out = _parti_cubuklari(plan.parca_partileri) + _parti_cubuklari(plan.varyant.partiler)
    akis, sira = plan.akis, plan.sira
    for op in (*f.hucreler, *f.istasyonlar):
        atolye = f.hucre_atolyesi if op in f.hucreler else f.hat_atolyesi
        c = plan.tahsis.personel[op.kod]
        for s in range(c):
            kaynak = kaynak_adi(op.kod, s + 1, f)
            idx = [i for i in range(len(sira)) if akis.istasyon[op.kod][i] == s]
            idx.sort(key=lambda i: akis.bas[op.kod][i])
            grup: List[int] = []

            def bosalt() -> None:
                if not grup:
                    return
                sip = Counter(sira[i][0] for i in grup)
                var = Counter(sira[i][1] for i in grup)
                out.append(Cubuk(
                    atolye, kaynak, URETIM, f"{op.kod} {op.ad}",
                    akis.bas[op.kod][grup[0]], akis.bit[op.kod][grup[-1]], len(grup),
                    ozet_metni(sip), ozet_metni(var, f.varyantlar),
                    f"{op.sure_sn:g} sn/adet · istasyon {s + 1}/{c}",
                    urunler=tuple(grup)))
                grup.clear()

            for i in idx:
                if grup:
                    j = grup[-1]
                    ayni_gun = (not gune_bol) or tk.hangi_gun(akis.bas[op.kod][i]) == \
                        tk.hangi_gun(akis.bas[op.kod][j])
                    if not (sira[i][0] == sira[j][0] and ayni_gun
                            and akis.bas[op.kod][i] - akis.bit[op.kod][j] <= bosluk_sn):
                        bosalt()
                grup.append(i)
            bosalt()
    return out


def _birlestir(araliklar: List[Tuple[float, float]], tolerans: float = 1.0
               ) -> List[Tuple[float, float]]:
    araliklar.sort()
    out: List[List[float]] = []
    for a, b in araliklar:
        if out and a - out[-1][1] <= tolerans:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def mesgul_araliklar(plan: "Plan") -> Dict[str, List[Tuple[float, float]]]:
    f = plan.fabrika
    ham: Dict[str, List[Tuple[float, float]]] = defaultdict(list)
    for p in (*plan.parca_partileri, *plan.varyant.partiler):
        if p.ayar_var:
            ham[p.kaynak].append((p.ayar_bas, p.ayar_bit))
        ham[p.kaynak].append((p.bas, p.bit))
    for op in (*f.hucreler, *f.istasyonlar):
        adlar = [kaynak_adi(op.kod, s + 1, f) for s in range(plan.tahsis.personel[op.kod])]
        akis = plan.akis
        for i in range(len(plan.sira)):
            ham[adlar[akis.istasyon[op.kod][i]]].append((akis.bas[op.kod][i],
                                                         akis.bit[op.kod][i]))
    return {k: _birlestir(v) for k, v in ham.items()}


def calisilan_saatler(takvim: FabrikaTakvimi,
                      mesgul: Dict[str, List[Tuple[float, float]]]
                      ) -> Dict[Tuple[str, date], float]:
    """(kaynak, üretim günü) -> o gün FİİLEN çalışılan net saat."""
    out: Dict[Tuple[str, date], float] = {}
    for k, araliklar in mesgul.items():
        pencereler = takvim.pencereler.get(k, {})
        gunluk = sorted((a, b, g) for g, bl in pencereler.items() for a, b in bl)
        i = j = 0
        while i < len(araliklar) and j < len(gunluk):
            a, b = araliklar[i]
            x, y, g = gunluk[j]
            ortak = min(b, y) - max(a, x)
            if ortak > 1e-9:
                out[(k, g)] = out.get((k, g), 0.0) + ortak / SAAT
            if b < y:
                i += 1
            else:
                j += 1
    return out


def mola_paylari(takvim: FabrikaTakvimi,
                 saatler: Dict[Tuple[str, date], float]
                 ) -> Dict[Tuple[str, date], float]:
    """Çalışılan kaynak-günlerinde zorunlu molanın, çalışılan pay kadar kısmı."""
    out: Dict[Tuple[str, date], float] = {}
    for (k, g), h in saatler.items():
        tam = takvim.net.get(k, {}).get(g, 0.0)
        mola = takvim.zorunlu_mola.get(k, {}).get(g, 0.0)
        if mola > 0 and tam > 0:
            out[(k, g)] = mola * min(1.0, h / tam)
    return out
