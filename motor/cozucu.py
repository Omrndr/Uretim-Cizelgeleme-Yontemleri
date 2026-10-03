"""
Uçtan uca planlayıcı.

    siparişler ─► üretim sırası (EDD + heijunka)
               ─► personel tahsisi (kesin min-maks)  ─► kaynak listesi
               ─► kaynak takvimleri (düzen + ek mesai talimatları)
               ─► varyant planı (bir kez)            ┐
               ─► parti planı (K, r) ─► akış hesabı ┴► termin değerlendirmesi
                  (K, r) ızgarası leksikografik amaçla taranır
               ─► en iyi plan için bireysel personel ataması (yasal sınırlar)

AMAÇ HİYERARŞİSİ (leksikografik):
    1) termine yetişmek               (yetişmiyorsa en büyük gecikmeyi küçült)
    2) ayar sayısını azaltmak          (yalnız termine yetişen planlar arasında)
    3) tamamlanma süresi (makespan)    (eşitlik bozucu)

Ek mesai yalnızca planlamacının talimatıyla eklenir. Termin aşılıyorsa bu raporlanır;
hangi hattın ne kadar açık verdiğini uyarı panosu gösterir, ek mesai kararı
planlamacınındır (``ek_mesai_onerisi`` yalnızca öneri üretir).
"""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from motor import cubuklar as cb
from motor.akis import AkisTablosu, akisi_coz
from motor.model import (EkMesai, Fabrika, PlanAyarlari, Siparis, TanimHatasi,
                         duzen_kodu, varsayilan_personel)
from motor.parti import Parti, ParcaZamanlari, parca_partileri
from motor.personel import PersonelAtamasi, personel_ata
from motor.siralama import is_sirasi
from motor.tahsis import (KaynakKaydi, Dagilim, yapisal_alt_sinir, kaynaklari_olustur,
                          en_iyi_dagilim)
from motor.takvim import (GUN, SAAT, FabrikaTakvimi, UfukAsildi, azami_net,
                          brut_pencere_neti)
from motor.varyant import VaryantSonucu, varyant_plani

Ilerleme = Callable[[float, str], None]


class Durduruldu(Exception):
    """İlerleme geri çağrısı bu istisnayı fırlatarak hesabı durdurabilir."""


@dataclass
class Plan:
    fabrika: Fabrika
    baslangic: date
    siparisler: List[Siparis]
    ek_mesailer: List[EkMesai]
    ayarlar: PlanAyarlari
    personel: List[str]
    tahsis: Dagilim
    kaynaklar: List[KaynakKaydi]
    takvim: FabrikaTakvimi
    sira: List[Tuple[str, str]]
    varyant_talebi: Dict[str, int]
    parca_partileri: List[Parti]
    varyant: VaryantSonucu
    akis: AkisTablosu
    parti_sayisi: int
    ramp: float
    ayar_sn: Dict[str, float]
    parca_ayar_sayisi: int
    siparis_bitis: Dict[str, float]
    gecikme_gun: Dict[str, float]
    atama: Optional[PersonelAtamasi]
    arama: List[Dict]
    uyarilar: List[str] = field(default_factory=list)

    # ------------------------------------------------------------------ özet
    @property
    def makespan(self) -> float:
        return self.akis.makespan

    @property
    def bitis_tarihi(self) -> datetime:
        return self.takvim.zamana(self.makespan)

    @property
    def urun_sayisi(self) -> int:
        return len(self.sira)

    @property
    def ayar_sayisi(self) -> int:
        return self.parca_ayar_sayisi + self.varyant.ayar_sayisi

    @property
    def toplam_ayar_sn(self) -> float:
        """Ayarlarda harcanan ÇALIŞMA süresi (gece ve molalar hariç)."""
        return sum(self.takvim.takvim(p.kaynak).calisma(p.ayar_bas, p.ayar_bit)
                   for p in (*self.parca_partileri, *self.varyant.partiler) if p.ayar_var)

    @property
    def termine_uygun(self) -> bool:
        return all(g <= 1e-9 for g in self.gecikme_gun.values())

    @property
    def mevzuata_uygun(self) -> bool:
        return self.atama is None or self.atama.uygun

    @property
    def en_buyuk_gecikme(self) -> float:
        return max(self.gecikme_gun.values(), default=0.0)

    def kaynak(self, ad: str) -> KaynakKaydi:
        return next(k for k in self.kaynaklar if k.ad == ad)


# ==============================================================================
# YARDIMCILAR
# ==============================================================================

def _ilerle(ilerleme: Optional[Ilerleme], oran: float, mesaj: str) -> None:
    if ilerleme:
        ilerleme(min(1.0, max(0.0, oran)), mesaj)


def _siparis_son_bitisleri(sira, urun_bitis) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for (kod, _), t in zip(sira, urun_bitis):
        out[kod] = max(out.get(kod, 0.0), t)
    return out


def _gecikmeler(siparisler, bitisler, takvim: FabrikaTakvimi) -> Dict[str, float]:
    return {s.kod: (bitisler.get(s.kod, math.inf) - takvim.termin_saniyesi(s.termin)) / GUN
            for s in siparisler}


def _girdi_uyarilari(fabrika: Fabrika, tahsis: Dagilim, kaynaklar: List[KaynakKaydi],
                     ek_mesailer: Sequence[EkMesai], talep: Dict[str, int],
                     baslangic: date, varsayilan: str) -> List[str]:
    u: List[str] = []
    vg = fabrika.varyant_grubu
    if vg:
        istenen = [v for v, d in talep.items() if d > 0]
        kullanilabilir = vg.kullanilabilir_makine(istenen)
        if kullanilabilir < vg.makine_sayisi:
            u.append(f"[Kapasite] Talep edilen varyantlar ({', '.join(istenen)}) için "
                     f"{vg.takim_adi.lower()} toplamı {kullanilabilir}; {vg.ad} içindeki "
                     f"{vg.makine_sayisi} makinenin yalnız {kullanilabilir} tanesi "
                     f"kullanılabilir.")
    taban, sebep = yapisal_alt_sinir(fabrika, [v for v, d in talep.items() if d > 0])
    b = tahsis.birimler[tahsis.darbogaz]
    u.append(f"[Kapasite] Darboğaz {tahsis.darbogaz} {b.ad}: {tahsis.cevrim:.1f} sn/adet "
             f"({tahsis.kapasite_saat:.1f} adet/saat). Sınırsız personelle bile "
             f"aşılamayan yapısal alt sınır {taban:.1f} sn/adet ({sebep}).")
    if tahsis.bosta > 0:
        u.append(f"[Kapasite] {tahsis.bosta} personel bir kaynağa bağlanamadı: makine, takım ve "
                 f"istasyon sınırları daha fazla paralel çalışmaya izin vermiyor.")
    adlar = {k.ad for k in kaynaklar}
    kural = fabrika.takvim
    for e in ek_mesailer:
        if not e.aktif:
            continue
        if e.kaynak not in adlar:
            u.append(f"[Talimat] '{e.kaynak}' bu dağılımda bulunmuyor, satır hesaba katılmadı. "
                     f"Geçerli kaynaklar: {', '.join(sorted(adlar))}.")
            continue
        d = kural.duzen(e.duzen or varsayilan)
        gunluk = brut_pencere_neti(kural, baslangic, d.brut_bitis) + e.ek_saat
        if gunluk > fabrika.mevzuat.gunluk_azami_saat + 1e-9:
            u.append(f"[Mevzuat] '{e}' günde {gunluk:g} saat; kişi başı sınır "
                     f"{fabrika.mevzuat.gunluk_azami_saat:g} saat. Gün vardiyalara "
                     f"bölünür ve her vardiyaya AYRI personel gerekir.")
        tavan = azami_net(kural, baslangic)
        if gunluk > tavan + 1e-9:
            u.append(f"[Talimat] '{e}' günde {gunluk:g} saat istiyor; molalar "
                     f"düşüldüğünde bir üretim gününde en fazla {tavan:g} saat çalışılır. "
                     f"Fazlası çizelgelenmez.")
    cift = [k for k, n in Counter(e.kaynak for e in ek_mesailer if e.aktif).items() if n > 1]
    if cift:
        u.append("[Talimat] Birden çok talimatı olan kaynaklar: " + ", ".join(cift)
                 + ". Tarihler kesişiyorsa ek saatler toplanır.")
    return u


# ==============================================================================
# PLANLAYICI
# ==============================================================================

def plan_olustur(fabrika: Fabrika, siparisler: Sequence[Siparis], baslangic: date,
                 ek_mesailer: Sequence[EkMesai] = (), ayarlar: Optional[PlanAyarlari] = None,
                 personel: Optional[Sequence[str]] = None,
                 acilis_bakiye: Optional[Dict[str, float]] = None,
                 ilerleme: Optional[Ilerleme] = None) -> Plan:
    ayarlar = ayarlar or PlanAyarlari()
    siparisler = [s for s in siparisler if s.toplam > 0]
    if not siparisler:
        raise TanimHatasi("En az bir sipariş ve pozitif miktar gerekir.")
    bilinmeyen = {v for s in siparisler for v, a in s.miktarlar.items()
                  if a > 0 and v not in fabrika.varyantlar}
    if bilinmeyen:
        raise TanimHatasi(f"Tanımsız varyant: {', '.join(sorted(bilinmeyen))}")
    kodlar = [s.kod for s in siparisler]
    if len(set(kodlar)) != len(kodlar):
        raise TanimHatasi("Sipariş kodları benzersiz olmalı.")
    kadro = [str(p).strip() for p in (personel or varsayilan_personel(
        fabrika.personel_sayisi)) if str(p).strip()]
    if not kadro:
        raise TanimHatasi("En az bir personel gerekir.")
    if len(set(kadro)) != len(kadro):
        raise TanimHatasi("Personel adları benzersiz olmalı.")

    _ilerle(ilerleme, 0.02, "Üretim sırası ve personel tahsisi...")
    sira = is_sirasi(siparisler, fabrika.varyantlar)
    talep = Counter(v for _, v in sira)
    istenen = [v for v in fabrika.varyantlar if talep[v] > 0]
    tahsis = en_iyi_dagilim(fabrika, len(kadro), istenen)
    if tahsis is None:
        asgari = (len(fabrika.parca_gruplari) + (1 if fabrika.varyant_grubu else 0)
                  + len(fabrika.hucreler) + len(fabrika.istasyonlar))
        raise TanimHatasi(f"{len(kadro)} personelle her birime en az bir kişi verilemiyor; "
                          f"en az {asgari} kişi gerekir.")
    kaynaklar = kaynaklari_olustur(fabrika, tahsis)
    duzen = duzen_kodu(ayarlar.varsayilan_duzen, fabrika.takvim)
    uyarilar = _girdi_uyarilari(fabrika, tahsis, kaynaklar, ek_mesailer, talep,
                                baslangic, duzen)

    _ilerle(ilerleme, 0.05, "Kaynak takvimleri kuruluyor...")
    takvim = FabrikaTakvimi(fabrika, baslangic, [k.ad for k in kaynaklar], ek_mesailer,
                            duzen, ayarlar.ufuk_gun)
    tk = takvim.takvimler
    ayar_saat = fabrika.ayar_saatleri()
    ayar_saat.update({k: float(v) for k, v in ayarlar.ayar_saatleri.items() if k in ayar_saat})
    ayar_sn = {k: max(0.0, s) * SAAT for k, s in ayar_saat.items()}

    try:
        vg = fabrika.varyant_grubu
        varyant = varyant_plani(fabrika, tahsis, sira,
                                ayar_sn.get(vg.kod, 0.0) if vg else 0.0, tk,
                                ayarlar.ayari_gun_basina_hizala, ayarlar.azami_ayar_payi)
        uyarilar.extend(x for x in varyant.uyarilar if not x.startswith("[Kapasite]"))

        izgara = [(k, r) for k in ayarlar.parti_sayilari for r in ayarlar.ramp_adaylari
                  if not (k == 1 and r != ayarlar.ramp_adaylari[0])]
        en_iyi = None
        arama: List[Dict] = []
        son = fabrika.istasyonlar[-1].kod
        for n_deneme, (k, r) in enumerate(izgara, start=1):
            _ilerle(ilerleme, 0.08 + 0.80 * (n_deneme - 1) / len(izgara),
                    f"Parti araması {n_deneme}/{len(izgara)} (K={k}, r={r:g})")
            zaman = ParcaZamanlari()
            partiler: List[Parti] = []
            ayar = 0
            for g in fabrika.parca_gruplari:
                p, a = parca_partileri(fabrika, tahsis, g, len(sira), k, r,
                                       ayar_sn.get(g.kod, 0.0), tk, zaman,
                                       ayarlar.ayari_gun_basina_hizala,
                                       ayarlar.serpantin_sira)
                partiler.extend(p)
                ayar += a
            akis = akisi_coz(fabrika, sira, zaman, varyant.bitisler, tahsis, tk)
            bitis = _siparis_son_bitisleri(sira, akis.bit[son])
            gecikme = _gecikmeler(siparisler, bitis, takvim)
            uygun = all(x <= 1e-9 for x in gecikme.values())
            mg = max(gecikme.values())
            toplam_ayar = ayar + varyant.ayar_sayisi
            arama.append({
                "Parti sayısı (K)": k, "Rampa (r)": r, "Ayar sayısı": toplam_ayar,
                "Tamamlanma (gün)": round(akis.makespan / GUN, 1),
                "En büyük gecikme (gün)": round(mg, 1),
                "Termine uygun": "EVET" if uygun else "HAYIR"})
            anahtar = (0 if uygun else 1, toplam_ayar if uygun else round(mg, 4),
                       round(akis.makespan, 1), toplam_ayar)
            if en_iyi is None or anahtar < en_iyi[0]:
                en_iyi = (anahtar, k, r, partiler, ayar, akis, bitis, gecikme)
    except UfukAsildi as hata:
        raise TanimHatasi(f"Plan {ayarlar.ufuk_gun} günlük takvim ufkuna sığmıyor: "
                          f"miktarlar çok büyük ya da çalışma süresi çok az. ({hata})")

    _, k, r, partiler, ayar, akis, bitis, gecikme = en_iyi
    plan = Plan(fabrika, baslangic, siparisler, list(ek_mesailer), ayarlar, kadro,
                tahsis, kaynaklar, takvim, sira, dict(talep), partiler, varyant,
                akis, k, r, ayar_sn, ayar, bitis, gecikme, None, arama, uyarilar)

    if ayarlar.personel_denetimi:
        _ilerle(ilerleme, 0.92, "Bireysel personel ataması ve yasal denetim...")
        saatler = cb.calisilan_saatler(takvim, cb.mesgul_araliklar(plan))
        molalar = (cb.mola_paylari(takvim, saatler)
                   if fabrika.takvim.zorunlu_mola_mesaiye_sayilir else {})
        plan.atama = personel_ata(saatler, {x.ad: x.atolye for x in kaynaklar}, kadro,
                                  fabrika.mevzuat, acilis_bakiye or {}, molalar)
        uyarilar.extend(plan.atama.uyarilar)
    if not plan.termine_uygun:
        uyarilar.append(
            f"[Termin] En geç biten sipariş terminini {plan.en_buyuk_gecikme:.1f} gün aşıyor. "
            f"Ek mesai yalnızca talimatla eklenir; yetersiz grupları ve günlük "
            f"açığı uyarı panosu gösterir.")
    _ilerle(ilerleme, 1.0, "Tamamlandı.")
    return plan


# ==============================================================================
# EK MESAİ ÖNERİSİ — DARBOĞAZ TAKİBİ
# ==============================================================================

def _kapasite_gruplari(plan: Plan, atolye: str) -> List[Tuple[str, List[str], float]]:
    """(grup adı, kaynak adları, ürün başına süre). Her parça makinesi kendi
    grubudur (parçaları başka makinede işlenemez)."""
    f, t = plan.fabrika, plan.tahsis
    out: List[Tuple[str, List[str], float]] = []
    for g in f.parca_gruplari:
        if g.ad != atolye:
            continue
        d = t.dengelemeler[g.kod]
        for i, yuk in enumerate(d.yukler, start=1):
            if yuk > 0:
                out.append((f"{g.kaynak_oneki}-{i}", [f"{g.kaynak_oneki}-{i}"], yuk))
    vg = f.varyant_grubu
    if vg and vg.ad == atolye:
        out.append((vg.kod, [k.ad for k in plan.kaynaklar if k.birim == vg.kod], vg.sure_sn))
    for op in (*f.hucreler, *f.istasyonlar):
        if t.birimler[op.kod].atolye == atolye:
            out.append((op.kod, [k.ad for k in plan.kaynaklar if k.birim == op.kod],
                        op.sure_sn))
    return out


def ek_mesai_onerisi(plan: Plan, atolye: str, adet: int, ek_saat: float) -> List[str]:
    """
    "Bu atölyede ``adet`` kaynağı günde ``ek_saat`` uzatacaksam hangileri?"

    Her adımda günlük kapasitesi en düşük grup seçilir ve o gruptan bir kaynak
    eklenir; kapasiteler yeniden hesaplanır:

        kapasite_g = (c_g · H + s_g · E) · 3600 / τ_g     [adet/gün]

    c_g: gruptaki kaynak, s_g: seçilen kaynak, H: taban net saat, E: ek saat.
    Aynı grubu uzatıp darboğazı bir sonraki gruba kaydırma hatasını önler.
    Bu bir ÖNERİDİR; talimatı planlamacı yazar.
    """
    gruplar = [g for g in _kapasite_gruplari(plan, atolye) if g[1] and g[2] > 0]
    if not gruplar or adet <= 0:
        return []
    h = plan.takvim.taban_net(plan.baslangic) or plan.takvim.ortalama_gun_saati
    secili = {ad: 0 for ad, _, _ in gruplar}
    out: List[str] = []
    for _ in range(min(adet, sum(len(k) for _, k, _ in gruplar))):
        adaylar = [g for g in gruplar if secili[g[0]] < len(g[1])]
        if not adaylar:
            break
        ad, kaynaklar, tau = min(
            adaylar, key=lambda g: ((len(g[1]) * h + secili[g[0]] * ek_saat) * SAAT / g[2], g[0]))
        out.append(kaynaklar[secili[ad]])
        secili[ad] += 1
    return out


# ==============================================================================
# DÜZEN KARŞILAŞTIRMASI (bilgi amaçlı)
# ==============================================================================

def duzen_karsilastir(fabrika: Fabrika, siparisler: Sequence[Siparis], baslangic: date,
                      ek_mesailer: Sequence[EkMesai] = (),
                      ayarlar: Optional[PlanAyarlari] = None,
                      personel: Optional[Sequence[str]] = None,
                      ilerleme: Optional[Ilerleme] = None) -> List[Dict]:
    """Bütün fabrika her düzende çalışsaydı ne olurdu? Uygulanmaz, yalnız bilgi verir."""
    ayarlar = ayarlar or PlanAyarlari()
    out: List[Dict] = []
    duzenler = fabrika.takvim.duzenler
    for i, d in enumerate(duzenler):
        _ilerle(ilerleme, i / len(duzenler), f"{d.etiket} hesaplanıyor...")
        a = PlanAyarlari(**{**ayarlar.__dict__, "varsayilan_duzen": d.kod})
        try:
            p = plan_olustur(fabrika, siparisler, baslangic, ek_mesailer, a, personel)
        except TanimHatasi as hata:
            out.append({"Düzen": d.etiket, "Durum": str(hata)})
            continue
        out.append({
            "Düzen": d.etiket,
            "Net sa/gün": round(brut_pencere_neti(fabrika.takvim, baslangic, d.brut_bitis), 2),
            "Gün/hafta": d.gun,
            "Bitiş": p.bitis_tarihi.strftime("%d.%m.%Y"),
            "Tamamlanma (gün)": round(p.makespan / GUN, 1),
            "Termine uygun": "EVET" if p.termine_uygun else "HAYIR",
            "Fazla çalışma (sa)": round(p.atama.toplam_fazla_mesai, 1) if p.atama else 0.0,
            "Atanamayan vardiya": len(p.atama.karsilanamayan) if p.atama else 0,
        })
    _ilerle(ilerleme, 1.0, "Tamamlandı.")
    return out
