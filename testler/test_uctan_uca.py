"""Uçtan uca testler: örnek senaryo, plan tutarlılığı, iş emirleri, çıktılar, defter."""
import sys
import tempfile
import unittest
import zipfile
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from motor import analiz, defter                                        # noqa: E402
from motor.cozucu import ek_mesai_onerisi, plan_olustur                          # noqa: E402
from motor.model import (EkMesai, fabrika_yukle, senaryo_yaz,        # noqa: E402
                         senaryo_oku, varsayilan_personel, veri_dizini)
from motor.uyarilar import panolar_metin                                   # noqa: E402
from rapor import genel_bakis, semalar                                  # noqa: E402
from rapor.is_emirleri import is_emirleri                               # noqa: E402
from rapor.paket import paket_olustur                                   # noqa: E402

FABRIKA = fabrika_yukle()
SENARYO = senaryo_oku(veri_dizini() / "ornek_senaryo.json")
PLAN = plan_olustur(FABRIKA, SENARYO.siparisler, SENARYO.baslangic, SENARYO.ek_mesailer,
                    SENARYO.ayarlar)


class PlanTesti(unittest.TestCase):
    def test_ornek_termine_yetisir(self):
        self.assertTrue(PLAN.termine_uygun)
        self.assertTrue(PLAN.mevzuata_uygun)
        self.assertEqual(PLAN.urun_sayisi, sum(s.toplam for s in SENARYO.siparisler))

    def test_akis_oncelik_ve_kapasite(self):
        f, a = FABRIKA, PLAN.akis
        for op in (*f.hucreler, *f.istasyonlar):
            for i in range(PLAN.urun_sayisi):
                self.assertGreaterEqual(a.bit[op.kod][i], a.bas[op.kod][i])
            # aynı istasyonda çakışma yok
            for s in range(PLAN.tahsis.personel[op.kod]):
                isler = sorted((a.bas[op.kod][i], a.bit[op.kod][i])
                               for i in range(PLAN.urun_sayisi) if a.istasyon[op.kod][i] == s)
                for (b0, e0), (b1, _) in zip(isler, isler[1:]):
                    self.assertGreaterEqual(b1, e0 - 1e-6)
        for x, y in zip(f.istasyonlar, f.istasyonlar[1:]):
            for i in range(PLAN.urun_sayisi):
                self.assertGreaterEqual(a.bas[y.kod][i], a.bit[x.kod][i] - 1e-6)

    def test_varyant_adetleri_ve_takim_siniri(self):
        uretilen = Counter()
        for p in PLAN.varyant.partiler:
            uretilen[p.nesne] += p.adet
        self.assertEqual(dict(uretilen), dict(PLAN.varyant_talebi))
        takim = FABRIKA.varyant_grubu.takim_adedi
        for v in uretilen:
            olaylar = sorted([(p.bas, 1) for p in PLAN.varyant.partiler if p.nesne == v]
                             + [(p.bit, -1) for p in PLAN.varyant.partiler if p.nesne == v],
                             key=lambda x: (x[0], x[1]))
            n = 0
            for _, d in olaylar:
                n += d
                self.assertLessEqual(n, takim[v])

    def test_is_emri_adetleri(self):
        emirler = is_emirleri(PLAN)
        toplam = defaultdict(int)
        for r in emirler:
            if r.tur == "Üretim":
                toplam[r.kaynak] += r.adet
        n = PLAN.urun_sayisi
        for op in FABRIKA.istasyonlar:
            istasyonlar = [k.ad for k in PLAN.kaynaklar if k.birim == op.kod]
            self.assertEqual(sum(toplam[k] for k in istasyonlar), n)
        parca_sayisi = len(FABRIKA.tum_parcalar())
        tornalar = [k.ad for k in PLAN.kaynaklar if k.tip == "parca"]
        self.assertEqual(sum(toplam[k] for k in tornalar), n * parca_sayisi)
        self.assertTrue(all(r.personel not in ("", None) for r in emirler))

    def test_tablolar_ve_rapor(self):
        self.assertIn("PANO A", panolar_metin(PLAN))
        self.assertIn("PARTİ ARAMASI", analiz.duz_metin_rapor(PLAN))
        for fonk in (analiz.kaynak_kullanimi, analiz.gunluk_cikis, analiz.ayar_tablosu,
                     analiz.kisit_tablosu, analiz.personel_ozeti, analiz.dengeleme_tablosu):
            self.assertTrue(fonk(PLAN))
        cikis = analiz.gunluk_cikis(PLAN)
        self.assertEqual(cikis[-1]["Kümülatif"], PLAN.urun_sayisi)

    def test_semalar_cizilir(self):
        emirler = is_emirleri(PLAN)
        g = emirler[0].tarih
        for atolye in FABRIKA.atolyeler:
            self.assertIn("<svg", semalar.gun_plani(PLAN, emirler, atolye, g).svg())
            self.assertIn("<svg", semalar.hafta_plani(PLAN, emirler, atolye,
                                                      semalar.hafta_basi(g)).svg())
        self.assertIn("Termin", genel_bakis.genel_bakis(PLAN).svg())


class SikisikSenaryoTesti(unittest.TestCase):
    def test_ek_mesai_ve_yasal_bolme(self):
        sip = [type(s)(s.kod, dict(s.miktarlar), s.termin) for s in SENARYO.siparisler]
        sip[0].termin = date(2026, 11, 18)
        kaynaklar = ek_mesai_onerisi(PLAN, FABRIKA.hat_atolyesi, 3, 3.0)
        self.assertEqual(len(kaynaklar), 3)
        ek = [EkMesai(k, date(2026, 11, 2), date(2026, 11, 20), 3.0, "D2")
              for k in kaynaklar + ["H2.1"]]
        p = plan_olustur(FABRIKA, sip, SENARYO.baslangic, ek, personel=varsayilan_personel(16))
        self.assertTrue(any(u.startswith("[Mevzuat]") for u in p.uyarilar))
        self.assertTrue(any(g.vardiya == 2 for g in p.atama.gorevler))
        m = FABRIKA.mevzuat
        gunluk = Counter()
        for g in p.atama.gorevler:
            gunluk[(g.personel, g.tarih)] += g.saat
        self.assertTrue(all(v <= m.gunluk_azami_saat + 1e-9 for v in gunluk.values()))


class CiktiVeKayitTesti(unittest.TestCase):
    def test_paket_html(self):
        with tempfile.TemporaryDirectory() as d:
            klasor, ozet = paket_olustur(PLAN, Path(d), pdf=False)
            self.assertTrue((klasor / "02_Plan_Tablolari.xlsx").exists())
            self.assertTrue(zipfile.is_zipfile(klasor / "02_Plan_Tablolari.xlsx"))
            self.assertTrue((klasor / "03_Is_Emirleri.csv").exists())
            self.assertGreater(ozet["html"], 10)
            self.assertTrue(list(klasor.glob("Hafta 01*/*/_Haftalik_Plan.html")))

    def test_senaryo_gidis_donus(self):
        with tempfile.TemporaryDirectory() as d:
            yol = Path(d) / "s.json"
            senaryo_yaz(SENARYO, yol)
            s2 = senaryo_oku(yol)
            self.assertEqual([(s.kod, s.miktarlar, s.termin) for s in s2.siparisler],
                             [(s.kod, s.miktarlar, s.termin) for s in SENARYO.siparisler])

    def test_defter(self):
        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / "d.db"
            defter.isle(2026, {"P01": 5.0, "P02": 2.5}, "test", db)
            defter.isle(2026, {"P01": 1.0}, "test", db)
            self.assertEqual(defter.bakiyeler(2026, ["P01", "P02", "P03"], db),
                             {"P01": 6.0, "P02": 2.5, "P03": 0.0})
            defter.ad_degistir("P02", "P09", 2026, db)
            self.assertEqual(defter.bakiyeler(2026, None, db).get("P09"), 2.5)
            self.assertEqual(defter.yil_sil(2026, db), 2)
            self.assertEqual(len(defter.son_hareketler(yol=db)), 5)


if __name__ == "__main__":
    unittest.main()
