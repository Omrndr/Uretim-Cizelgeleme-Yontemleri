"""
Varyant bileşeni planı — takım kısıtlı paralel makineler.

Varyant v için en fazla T_v makine aynı anda çalışabilir (takım adedi). Makine
sayısı m, talep d_v.

1) BAŞLANGIÇ PAYLARI — akışkan gevşetme:
   Makineler sürekli bölünebilseydi her varyanta talebi oranında pay düşerdi:
        s_v = m · d_v / Σ d
   Tam sayıya indirgeme: n_v = clamp(⌊s_v⌋, 1, T_v). Toplam m'yi aşarsa önce
   üretim sırasında EN GEÇ ihtiyaç duyulan varyanttan eksiltilir; eksikse kalan
   makineler d_v / (n_v + 1) oranı en büyük varyanta (D'Hondt / Jefferson bölen
   yöntemi) takım sınırı içinde verilir.

2) OLAY GÜDÜMLÜ BENZETİM:
   Makineler bir öncelik kuyruğunda (en erken müsait olan önce) tutulur. Her
   olayda makine ya kendi varyantından bir adet daha üretir ya da varyant
   değiştirir. Değişim kuralları:
     * Kendi varyantının talebi bittiyse -> takımı boşta olan varyantlar içinde
       bir sonraki adedine hatta EN ERKEN ihtiyaç duyulana geçer (ihtiyaç anı
       önceliği: k. adedin üretim sırasındaki konumu).
     * AMORTİSMAN KESMESİ: Hiç makinesi olmayan ("aç") bir varyant varsa ve bu
       makine son ayardan beri en az q_min adet ürettiyse VE hat aç varyantı
       mevcut varyanttan daha önce isteyecekse (ihtiyaç konumu daha küçükse) seri
       kesilir ve aç varyanta geçilir. Böylece hiçbir varyant hat sonuna kadar
       bekletilmez, ama makine de iki renk arasında gereksiz yere gidip gelmez.

   q_min, ayarın makine zamanındaki payını α ile sınırlar. q adetlik bir seride
   ayar payı  S / (S + q·τ) ≤ α  ⇔  q ≥ S(1 − α) / (α·τ):

        q_min = ⌈ S (1 − α) / (α τ) ⌉        α = 0,5 → q_min = ⌈S/τ⌉ (başa baş)

SİPARİŞ ATFI: Varyant v'nin j. bitirilen adedi, üretim sırasında v varyantlı
j. ürünü besler (bitiş zamanına göre sıralanır).
"""
from __future__ import annotations

import heapq
import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from motor.model import Fabrika
from motor.parti import Parti
from motor.tahsis import Dagilim, kaynak_adi
from motor.takvim import KaynakTakvimi


@dataclass
class VaryantSonucu:
    partiler: List[Parti]
    bitisler: Dict[str, List[float]]       # varyant -> sıralı bitiş anları
    ayar_sayisi: int
    uyarilar: List[str] = field(default_factory=list)


def varyant_paylari(talep: Dict[str, int], makine: int, takim: Dict[str, int],
                    ilk_ihtiyac: Optional[Dict[str, int]] = None) -> Dict[str, int]:
    aktif = {v: d for v, d in talep.items() if d > 0}
    if not aktif or makine <= 0:
        return {}
    toplam = sum(aktif.values())
    pay = {v: makine * d / toplam for v, d in aktif.items()}
    n = {v: max(1, min(math.floor(pay[v]), takim.get(v, 1))) for v in aktif}
    ilk = ilk_ihtiyac or {}
    while sum(n.values()) > makine:
        v = max((v for v in n if n[v] > 0),
                key=lambda v: (n[v] > 1, ilk.get(v, 0), -aktif[v], v))
        n[v] -= 1
    while sum(n.values()) < makine:
        aday = [v for v in aktif if n[v] < takim.get(v, 1)]
        if not aday:
            break
        v = max(aday, key=lambda v: (aktif[v] / (n[v] + 1), v))
        n[v] += 1
    return {v: k for v, k in n.items() if k > 0}


@dataclass
class _Makine:
    no: int
    ad: str
    tk: KaynakTakvimi
    t: float
    varyant: Optional[str] = None
    ayar_gerek: bool = True
    seri: int = 0
    parti_no: int = 0
    acik_bas: Optional[float] = None
    acik_adet: int = 0
    acik_ayar: Tuple[Optional[float], Optional[float]] = (None, None)
    acik_id: int = -1


def varyant_plani(fabrika: Fabrika, tahsis: Dagilim, sira: Sequence[Tuple[str, str]],
                  ayar_sn: float, takvimler: Dict[str, KaynakTakvimi],
                  hizala: bool = False, azami_ayar_payi: float = 0.25) -> VaryantSonucu:
    vg = fabrika.varyant_grubu
    if vg is None:
        return VaryantSonucu([], {}, 0)
    uyarilar: List[str] = []
    konumlar: Dict[str, List[int]] = defaultdict(list)
    for i, (_, v) in enumerate(sira):
        konumlar[v].append(i)
    talep = {v: len(k) for v, k in konumlar.items()}
    bitisler: Dict[str, List[float]] = {v: [] for v in fabrika.varyantlar}
    if not talep:
        return VaryantSonucu([], bitisler, 0)

    m = tahsis.personel[vg.kod]
    paylar = varyant_paylari(talep, m, vg.takim_adedi, {v: k[0] for v, k in konumlar.items()})
    if sum(paylar.values()) < m:
        uyarilar.append(
            f"[Kapasite] {vg.ad}: {m} makineden yalnız "
            f"{sum(paylar.values())} tanesi aynı anda çalışabiliyor; talep edilen "
            f"varyantların {vg.takim_adi.lower()} toplamı yetersiz.")

    makineler: List[_Makine] = []
    for no in range(1, m + 1):
        ad = kaynak_adi(vg.kod, no, fabrika)
        tk = takvimler[ad]
        makineler.append(_Makine(no, ad, tk, tk.ilk_musait(0.0)))
    atanacak = [v for v, k in sorted(paylar.items(), key=lambda x: konumlar[x[0]][0])
                for _ in range(k)]
    for mk, v in zip(makineler, atanacak):
        mk.varyant = v

    aktif = defaultdict(int)
    for mk in makineler:
        if mk.varyant:
            aktif[mk.varyant] += 1
    kalan = dict(talep)

    def ihtiyac(v: str) -> int:
        """v'nin henüz üretimine başlanmamış ilk adedinin sıradaki konumu."""
        return konumlar[v][talep[v] - kalan[v]]

    alfa = min(0.95, max(0.05, azami_ayar_payi))
    q_min = max(1, math.ceil(ayar_sn * (1 - alfa) / (alfa * vg.sure_sn))) if ayar_sn > 0 else 1
    partiler: List[Parti] = []
    birimler: Dict[str, List[Tuple[float, int]]] = defaultdict(list)
    kimlik_indeksi: Dict[int, int] = {}
    sayac = 0
    ayar_sayisi = 0

    def seriyi_kapat(mk: _Makine) -> None:
        if mk.acik_adet > 0 and mk.acik_bas is not None:
            kimlik_indeksi[mk.acik_id] = len(partiler)
            partiler.append(Parti(vg.ad, vg.kod, mk.ad, mk.varyant,
                                  f"{vg.bilesen} · {mk.varyant}", mk.parti_no,
                                  mk.acik_ayar[0], mk.acik_ayar[1], mk.acik_bas, mk.t,
                                  mk.acik_adet, vg.sure_sn, vg.ayar_etiketi))
        mk.acik_bas, mk.acik_adet, mk.acik_ayar = None, 0, (None, None)

    kuyruk = [(mk.t, mk.no) for mk in makineler]
    heapq.heapify(kuyruk)
    while kuyruk and sum(kalan.values()) > 0:
        _, no = heapq.heappop(kuyruk)
        mk = makineler[no - 1]
        bos_takim = [v for v in talep if kalan[v] > 0 and aktif[v] < vg.takim_adedi[v]]
        yeni = None
        if mk.varyant is None or kalan.get(mk.varyant, 0) <= 0:
            if bos_takim:
                yeni = min(bos_takim, key=lambda v: (ihtiyac(v), v))
        elif mk.seri >= q_min:
            simdi = ihtiyac(mk.varyant)
            ac = [v for v in bos_takim if aktif[v] == 0 and ihtiyac(v) < simdi]
            if ac:
                yeni = min(ac, key=lambda v: (ihtiyac(v), v))
        if yeni is not None:
            seriyi_kapat(mk)
            if mk.varyant:
                aktif[mk.varyant] -= 1
            aktif[yeni] += 1
            mk.varyant, mk.ayar_gerek, mk.seri = yeni, True, 0
            heapq.heappush(kuyruk, (mk.t, mk.no))
            continue
        if mk.varyant is None or kalan.get(mk.varyant, 0) <= 0:
            seriyi_kapat(mk)                       # iş kalmadı: makine devreden çıkar
            if mk.varyant:
                aktif[mk.varyant] -= 1
            mk.varyant = None
            continue
        if mk.ayar_gerek:
            mk.parti_no += 1
            if ayar_sn > 0:
                ab = mk.tk.sonraki_gun_basi(mk.t) if hizala else mk.tk.ilk_musait(mk.t)
                abit = mk.tk.ilerlet(ab, ayar_sn)
                mk.acik_ayar = (ab, abit)
                mk.t = abit
                ayar_sayisi += 1
            mk.ayar_gerek = False
        if mk.acik_bas is None:
            mk.acik_bas = mk.tk.ilk_musait(mk.t)
            mk.t = mk.acik_bas
            sayac += 1
            mk.acik_id = sayac
        mk.t = mk.tk.ilerlet(mk.t, vg.sure_sn)
        mk.acik_adet += 1
        mk.seri += 1
        kalan[mk.varyant] -= 1
        birimler[mk.varyant].append((mk.t, mk.acik_id))
        heapq.heappush(kuyruk, (mk.t, mk.no))
    for mk in makineler:
        seriyi_kapat(mk)

    dilim: Dict[int, List[int]] = defaultdict(list)
    for v, kayit in birimler.items():
        kayit.sort()
        bitisler[v] = [t for t, _ in kayit]
        for j, (_, kid) in enumerate(kayit):
            dilim[kid].append(j)
    for kid, js in dilim.items():
        i = kimlik_indeksi.get(kid)
        if i is not None:
            partiler[i].dilimler = tuple(js)
    return VaryantSonucu(partiler, bitisler, ayar_sayisi, uyarilar)
