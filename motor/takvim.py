"""
Kaynak takvimleri — "çalışma zamanı" ile "duvar saati" arasındaki dönüşüm.

Bütün zamanlar plan başlangıç gününün 00:00'ından itibaren MUTLAK SANİYEDİR.
Her kaynağın (makine/istasyon) kendi takvimi vardır; çünkü ek mesai tek bir
kaynağa verilebilir ve o kaynak diğerlerinden uzun çalışır.

Bir kaynağın takvimi, ayrık çalışma aralıklarının birleşimidir:

    W = [a_1, b_1) ∪ [a_2, b_2) ∪ ... ,    K_i = Σ_{j<i} (b_j − a_j)   (birikimli)

İki temel fonksiyon:

    g(t)  = t anına kadar birikmiş çalışma       = K_i + (min(t, b_i) − a_i)
    g⁻¹(w)= w çalışma saniyesine ulaşılan an     = a_i + (w − K_i),  K_i < w ≤ K_{i+1}

"t anında başlayıp d saniye süren iş" artık t + d değil, g⁻¹(g(t) + d)'dir.
Her ikisi de ikili arama ile O(log n) hesaplanır.

ÜRETİM GÜNÜ: vardiya başlangıcında başlar ve 24 saat sürer. Gece yarısından
sonra yapılan mesai, bir önceki üretim gününe aittir.

GÜNÜN ÇALIŞMA BLOKLARI: vardiya başından itibaren hedef net süre yerleştirilir;
araya (1) sabit molalar ve (2) aralıksız çalışma sınırını aşan her kesintisiz
dilimden sonra zorunlu mola girer. Molalar çalışma süresi değildir; gün, hedef
nete ulaşmak için gerektiği kadar uzar.
"""
from __future__ import annotations

import math
from bisect import bisect_left, bisect_right
from datetime import date, datetime, time, timedelta
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from motor.model import CalismaDuzeni, EkMesai, Fabrika, TakvimKurali, duzen_kodu

_EPS = 1e-9
SAAT = 3600.0
GUN = 86400.0


class UfukAsildi(RuntimeError):
    """Plan, takvim ufkunun ötesine taşıyor."""


# ==============================================================================
# TEK GÜNÜN BLOKLARI
# ==============================================================================

def gunun_dilimleri(kural: TakvimKurali, gun: date, hedef_net: float,
                    tavan: Optional[float] = None) -> Tuple[List[Tuple[float, float]], float]:
    """
    Bir üretim gününün çalışma blokları (saat cinsinden, gün 00:00'ına göre).

    Dönüş: (bloklar, eklenen_zorunlu_mola_saati). Sabit molalar sayılmaz.
    ``tavan`` brüt pencerenin bitişidir; verilmezse üretim günü sonu (başlangıç+24).
    """
    bas = kural.baslangic
    son = bas + 24.0 if tavan is None else min(float(tavan), bas + 24.0)
    molalar = [m for m in kural.gunun_molalari(gun.weekday()) if m[1] > bas]
    bloklar: List[Tuple[float, float]] = []
    zorunlu = 0.0
    t = bas
    dilim_basi = bas                  # son moladan beri kesintisiz çalışmanın başı
    kalan = max(0.0, float(hedef_net))
    while kalan > _EPS and t < son - _EPS:
        icinde = next((m for m in molalar if m[0] <= t + _EPS and t < m[1] - _EPS), None)
        if icinde:                    # sabit molanın içindeyiz: sonuna atla
            t = dilim_basi = icinde[1]
            continue
        sinir, mola_bitis, zorunlu_mu = son, None, False
        sonraki = next((m for m in molalar if m[0] > t + _EPS), None)
        if sonraki and sonraki[0] < sinir:
            sinir, mola_bitis = sonraki[0], sonraki[1]
        if sinir - dilim_basi > kural.araliksiz_azami_saat + _EPS:
            sinir = dilim_basi + kural.araliksiz_azami_saat
            mola_bitis = sinir + kural.zorunlu_mola_saat
            zorunlu_mu = True
        calisma = min(kalan, sinir - t)
        if calisma > _EPS:
            bloklar.append((t, t + calisma))
            kalan -= calisma
            t += calisma
        if kalan <= _EPS or mola_bitis is None or t < sinir - _EPS:
            break
        if zorunlu_mu:
            zorunlu += mola_bitis - sinir
        t = dilim_basi = mola_bitis
    return bloklar, zorunlu


def brut_pencere_neti(kural: TakvimKurali, gun: date, brut_bitis: float) -> float:
    """[vardiya başı, brüt bitiş) penceresindeki net çalışma saati."""
    bloklar, _ = gunun_dilimleri(kural, gun, math.inf, tavan=brut_bitis)
    return sum(b - a for a, b in bloklar)


def azami_net(kural: TakvimKurali, gun: date) -> float:
    """Bir üretim gününde çalışılabilecek azami net saat (24 saatlik pencere)."""
    bloklar, _ = gunun_dilimleri(kural, gun, math.inf)
    return sum(b - a for a, b in bloklar)


# ==============================================================================
# TEK KAYNAĞIN TAKVİMİ
# ==============================================================================

class KaynakTakvimi:
    """Bir kaynağın çalışma aralıkları ve g / g⁻¹ dönüşümleri."""

    __slots__ = ("a", "b", "kum", "toplam", "gun_baslari")

    def __init__(self, araliklar: Sequence[Tuple[float, float]],
                 gun_baslari: Sequence[float] = ()):
        self.a: List[float] = []
        self.b: List[float] = []
        self.kum: List[float] = []
        k = 0.0
        for x, y in sorted(araliklar):
            if y - x <= _EPS:
                continue
            self.a.append(x)
            self.b.append(y)
            self.kum.append(k)
            k += y - x
        self.toplam = k
        self.gun_baslari: List[float] = sorted(gun_baslari)

    def gecen(self, t: float) -> float:
        """g(t): t anına kadar birikmiş çalışma saniyesi."""
        i = bisect_right(self.a, t) - 1
        if i < 0:
            return 0.0
        return self.kum[i] + (min(t, self.b[i]) - self.a[i])

    def zaman(self, w: float) -> float:
        """g⁻¹(w): w çalışma saniyesine ulaşılan an (bitiş anlamında)."""
        if not self.a:
            raise UfukAsildi("Kaynağın hiç çalışma zamanı yok.")
        if w > self.toplam + _EPS:
            raise UfukAsildi("İş, takvim ufkunun ötesine taşıyor.")
        i = max(0, bisect_left(self.kum, w) - 1)
        return self.a[i] + (w - self.kum[i])

    def ilk_musait(self, t: float) -> float:
        i = bisect_right(self.a, t) - 1
        if i >= 0 and t < self.b[i] - _EPS:
            return t
        if i + 1 < len(self.a):
            return self.a[i + 1]
        raise UfukAsildi("Takvim ufkunun ötesinde çalışma zamanı yok.")

    def ilerlet(self, t: float, sure: float) -> float:
        """t anında (ya da ilk müsait anda) başlayan, ``sure`` sn'lik işin bitişi."""
        if sure <= 0:
            return self.ilk_musait(t)
        return self.zaman(self.gecen(t) + sure)

    def sonraki_gun_basi(self, t: float) -> float:
        """t'den sonraki ilk çalışma GÜNÜNÜN başı (ayarı güne hizalamak için)."""
        i = bisect_left(self.gun_baslari, t - _EPS)
        if i < len(self.gun_baslari):
            return self.gun_baslari[i]
        raise UfukAsildi("Takvim ufkunun ötesinde çalışma günü yok.")

    def calisma(self, x: float, y: float) -> float:
        """[x, y) aralığındaki çalışma saniyesi."""
        return max(0.0, self.gecen(y) - self.gecen(x)) if y > x else 0.0


# ==============================================================================
# FABRİKANIN TAKVİMİ
# ==============================================================================

class FabrikaTakvimi:
    """Varsayılan çalışma düzeni + ek mesai talimatlarıyla bütün kaynak takvimleri."""

    def __init__(self, fabrika: Fabrika, baslangic: date, kaynak_adlari: Iterable[str],
                 ek_mesailer: Sequence[EkMesai] = (), duzen: str = "",
                 ufuk_gun: int = 900):
        self.kural = fabrika.takvim
        self.baslangic = baslangic
        self.t0 = datetime.combine(baslangic, time())
        self.duzen: CalismaDuzeni = self.kural.duzen(duzen)
        self.kaynaklar = list(kaynak_adlari)
        gecerli = set(self.kaynaklar)
        self.ek_mesailer = [e for e in ek_mesailer
                            if e.etkili_mi(self.duzen.kod) and e.kaynak in gecerli]
        self.gunler = [baslangic + timedelta(days=i) for i in range(ufuk_gun)]
        self._onbellek: Dict[Tuple[int, float, float], Tuple[List, float]] = {}
        self.net: Dict[str, Dict[date, float]] = {}
        self.zorunlu_mola: Dict[str, Dict[date, float]] = {}
        self.pencereler: Dict[str, Dict[date, List[Tuple[float, float]]]] = {}
        self.takvimler: Dict[str, KaynakTakvimi] = {}
        for k in self.kaynaklar:
            self._kaynagi_kur(k)

    # ------------------------------------------------------------------ kurulum
    def _bloklar(self, gun: date, hedef: float, tavan: Optional[float]):
        anahtar = (gun.weekday(), round(hedef, 6), round(tavan or -1.0, 6))
        if anahtar not in self._onbellek:
            self._onbellek[anahtar] = gunun_dilimleri(self.kural, gun, hedef, tavan)
        return self._onbellek[anahtar]

    def gun_ayari(self, kaynak: str, gun: date) -> Tuple[CalismaDuzeni, float, bool]:
        """(geçerli düzen, toplam ek saat, hafta sonu izni). Çakışan talimatlarda
        brüt bitişi en geç olan düzen kazanır, ek saatler toplanır."""
        duzen, ek, hafta_sonu = self.duzen, 0.0, False
        for e in self.ek_mesailer:
            if e.kaynak != kaynak or not (e.baslangic <= gun <= e.bitis):
                continue
            d = self.kural.duzen(duzen_kodu(e.duzen, self.kural) if e.duzen else self.duzen.kod)
            if d.brut_bitis > duzen.brut_bitis:
                duzen = d
            ek += e.ek_saat
            hafta_sonu = hafta_sonu or e.hafta_sonu
        return duzen, ek, hafta_sonu

    def _gun_hedefi(self, kaynak: str, gun: date) -> float:
        duzen, ek, hafta_sonu = self.gun_ayari(kaynak, gun)
        if gun.weekday() < duzen.gun:
            bloklar, _ = self._bloklar(gun, math.inf, duzen.brut_bitis)
            return sum(b - a for a, b in bloklar) + ek
        return ek if (hafta_sonu and ek > 0) else 0.0

    def _kaynagi_kur(self, kaynak: str) -> None:
        net, mola, pen = {}, {}, {}
        araliklar: List[Tuple[float, float]] = []
        gun_baslari: List[float] = []
        for g in self.gunler:
            hedef = self._gun_hedefi(kaynak, g)
            if hedef <= _EPS:
                continue
            bloklar, zorunlu = self._bloklar(g, hedef, None)
            if not bloklar:
                continue
            taban = (g - self.baslangic).days * GUN
            mutlak = [(taban + a * SAAT, taban + b * SAAT) for a, b in bloklar]
            net[g] = sum(b - a for a, b in bloklar)
            mola[g] = zorunlu
            pen[g] = mutlak
            araliklar.extend(mutlak)
            gun_baslari.append(mutlak[0][0])
        self.net[kaynak] = net
        self.zorunlu_mola[kaynak] = mola
        self.pencereler[kaynak] = pen
        self.takvimler[kaynak] = KaynakTakvimi(araliklar, gun_baslari)

    # ---------------------------------------------------------------- yardımcı
    def takvim(self, kaynak: str) -> KaynakTakvimi:
        return self.takvimler[kaynak]

    def zamana(self, t: float) -> datetime:
        return self.t0 + timedelta(seconds=max(0.0, float(t)))

    def hangi_gun(self, t: float) -> date:
        return (self.zamana(t) - timedelta(hours=self.kural.baslangic)).date()

    def taban_net(self, gun: date) -> float:
        """Varsayılan düzende o günün net saati (0 = çalışılmayan gün)."""
        if gun.weekday() >= self.duzen.gun:
            return 0.0
        bloklar, _ = self._bloklar(gun, math.inf, self.duzen.brut_bitis)
        return sum(b - a for a, b in bloklar)

    @property
    def ortalama_gun_saati(self) -> float:
        hafta = [self.taban_net(self.baslangic + timedelta(days=i)) for i in range(7)]
        calisan = [h for h in hafta if h > 0]
        return sum(calisan) / len(calisan) if calisan else 0.0

    @property
    def haftalik_saat(self) -> float:
        return sum(self.taban_net(self.baslangic + timedelta(days=i)) for i in range(7))

    def aktif_gunler(self) -> List[date]:
        out = set()
        for net in self.net.values():
            out.update(net)
        return sorted(out)

    def is_gunu_sayisi(self, bas: date, bit: date) -> int:
        n, g = 0, bas
        while g <= bit:
            n += self.taban_net(g) > 0
            g += timedelta(days=1)
        return n

    def termin_saniyesi(self, termin: date) -> float:
        """Termin = termin gününün (çalışılmıyorsa önceki iş gününün) varsayılan
        vardiya bitişi."""
        g = termin
        while g >= self.baslangic and self.taban_net(g) <= 0:
            g -= timedelta(days=1)
        if g < self.baslangic:
            return 0.0
        bloklar, _ = self._bloklar(g, math.inf, self.duzen.brut_bitis)
        return (g - self.baslangic).days * GUN + bloklar[-1][1] * SAAT

    def gun_penceresi(self, gun: date) -> Tuple[float, float]:
        """Üretim gününün (en geç biten kaynağa göre) brüt penceresi, saat olarak."""
        bas = self.kural.baslangic
        son = bas
        taban = (gun - self.baslangic).days * GUN
        for pen in self.pencereler.values():
            bloklar = pen.get(gun)
            if bloklar:
                son = max(son, (bloklar[-1][1] - taban) / SAAT)
        if son <= bas:
            son = self.duzen.brut_bitis
        return bas, son
