"""
Ölçütler, tablolar ve metin raporu.

Tablolar ``List[Dict[str, object]]`` biçimindedir; arayüz, CSV/XLSX ve rapor
katmanı aynı yapıyı kullanır.

KULLANIM ORANI çalışma saniyesiyle ölçülür:

    ρ_k = Σ_{meşgul aralık} g_k(b) − g_k(a)   /   g_k(T)

T: planın tamamlanma anı, g_k: kaynağın birikimli çalışma fonksiyonu.
Duvar saatiyle ölçmek, geceleri ve molaları da "boş" saydığı için ρ'yu
olduğundan düşük gösterirdi.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from typing import Dict, List

from motor import cubuklar as cb
from motor.cozucu import Plan
from motor.takvim import GUN, SAAT

Tablo = List[Dict[str, object]]


def _tarih(g: date) -> str:
    return g.strftime("%d.%m.%Y")


def gostergeler(plan: Plan) -> Dict[str, object]:
    t, tk = plan.tahsis, plan.takvim
    gun_sn = max(tk.ortalama_gun_saati * SAAT, 1e-9)
    a = plan.atama
    return {
        "Çalışma düzeni": tk.duzen.etiket,
        "Haftalık net saat (taban)": round(tk.haftalik_saat, 2),
        "Toplam adet": plan.urun_sayisi,
        "Sistem çevrimi (sn/adet)": round(t.cevrim, 1),
        "Kapasite (adet/saat)": round(t.kapasite_saat, 2),
        "Darboğaz": f"{t.darbogaz} {t.birimler[t.darbogaz].ad}",
        "Kullanılan kaynak / kadro": f"{t.kullanilan} / {t.kadro}",
        "Parti sayısı (K)": plan.parti_sayisi,
        "Rampa (r)": plan.ramp,
        "Ayar sayısı": plan.ayar_sayisi,
        "Ayar kaybı (iş günü)": round(plan.toplam_ayar_sn / gun_sn, 1),
        "Tamamlanma (takvim günü)": round(plan.makespan / GUN, 1),
        "Bitiş": plan.bitis_tarihi.strftime("%d.%m.%Y %H:%M"),
        "Termine uygun": "EVET" if plan.termine_uygun else "HAYIR",
        "Yasal sınırlara uygun": "EVET" if plan.mevzuata_uygun else "HAYIR",
        "Fazla çalışma (personel-saat)": round(a.toplam_fazla_mesai, 1) if a else 0.0,
        "Atanamayan vardiya": len(a.karsilanamayan) if a else 0,
        "Ek mesai talimatı": sum(1 for e in plan.ek_mesailer if e.aktif),
    }


def tahsis_tablosu(plan: Plan) -> Tablo:
    t = plan.tahsis
    return [{"Birim": k, "Ad": b.ad, "Atölye": b.atolye,
             "Kaynak": t.personel[k], "Üst sınır": b.ust,
             "Çevrim (sn/adet)": round(t.cevrimler[k], 2),
             "Kapasite (adet/sa)": round(3600 / t.cevrimler[k], 1),
             "Not": "DARBOĞAZ" if k == t.darbogaz else ""}
            for k, b in t.birimler.items()]


def dengeleme_tablosu(plan: Plan) -> Tablo:
    out: Tablo = []
    for g in plan.fabrika.parca_gruplari:
        d = plan.tahsis.dengelemeler[g.kod]
        for i, (parcalar, yuk) in enumerate(zip(d.gruplar, d.yukler), start=1):
            out.append({"Grup": g.ad, "Makine": f"{g.kaynak_oneki}-{i}",
                        "Parçalar": ", ".join(parcalar), "Yük (sn/ürün)": round(yuk, 1),
                        "Alt sınır": round(d.alt_sinir, 1)})
    return out


def siparis_tablosu(plan: Plan) -> Tablo:
    out: Tablo = []
    for s in sorted(plan.siparisler, key=lambda x: (x.termin, x.kod)):
        bit = plan.siparis_bitis.get(s.kod)
        g = plan.gecikme_gun.get(s.kod, 0.0)
        out.append({"Sipariş": s.kod, "Adet": s.toplam,
                    "İçerik": ", ".join(f"{v} {a}" for v, a in s.miktarlar.items() if a),
                    "Termin": _tarih(s.termin),
                    "Bitiş": plan.takvim.zamana(bit).strftime("%d.%m.%Y %H:%M") if bit else "-",
                    "Fark (gün)": round(g, 1),
                    "Durum": "Zamanında" if g <= 1e-9 else "GECİKMELİ"})
    return out


def kaynak_kullanimi(plan: Plan) -> Tablo:
    tk = plan.takvim
    mesgul = cb.mesgul_araliklar(plan)
    ayar: Dict[str, float] = defaultdict(float)
    for p in (*plan.parca_partileri, *plan.varyant.partiler):
        if p.ayar_var:
            ayar[p.kaynak] += tk.takvim(p.kaynak).calisma(p.ayar_bas, p.ayar_bit)
    gunler: Dict[str, int] = Counter()
    kisiler: Dict[str, set] = defaultdict(set)
    if plan.atama:
        for g in plan.atama.gorevler:
            gunler[g.kaynak] += 1
            kisiler[g.kaynak].add(g.personel)
    out: Tablo = []
    for k in plan.kaynaklar:
        takvim = tk.takvim(k.ad)
        dolu = sum(takvim.calisma(a, b) for a, b in mesgul.get(k.ad, []))
        acik = takvim.gecen(plan.makespan)
        out.append({"Kaynak": k.ad, "Atölye": k.atolye,
                    "Üretim (sa)": round((dolu - ayar[k.ad]) / SAAT, 1),
                    "Ayar (sa)": round(ayar[k.ad] / SAAT, 1),
                    "Kullanım (%)": round(100 * dolu / acik, 1) if acik > 0 else 0.0,
                    "Çalışılan gün": gunler.get(k.ad, 0),
                    "Personel": ", ".join(sorted(kisiler.get(k.ad, ()))) or "-"})
    return out


def gunluk_cikis(plan: Plan) -> Tablo:
    tk = plan.takvim
    son = plan.fabrika.istasyonlar[-1].kod
    var: Dict[date, Counter] = defaultdict(Counter)
    sip: Dict[date, Counter] = defaultdict(Counter)
    for (kod, v), t in zip(plan.sira, plan.akis.bit[son]):
        g = tk.hangi_gun(t - 1e-6)
        var[g][v] += 1
        sip[g][kod] += 1
    out: Tablo = []
    kum = 0
    for g in sorted(var):
        adet = sum(var[g].values())
        kum += adet
        satir: Dict[str, object] = {"Tarih": _tarih(g), "Adet": adet, "Kümülatif": kum}
        for v in plan.fabrika.varyantlar:
            satir[v] = var[g][v]
        satir["Siparişler"] = ", ".join(f"{k}:{n}" for k, n in sorted(sip[g].items()))
        out.append(satir)
    return out


def gunluk_personel(plan: Plan) -> Tablo:
    if not plan.atama:
        return []
    gun: Dict[date, Dict] = defaultdict(lambda: {"kisi": set(), "saat": 0.0, "fm": 0.0,
                                                 "atolye": defaultdict(set)})
    for g in plan.atama.gorevler:
        d = gun[g.tarih]
        d["kisi"].add(g.personel)
        d["saat"] += g.saat
        d["fm"] += g.fazla_mesai
        d["atolye"][g.atolye].add(g.personel)
    out: Tablo = []
    for g in sorted(gun):
        d = gun[g]
        satir = {"Tarih": _tarih(g), "Çalışan": len(d["kisi"]),
                 "Personel-saat": round(d["saat"], 1),
                 "Fazla çalışma (sa)": round(d["fm"], 1)}
        for a in plan.fabrika.atolyeler:
            satir[a] = len(d["atolye"].get(a, ()))
        out.append(satir)
    return out


def ek_mesai_ozeti(plan: Plan) -> Tablo:
    tk = plan.takvim
    out: Tablo = []
    for e in plan.ek_mesailer:
        if not e.aktif:
            continue
        gecerli = e.kaynak in tk.net
        gunler = [g for g in tk.gunler if e.baslangic <= g <= e.bitis
                  and (g.weekday() < tk.duzen.gun or e.hafta_sonu)]
        fiili = 0.0
        kisiler = set()
        if plan.atama and gecerli:
            gun_saat: Dict[date, float] = defaultdict(float)
            for g in plan.atama.gorevler:
                if g.kaynak == e.kaynak and e.baslangic <= g.tarih <= e.bitis:
                    gun_saat[g.tarih] += g.saat
                    kisiler.add(g.personel)
            fiili = sum(max(0.0, h - tk.taban_net(g)) for g, h in gun_saat.items())
        out.append({"Kaynak": e.kaynak, "Başlangıç": _tarih(e.baslangic),
                    "Bitiş": _tarih(e.bitis), "Düzen": e.duzen or tk.duzen.kod,
                    "Ek sa/gün": e.ek_saat, "Hafta sonu": "Evet" if e.hafta_sonu else "Hayır",
                    "Planlanan ek (sa)": round(len(gunler) * e.ek_saat, 1),
                    "Kullanılan ek (sa)": round(fiili, 1),
                    "Personel": ", ".join(sorted(kisiler)) or "-",
                    "Durum": "Geçerli" if gecerli else "GEÇERSİZ KAYNAK"})
    return out


def ayar_tablosu(plan: Plan) -> Tablo:
    tk = plan.takvim
    out = [{"Atölye": p.atolye, "Kaynak": p.kaynak, "Değişim": p.ayar_etiketi,
            "Yeni iş": p.nesne, "Parti": p.parti_no,
            "Başlangıç": tk.zamana(p.ayar_bas).strftime("%d.%m.%Y %H:%M"),
            "Bitiş": tk.zamana(p.ayar_bit).strftime("%d.%m.%Y %H:%M"),
            "Ardından (adet)": p.adet}
           for p in (*plan.parca_partileri, *plan.varyant.partiler) if p.ayar_var]
    out.sort(key=lambda r: (r["Atölye"], r["Kaynak"], r["Başlangıç"]))
    return out


def kisit_tablosu(plan: Plan) -> Tablo:
    n = max(1, plan.urun_sayisi)
    out: Tablo = []
    for op in (*plan.fabrika.hucreler, *plan.fabrika.istasyonlar):
        sayac = plan.akis.kisit.get(op.kod, {})
        aclik = plan.akis.aclik_sn.get(op.kod, {})
        for neden, k in sorted(sayac.items(), key=lambda x: -x[1]):
            out.append({"Operasyon": f"{op.kod} {op.ad}", "Bağlayıcı neden": neden,
                        "Ürün": k, "Pay (%)": round(100 * k / n, 1),
                        "Starvation (sa)": round(aclik.get(neden, 0.0) / SAAT, 1)})
    return out


def personel_ozeti(plan: Plan) -> Tablo:
    if not plan.atama:
        return []
    tavan = plan.fabrika.mevzuat.yillik_fazla_calisma_tavani
    return [{"Personel": o.personel, "Gün": o.gun, "Saat": o.saat,
             "Bu plandaki fazla çalışma": o.plan_fazla_mesai,
             "Yıl açılışı": round(o.acilis, 1), "Yıl sonu": round(o.yil_sonu, 1),
             "Kalan hak": round(tavan - o.yil_sonu, 1),
             "Doluluk (%)": round(100 * o.yil_sonu / tavan, 1)}
            for o in plan.atama.ozet]


def gorev_tablosu(plan: Plan) -> Tablo:
    if not plan.atama:
        return []
    return [{"Tarih": _tarih(g.tarih), "Kaynak": g.kaynak, "Atölye": g.atolye,
             "Personel": g.personel, "Vardiya": g.vardiya, "Saat": g.saat,
             "Fazla çalışma": g.fazla_mesai} for g in plan.atama.gorevler]


def atanamayan_tablosu(plan: Plan) -> Tablo:
    if not plan.atama:
        return []
    return [{"Tarih": _tarih(k.tarih), "Kaynak": k.kaynak, "Atölye": k.atolye,
             "Vardiya": k.vardiya, "Saat": k.saat, "Sebep": k.sebep}
            for k in plan.atama.karsilanamayan]


def duz_metin_rapor(plan: Plan) -> str:
    from motor.uyarilar import panolar_metin
    f, t = plan.fabrika, plan.tahsis
    L: List[str] = []
    cizgi = "=" * 78
    L += [cizgi, f"ÜRETİM PLANI — {f.ad}", cizgi,
          f"Ürün          : {f.urun}",
          f"Plan başlangıcı: {plan.baslangic:%d.%m.%Y}   Toplam adet: {plan.urun_sayisi}"]
    for s in plan.siparisler:
        L.append(f"   • {s}")
    L += ["", "1) KAPASİTE VE DARBOĞAZ", "-" * 78]
    for r in sorted(tahsis_tablosu(plan), key=lambda r: -r["Çevrim (sn/adet)"]):
        L.append(f"   {r['Birim']:5s} {r['Ad']:26s} {r['Kaynak']} kaynak  "
                 f"{r['Çevrim (sn/adet)']:8.2f} sn/adet  {r['Not']}")
    L.append(f"   Sistem: {t.cevrim:.1f} sn/adet = {t.kapasite_saat:.1f} adet/saat "
             f"(kadro {t.kadro}, kullanılan {t.kullanilan})")
    L += ["", "2) PARÇA MAKİNESİ DENGELEMESİ (P||Cmax)", "-" * 78]
    for r in dengeleme_tablosu(plan):
        L.append(f"   {r['Makine']:8s} {r['Yük (sn/ürün)']:6.1f} sn  [{r['Parçalar']}]")
    L += ["", "3) PARTİ ARAMASI", "-" * 78]
    for r in plan.arama:
        isaret = "  <== seçilen" if (r["Parti sayısı (K)"], r["Rampa (r)"]) == \
            (plan.parti_sayisi, plan.ramp) else ""
        L.append(f"   K={r['Parti sayısı (K)']} r={r['Rampa (r)']:<4g} ayar={r['Ayar sayısı']:<4} "
                 f"tamamlanma={r['Tamamlanma (gün)']:>6} gün  "
                 f"gecikme={r['En büyük gecikme (gün)']:>6} "
                 f"{r['Termine uygun']}{isaret}")
    L += ["", "4) SİPARİŞLER", "-" * 78]
    for r in siparis_tablosu(plan):
        L.append(f"   {r['Sipariş']:8s} termin {r['Termin']}  bitiş {r['Bitiş']}  "
                 f"fark {r['Fark (gün)']:+.1f} gün  {r['Durum']}")
    L += ["", "5) UYARI PANOLARI", "-" * 78, panolar_metin(plan)]
    if plan.uyarilar:
        L += ["", "6) UYARILAR", "-" * 78]
        L += [f"   ! {u}" for u in plan.uyarilar]
    L.append(cizgi)
    return "\n".join(L)
