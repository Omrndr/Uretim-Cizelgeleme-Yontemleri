"""
Personel çizelgeleme (rostering) — yasal çalışma süresi sınırlarıyla.

Girdi: her (kaynak, üretim günü) için fiilen çalışılacak net saat h_{k,g}.
Her kaynak-gününe bir personel atanır. Personel e için:

    günlük     Σ_k h_{e,k,g}            ≤ H_gün     (4857 s. İş K. m.63: 11 sa)
    haftalık   Σ_{g∈hafta} h_{e,g}      ≤ H_hafta   (işletme politikası)
    yıllık     B_e + Σ_hafta FM_{e,w}   ≤ H_yıl     (m.41: 270 sa fazla çalışma)
    fazla çalışma  FM_{e,w} = max(0, Σ_{g∈w} h_{e,g} − 45)

Tam model bir tam sayılı programdır (atama + kaynak kısıtları); gün gün
ilerleyen açgözlü bir sezgiselle çözülür:

  1) h_{k,g} > H_gün ise gün ⌈h / H_gün⌉ eşit vardiyaya bölünür; her vardiya AYRI
     personel gerektirir (bir personel günde tek vardiya).
  2) Vardiyalar süresi büyükten küçüğe atanır (en zor yerleşen önce).
  3) Uygun adaylar (üç sınırı da sağlayan) şu sırayla seçilir:
        a. MARJİNAL fazla çalışma doğurmayan önce
              ΔFM = max(0, H_w + h − 45) − max(0, H_w − 45)
           (yıllık 270 saatlik bütçe boşa harcanmasın),
        b. süreklilik: dün aynı kaynakta çalışan,
        c. bu hafta en az çalışmış, yıllık fazla çalışması en düşük olan.
  4) Uygun aday yoksa vardiya "karşılanamayan" olarak raporlanır (plan değişmez,
     ustabaşı kaynağın neden boş kalacağını görür).

Zorunlu molalar çalışma süresi değildir; ama uzun günde doğdukları için
(seçenek açıksa) personelin fazla çalışmasına eklenir.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Sequence, Tuple

from motor.model import Mevzuat

_EPS = 1e-9


@dataclass
class Gorevlendirme:
    tarih: date
    kaynak: str
    atolye: str
    personel: str
    vardiya: int               # 1 = gündüz; 2,3 = bölünmüş günün sonraki vardiyaları
    saat: float
    fazla_mesai: float


@dataclass
class Karsilanamayan:
    tarih: date
    kaynak: str
    atolye: str
    vardiya: int
    saat: float
    sebep: str


@dataclass
class PersonelOzeti:
    personel: str
    gun: int
    saat: float
    plan_fazla_mesai: float
    acilis: float

    @property
    def yil_sonu(self) -> float:
        return self.acilis + self.plan_fazla_mesai


@dataclass
class PersonelAtamasi:
    gorevler: List[Gorevlendirme]
    ozet: List[PersonelOzeti]
    karsilanamayan: List[Karsilanamayan]
    plan_fazla_mesai: Dict[str, float]
    acilis: Dict[str, float]
    yil: int
    uyarilar: List[str] = field(default_factory=list)

    @property
    def uygun(self) -> bool:
        return not self.karsilanamayan

    @property
    def toplam_fazla_mesai(self) -> float:
        return sum(self.plan_fazla_mesai.values())


def vardiyalara_bol(saat: float, gunluk_azami: float) -> List[float]:
    if saat <= gunluk_azami + _EPS:
        return [saat]
    n = math.ceil(saat / gunluk_azami - _EPS)
    return [saat / n] * n


def personel_ata(kaynak_gun_saat: Dict[Tuple[str, date], float],
                 kaynak_atolye: Dict[str, str], personel: Sequence[str],
                 mevzuat: Mevzuat, acilis: Dict[str, float] | None = None,
                 kaynak_gun_mola: Dict[Tuple[str, date], float] | None = None
                 ) -> PersonelAtamasi:
    acilis = {p: float(s) for p, s in (acilis or {}).items()}
    mola = dict(kaynak_gun_mola or {})
    personel = list(personel)
    sira_no = {p: i for i, p in enumerate(personel)}
    gunluk: Dict[Tuple[str, date], float] = defaultdict(float)
    haftalik: Dict[Tuple[str, Tuple[int, int]], float] = defaultdict(float)
    yillik: Dict[Tuple[str, int], float] = {}
    plan_fm: Dict[str, float] = defaultdict(float)
    gun_sayisi: Counter = Counter()
    toplam: Dict[str, float] = defaultdict(float)
    dunku: Dict[str, str] = {}
    gorevler: List[Gorevlendirme] = []
    karsilanamayan: List[Karsilanamayan] = []

    gunler = sorted({g for _, g in kaynak_gun_saat})
    ilk_yil = gunler[0].year if gunler else date.today().year

    def yil_bakiyesi(p: str, yil: int) -> float:
        if (p, yil) not in yillik:
            yillik[(p, yil)] = acilis.get(p, 0.0) if yil == ilk_yil else 0.0
        return yillik[(p, yil)]

    gune_gore: Dict[date, List[Tuple[str, float]]] = defaultdict(list)
    for (k, g), h in kaynak_gun_saat.items():
        if h > _EPS:
            gune_gore[g].append((k, h))

    for g in gunler:
        hafta = tuple(g.isocalendar()[:2])
        bugun: set = set()
        bugunku_kaynak: Dict[str, str] = {}
        for k, h in sorted(gune_gore[g], key=lambda x: (-x[1], x[0])):
            gun_mola = mola.get((k, g), 0.0)
            for vno, vh in enumerate(vardiyalara_bol(h, mevzuat.gunluk_azami_saat), start=1):
                mola_payi = gun_mola * vh / h
                adaylar = []
                for p in personel:
                    if p in bugun:
                        continue
                    if gunluk[(p, g)] + vh > mevzuat.gunluk_azami_saat + _EPS:
                        continue
                    hw = haftalik[(p, hafta)]
                    if hw + vh > mevzuat.haftalik_azami_saat + _EPS:
                        continue
                    dfm = (max(0.0, hw + vh - mevzuat.haftalik_normal_saat)
                           - max(0.0, hw - mevzuat.haftalik_normal_saat))
                    ek = dfm + mola_payi
                    if yil_bakiyesi(p, g.year) + ek > mevzuat.yillik_fazla_calisma_tavani + _EPS:
                        continue
                    adaylar.append((0 if ek <= _EPS else 1,
                                    0 if (vno == 1 and dunku.get(k) == p) else 1,
                                    hw, yil_bakiyesi(p, g.year), sira_no[p], p, ek))
                if not adaylar:
                    karsilanamayan.append(Karsilanamayan(
                        g, k, kaynak_atolye.get(k, "-"), vno, round(vh, 2),
                        "Yasal sınırlar içinde uygun personel kalmadı"))
                    continue
                *_, p, ek = min(adaylar)
                bugun.add(p)
                gunluk[(p, g)] += vh
                haftalik[(p, hafta)] += vh
                yillik[(p, g.year)] = yil_bakiyesi(p, g.year) + ek
                plan_fm[p] += ek
                toplam[p] += vh
                gun_sayisi[p] += 1
                if vno == 1:
                    bugunku_kaynak[k] = p
                gorevler.append(Gorevlendirme(g, k, kaynak_atolye.get(k, "-"), p, vno,
                                              round(vh, 3), round(ek, 3)))
        dunku.update(bugunku_kaynak)

    ozet = [PersonelOzeti(p, gun_sayisi[p], round(toplam[p], 2),
                          round(plan_fm[p], 2), acilis.get(p, 0.0)) for p in personel]
    uyarilar: List[str] = []
    if karsilanamayan:
        say = Counter(x.atolye for x in karsilanamayan)
        uyarilar.append(
            f"[Mevzuat] {len(karsilanamayan)} kaynak-vardiyasına sınırlar içinde "
            f"personel bulunamadı ("
            + ", ".join(f"{a}: {n}" for a, n in say.most_common()) + ").")
    tavan = mevzuat.yillik_fazla_calisma_tavani
    dolu = [o for o in ozet if o.yil_sonu > 0.9 * tavan]
    if dolu:
        uyarilar.append(f"[Mevzuat] {len(dolu)} personel yıllık {tavan:g} saatlik fazla çalışma "
                        f"tavanının %90'ını aştı: "
                        + ", ".join(o.personel for o in dolu[:8])
                        + (" …" if len(dolu) > 8 else ""))
    return PersonelAtamasi(gorevler, ozet, karsilanamayan, dict(plan_fm), acilis,
                           ilk_yil, uyarilar)
