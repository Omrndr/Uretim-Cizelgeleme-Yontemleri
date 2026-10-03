"""
Yöntem testleri — her algoritma bağımsız bir doğrulamayla karşılaştırılır.

    python -m unittest discover -s testler -v
"""
import itertools
import math
import random
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from motor.dengeleme import alt_sinir, dengele                       # noqa: E402
from motor.model import fabrika_yukle, Siparis                       # noqa: E402
from motor.parti import parti_buyuklukleri                           # noqa: E402
from motor.personel import personel_ata, vardiyalara_bol              # noqa: E402
from motor.siralama import hedef_kovalama, is_sirasi              # noqa: E402
from motor.tahsis import TahsisBirimi, min_max_tahsis, tahsis_birimleri  # noqa: E402
from motor.takvim import KaynakTakvimi, gunun_dilimleri, brut_pencere_neti   # noqa: E402
from motor.varyant import varyant_paylari                            # noqa: E402

FABRIKA = fabrika_yukle()


def kesin_cmax(sureler, m):
    """Kaba kuvvet P||Cmax optimumu (küçük örnekler için)."""
    t = list(sureler.values())
    en = math.inf
    for atama in itertools.product(range(m), repeat=len(t)):
        if atama and atama[0] != 0:          # simetri kırma
            continue
        yuk = [0.0] * m
        for p, k in zip(t, atama):
            yuk[k] += p
        en = min(en, max(yuk))
    return en


class DengelemeTesti(unittest.TestCase):
    def test_lpt_garantisi_ve_alt_sinir(self):
        rnd = random.Random(7)
        for _ in range(40):
            n, m = rnd.randint(3, 8), rnd.randint(2, 3)
            sureler = {f"p{i}": float(rnd.randint(3, 60)) for i in range(n)}
            d = dengele(sureler, m)
            opt = kesin_cmax(sureler, m)
            self.assertGreaterEqual(d.cmax + 1e-9, opt)
            self.assertGreaterEqual(opt + 1e-9, alt_sinir(sureler, m))
            self.assertLessEqual(d.lpt_cmax, (4 / 3 - 1 / (3 * m)) * opt + 1e-9)
            self.assertLessEqual(d.cmax, d.lpt_cmax + 1e-9)      # yerel arama kötüleştirmez
            self.assertEqual(sorted(p for g in d.gruplar for p in g), sorted(sureler))

    def test_yerel_arama_cogunlukla_optimum(self):
        rnd = random.Random(11)
        optimum = 0
        for _ in range(30):
            sureler = {f"p{i}": float(rnd.randint(5, 50)) for i in range(7)}
            optimum += abs(dengele(sureler, 3).cmax - kesin_cmax(sureler, 3)) < 1e-9
        self.assertGreaterEqual(optimum, 24)


class TahsisTesti(unittest.TestCase):
    def _kaba_kuvvet(self, birimler, butce):
        en = None
        for w in itertools.product(*[range(1, b.ust + 1) for b in birimler]):
            if sum(w) > butce:
                continue
            c = max(b.cevrim(k) for b, k in zip(birimler, w))
            anahtar = (round(c, 9), sum(w))
            en = anahtar if en is None or anahtar < en else en
        return en

    def test_ornek_fabrikada_kaba_kuvvete_esit(self):
        birimler, _ = tahsis_birimleri(FABRIKA, FABRIKA.varyantlar)
        for butce in range(len(birimler), 23):
            beklenen = self._kaba_kuvvet(birimler, butce)
            w, c = min_max_tahsis(birimler, butce)
            self.assertEqual((round(c, 9), sum(w.values())), beklenen, f"bütçe {butce}")

    def test_rastgele_birimler(self):
        rnd = random.Random(3)
        for _ in range(60):
            birimler = []
            for i in range(rnd.randint(2, 5)):
                tau = rnd.uniform(20, 200)
                ust = rnd.randint(1, 4)
                birimler.append(TahsisBirimi(f"U{i}", "", "", "hat",
                                             tuple(tau / k for k in range(1, ust + 1))))
            butce = rnd.randint(len(birimler), len(birimler) + 6)
            w, c = min_max_tahsis(birimler, butce)
            self.assertEqual((round(c, 9), sum(w.values())), self._kaba_kuvvet(birimler, butce))

    def test_yetersiz_kadro(self):
        birimler, _ = tahsis_birimleri(FABRIKA, FABRIKA.varyantlar)
        self.assertIsNone(min_max_tahsis(birimler, len(birimler) - 1))


class TakvimTesti(unittest.TestCase):
    kural = FABRIKA.takvim
    pzt = date(2026, 11, 2)

    def test_net_saatler(self):
        self.assertAlmostEqual(brut_pencere_neti(self.kural, self.pzt, 17.75), 8.5)
        self.assertAlmostEqual(brut_pencere_neti(self.kural, self.pzt, 20.25), 11.0)

    def test_zorunlu_mola(self):
        bloklar, mola = gunun_dilimleri(self.kural, self.pzt, 12.0)
        self.assertAlmostEqual(sum(b - a for a, b in bloklar), 12.0)
        self.assertAlmostEqual(mola, self.kural.zorunlu_mola_saat)
        for (a, b) in bloklar:                       # hiçbir blok sınırı aşmaz
            self.assertLessEqual(b - a, self.kural.araliksiz_azami_saat + 1e-9)
        for m0, m1 in self.kural.molalar:            # sabit molalar çalışılmaz
            for a, b in bloklar:
                self.assertFalse(a < m1 - 1e-9 and b > m0 + 1e-9)

    def test_ters_donusum(self):
        tk = KaynakTakvimi([(100, 200), (300, 450), (1000, 1100)], [100, 1000])
        for w in [1, 50, 100, 101, 149, 250, 349]:
            self.assertAlmostEqual(tk.gecen(tk.zaman(w)), w)
        self.assertEqual(tk.ilerlet(150, 100), 350)    # 50 (ilk blok) + 50 (ikinci blok)
        self.assertEqual(tk.ilerlet(150, 200), 450)    # 50 + 150: ikinci bloğun tam sonu
        self.assertEqual(tk.ilk_musait(250), 300)
        self.assertEqual(tk.zaman(100), 200)          # tam blok sonunda biten iş
        self.assertEqual(tk.sonraki_gun_basi(150), 1000)


class PartiVeSiraTesti(unittest.TestCase):
    def test_parti_buyuklukleri(self):
        for n in (1, 7, 100, 5501):
            for k in (1, 2, 3, 5):
                for r in (1.0, 1.5, 3.0):
                    q = parti_buyuklukleri(n, k, r)
                    self.assertEqual(sum(q), n)
                    self.assertTrue(all(x >= 1 for x in q))
                    if n >= 50 and r > 1:
                        self.assertTrue(all(a <= b for a, b in zip(q, q[1:])))

    def test_hedef_kovalama_oran_sapmasi(self):
        d = {"A": 37, "B": 11, "C": 23}
        s = hedef_kovalama(d)
        toplam = sum(d.values())
        sayac = {v: 0 for v in d}
        for k, v in enumerate(s, start=1):
            sayac[v] += 1
            for x in d:
                self.assertLess(abs(sayac[x] - d[x] * k / toplam), 1.0 + 1e-9)
        self.assertEqual({v: s.count(v) for v in d}, d)

    def test_edd(self):
        s = [Siparis("B", {"Krem": 2}, date(2027, 1, 5)),
             Siparis("A", {"Krem": 1}, date(2026, 12, 1))]
        self.assertEqual([k for k, _ in is_sirasi(s)], ["A", "B", "B"])

    def test_varyant_paylari(self):
        takim = {"A": 2, "B": 1, "C": 1}
        for talep in ({"A": 100, "B": 5}, {"A": 1, "B": 1, "C": 1}, {"C": 10}):
            for m in (1, 2, 3, 4):
                p = varyant_paylari(talep, m, takim)
                self.assertLessEqual(sum(p.values()), m)
                for v, n in p.items():
                    self.assertLessEqual(n, takim[v])


class PersonelTesti(unittest.TestCase):
    def test_bolme(self):
        self.assertEqual(vardiyalara_bol(10, 11), [10])
        self.assertEqual(vardiyalara_bol(14, 11), [7, 7])
        self.assertEqual(len(vardiyalara_bol(23, 11)), 3)

    def test_yasal_sinirlar(self):
        m = FABRIKA.mevzuat
        gunler = [date(2026, 11, 2 + i) for i in range(12)]
        talep = {(f"K{k}", g): (13.0 if k < 2 else 9.0) for k in range(5) for g in gunler}
        a = personel_ata(talep, {}, [f"P{i}" for i in range(9)], m, {"P0": 260.0})
        gunluk, haftalik, gunde_kac = {}, {}, {}
        for x in a.gorevler:
            gunluk[(x.personel, x.tarih)] = gunluk.get((x.personel, x.tarih), 0) + x.saat
            h = (x.personel, x.tarih.isocalendar()[:2])
            haftalik[h] = haftalik.get(h, 0) + x.saat
            gunde_kac[(x.personel, x.tarih)] = gunde_kac.get((x.personel, x.tarih), 0) + 1
        self.assertTrue(all(v <= m.gunluk_azami_saat + 1e-9 for v in gunluk.values()))
        self.assertTrue(all(v <= m.haftalik_azami_saat + 1e-9 for v in haftalik.values()))
        self.assertTrue(all(v == 1 for v in gunde_kac.values()))
        for o in a.ozet:
            self.assertLessEqual(o.yil_sonu, m.yillik_fazla_calisma_tavani + 1e-9)
        atanan = sum(x.saat for x in a.gorevler) + sum(k.saat for k in a.karsilanamayan)
        self.assertAlmostEqual(atanan, sum(talep.values()), places=2)


if __name__ == "__main__":
    unittest.main()
