"""
İş emirleri — sahaya verilecek satırların veri katmanı.

Bir satır, bir kaynağın bir üretim gününde bir vardiyada bir sipariş için
yaptığı işi anlatır ve dört bilgiyi birlikte taşır:

    ZAMAN (başlangıç–bitiş) · KAYNAK · PERSONEL · İŞ EMRİ (sipariş)

YÖNTEM
  1. Her (kaynak, gün) için o gün fiilen çalışılan aralıklar çıkarılır
     (meşgul aralıklar ∩ takvim pencereleri).
  2. Bu birleşik zaman çizgisi, personel atamasındaki vardiya saatleri kadar
     sırayla dilimlenir: 1. vardiya ilk h₁ saati, 2. vardiya sonraki h₂ saati...
     Böylece 11 saati aşıp bölünen bir günde her vardiyanın gerçek saatleri belli olur.
  3. Her zaman çubuğu her vardiya dilimiyle kesiştirilir. Kesişen parçanın adedi:
       hücre/hat : kesin — başlangıcı parçaya düşen ürünler sayılır
       makine    : çalışma süresi oranıyla, parti ilerlemesine göre
  4. Sipariş atfı: montajda kesindir. Makinelerde parçalar ortak stoğa girer;
     sipariş, partinin beslediği ürünlerin üretim sırasındaki konumundan türetilir
     (parça partisi: sıra aralığı; varyant partisi: varyantın kaçıncı adetleri).
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional, Sequence, Tuple

from motor import cubuklar as cb
from motor.cozucu import Plan
from motor.personel import vardiyalara_bol
from motor.takvim import SAAT

GUN_KISALTMA = ("Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz")
ATANAMADI = "ATANAMADI"
AYAR_IS = "Ayar"

BASLIKLAR = ("Tarih", "Gün", "Atölye", "Kaynak", "Vardiya", "Başlangıç", "Bitiş",
             "Süre (sa)", "Personel", "Tür", "Görev", "Sipariş", "Varyant", "Adet")

KAYNAK_NOTU = ("Makine satırlarındaki sipariş bilgisi, o partinin karşıladığı ihtiyacı "
               "gösterir; parçalar ortak stoktan çekilir.")


@dataclass
class IsEmri:
    tarih: date
    atolye: str
    kaynak: str
    vardiya: int
    bas: float
    bit: float
    calisma_sn: float
    personel: str
    tur: str
    gorev: str
    siparis: str
    varyant: str
    adet: int

    def satir(self, plan: Plan) -> Dict[str, object]:
        tk = plan.takvim
        return {"Tarih": self.tarih.strftime("%d.%m.%Y"), "Gün": GUN_KISALTMA[self.tarih.weekday()],
                "Atölye": self.atolye, "Kaynak": self.kaynak, "Vardiya": self.vardiya,
                "Başlangıç": tk.zamana(self.bas).strftime("%H:%M"),
                "Bitiş": tk.zamana(self.bit).strftime("%H:%M"),
                "Süre (sa)": round(self.calisma_sn / SAAT, 2), "Personel": self.personel,
                "Tür": self.tur, "Görev": self.gorev, "Sipariş": self.siparis,
                "Varyant": self.varyant, "Adet": self.adet}


def _kesisim(araliklar: Sequence[Tuple[float, float]], a: float, b: float
             ) -> List[Tuple[float, float]]:
    return [(max(x, a), min(y, b)) for x, y in araliklar if min(y, b) - max(x, a) > 1e-6]


def _dilimle(araliklar: List[Tuple[float, float]], saatler: List[float]
             ) -> List[List[Tuple[float, float]]]:
    """Aralık listesini sırayla verilen saat uzunluklarında parçalara böler."""
    out: List[List[Tuple[float, float]]] = []
    kuyruk = list(araliklar)
    for h in saatler:
        kalan = h * SAAT
        dilim: List[Tuple[float, float]] = []
        while kuyruk and kalan > 1e-6:
            a, b = kuyruk[0]
            if b - a <= kalan + 1e-6:
                dilim.append((a, b))
                kalan -= b - a
                kuyruk.pop(0)
            else:
                dilim.append((a, a + kalan))
                kuyruk[0] = (a + kalan, b)
                kalan = 0
        out.append(dilim)
    if kuyruk and out:                 # yuvarlama artığı son vardiyaya
        out[-1].extend(kuyruk)
    return out


def _ozet(sayac: Counter, sira: Sequence[str] = ()) -> str:
    return cb.ozet_metni(+sayac, sira)


def is_emirleri(plan: Plan) -> List[IsEmri]:
    f, tk = plan.fabrika, plan.takvim
    mesgul = cb.mesgul_araliklar(plan)
    saatler = cb.calisilan_saatler(tk, mesgul)
    kim: Dict[Tuple[str, date, int], str] = {}
    if plan.atama:
        for g in plan.atama.gorevler:
            kim[(g.kaynak, g.tarih, g.vardiya)] = g.personel
    # (kaynak, gün) -> [(vardiya no, personel, aralıklar)]
    vardiyalar: Dict[Tuple[str, date], List[Tuple[int, str, List[Tuple[float, float]]]]] = {}
    for (k, g), h in saatler.items():
        gun_mesgul: List[Tuple[float, float]] = []
        for a, b in tk.pencereler[k].get(g, ()):
            gun_mesgul.extend(_kesisim(mesgul.get(k, ()), a, b))
        gun_mesgul.sort()
        bolum = vardiyalara_bol(h, f.mevzuat.gunluk_azami_saat)
        dilimler = _dilimle(gun_mesgul, bolum)
        vardiyalar[(k, g)] = [
            (i, (kim.get((k, g, i), ATANAMADI) if plan.atama else "-"), d)
            for i, d in enumerate(dilimler, start=1)]

    varyant_konum: Dict[str, List[int]] = defaultdict(list)
    for i, (_, v) in enumerate(plan.sira):
        varyant_konum[v].append(i)

    out: List[IsEmri] = []
    for c in cb.tum_cubuklar(plan, gune_bol=True):
        takvim = tk.takvim(c.kaynak)
        toplam_is = max(takvim.calisma(c.bas, c.bit), 1e-9)
        g0, g1 = tk.hangi_gun(c.bas), tk.hangi_gun(max(c.bas, c.bit - 1e-6))
        gunler = [g for g in tk.net.get(c.kaynak, {}) if g0 <= g <= g1]
        for g in sorted(gunler):
            for vno, kisi, dilim in vardiyalar.get((c.kaynak, g), ()):
                parca = _kesisim(dilim, c.bas, c.bit)
                if not parca:
                    continue
                is_sn = sum(b - a for a, b in parca)
                x, y = parca[0][0], parca[-1][1]
                if c.tur == cb.AYAR:
                    out.append(IsEmri(g, c.atolye, c.kaynak, vno, x, y, is_sn, kisi,
                                      cb.AYAR, c.gorev, AYAR_IS, "", 0))
                    continue
                if c.urunler:                       # hücre / hat: kesin
                    kod = c.urunler
                    op = c.gorev.split()[0]
                    bas_, bit_ = plan.akis.bas[op], plan.akis.bit[op]
                    secili = [i for i in kod
                              if any(a - 1e-6 <= bas_[i] < b for a, b in parca)]
                    # Önceki günden taşan ürünün kalan kısmı: adet sayılmaz, sipariş yazılır
                    temas = secili or [i for i in kod if bas_[i] < y and bit_[i] > x]
                    sip = Counter(plan.sira[i][0] for i in temas)
                    var = Counter(plan.sira[i][1] for i in secili)
                    adet = len(secili)
                else:                                # makine: oransal
                    p = c.parti
                    u0 = round(p.adet * takvim.calisma(c.bas, x) / toplam_is)
                    u1 = round(p.adet * takvim.calisma(c.bas, y) / toplam_is)
                    adet = max(0, u1 - u0)
                    if p.sira_bas >= 0:
                        urunler = range(p.sira_bas + u0, p.sira_bas + u1)
                    else:
                        konum = varyant_konum.get(p.nesne, [])
                        urunler = [konum[j] for j in p.dilimler[u0:u1] if j < len(konum)]
                    sip = Counter(plan.sira[i][0] for i in urunler)
                    var = Counter(plan.sira[i][1] for i in urunler)
                if adet <= 0 and is_sn < 60:
                    continue
                out.append(IsEmri(g, c.atolye, c.kaynak, vno, x, y, is_sn, kisi,
                                  cb.URETIM, c.gorev, _ozet(sip), _ozet(var, f.varyantlar),
                                  adet))
    return _birlestir(out)


def _birlestir(kayitlar: List[IsEmri]) -> List[IsEmri]:
    kayitlar.sort(key=lambda r: (r.kaynak, r.tarih, r.vardiya, r.bas))
    out: List[IsEmri] = []
    for r in kayitlar:
        if out:
            s = out[-1]
            if (s.kaynak, s.tarih, s.vardiya, s.gorev, s.siparis, s.tur) == \
                    (r.kaynak, r.tarih, r.vardiya, r.gorev, r.siparis, r.tur) \
                    and r.bas - s.bit <= 3600:
                s.bit = max(s.bit, r.bit)
                s.calisma_sn += r.calisma_sn
                s.adet += r.adet
                s.varyant = s.varyant or r.varyant
                continue
        out.append(r)
    out.sort(key=lambda r: (r.tarih, r.atolye, r.kaynak, r.bas))
    return out


# ==============================================================================
# SÜZGEÇLER VE GÖRÜNÜMLER
# ==============================================================================

def suz(emirler: Sequence[IsEmri], *, atolye: Optional[str] = None,
        kaynak: Optional[str] = None, personel: Optional[str] = None,
        siparis: Optional[str] = None, bas: Optional[date] = None,
        bit: Optional[date] = None) -> List[IsEmri]:
    out = []
    for r in emirler:
        if atolye and r.atolye != atolye:
            continue
        if kaynak and r.kaynak != kaynak:
            continue
        if personel and r.personel != personel:
            continue
        if siparis and siparis not in r.siparis:
            continue
        if bas and r.tarih < bas:
            continue
        if bit and r.tarih > bit:
            continue
        out.append(r)
    return out


def personel_karti(emirler: Sequence[IsEmri], personel: str) -> List[IsEmri]:
    """Bir personelin bütün görevleri, zaman sırasıyla."""
    return sorted(suz(emirler, personel=personel), key=lambda r: r.bas)


def tablo(plan: Plan, emirler: Sequence[IsEmri]) -> List[Dict[str, object]]:
    return [r.satir(plan) for r in emirler]
