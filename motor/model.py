"""
Veri modeli: fabrika tanımı, siparişler, ek mesai talimatları ve senaryo.

Motor hiçbir fabrikayı "bilmez". Bütün kaynaklar, süreler, ürün ağacı ve
çalışma düzeni bir JSON dosyasından okunur (bkz. ``veri/ornek_fabrika.json``).
Aynı motor başka bir fabrika tanımıyla da çalışır.

Ürün ağacının biçimi (genel):

    parça grupları   -> paralel özdeş makineler; her parçanın TEK aparatı var
    varyant grubu    -> ürünün varyantını belirleyen bileşen; varyant başına
                        sınırlı sayıda takım (ör. renk tabancası seti)
    hücreler         -> parçaları birleştiren manuel ön montaj; c paralel istasyon
    hat              -> sıralı istasyonlar; her istasyon parça, hücre çıktısı
                        veya varyant bileşeni tüketebilir

Bağımlılık: yalnızca standart kütüphane.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union

VARYANT_GIRDISI = "VARYANT"


class TanimHatasi(ValueError):
    """Fabrika veya senaryo tanımında tutarsızlık."""


def saat_oku(metin: Union[str, float, int]) -> float:
    """'08:00' -> 8.0, '24:00' -> 24.0, '01:30+1' -> 25.5, 17.75 -> 17.75"""
    if isinstance(metin, (int, float)):
        return float(metin)
    s = str(metin).strip()
    ek_gun = 0
    if "+" in s:
        s, ek = s.split("+", 1)
        ek_gun = int(ek or 1)
    sa, _, dk = s.partition(":")
    return int(sa) + int(dk or 0) / 60.0 + 24.0 * ek_gun


def saat_yaz(saat: float) -> str:
    """8.0 -> '08:00', 25.5 -> '01:30 (+1)'"""
    gun, kalan = divmod(round(saat * 60), 24 * 60)
    metin = f"{kalan // 60:02d}:{kalan % 60:02d}"
    return metin + (f" (+{gun})" if gun else "")


# ==============================================================================
# FABRİKA TANIMI
# ==============================================================================

@dataclass(frozen=True)
class Parca:
    kod: str
    ad: str
    sure_sn: float


@dataclass(frozen=True)
class ParcaGrubu:
    """Paralel özdeş makineler. Her parçanın tek aparatı olduğu için bir parça
    aynı anda yalnızca bir makinede işlenebilir."""
    kod: str
    ad: str
    kaynak_oneki: str
    makine_sayisi: int
    ayar_saat: float
    ayar_etiketi: str
    parcalar: Tuple[Parca, ...]

    def sureler(self) -> Dict[str, float]:
        return {p.kod: p.sure_sn for p in self.parcalar}

    @property
    def set_suresi(self) -> float:
        """Bir ürün için gereken bütün parçaların toplam işlem süresi."""
        return sum(p.sure_sn for p in self.parcalar)


@dataclass(frozen=True)
class VaryantGrubu:
    """Ürünün varyantını belirleyen bileşeni üreten makine grubu."""
    kod: str
    ad: str
    kaynak_oneki: str
    makine_sayisi: int
    sure_sn: float
    ayar_saat: float
    ayar_etiketi: str
    bilesen: str
    takim_adi: str
    takim_adedi: Dict[str, int]

    def kullanilabilir_makine(self, varyantlar: Sequence[str]) -> int:
        """Talep edilen varyantların takım toplamı makine sayısını sınırlar."""
        return min(self.makine_sayisi,
                   sum(self.takim_adedi.get(v, 0) for v in set(varyantlar)))


@dataclass(frozen=True)
class Operasyon:
    """Bir ön montaj hücresi ya da hat istasyonu (manuel, c paralel istasyon)."""
    kod: str
    ad: str
    girdiler: Tuple[str, ...]
    sure_sn: float
    azami_istasyon: int


@dataclass(frozen=True)
class CalismaDuzeni:
    """Vardiya başlangıcı ve molalar sabittir; düzen yalnız brüt bitişi ve
    haftalık çalışma günü sayısını belirler."""
    kod: str
    ad: str
    brut_bitis: float          # saat, üretim gününün 00:00'ına göre (24'ü aşabilir)
    gun: int                   # haftalık gün: 5 -> Pzt-Cum, 6 -> Pzt-Cmt

    @property
    def etiket(self) -> str:
        return f"{self.kod} · {self.ad}"


@dataclass(frozen=True)
class TakvimKurali:
    baslangic: float
    molalar: Tuple[Tuple[float, float], ...]
    gun_molalari: Dict[int, Tuple[Tuple[float, float], ...]]
    araliksiz_azami_saat: float
    zorunlu_mola_saat: float
    zorunlu_mola_mesaiye_sayilir: bool
    duzenler: Tuple[CalismaDuzeni, ...]
    varsayilan_duzen: str

    def gunun_molalari(self, haftanin_gunu: int) -> Tuple[Tuple[float, float], ...]:
        return self.gun_molalari.get(haftanin_gunu, self.molalar)

    def duzen(self, kod: Optional[str]) -> CalismaDuzeni:
        kod = duzen_kodu(kod, self)
        return next(d for d in self.duzenler if d.kod == kod)


def duzen_kodu(metin: Optional[str], kural: TakvimKurali) -> str:
    """'D2 · Uzun gün' / 'd2' / '' -> geçerli düzen kodu."""
    if metin:
        kod = str(metin).replace("·", " ").split()[0].strip().upper()
        if any(d.kod == kod for d in kural.duzenler):
            return kod
    return kural.varsayilan_duzen


@dataclass(frozen=True)
class Mevzuat:
    gunluk_azami_saat: float
    haftalik_normal_saat: float
    haftalik_azami_saat: float
    yillik_fazla_calisma_tavani: float


@dataclass
class Fabrika:
    ad: str
    urun: str
    varyantlar: Tuple[str, ...]
    parca_gruplari: Tuple[ParcaGrubu, ...]
    varyant_grubu: Optional[VaryantGrubu]
    hucre_atolyesi: str
    hucreler: Tuple[Operasyon, ...]
    hat_atolyesi: str
    istasyonlar: Tuple[Operasyon, ...]
    personel_sayisi: int
    takvim: TakvimKurali
    mevzuat: Mevzuat
    kaynak_dosyasi: str = ""

    # ------------------------------------------------------------- türetilmiş
    def parca_suresi(self, kod: str) -> float:
        for g in self.parca_gruplari:
            for p in g.parcalar:
                if p.kod == kod:
                    return p.sure_sn
        raise KeyError(kod)

    def parca_grubu(self, parca_kodu: str) -> ParcaGrubu:
        for g in self.parca_gruplari:
            if any(p.kod == parca_kodu for p in g.parcalar):
                return g
        raise KeyError(parca_kodu)

    def tum_parcalar(self) -> List[str]:
        return [p.kod for g in self.parca_gruplari for p in g.parcalar]

    @property
    def atolyeler(self) -> List[str]:
        """Akış sırasına göre atölye adları."""
        out = [g.ad for g in self.parca_gruplari]
        if self.varyant_grubu:
            out.append(self.varyant_grubu.ad)
        if self.hucreler:
            out.append(self.hucre_atolyesi)
        out.append(self.hat_atolyesi)
        return out

    def operasyon(self, kod: str) -> Operasyon:
        for o in (*self.hucreler, *self.istasyonlar):
            if o.kod == kod:
                return o
        raise KeyError(kod)

    def ayar_saatleri(self) -> Dict[str, float]:
        out = {g.kod: g.ayar_saat for g in self.parca_gruplari}
        if self.varyant_grubu:
            out[self.varyant_grubu.kod] = self.varyant_grubu.ayar_saat
        return out

    # -------------------------------------------------------------- doğrulama
    def denetle(self) -> List[str]:
        """Ölümcül hatalarda TanimHatasi fırlatır; uyarıları liste olarak döndürür."""
        uyarilar: List[str] = []
        parcalar = self.tum_parcalar()
        if len(parcalar) != len(set(parcalar)):
            raise TanimHatasi("Aynı parça kodu birden fazla grupta tanımlanmış.")
        if not self.istasyonlar:
            raise TanimHatasi("Hatta en az bir istasyon olmalı.")
        if not self.varyantlar:
            raise TanimHatasi("En az bir ürün varyantı tanımlanmalı.")
        hucre_kodlari = {h.kod for h in self.hucreler}
        tuketilen: set = set()
        for h in self.hucreler:
            for g in h.girdiler:
                if g not in parcalar:
                    raise TanimHatasi(f"Hücre {h.kod}: '{g}' tanımlı bir parça değil.")
                tuketilen.add(g)
        varyant_kullanildi = False
        for i in self.istasyonlar:
            for g in i.girdiler:
                if g == VARYANT_GIRDISI:
                    varyant_kullanildi = True
                elif g in hucre_kodlari or g in parcalar:
                    tuketilen.add(g)
                else:
                    raise TanimHatasi(f"İstasyon {i.kod}: '{g}' bilinmeyen girdi.")
        for o in (*self.hucreler, *self.istasyonlar):
            if o.sure_sn <= 0 or o.azami_istasyon < 1:
                raise TanimHatasi(f"{o.kod}: süre ve istasyon sayısı pozitif olmalı.")
        if self.varyant_grubu and not varyant_kullanildi:
            raise TanimHatasi("Varyant grubu var ama hiçbir istasyon 'VARYANT' tüketmiyor.")
        if varyant_kullanildi and not self.varyant_grubu:
            raise TanimHatasi("Bir istasyon 'VARYANT' tüketiyor ama varyant grubu yok.")
        if self.varyant_grubu:
            eksik = [v for v in self.varyantlar if self.varyant_grubu.takim_adedi.get(v, 0) < 1]
            if eksik:
                raise TanimHatasi(f"Şu varyantların takımı yok: {', '.join(eksik)}")
        for p in parcalar:
            if p not in tuketilen:
                uyarilar.append(f"Parça {p} hiçbir yerde tüketilmiyor (yine de üretilir).")
        for h in self.hucreler:
            if h.kod not in tuketilen:
                uyarilar.append(f"Hücre {h.kod} çıktısını hiçbir istasyon tüketmiyor.")
        if not self.takvim.duzenler:
            raise TanimHatasi("En az bir çalışma düzeni tanımlanmalı.")
        return uyarilar


def _operasyonlar(liste: Sequence[dict]) -> Tuple[Operasyon, ...]:
    return tuple(Operasyon(str(o["kod"]), str(o.get("ad", o["kod"])),
                           tuple(str(x) for x in o.get("girdiler", [])),
                           float(o["sure_sn"]), int(o.get("azami_istasyon", 1)))
                 for o in liste)


def _araliklar(liste) -> Tuple[Tuple[float, float], ...]:
    return tuple(sorted((saat_oku(a), saat_oku(b)) for a, b in liste))


def fabrika_sozlukten(v: dict, kaynak: str = "") -> Fabrika:
    """JSON sözlüğünden Fabrika nesnesi kurar ve doğrular."""
    try:
        gruplar = tuple(
            ParcaGrubu(str(g["kod"]), str(g["ad"]), str(g.get("kaynak_oneki", g["kod"])),
                       int(g["makine_sayisi"]), float(g.get("ayar_saat", 0.0)),
                       str(g.get("ayar_etiketi", "Ayar")),
                       tuple(Parca(str(k), str(p.get("ad", k)), float(p["sure_sn"]))
                             for k, p in g["parcalar"].items()))
            for g in v.get("parca_gruplari", []))
        vg = v.get("varyant_grubu")
        varyant_grubu = None
        if vg:
            varyant_grubu = VaryantGrubu(
                str(vg["kod"]), str(vg["ad"]), str(vg.get("kaynak_oneki", vg["kod"])),
                int(vg["makine_sayisi"]), float(vg["sure_sn"]),
                float(vg.get("ayar_saat", 0.0)), str(vg.get("ayar_etiketi", "Ayar")),
                str(vg.get("bilesen", "Varyant bileşeni")),
                str(vg.get("takim_adi", "Takım")),
                {str(k): int(a) for k, a in vg["takim_adedi"].items()})
        t = v["takvim"]
        duzenler = tuple(CalismaDuzeni(str(d["kod"]).upper(), str(d["ad"]),
                                       saat_oku(d["brut_bitis"]), int(d["gun"]))
                         for d in t["duzenler"])
        kural = TakvimKurali(
            baslangic=saat_oku(t["vardiya_baslangic"]),
            molalar=_araliklar(t.get("molalar", [])),
            gun_molalari={int(k): _araliklar(a) for k, a in t.get("gun_molalari", {}).items()},
            araliksiz_azami_saat=float(t.get("araliksiz_azami_saat", 7.5)),
            zorunlu_mola_saat=float(t.get("zorunlu_mola_saat", 0.5)),
            zorunlu_mola_mesaiye_sayilir=bool(t.get("zorunlu_mola_mesaiye_sayilir", True)),
            duzenler=duzenler,
            varsayilan_duzen=str(t.get("varsayilan_duzen", duzenler[0].kod)).upper())
        m = v.get("mevzuat", {})
        mevzuat = Mevzuat(float(m.get("gunluk_azami_saat", 11.0)),
                          float(m.get("haftalik_normal_saat", 45.0)),
                          float(m.get("haftalik_azami_saat", 60.0)),
                          float(m.get("yillik_fazla_calisma_tavani", 270.0)))
        f = Fabrika(
            ad=str(v.get("ad", "Fabrika")), urun=str(v.get("urun", "Ürün")),
            varyantlar=tuple(str(x) for x in v["varyantlar"]),
            parca_gruplari=gruplar, varyant_grubu=varyant_grubu,
            hucre_atolyesi=str(v.get("hucreler", {}).get("ad", "Ön Montaj")),
            hucreler=_operasyonlar(v.get("hucreler", {}).get("liste", [])),
            hat_atolyesi=str(v["hat"].get("ad", "Hat")),
            istasyonlar=_operasyonlar(v["hat"]["istasyonlar"]),
            personel_sayisi=int(v.get("personel_sayisi", 10)),
            takvim=kural, mevzuat=mevzuat, kaynak_dosyasi=kaynak)
    except (KeyError, TypeError, ValueError) as hata:
        if isinstance(hata, TanimHatasi):
            raise
        raise TanimHatasi(f"Fabrika tanımı okunamadı: {hata!r}") from hata
    f.denetle()
    return f


def fabrika_yukle(yol: Union[str, Path, None] = None) -> Fabrika:
    """Fabrika tanımını dosyadan okur; yol verilmezse örnek fabrika."""
    yol = Path(yol) if yol else varsayilan_fabrika_yolu()
    with open(yol, encoding="utf-8") as f:
        return fabrika_sozlukten(json.load(f), str(yol))


def veri_dizini() -> Path:
    """Paketlenmiş (.exe) uygulamada da çalışan veri klasörü yolu."""
    import sys
    kok = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return kok / "veri"


def varsayilan_fabrika_yolu() -> Path:
    return veri_dizini() / "ornek_fabrika.json"


# ==============================================================================
# SİPARİŞ, EK MESAİ, SENARYO
# ==============================================================================

@dataclass
class Siparis:
    kod: str
    miktarlar: Dict[str, int]
    termin: date

    @property
    def toplam(self) -> int:
        return sum(max(0, int(a)) for a in self.miktarlar.values())

    def __str__(self) -> str:
        icerik = ", ".join(f"{v}: {a}" for v, a in self.miktarlar.items() if a > 0)
        return f"{self.kod} [{icerik}] termin {self.termin:%d.%m.%Y}"


@dataclass
class EkMesai:
    """
    Tek bir kaynağa (makine/istasyon) verilen ek çalışma talimatı.

    Talimat yalnız hedef kaynağı etkiler; diğerleri varsayılan düzende kalır.
    ``duzen`` bu talimatın üzerine kurulduğu çalışma düzenidir; ``ek_saat``
    o düzenin üstüne eklenen net çalışma saatidir (0 olabilir).
    """
    kaynak: str
    baslangic: date
    bitis: date
    ek_saat: float = 0.0
    duzen: str = ""
    hafta_sonu: bool = False
    aktif: bool = True

    def __post_init__(self) -> None:
        self.ek_saat = max(0.0, float(self.ek_saat or 0.0))

    def etkili_mi(self, varsayilan: str) -> bool:
        return self.aktif and bool(self.kaynak) and (
            self.ek_saat > 0 or (self.duzen or varsayilan) != varsayilan)

    def __str__(self) -> str:
        return (f"{self.kaynak} {self.baslangic:%d.%m}–{self.bitis:%d.%m.%Y} "
                f"{self.duzen or '-'} +{self.ek_saat:g} sa"
                + (" (hafta sonu dahil)" if self.hafta_sonu else ""))


@dataclass
class PlanAyarlari:
    parti_sayilari: Tuple[int, ...] = (1, 2, 3, 4)
    ramp_adaylari: Tuple[float, ...] = (1.0, 2.0)
    ayar_saatleri: Dict[str, float] = field(default_factory=dict)  # grup kodu -> saat
    ayari_gun_basina_hizala: bool = False
    serpantin_sira: bool = True
    azami_ayar_payi: float = 0.25            # varyant serisinde ayarın en büyük payı (α)
    personel_denetimi: bool = True
    varsayilan_duzen: str = ""
    ufuk_gun: int = 900


@dataclass
class PlanGirdisi:
    baslangic: date
    siparisler: List[Siparis]
    ek_mesailer: List[EkMesai] = field(default_factory=list)
    personel: List[str] = field(default_factory=list)
    ayarlar: PlanAyarlari = field(default_factory=PlanAyarlari)
    fabrika_dosyasi: str = ""


def _tarih(metin) -> date:
    if isinstance(metin, date):
        return metin
    return datetime.strptime(str(metin)[:10], "%Y-%m-%d").date()


def senaryo_sozlukten(v: dict) -> PlanGirdisi:
    try:
        siparisler = [Siparis(str(s["kod"]),
                              {str(k): int(a) for k, a in s["miktarlar"].items() if int(a) > 0},
                              _tarih(s["termin"]))
                      for s in v.get("siparisler", [])]
        ekler = [EkMesai(str(e["kaynak"]), _tarih(e["baslangic"]), _tarih(e["bitis"]),
                         float(e.get("ek_saat", 0.0)), str(e.get("duzen", "")),
                         bool(e.get("hafta_sonu", False)), bool(e.get("aktif", True)))
                 for e in v.get("ek_mesailer", [])]
        a = v.get("ayarlar", {})
        ayarlar = PlanAyarlari(
            parti_sayilari=tuple(int(x) for x in a.get("parti_sayilari", (1, 2, 3, 4))),
            ramp_adaylari=tuple(float(x) for x in a.get("ramp_adaylari", (1.0, 2.0))),
            ayar_saatleri={str(k): float(s) for k, s in a.get("ayar_saatleri", {}).items()},
            ayari_gun_basina_hizala=bool(a.get("ayari_gun_basina_hizala", False)),
            serpantin_sira=bool(a.get("serpantin_sira", True)),
            azami_ayar_payi=float(a.get("azami_ayar_payi", 0.25)),
            personel_denetimi=bool(a.get("personel_denetimi", True)),
            varsayilan_duzen=str(a.get("varsayilan_duzen", "")))
        return PlanGirdisi(_tarih(v["baslangic"]), siparisler, ekler,
                           [str(x) for x in v.get("personel", [])], ayarlar,
                           str(v.get("fabrika_dosyasi", "")))
    except (KeyError, TypeError, ValueError) as hata:
        raise TanimHatasi(f"Senaryo okunamadı: {hata!r}") from hata


def senaryo_sozluge(s: PlanGirdisi) -> dict:
    a = s.ayarlar
    return {
        "baslangic": s.baslangic.isoformat(),
        "siparisler": [{"kod": x.kod, "miktarlar": dict(x.miktarlar),
                        "termin": x.termin.isoformat()} for x in s.siparisler],
        "ek_mesailer": [{"kaynak": e.kaynak, "baslangic": e.baslangic.isoformat(),
                         "bitis": e.bitis.isoformat(), "ek_saat": e.ek_saat,
                         "duzen": e.duzen, "hafta_sonu": e.hafta_sonu, "aktif": e.aktif}
                        for e in s.ek_mesailer],
        "personel": list(s.personel),
        "ayarlar": {"parti_sayilari": list(a.parti_sayilari),
                    "ramp_adaylari": list(a.ramp_adaylari),
                    "ayar_saatleri": dict(a.ayar_saatleri),
                    "ayari_gun_basina_hizala": a.ayari_gun_basina_hizala,
                    "serpantin_sira": a.serpantin_sira,
                    "azami_ayar_payi": a.azami_ayar_payi,
                    "personel_denetimi": a.personel_denetimi,
                    "varsayilan_duzen": a.varsayilan_duzen},
        "fabrika_dosyasi": s.fabrika_dosyasi,
    }


def senaryo_oku(yol: Union[str, Path]) -> PlanGirdisi:
    with open(yol, encoding="utf-8") as f:
        return senaryo_sozlukten(json.load(f))


def senaryo_yaz(s: PlanGirdisi, yol: Union[str, Path]) -> None:
    with open(yol, "w", encoding="utf-8") as f:
        json.dump(senaryo_sozluge(s), f, ensure_ascii=False, indent=2)


def varsayilan_personel(n: int) -> List[str]:
    """P01, P02, ... biçiminde personel kodları."""
    return [f"P{i:02d}" for i in range(1, max(1, int(n)) + 1)]
