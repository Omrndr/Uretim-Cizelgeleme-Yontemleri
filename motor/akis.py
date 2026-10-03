"""
Akış hesabı — hücreler ve hat için kaynak takvimli ileri özyineleme.

Ürünler üretim sırasına göre (i = 1..N) işlenir. Operasyon j'nin c_j paralel
istasyonu vardır. i. ürünün j'ye hazır olma anı, tükettiği bütün girdilerin
en geç bitişidir:

    R_j(i) = max( F_{j−1}(i) ,  max_{p ∈ parça girdileri} P_p(i) ,
                  max_{h ∈ hücre girdileri} F_h(i) ,  V_{v(i)}(k_i) )

    P_p(i)   : parça p'nin i. adedinin bitişi (parti planından)
    V_v(k)   : varyant v'nin k. bileşeninin bitişi; k_i = i. üründen önceki v'li ürün sayısı + 1

Liste çizelgeleme: ürün, en erken BİTİRECEK istasyona verilir

    s* = argmin_s  ilerle_s( max(R_j(i), A_s), τ_j ),    A_s: istasyonun müsait anı
    S_j(i) = max(R_j(i), A_{s*}) (takvime göre ilk müsait an),  F_j(i) = ilerlet(S_j(i), τ_j)

Bütün istasyonların takvimi özdeşse bu, bilinen kapalı biçime indirgenir:
    S_j(i) = max( R_j(i), F_j(i − c_j) ),  F_j(i) = S_j(i) ⊕ τ_j
(⊕: takvim üzerinde ilerletme). Takvimler farklıysa (tek istasyona ek mesai)
genel kural kullanılır.

KISIT ANALİZİ: Her ürün-istasyon için gecikmeye hangi girdinin yol açtığı
sayılır; istasyon boştayken girdi bekleniyorsa bu "aç kalma" süresi
(çalışma saniyesi olarak) o girdiye yazılır.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple

from motor.model import VARYANT_GIRDISI, Fabrika, Operasyon
from motor.parti import ParcaZamanlari
from motor.tahsis import Dagilim, kaynak_adi
from motor.takvim import KaynakTakvimi

ISTASYON_DOLU = "İstasyon dolu (kapasite)"


@dataclass
class AkisTablosu:
    bas: Dict[str, List[float]]
    bit: Dict[str, List[float]]
    istasyon: Dict[str, List[int]]           # 0 tabanlı istasyon indeksi
    makespan: float
    kisit: Dict[str, Counter] = field(default_factory=dict)
    aclik_sn: Dict[str, Dict[str, float]] = field(default_factory=dict)

    def urun_bitisi(self, son_istasyon: str) -> List[float]:
        return self.bit[son_istasyon]


class _Operasyon:
    __slots__ = ("op", "takvimler", "musait")

    def __init__(self, op: Operasyon, takvimler: List[KaynakTakvimi]):
        self.op = op
        self.takvimler = takvimler
        self.musait = [0.0] * len(takvimler)

    def istasyona_ver(self, hazir: float) -> Tuple[float, float, int, float]:
        """(başlangıç, bitiş, istasyon, istasyonun önceki müsait anı)"""
        en = None
        for s, tk in enumerate(self.takvimler):
            b = tk.ilk_musait(max(hazir, self.musait[s]))
            e = tk.ilerlet(b, self.op.sure_sn)
            if en is None or e < en[1] - 1e-9:
                en = (b, e, s)
        b, e, s = en
        onceki = self.musait[s]
        self.musait[s] = e
        return b, e, s, onceki


def akisi_coz(fabrika: Fabrika, sira: Sequence[Tuple[str, str]],
              parcalar: ParcaZamanlari, varyant_bitis: Dict[str, List[float]],
              tahsis: Dagilim, takvimler: Dict[str, KaynakTakvimi]) -> AkisTablosu:
    n = len(sira)
    ops = list(fabrika.hucreler) + list(fabrika.istasyonlar)
    durum = {o.kod: _Operasyon(o, [takvimler[kaynak_adi(o.kod, s, fabrika)]
                                   for s in range(1, tahsis.personel[o.kod] + 1)])
             for o in ops}
    bas = {o.kod: [0.0] * n for o in ops}
    bit = {o.kod: [0.0] * n for o in ops}
    ist = {o.kod: [0] * n for o in ops}
    kisit: Dict[str, Counter] = defaultdict(Counter)
    aclik: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    hucre_adi = {h.kod: f"{h.kod} {h.ad}" for h in fabrika.hucreler}
    bilesen = fabrika.varyant_grubu.bilesen if fabrika.varyant_grubu else "Varyant"
    varyant_sayaci: Counter = Counter()
    onceki_istasyon = {}
    for a, b in zip(fabrika.istasyonlar, fabrika.istasyonlar[1:]):
        onceki_istasyon[b.kod] = a.kod

    for i, (_, varyant) in enumerate(sira):
        idx = i + 1
        varyant_sayaci[varyant] += 1
        parca_onbellek: Dict[str, float] = {}

        def parca(p: str) -> float:
            if p not in parca_onbellek:
                parca_onbellek[p] = parcalar.bitis(p, idx)
            return parca_onbellek[p]

        for op in ops:
            adaylar: List[Tuple[float, str]] = []
            for g in op.girdiler:
                if g == VARYANT_GIRDISI:
                    liste = varyant_bitis.get(varyant, [])
                    k = varyant_sayaci[varyant] - 1
                    adaylar.append((liste[k] if k < len(liste) else float("inf"),
                                    f"{bilesen} ({varyant})"))
                elif g in hucre_adi:
                    adaylar.append((bit[g][i], hucre_adi[g]))
                else:
                    adaylar.append((parca(g), f"Parça {g}"))
            if op.kod in onceki_istasyon:
                o = onceki_istasyon[op.kod]
                adaylar.append((bit[o][i], f"Önceki istasyon {o}"))
            hazir, neden = max(adaylar, default=(0.0, "-"))
            b, e, s, musait = durum[op.kod].istasyona_ver(hazir)
            bas[op.kod][i], bit[op.kod][i], ist[op.kod][i] = b, e, s
            if b > hazir + 1e-6:
                kisit[op.kod][ISTASYON_DOLU] += 1
            else:
                kisit[op.kod][neden] += 1
                if hazir > musait:
                    tk = durum[op.kod].takvimler[s]
                    aclik[op.kod][neden] += tk.calisma(musait, hazir)

    son = fabrika.istasyonlar[-1].kod
    makespan = max(bit[son]) if n else 0.0
    return AkisTablosu(bas, bit, ist, makespan, dict(kisit),
                       {k: dict(v) for k, v in aclik.items()})
