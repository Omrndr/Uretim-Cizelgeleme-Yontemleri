"""
Paralel özdeş makinelerde iş yükü dengeleme — P || Cmax.

Her parçanın tek aparatı olduğu için parça bölünemez; bir parça tümüyle tek bir
makineye atanır. Bir ürün her parçadan birer adet gerektirdiğinden makine k'nin
ürün başına yükü L_k = Σ_{p∈S_k} t_p, grubun çevrim süresi C = max_k L_k olur.

Problem NP-zordur (2 makinede bile PARTITION'a indirgenir). Kullanılan yöntem:

  1) LPT (Longest Processing Time): parçalar süreye göre azalan sırada, o an en
     az yüklü makineye atanır. Garanti: C_LPT ≤ (4/3 − 1/(3m)) · C*  (Graham, 1969)
  2) Local search: en yüklü makineden bir parçayı TAŞIMA ya da bir parçayı başka
     makinedeki parçayla TAKAS etme; en çok iyileştiren hamle uygulanır (en dik
     iniş). Hamle kabul ölçütü, iki makinenin yeni yüklerinin büyüğünün mevcut
     C'den kesin küçük olmasıdır; bu, Σ L_k² değerini kesin azalttığından arama
     sonlu adımda durur.

Alt sınır:  C* ≥ max( Σ t_p / m ,  max_p t_p )
"""
from __future__ import annotations

import heapq
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

_EPS = 1e-9


@dataclass
class Dengeleme:
    gruplar: List[List[str]]      # makine -> parça kodları (işlem sırası)
    yukler: List[float]           # makine -> ürün başına yük (sn)
    alt_sinir: float
    lpt_cmax: float               # local search'ten ÖNCEKİ değer (rapor için)

    @property
    def cmax(self) -> float:
        return max(self.yukler) if self.yukler else 0.0

    @property
    def bosluk(self) -> float:
        """Alt sınıra göre en kötü durum optimallik boşluğu (oran)."""
        return (self.cmax / self.alt_sinir - 1.0) if self.alt_sinir > 0 else 0.0


def alt_sinir(sureler: Dict[str, float], m: int) -> float:
    if not sureler or m <= 0:
        return 0.0
    return max(sum(sureler.values()) / m, max(sureler.values()))


def _lpt(sureler: Dict[str, float], m: int) -> Tuple[List[List[str]], List[float]]:
    gruplar: List[List[str]] = [[] for _ in range(m)]
    yukler = [0.0] * m
    yigin = [(0.0, k) for k in range(m)]            # (yük, makine)
    for p in sorted(sureler, key=lambda x: (-sureler[x], x)):
        yuk, k = heapq.heappop(yigin)
        gruplar[k].append(p)
        yukler[k] = yuk + sureler[p]
        heapq.heappush(yigin, (yukler[k], k))
    return gruplar, yukler


def _en_iyi_hamle(gruplar: List[List[str]], yukler: List[float],
                  sureler: Dict[str, float]) -> Optional[Tuple]:
    """En yüklü makine için en iyi taşıma/takas hamlesini bulur."""
    m = len(yukler)
    a = max(range(m), key=lambda k: (yukler[k], -k))
    cmax = yukler[a]
    en_iyi = None                      # (yeni_çift_maksimumu, hamle)
    for b in range(m):
        if b == a:
            continue
        for p in gruplar[a]:
            tp = sureler[p]
            yeni = max(yukler[a] - tp, yukler[b] + tp)           # taşıma
            if yeni < cmax - _EPS and (en_iyi is None or yeni < en_iyi[0] - _EPS):
                en_iyi = (yeni, ("tasi", a, b, p, None))
            for q in gruplar[b]:                                 # takas
                fark = tp - sureler[q]
                if fark <= _EPS:
                    continue
                yeni = max(yukler[a] - fark, yukler[b] + fark)
                if yeni < cmax - _EPS and (en_iyi is None or yeni < en_iyi[0] - _EPS):
                    en_iyi = (yeni, ("takas", a, b, p, q))
    return en_iyi[1] if en_iyi else None


def dengele(sureler: Dict[str, float], m: int, azami_adim: int = 10_000) -> Dengeleme:
    """Parçaları m makineye dağıtır (LPT + steepest descent local search)."""
    if m <= 0:
        raise ValueError("Makine sayısı pozitif olmalı.")
    gruplar, yukler = _lpt(sureler, m)
    lpt_cmax = max(yukler) if yukler else 0.0
    for _ in range(azami_adim):
        hamle = _en_iyi_hamle(gruplar, yukler, sureler)
        if hamle is None:
            break
        tur, a, b, p, q = hamle
        gruplar[a].remove(p)
        gruplar[b].append(p)
        yukler[a] -= sureler[p]
        yukler[b] += sureler[p]
        if tur == "takas":
            gruplar[b].remove(q)
            gruplar[a].append(q)
            yukler[b] -= sureler[q]
            yukler[a] += sureler[q]
    # Makine içi işlem sırası: uzun parça önce (ilk partide hat daha erken beslenir)
    for g in gruplar:
        g.sort(key=lambda x: (-sureler[x], x))
    # Makineleri yüke göre sırala: TORNA-1 en yüklü makinedir
    sira = sorted(range(m), key=lambda k: (-yukler[k], k))
    return Dengeleme([gruplar[k] for k in sira], [yukler[k] for k in sira],
                     alt_sinir(sureler, m), lpt_cmax)
