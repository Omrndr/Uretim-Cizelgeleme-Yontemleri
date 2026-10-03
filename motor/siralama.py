"""
Üretim sırası — EDD + karma model dengeleme (heijunka).

1) Siparişler arası: EN ERKEN TERMİN ÖNCE (EDD). Tek makinede en büyük gecikmeyi
   (L_max) en aza indiren kuraldır (Jackson, 1955); akış hattında da güçlü bir
   heuristic'tir.

2) Sipariş içi: varyantlar blok blok değil, oranları korunarak karıştırılır.
   "Goal chasing" (goal chasing, Toyota / Monden): k. adımda, ideal birikimli
   üretimin gerisinde en çok kalan varyant seçilir:

        v_k = argmax_v ( d_v · k / D  −  x_v(k−1) )

   x_v: o ana kadar sıraya giren v adedi, d_v: siparişteki v adedi, D = Σ d_v.
   Sonuç: her önekte varyant oranları sipariş oranına en fazla 1 adet uzaklıktadır
   ve varyant bileşeni hattı dengeli tüketir (bir rengin stoğu tükenip diğeri
   yığılmaz).
"""
from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

from motor.model import Siparis


def hedef_kovalama(miktarlar: Dict[str, int], varyant_sirasi: Sequence[str] = ()
                   ) -> List[str]:
    d = {v: int(a) for v, a in miktarlar.items() if int(a) > 0}
    toplam = sum(d.values())
    oncelik = {v: i for i, v in enumerate(varyant_sirasi)}
    x = {v: 0 for v in d}
    out: List[str] = []
    for k in range(1, toplam + 1):
        v = max(d, key=lambda v: (d[v] * k / toplam - x[v], d[v], -oncelik.get(v, 0)))
        x[v] += 1
        out.append(v)
    return out


def is_sirasi(siparisler: Sequence[Siparis], varyant_sirasi: Sequence[str] = ()
              ) -> List[Tuple[str, str]]:
    """[(sipariş kodu, varyant), ...] — hattın ürünleri işleme sırası."""
    sira: List[Tuple[str, str]] = []
    for s in sorted(siparisler, key=lambda s: (s.termin, s.kod)):
        sira.extend((s.kod, v) for v in hedef_kovalama(s.miktarlar, varyant_sirasi))
    return sira
