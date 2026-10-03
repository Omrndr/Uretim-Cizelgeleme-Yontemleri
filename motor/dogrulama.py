"""
Hesaplamadan ÖNCE gösterilen girdi uyarıları (arayüzden bağımsız).

  * ek mesai talimatlarının yasal sınırlarla ilişkisi,
  * kadro: boş, tekrar eden ya da çizelgede okunamayacak kadar uzun adlar,
  * defter: bakiyesi olup kadroda bulunmayan personel (ad değişikliği bakiyeyi
    eski adda öksüz bırakır ve yıllık tavan yanlış hesaplanır).

Uyarılar engelleyici değildir; kullanıcı bilerek devam edebilir.
"""
from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Dict, List, Optional, Sequence

from motor.model import EkMesai, Fabrika
from motor.takvim import azami_net, brut_pencere_neti

AZAMI_KADRO = 80
ETIKET_UZUNLUGU = 10          # çizelge çubuğunda rahat okunan ad uzunluğu


def ek_mesai_uyarilari(fabrika: Fabrika, talimatlar: Sequence[EkMesai], gun: date,
                       gecerli_kaynaklar: Optional[Sequence[str]] = None) -> List[str]:
    m, kural = fabrika.mevzuat, fabrika.takvim
    out: List[str] = []
    gecerli = set(gecerli_kaynaklar or ())
    for e in talimatlar:
        if not e.aktif:
            continue
        if gecerli and e.kaynak not in gecerli:
            out.append(f"'{e.kaynak}' geçerli bir kaynak değil; satır hesaba katılmaz.")
            continue
        if e.bitis < e.baslangic:
            out.append(f"{e.kaynak}: bitiş tarihi başlangıçtan önce.")
        d = kural.duzen(e.duzen)
        gunluk = brut_pencere_neti(kural, gun, d.brut_bitis) + e.ek_saat
        if gunluk > m.gunluk_azami_saat + 1e-9:
            out.append(f"{e.kaynak}: günde {gunluk:g} saat > yasal {m.gunluk_azami_saat:g} saat. "
                       f"Gün iki vardiyaya bölünür, ikinci vardiya AYRI personel ister.")
        if gunluk > azami_net(kural, gun) + 1e-9:
            out.append(f"{e.kaynak}: günde {gunluk:g} saat istendi; bir üretim günü en fazla "
                       f"{azami_net(kural, gun):g} net saat alır.")
        haftalik = gunluk * d.gun + (e.ek_saat * (7 - d.gun) if e.hafta_sonu else 0.0)
        if haftalik > m.haftalik_azami_saat + 1e-9:
            out.append(f"{e.kaynak}: kaynak haftada {haftalik:g} saat çalışabilir; personel "
                       f"başına üst sınır {m.haftalik_azami_saat:g} saat. Çizelgeleyici "
                       f"personel değiştirerek sınırı korur.")
    for k, n in Counter(e.kaynak for e in talimatlar if e.aktif).items():
        if n > 1:
            out.append(f"{k} için {n} talimat var; tarihler kesişirse ek saatler toplanır.")
    return out


def personel_listesi_uyarilari(adlar: Sequence[str]) -> List[str]:
    out: List[str] = []
    temiz = [a.strip() for a in adlar if a.strip()]
    if not temiz:
        return ["Kadro boş: en az bir personel gerekir."]
    if len(temiz) > AZAMI_KADRO:
        out.append(f"{len(temiz)} personel girildi; en fazla {AZAMI_KADRO} desteklenir.")
    tekrar = [a for a, n in Counter(temiz).items() if n > 1]
    if tekrar:
        out.append("Aynı ad birden fazla kez girilmiş: " + ", ".join(tekrar))
    uzun = [a for a in temiz if len(a) > ETIKET_UZUNLUGU]
    if uzun:
        out.append(f"{len(uzun)} ad {ETIKET_UZUNLUGU} karakterden uzun; çizelge çubuklarında "
                   f"kısaltılarak görünür (ör. {uzun[0]}). Kısa kod (P01, AY-03) önerilir.")
    kisa = Counter(a[:ETIKET_UZUNLUGU] for a in temiz)
    cakisan = [k for k, n in kisa.items() if n > 1]
    if cakisan:
        out.append("Şu adlar kısaltıldığında aynı görünür: " + ", ".join(cakisan))
    return out


def bakiye_uyarilari(kadro: Sequence[str], bakiyeler: Dict[str, float]) -> List[str]:
    kume = set(kadro)
    oksuz = {p: s for p, s in bakiyeler.items() if p not in kume and s > 0.005}
    if not oksuz:
        return []
    sirali = sorted(oksuz.items(), key=lambda x: -x[1])[:6]
    liste = ", ".join(f"{p} ({s:.1f} sa)" for p, s in sirali)
    return [f"Defterde bakiyesi olup kadroda olmayan {len(oksuz)} personel var: {liste}. "
            f"Ad değiştirdiyseniz bakiye eski adda kalır ve yıllık tavan yanlış hesaplanır; "
            f"'Personel ve defter' sekmesinden bakiyeyi yeni ada taşıyın."]
