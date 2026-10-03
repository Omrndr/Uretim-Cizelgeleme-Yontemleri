"""
Parti (kampanya) planı — parça makineleri.

Bir makinede birden çok parça varsa her parça değişimi bir aparat ayarı
gerektirir. N ürünlük talep K partiye bölünür; her partide makine kendi
parçalarını sırayla, partinin adedi kadar üretir.

  * K = 1  : en az ayar, ama son parça çok geç başlar -> hat uzun süre aç kalır.
  * K büyük: hat erken beslenir, ama ayar sayısı ~ K · (parça sayısı) artar.

Parti büyüklükleri geometrik "rampa" ile dağıtılır:

    q_j ∝ r^j  (j = 0..K−1),   Σ q_j = N,   q_j ≥ 1

r > 1 ilk partiyi küçük tutar (hat çabuk beslenir), sonrakileri büyütür.
Tam sayıya yuvarlama en büyük kalan (Hamilton) yöntemiyle yapılır; böylece
toplam korunur ve her parti ideal değerinden en fazla 1 sapar.

YILAN (SERPANTİN) SIRA: Ardışık partilerde parça sırası ters çevrilir
(A,B,C | C,B,A | A,B,C ...). Bir partinin son parçası bir sonrakinin ilk parçası
olduğu için parti geçişinde ayar gerekmez; makine başına K−1 ayar kazanılır.

SİPARİŞ ATFI: j. parti, üretim sırasındaki [Σ_{<j} q, Σ_{≤j} q) aralığındaki
ürünlere birer parça üretir.
"""
from __future__ import annotations

import math
from bisect import bisect_right
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from motor.model import Fabrika, ParcaGrubu
from motor.tahsis import Dagilim, kaynak_adi
from motor.takvim import KaynakTakvimi, UfukAsildi


@dataclass
class Parti:
    """Bir makinede kesintisiz üretilen tek nesneli iş (gerekirse ayarla başlar)."""
    atolye: str
    grup: str
    kaynak: str
    nesne: str                 # parça kodu ya da varyant adı
    etiket: str                # ekranda görünen görev adı
    parti_no: int
    ayar_bas: Optional[float]
    ayar_bit: Optional[float]
    bas: float
    bit: float
    adet: int
    birim_sn: float
    ayar_etiketi: str = "Ayar"
    sira_bas: int = -1         # parça partisi: beslenen ürün aralığı [bas, bit)
    sira_bit: int = -1
    dilimler: Tuple[int, ...] = ()   # varyant partisi: varyantın kaçıncı adetleri

    @property
    def ayar_var(self) -> bool:
        return self.ayar_bas is not None


def parti_buyuklukleri(n: int, k: int, ramp: float = 1.0) -> List[int]:
    """N adedi K partiye geometrik rampayla böler (Hamilton yuvarlaması)."""
    if n <= 0:
        return []
    k = max(1, min(int(k), n))
    agirlik = [ramp ** j for j in range(k)]
    toplam = sum(agirlik)
    ideal = [n * a / toplam for a in agirlik]
    q = [max(1, math.floor(x)) for x in ideal]
    fark = n - sum(q)
    sira = sorted(range(k), key=lambda j: (-(ideal[j] - math.floor(ideal[j])), j))
    i = 0
    while fark > 0:
        q[sira[i % k]] += 1
        fark -= 1
        i += 1
    while fark < 0:
        j = max((j for j in range(k) if q[j] > 1), key=lambda j: (q[j] - ideal[j], j))
        q[j] -= 1
        fark += 1
    return q


class ParcaZamanlari:
    """Parça p'nin i. adedinin bitiş anı — ikili aramayla O(log n)."""

    def __init__(self) -> None:
        self._seg: Dict[str, List[Tuple[float, int, float, KaynakTakvimi]]] = {}
        self._kum: Dict[str, List[int]] = {}

    def ekle(self, parca: str, bas: float, adet: int, birim: float,
             takvim: KaynakTakvimi) -> None:
        seg = self._seg.setdefault(parca, [])
        kum = self._kum.setdefault(parca, [])
        kum.append((kum[-1] + seg[-1][1]) if seg else 0)
        seg.append((bas, adet, birim, takvim))

    def bitis(self, parca: str, i: int) -> float:
        """1 tabanlı i. adet."""
        kum = self._kum.get(parca)
        if not kum:
            raise KeyError(f"Parça {parca} çizelgelenmedi.")
        j = bisect_right(kum, i - 1) - 1
        bas, adet, birim, tk = self._seg[parca][j]
        if i - kum[j] > adet:
            raise UfukAsildi(f"Parça {parca}: {i}. adet üretilmedi.")
        return tk.ilerlet(bas, (i - kum[j]) * birim)


def parca_partileri(fabrika: Fabrika, tahsis: Dagilim, grup: ParcaGrubu, n: int,
                    k: int, ramp: float, ayar_sn: float,
                    takvimler: Dict[str, KaynakTakvimi], zamanlar: ParcaZamanlari,
                    hizala: bool = False, serpantin: bool = True
                    ) -> Tuple[List[Parti], int]:
    """Bir parça grubunun bütün makineleri için parti çizelgesi."""
    partiler: List[Parti] = []
    ayar_sayisi = 0
    lotlar = parti_buyuklukleri(n, k, ramp)
    sureler = grup.sureler()
    adlar = {p.kod: p.ad for p in grup.parcalar}
    for mi, parcalar in enumerate(tahsis.dengelemeler[grup.kod].gruplar, start=1):
        if not parcalar:
            continue
        kaynak = kaynak_adi(grup.kod, mi, fabrika)
        tk = takvimler[kaynak]
        t = tk.ilk_musait(0.0)
        onceki: Optional[str] = None
        kum = 0
        for j, q in enumerate(lotlar):
            sira = parcalar[::-1] if (serpantin and j % 2 == 1) else parcalar
            for p in sira:
                ab = abit = None
                if p != onceki and ayar_sn > 0:
                    ab = tk.sonraki_gun_basi(t) if hizala else tk.ilk_musait(t)
                    abit = tk.ilerlet(ab, ayar_sn)
                    t = abit
                    ayar_sayisi += 1
                bas = tk.ilk_musait(t)
                t = tk.ilerlet(bas, q * sureler[p])
                zamanlar.ekle(p, bas, q, sureler[p], tk)
                partiler.append(Parti(grup.ad, grup.kod, kaynak, p, f"{p} {adlar[p]}",
                                      j + 1, ab, abit, bas, t, q, sureler[p],
                                      grup.ayar_etiketi, sira_bas=kum, sira_bit=kum + q))
                onceki = p
            kum += q
    return partiler, ayar_sayisi
