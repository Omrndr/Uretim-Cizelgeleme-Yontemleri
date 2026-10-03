"""
Masaüstü arayüzü (Tkinter — Python ile birlikte gelir, ek kurulum gerekmez).

Akış:  girdileri düzenle → HESAPLA (arka planda, iptal edilebilir)
       → uyarıları oku → gerekirse ek mesai talimatı yaz → yeniden hesapla
       → şemaları incele → ÇIKTI PAKETİ (PDF/HTML + XLSX + CSV)

Hesap ayrı bir iş parçacığında koşar; ilerleme bir kuyruk üzerinden ana
döngüye aktarılır, böylece pencere donmaz.
"""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import traceback
import tkinter as tk
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Dict, List, Optional

from motor import analiz as an
from motor import defter
from motor import dogrulama as dg
from motor.cozucu import Durduruldu, Plan, duzen_karsilastir, ek_mesai_onerisi, plan_olustur
from motor.model import (EkMesai, PlanAyarlari, PlanGirdisi, Siparis, TanimHatasi,
                         fabrika_yukle, senaryo_yaz, senaryo_oku,
                         varsayilan_personel, veri_dizini)
from motor.tahsis import kaynaklari_olustur, en_iyi_dagilim
from motor.uyarilar import SEMBOL, geciken_siparisler, grup_aciklari, mevzuat_panosu
from rapor import genel_bakis as gb
from rapor import semalar as sm
from rapor import tablolar as tb
from rapor.is_emirleri import ATANAMADI, BASLIKLAR, is_emirleri, suz, tablo
from arayuz.tablolar import DuzenlenebilirTablo, VeriTablosu
from arayuz.tuval import SahneTuvali

SURUM = "1.0"
VURGU = "#0f766e"
EVET, HAYIR = "Evet", "Hayır"


def tarih_oku(metin: str) -> date:
    metin = str(metin).strip()
    for bicim in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(metin, bicim).date()
        except ValueError:
            continue
    raise TanimHatasi(f"Tarih anlaşılamadı: '{metin}' (gg.aa.yyyy yazın)")


def tarih_yaz(g: date) -> str:
    return g.strftime("%d.%m.%Y")


def klasoru_ac(yol: Path) -> None:
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(yol))                      # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(yol)])
        else:
            subprocess.Popen(["xdg-open", str(yol)])
    except OSError:
        pass


class Uygulama(tk.Tk):
    def __init__(self, fabrika_yolu: Optional[str] = None, senaryo_yolu: Optional[str] = None):
        super().__init__()
        self.fabrika = fabrika_yukle(fabrika_yolu)
        self.plan: Optional[Plan] = None
        self.emirler = []
        self._kuyruk: "queue.Queue" = queue.Queue()
        self._iptal = threading.Event()
        self._calisiyor = False
        self.title(f"Üretim Çizelgeleme — {self.fabrika.ad}")
        self.geometry("1380x880")
        try:
            self._simge = tk.PhotoImage(file=str(veri_dizini() / "simge.png"))
            self.iconphoto(True, self._simge)
        except tk.TclError:
            pass
        self.minsize(1040, 700)
        self._stil()
        self._menu()
        self._ust_serit()
        self.sekmeler = ttk.Notebook(self)
        self.sekmeler.pack(fill="both", expand=True, padx=8, pady=(0, 4))
        self._kur_girdiler()
        self._kur_uyarilar()
        self._kur_ozet()
        self.tuval_gunluk = self._kur_sema("Günlük şema", gunluk=True)
        self.tuval_haftalik = self._kur_sema("Haftalık şema", gunluk=False)
        self._kur_genel()
        self._kur_is_emirleri()
        self._kur_defter()
        self._kur_tablolar()
        self._kur_cikti()
        self.durum = ttk.Label(self, text="Hazır.", anchor="w", style="Durum.TLabel")
        self.durum.pack(fill="x", side="bottom")
        self.senaryoyu_doldur(senaryo_oku(senaryo_yolu or veri_dizini() / "ornek_senaryo.json"))
        self.bind("<F5>", lambda _: self.hesapla())
        self.after(100, self._kuyrugu_isle)

    # ================================================================ görünüm
    def _stil(self) -> None:
        s = ttk.Style(self)
        try:
            s.theme_use("clam")
        except tk.TclError:
            pass
        s.configure("TNotebook.Tab", padding=(12, 5))
        s.configure("Vurgu.TButton", foreground="#ffffff", background=VURGU, padding=(14, 6))
        s.map("Vurgu.TButton", background=[("active", "#115e59"), ("disabled", "#a8a29e")])
        s.configure("Durum.TLabel", padding=(10, 3), background="#f5f5f4")
        s.configure("Baslik.TLabel", font=("TkDefaultFont", 11, "bold"))
        s.configure("Treeview", rowheight=22)
        s.configure("Horizontal.TProgressbar", background=VURGU, troughcolor="#e7e5e4")

    def _menu(self) -> None:
        m = tk.Menu(self)
        dosya = tk.Menu(m, tearoff=False)
        dosya.add_command(label="Senaryo aç…", command=self.senaryo_dosyasi_ac)
        dosya.add_command(label="Senaryo kaydet…", command=self.senaryo_yaz)
        dosya.add_separator()
        dosya.add_command(label="Fabrika tanımı aç…", command=self.fabrika_ac)
        dosya.add_separator()
        dosya.add_command(label="Çıkış", command=self.destroy)
        m.add_cascade(label="Dosya", menu=dosya)
        hesap = tk.Menu(m, tearoff=False)
        hesap.add_command(label="Hesapla (F5)", command=self.hesapla)
        hesap.add_command(label="İptal", command=self.iptal)
        hesap.add_separator()
        hesap.add_command(label="Çalışma düzenlerini karşılaştır…",
                          command=self.duzenleri_karsilastir)
        m.add_cascade(label="Hesap", menu=hesap)
        yardim = tk.Menu(m, tearoff=False)
        yardim.add_command(label="Hakkında", command=self.hakkinda)
        m.add_cascade(label="Yardım", menu=yardim)
        self.configure(menu=m)

    def _ust_serit(self) -> None:
        f = ttk.Frame(self, padding=(8, 8, 8, 6))
        f.pack(fill="x")
        self.d_hesapla = ttk.Button(f, text="▶  HESAPLA", style="Vurgu.TButton",
                                    command=self.hesapla)
        self.d_hesapla.pack(side="left")
        self.d_iptal = ttk.Button(f, text="■ İptal", command=self.iptal, state="disabled")
        self.d_iptal.pack(side="left", padx=6)
        self.d_paket = ttk.Button(f, text="Çıktı paketi…", command=self.cikti_paketi_dugmesi)
        self.d_paket.pack(side="left")
        self.ilerleme = ttk.Progressbar(f, length=260, maximum=100)
        self.ilerleme.pack(side="left", padx=12)
        self.ilerleme_yazi = ttk.Label(f, text="", foreground="#57534e")
        self.ilerleme_yazi.pack(side="left")
        self.sonuc_yazi = ttk.Label(f, text="", font=("TkDefaultFont", 10, "bold"))
        self.sonuc_yazi.pack(side="right")

    # ================================================================ girdiler
    def _kur_girdiler(self) -> None:
        sayfa = ttk.Frame(self.sekmeler, padding=8)
        self.sekmeler.add(sayfa, text="Girdiler")
        sol = ttk.LabelFrame(sayfa, text="Plan ayarları", padding=10)
        sol.pack(side="left", fill="y")
        f = self.fabrika
        self.v_baslangic = tk.StringVar()
        self.v_duzen = tk.StringVar()
        self.v_kadro = tk.IntVar(value=f.personel_sayisi)
        satir = 0

        def alan(etiket: str, widget: tk.Widget) -> None:
            nonlocal satir
            ttk.Label(sol, text=etiket).grid(row=satir, column=0, sticky="w", pady=3)
            widget.grid(row=satir, column=1, sticky="ew", pady=3, padx=(8, 0))
            satir += 1

        alan("Plan başlangıcı", ttk.Entry(sol, textvariable=self.v_baslangic, width=14))
        alan("Varsayılan düzen", ttk.Combobox(
            sol, textvariable=self.v_duzen, state="readonly", width=20,
            values=[d.etiket for d in f.takvim.duzenler]))
        self.v_ayar: Dict[str, tk.DoubleVar] = {}
        for kod, saat in f.ayar_saatleri().items():
            ad = next((g.ayar_etiketi for g in f.parca_gruplari if g.kod == kod),
                      f.varyant_grubu.ayar_etiketi if f.varyant_grubu else kod)
            self.v_ayar[kod] = tk.DoubleVar(value=saat)
            alan(f"{ad} ({kod}), sa", ttk.Spinbox(sol, from_=0, to=48, increment=0.25,
                                                  textvariable=self.v_ayar[kod], width=8))
        ttk.Separator(sol).grid(row=satir, column=0, columnspan=2, sticky="ew", pady=8)
        satir += 1
        self.v_gelismis = tk.BooleanVar(value=False)
        ttk.Checkbutton(sol, text="Gelişmiş ayarları göster", variable=self.v_gelismis,
                        command=self._gelismis_goster).grid(row=satir, column=0, columnspan=2,
                                                            sticky="w")
        satir += 1
        self.gelismis = ttk.Frame(sol)
        self.gelismis.grid(row=satir, column=0, columnspan=2, sticky="ew")
        self.v_partiler = tk.StringVar(value="1, 2, 3, 4")
        self.v_rampa = tk.StringVar(value="1, 2")
        self.v_hizala = tk.BooleanVar(value=False)
        self.v_serpantin = tk.BooleanVar(value=True)
        self.v_denetim = tk.BooleanVar(value=True)
        self.v_alfa = tk.DoubleVar(value=0.25)
        ttk.Label(self.gelismis, text="Parti sayıları (K)").grid(row=0, column=0, sticky="w")
        ttk.Entry(self.gelismis, textvariable=self.v_partiler, width=12).grid(row=0, column=1)
        ttk.Label(self.gelismis, text="Rampa adayları (r)").grid(row=1, column=0, sticky="w")
        ttk.Entry(self.gelismis, textvariable=self.v_rampa, width=12).grid(row=1, column=1)
        ttk.Checkbutton(self.gelismis, text="Ayarı gün başına hizala",
                        variable=self.v_hizala).grid(row=2, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(self.gelismis, text="Snake sequencing (parti geçişinde ayar yok)",
                        variable=self.v_serpantin).grid(row=3, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(self.gelismis, text="Bireysel personel denetimi",
                        variable=self.v_denetim).grid(row=4, column=0, columnspan=2, sticky="w")
        ttk.Label(self.gelismis, text="En büyük ayar payı (α)").grid(row=5, column=0, sticky="w")
        ttk.Spinbox(self.gelismis, from_=0.05, to=0.9, increment=0.05, textvariable=self.v_alfa,
                    width=6).grid(row=5, column=1, sticky="w")
        self.gelismis.grid_remove()
        satir += 1
        ttk.Separator(sol).grid(row=satir, column=0, columnspan=2, sticky="ew", pady=8)
        satir += 1
        bilgi = (f"Fabrika: {f.ad}\nÜrün: {f.urun}\nVaryantlar: {', '.join(f.varyantlar)}\n"
                 f"Atölyeler: {len(f.atolyeler)} · istasyon tipi: "
                 f"{len(f.hucreler) + len(f.istasyonlar)}")
        ttk.Label(sol, text=bilgi, foreground="#57534e", justify="left",
                  wraplength=250).grid(row=satir, column=0, columnspan=2, sticky="w")

        sag = ttk.Frame(sayfa)
        sag.pack(side="left", fill="both", expand=True, padx=(10, 0))
        ic = ttk.Notebook(sag)
        ic.pack(fill="both", expand=True)
        sip_sutun = ["Sipariş", "Termin"] + list(f.varyantlar)
        self.t_siparis = DuzenlenebilirTablo(
            ic, sip_sutun, genislikler={"Sipariş": 100, "Termin": 100},
            varsayilan=lambda: [f"S-{len(self.t_siparis.satirlar()) + 101}",
                                tarih_yaz(self._baslangic() + timedelta(days=28))]
            + ["0"] * len(f.varyantlar))
        ic.add(self.t_siparis, text="Siparişler")

        mesai = ttk.Frame(ic)
        ic.add(mesai, text="Ek mesai talimatları")
        self.t_mesai = DuzenlenebilirTablo(
            mesai, ["Kaynak", "Başlangıç", "Bitiş", "Ek saat/gün", "Düzen", "Hafta sonu", "Aktif"],
            secenekler={"Kaynak": self._kaynak_adlari,
                        "Düzen": lambda: [d.etiket for d in f.takvim.duzenler],
                        "Hafta sonu": lambda: [EVET, HAYIR], "Aktif": lambda: [EVET, HAYIR]},
            varsayilan=lambda: ["", tarih_yaz(self._baslangic()),
                                tarih_yaz(self._baslangic() + timedelta(days=11)), "2",
                                f.takvim.duzen(None).etiket, HAYIR, EVET])
        self.t_mesai.pack(fill="both", expand=True)
        oneri = ttk.LabelFrame(mesai, text="Bottleneck walk ile öneri (hesaplanmış plan gerekir)",
                               padding=6)
        oneri.pack(fill="x", pady=(6, 0))
        self.v_on_atolye = tk.StringVar(value=f.hat_atolyesi)
        self.v_on_adet = tk.IntVar(value=2)
        self.v_on_saat = tk.DoubleVar(value=2.0)
        ttk.Combobox(oneri, textvariable=self.v_on_atolye, values=f.atolyeler, width=28,
                     state="readonly").pack(side="left")
        ttk.Label(oneri, text="kaynak sayısı").pack(side="left", padx=(8, 2))
        ttk.Spinbox(oneri, from_=1, to=20, textvariable=self.v_on_adet, width=4).pack(side="left")
        ttk.Label(oneri, text="ek saat/gün").pack(side="left", padx=(8, 2))
        ttk.Spinbox(oneri, from_=0.5, to=12, increment=0.5, textvariable=self.v_on_saat,
                    width=5).pack(side="left")
        ttk.Button(oneri, text="Öneriyi tabloya ekle", command=self.oneri_ekle).pack(side="left",
                                                                                     padx=8)

        self.t_personel = DuzenlenebilirTablo(
            ic, ["Personel"], genislikler={"Personel": 200},
            varsayilan=lambda: [f"P{len(self.t_personel.satirlar()) + 1:02d}"])
        ic.add(self.t_personel, text="Personel kadrosu")

        alt = ttk.LabelFrame(sag, text="Girdi denetimi (hesaplamadan önce)", padding=6)
        alt.pack(fill="x", pady=(8, 0))
        ust = ttk.Frame(alt)
        ust.pack(fill="x")
        ttk.Button(ust, text="Denetle", command=self.girdileri_denetle).pack(side="left")
        self.girdi_uyari = tk.Text(alt, height=6, wrap="word", relief="flat",
                                   background="#fafaf9")
        self.girdi_uyari.pack(fill="x", pady=(4, 0))

    def _gelismis_goster(self) -> None:
        if self.v_gelismis.get():
            self.gelismis.grid()
        else:
            self.gelismis.grid_remove()

    def _baslangic(self) -> date:
        try:
            return tarih_oku(self.v_baslangic.get())
        except TanimHatasi:
            return date.today()

    def _personel_listesi(self) -> List[str]:
        return [r[0].strip() for r in self.t_personel.satirlar() if r and r[0].strip()]

    def _kaynak_adlari(self) -> List[str]:
        if self.plan:
            return [k.ad for k in self.plan.kaynaklar]
        try:
            t = en_iyi_dagilim(self.fabrika, max(1, len(self._personel_listesi())),
                               self.fabrika.varyantlar)
            return [k.ad for k in kaynaklari_olustur(self.fabrika, t)] if t else []
        except Exception:                               # noqa: BLE001
            return []

    # ------------------------------------------------------------ senaryo
    def senaryoyu_doldur(self, s: PlanGirdisi) -> None:
        f = self.fabrika
        self.v_baslangic.set(tarih_yaz(s.baslangic))
        self.v_duzen.set(f.takvim.duzen(s.ayarlar.varsayilan_duzen or None).etiket)
        for kod, v in self.v_ayar.items():
            v.set(s.ayarlar.ayar_saatleri.get(kod, f.ayar_saatleri()[kod]))
        self.v_partiler.set(", ".join(str(x) for x in s.ayarlar.parti_sayilari))
        self.v_rampa.set(", ".join(f"{x:g}" for x in s.ayarlar.ramp_adaylari))
        self.v_hizala.set(s.ayarlar.ayari_gun_basina_hizala)
        self.v_serpantin.set(s.ayarlar.serpantin_sira)
        self.v_denetim.set(s.ayarlar.personel_denetimi)
        self.v_alfa.set(s.ayarlar.azami_ayar_payi)
        self.t_siparis.doldur([[x.kod, tarih_yaz(x.termin)]
                               + [x.miktarlar.get(v, 0) for v in f.varyantlar]
                               for x in s.siparisler])
        self.t_mesai.doldur([[e.kaynak, tarih_yaz(e.baslangic), tarih_yaz(e.bitis),
                              f"{e.ek_saat:g}", f.takvim.duzen(e.duzen or None).etiket,
                              EVET if e.hafta_sonu else HAYIR, EVET if e.aktif else HAYIR]
                             for e in s.ek_mesailer])
        kadro = s.personel or varsayilan_personel(f.personel_sayisi)
        self.t_personel.doldur([[p] for p in kadro])

    def senaryoyu_oku(self) -> PlanGirdisi:
        f = self.fabrika
        siparisler = []
        for r in self.t_siparis.satirlar():
            if not r or not r[0].strip():
                continue
            miktar = {}
            for v, a in zip(f.varyantlar, r[2:]):
                try:
                    miktar[v] = max(0, int(float(str(a).replace(",", ".") or 0)))
                except ValueError:
                    raise TanimHatasi(f"{r[0]}: '{a}' geçerli bir miktar değil.")
            siparisler.append(Siparis(r[0].strip(), miktar, tarih_oku(r[1])))
        ekler = []
        for r in self.t_mesai.satirlar():
            if not r or not r[0].strip():
                continue
            ekler.append(EkMesai(r[0].strip(), tarih_oku(r[1]), tarih_oku(r[2]),
                                 float(str(r[3]).replace(",", ".") or 0), r[4],
                                 r[5] == EVET, r[6] != HAYIR))

        def liste(metin: str, tur):
            return tuple(tur(x) for x in metin.replace(";", ",").split(",") if x.strip())

        ayarlar = PlanAyarlari(
            parti_sayilari=liste(self.v_partiler.get(), int) or (1,),
            ramp_adaylari=liste(self.v_rampa.get(), float) or (1.0,),
            ayar_saatleri={k: float(v.get()) for k, v in self.v_ayar.items()},
            ayari_gun_basina_hizala=self.v_hizala.get(),
            serpantin_sira=self.v_serpantin.get(),
            azami_ayar_payi=float(self.v_alfa.get()),
            personel_denetimi=self.v_denetim.get(),
            varsayilan_duzen=self.v_duzen.get())
        return PlanGirdisi(tarih_oku(self.v_baslangic.get()), siparisler, ekler,
                           self._personel_listesi(), ayarlar, self.fabrika.kaynak_dosyasi)

    def senaryo_dosyasi_ac(self) -> None:
        yol = filedialog.askopenfilename(filetypes=[("Senaryo", "*.json")])
        if yol:
            try:
                self.senaryoyu_doldur(senaryo_oku(yol))
                self._durum(f"Senaryo yüklendi: {yol}")
            except (TanimHatasi, OSError) as h:
                messagebox.showerror("Senaryo açılamadı", str(h))

    def senaryo_yaz(self) -> None:
        yol = filedialog.asksaveasfilename(defaultextension=".json",
                                           filetypes=[("Senaryo", "*.json")])
        if yol:
            try:
                senaryo_yaz(self.senaryoyu_oku(), yol)
                self._durum(f"Senaryo kaydedildi: {yol}")
            except (TanimHatasi, OSError, ValueError) as h:
                messagebox.showerror("Kaydedilemedi", str(h))

    def fabrika_ac(self) -> None:
        yol = filedialog.askopenfilename(filetypes=[("Fabrika tanımı", "*.json")])
        if not yol:
            return
        try:
            fabrika_yukle(yol)
        except (TanimHatasi, OSError) as h:
            messagebox.showerror("Fabrika tanımı okunamadı", str(h))
            return
        messagebox.showinfo("Fabrika tanımı", "Yeni fabrika tanımı için uygulama yeniden açılıyor.")
        self.destroy()
        Uygulama(yol).mainloop()

    def girdileri_denetle(self) -> List[str]:
        uyarilar: List[str] = []
        try:
            s = self.senaryoyu_oku()
            uyarilar += dg.personel_listesi_uyarilari(s.personel)
            uyarilar += dg.ek_mesai_uyarilari(self.fabrika, s.ek_mesailer, s.baslangic,
                                              self._kaynak_adlari())
            try:
                uyarilar += dg.bakiye_uyarilari(s.personel, defter.bakiyeler(s.baslangic.year))
            except Exception:                           # noqa: BLE001
                pass
            if not s.siparisler:
                uyarilar.append("Sipariş tablosu boş.")
        except (TanimHatasi, ValueError) as h:
            uyarilar.append(f"GİRDİ HATASI: {h}")
        self.girdi_uyari.delete("1.0", "end")
        self.girdi_uyari.insert("end", "\n".join(f"• {u}" for u in uyarilar)
                                or "Girdilerde sorun bulunmadı.")
        return uyarilar

    def oneri_ekle(self) -> None:
        if not self.plan:
            messagebox.showinfo("Öneri", "Öneri için önce bir plan hesaplayın.")
            return
        adlar = ek_mesai_onerisi(self.plan, self.v_on_atolye.get(), int(self.v_on_adet.get()),
                                 float(self.v_on_saat.get()))
        bas = self._baslangic()
        for ad in adlar:
            self.t_mesai.satir_ekle([ad, tarih_yaz(bas), tarih_yaz(bas + timedelta(days=11)),
                                     f"{float(self.v_on_saat.get()):g}",
                                     self.fabrika.takvim.duzen(None).etiket, HAYIR, EVET])
        self._durum(f"Önerilen kaynaklar eklendi: {', '.join(adlar) or '-'}")

    # ================================================================ sonuç sekmeleri
    def _metin_kutusu(self, ust) -> tk.Text:
        t = tk.Text(ust, wrap="word", relief="flat", background="#ffffff", padx=10, pady=8)
        t.tag_configure("baslik", font=("TkDefaultFont", 11, "bold"), spacing3=4)
        t.tag_configure("TAMAM", foreground="#15803d")
        t.tag_configure("DİKKAT", foreground="#b45309")
        t.tag_configure("İHLAL", foreground="#b91c1c")
        return t

    def _kur_uyarilar(self) -> None:
        sayfa = ttk.Frame(self.sekmeler, padding=8)
        self.sekmeler.add(sayfa, text="Uyarılar")
        self.uyari_metni = self._metin_kutusu(sayfa)
        self.uyari_metni.pack(fill="both", expand=True)

    def _kur_ozet(self) -> None:
        sayfa = ttk.Frame(self.sekmeler, padding=8)
        self.sekmeler.add(sayfa, text="Özet")
        ust = ttk.Frame(sayfa)
        ust.pack(fill="both", expand=True)
        self.v_ozet = VeriTablosu(ust, 14)
        self.v_ozet.pack(side="left", fill="both", expand=True)
        self.v_siparis = VeriTablosu(ust, 14)
        self.v_siparis.pack(side="left", fill="both", expand=True, padx=(8, 0))
        alt = ttk.Frame(sayfa)
        alt.pack(fill="both", expand=True, pady=(8, 0))
        self.v_tahsis = VeriTablosu(alt, 10)
        self.v_tahsis.pack(side="left", fill="both", expand=True)
        self.v_arama = VeriTablosu(alt, 10)
        self.v_arama.pack(side="left", fill="both", expand=True, padx=(8, 0))

    def _kur_sema(self, ad: str, gunluk: bool) -> SahneTuvali:
        sayfa = ttk.Frame(self.sekmeler, padding=8)
        self.sekmeler.add(sayfa, text=ad)
        ust = ttk.Frame(sayfa)
        ust.pack(fill="x", pady=(0, 6))
        v_atolye = tk.StringVar(value=self.fabrika.atolyeler[-1])
        v_zaman = tk.StringVar()
        ttk.Label(ust, text="Atölye").pack(side="left")
        cb_a = ttk.Combobox(ust, textvariable=v_atolye, values=self.fabrika.atolyeler,
                            state="readonly", width=30)
        cb_a.pack(side="left", padx=(4, 12))
        ttk.Label(ust, text="Gün" if gunluk else "Hafta").pack(side="left")
        cb_z = ttk.Combobox(ust, textvariable=v_zaman, state="readonly", width=16)
        cb_z.pack(side="left", padx=4)
        tuval = SahneTuvali(sayfa)
        tuval.pack(fill="both", expand=True)

        def secenekler() -> List[str]:
            if not self.plan:
                return []
            if gunluk:
                return [tarih_yaz(g) for g in sm.gunler(self.emirler, v_atolye.get())]
            return [tarih_yaz(h) for h in
                    sm.haftalar([r for r in self.emirler if r.atolye == v_atolye.get()])]

        def yenile(*_):
            if not self.plan:
                tuval.goster(None)
                return
            liste = secenekler()
            cb_z.configure(values=liste)
            if v_zaman.get() not in liste:
                v_zaman.set(liste[0] if liste else "")
            if not v_zaman.get():
                tuval.goster(None)
                return
            g = tarih_oku(v_zaman.get())
            sahne = (sm.gun_plani(self.plan, self.emirler, v_atolye.get(), g) if gunluk
                     else sm.hafta_plani(self.plan, self.emirler, v_atolye.get(), g))
            tuval.goster(sahne)

        def kaydir(adim: int) -> None:
            liste = list(cb_z.cget("values"))
            if v_zaman.get() in liste:
                i = max(0, min(len(liste) - 1, liste.index(v_zaman.get()) + adim))
                v_zaman.set(liste[i])
                yenile()

        ttk.Button(ust, text="◀", width=3, command=lambda: kaydir(-1)).pack(side="left")
        ttk.Button(ust, text="▶", width=3, command=lambda: kaydir(1)).pack(side="left", padx=2)
        cb_a.bind("<<ComboboxSelected>>", yenile)
        cb_z.bind("<<ComboboxSelected>>", yenile)
        tuval.yenile = yenile                           # type: ignore[attr-defined]
        tuval.goster(None)
        return tuval

    def _kur_genel(self) -> None:
        sayfa = ttk.Frame(self.sekmeler, padding=8)
        self.sekmeler.add(sayfa, text="Overview")
        self.tuval_genel = SahneTuvali(sayfa)
        self.tuval_genel.pack(fill="both", expand=True)
        self.tuval_genel.goster(None)

    def _kur_is_emirleri(self) -> None:
        sayfa = ttk.Frame(self.sekmeler, padding=8)
        self.sekmeler.add(sayfa, text="İş emirleri")
        ust = ttk.Frame(sayfa)
        ust.pack(fill="x", pady=(0, 6))
        self.v_ie_atolye = tk.StringVar(value="(hepsi)")
        self.v_ie_personel = tk.StringVar(value="(hepsi)")
        self.v_ie_siparis = tk.StringVar(value="")
        ttk.Label(ust, text="Atölye").pack(side="left")
        self.cb_ie_atolye = ttk.Combobox(ust, textvariable=self.v_ie_atolye, state="readonly",
                                         width=28, values=["(hepsi)"] + self.fabrika.atolyeler)
        self.cb_ie_atolye.pack(side="left", padx=(4, 10))
        ttk.Label(ust, text="Personel").pack(side="left")
        self.cb_ie_personel = ttk.Combobox(ust, textvariable=self.v_ie_personel,
                                           state="readonly", width=12)
        self.cb_ie_personel.pack(side="left", padx=(4, 10))
        ttk.Label(ust, text="Sipariş içerir").pack(side="left")
        ttk.Entry(ust, textvariable=self.v_ie_siparis, width=12).pack(side="left", padx=4)
        ttk.Button(ust, text="Süz", command=self._is_emirlerini_goster).pack(side="left", padx=4)
        ttk.Button(ust, text="CSV kaydet…", command=self._is_emri_csv).pack(side="right")
        for cb in (self.cb_ie_atolye, self.cb_ie_personel):
            cb.bind("<<ComboboxSelected>>", lambda _: self._is_emirlerini_goster())
        self.v_is_emri = VeriTablosu(sayfa, 24)
        self.v_is_emri.pack(fill="both", expand=True)

    def _kur_defter(self) -> None:
        sayfa = ttk.Frame(self.sekmeler, padding=8)
        self.sekmeler.add(sayfa, text="Personel ve defter")
        ust = ttk.LabelFrame(sayfa, text="Bu plandaki personel yükü", padding=6)
        ust.pack(fill="both", expand=True)
        self.v_personel_ozet = VeriTablosu(ust, 10)
        self.v_personel_ozet.pack(fill="both", expand=True)
        alt = ttk.LabelFrame(sayfa,
                             text=f"Yıllık fazla çalışma defteri — {defter.varsayilan_yol()}",
                             padding=6)
        alt.pack(fill="both", expand=True, pady=(8, 0))
        arac = ttk.Frame(alt)
        arac.pack(fill="x")
        self.v_yil = tk.IntVar(value=date.today().year)
        ttk.Label(arac, text="Yıl").pack(side="left")
        ttk.Spinbox(arac, from_=2000, to=2100, textvariable=self.v_yil, width=6,
                    command=self._defteri_goster).pack(side="left", padx=4)
        ttk.Button(arac, text="Planı deftere işle", command=self._deftere_isle).pack(side="left",
                                                                                     padx=6)
        ttk.Button(arac, text="Yılı sıfırla", command=self._yili_sifirla).pack(side="left")
        self.v_eski = tk.StringVar()
        self.v_yeni = tk.StringVar()
        ttk.Label(arac, text="   Bakiye taşı:").pack(side="left")
        ttk.Entry(arac, textvariable=self.v_eski, width=10).pack(side="left", padx=2)
        ttk.Label(arac, text="→").pack(side="left")
        ttk.Entry(arac, textvariable=self.v_yeni, width=10).pack(side="left", padx=2)
        ttk.Button(arac, text="Taşı", command=self._bakiye_tasi).pack(side="left", padx=4)
        ic = ttk.Frame(alt)
        ic.pack(fill="both", expand=True, pady=(6, 0))
        self.v_bakiye = VeriTablosu(ic, 8)
        self.v_bakiye.pack(side="left", fill="both", expand=True)
        self.v_hareket = VeriTablosu(ic, 8)
        self.v_hareket.pack(side="left", fill="both", expand=True, padx=(8, 0))

    def _kur_tablolar(self) -> None:
        sayfa = ttk.Frame(self.sekmeler, padding=8)
        self.sekmeler.add(sayfa, text="Tablolar")
        self._tablo_kaynaklari: Dict[str, Callable[[Plan], list]] = {
            "Kaynak kullanımı": an.kaynak_kullanimi,
            "Makine dengeleme (P||Cmax)": an.dengeleme_tablosu,
            "Günlük çıkış": an.gunluk_cikis,
            "Günlük personel": an.gunluk_personel,
            "Ayar (değişim) listesi": an.ayar_tablosu,
            "Constraint analizi": an.kisit_tablosu,
            "Ek mesai özeti": an.ek_mesai_ozeti,
            "Görevlendirmeler": an.gorev_tablosu,
            "Atanamayan vardiyalar": an.atanamayan_tablosu,
        }
        ust = ttk.Frame(sayfa)
        ust.pack(fill="x", pady=(0, 6))
        self.v_tablo = tk.StringVar(value=next(iter(self._tablo_kaynaklari)))
        cb = ttk.Combobox(ust, textvariable=self.v_tablo, state="readonly", width=32,
                          values=list(self._tablo_kaynaklari))
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", lambda _: self._tabloyu_goster())
        ttk.Button(ust, text="Bütün tabloları XLSX kaydet…",
                   command=self._xlsx_kaydet).pack(side="right")
        self.v_genel_tablo = VeriTablosu(sayfa, 24)
        self.v_genel_tablo.pack(fill="both", expand=True)

    def _kur_cikti(self) -> None:
        sayfa = ttk.Frame(self.sekmeler, padding=12)
        self.sekmeler.add(sayfa, text="Çıktı")
        ttk.Label(sayfa, text="Çıktı paketi", style="Baslik.TLabel").pack(anchor="w")
        ttk.Label(sayfa, foreground="#57534e", justify="left", text=(
            "Overview, her hafta ve atölye için haftalık (A3) ve günlük (A4) planlar, "
            "personel kartları, plan raporu, bütün tablolar (XLSX) ve iş emirleri (CSV).\n"
            "PDF için bilgisayardaki Edge/Chrome kullanılır; bulunamazsa HTML bırakılır.")
        ).pack(anchor="w", pady=(2, 10))
        satir = ttk.Frame(sayfa)
        satir.pack(fill="x")
        varsayilan = Path.home() / "Documents"
        self.v_cikti = tk.StringVar(value=str((varsayilan if varsayilan.exists()
                                               else Path.home()) / "Ciktilar"))
        ttk.Entry(satir, textvariable=self.v_cikti, width=70).pack(side="left")
        ttk.Button(satir, text="Seç…", command=lambda: self.v_cikti.set(
            filedialog.askdirectory() or self.v_cikti.get())).pack(side="left", padx=4)
        self.v_pdf = tk.BooleanVar(value=True)
        ttk.Checkbutton(sayfa, text="PDF üret", variable=self.v_pdf).pack(anchor="w", pady=6)
        ttk.Button(sayfa, text="Çıktı paketini oluştur", style="Vurgu.TButton",
                   command=self.cikti_paketi_dugmesi).pack(anchor="w")
        self.cikti_kaydi = tk.Text(sayfa, height=12, relief="flat", background="#fafaf9")
        self.cikti_kaydi.pack(fill="both", expand=True, pady=(10, 0))
        self._son_paket: Optional[Path] = None
        ttk.Button(sayfa, text="Son paketin klasörünü aç",
                   command=lambda: self._son_paket and klasoru_ac(self._son_paket)
                   ).pack(anchor="w", pady=6)

    # ================================================================ iş parçacığı
    def _arka_planda(self, ad: str, is_: Callable[[Callable[[float, str], None]], object],
                     bitince: Callable[[object], None]) -> None:
        if self._calisiyor:
            return
        self._calisiyor = True
        self._iptal.clear()
        self.d_hesapla.configure(state="disabled")
        self.d_paket.configure(state="disabled")
        self.d_iptal.configure(state="normal")
        self.ilerleme["value"] = 0

        def ilerleme(oran: float, mesaj: str) -> None:
            if self._iptal.is_set():
                raise Durduruldu()
            self._kuyruk.put(("ilerleme", oran, mesaj))

        def pencereyi_ac() -> None:
            try:
                sonuc = is_(ilerleme)
                self._kuyruk.put(("bitti", bitince, sonuc))
            except Durduruldu:
                self._kuyruk.put(("iptal", ad, None))
            except TanimHatasi as h:
                self._kuyruk.put(("hata", ad, str(h)))
            except Exception:                           # noqa: BLE001
                self._kuyruk.put(("hata", ad, traceback.format_exc()))

        threading.Thread(target=pencereyi_ac, daemon=True).start()

    def _kuyrugu_isle(self) -> None:
        try:
            while True:
                tur, a, b = (lambda x: (x[0], x[1], x[2]))(self._kuyruk.get_nowait())
                if tur == "ilerleme":
                    self.ilerleme["value"] = 100 * a
                    self.ilerleme_yazi.configure(text=b)
                    continue
                self._calisiyor = False
                self.d_hesapla.configure(state="normal")
                self.d_paket.configure(state="normal")
                self.d_iptal.configure(state="disabled")
                if tur == "bitti":
                    self.ilerleme["value"] = 100
                    a(b)
                elif tur == "iptal":
                    self.ilerleme_yazi.configure(text="İptal edildi.")
                else:
                    self.ilerleme_yazi.configure(text="Hata.")
                    messagebox.showerror(f"{a} başarısız", b)
        except queue.Empty:
            pass
        self.after(100, self._kuyrugu_isle)

    def iptal(self) -> None:
        self._iptal.set()

    # ================================================================ eylemler
    def hesapla(self) -> None:
        try:
            s = self.senaryoyu_oku()
        except (TanimHatasi, ValueError) as h:
            messagebox.showerror("Girdi hatası", str(h))
            return
        if not s.siparisler:
            messagebox.showwarning("Sipariş yok", "En az bir sipariş girin.")
            return
        try:
            acilis = defter.bakiyeler(s.baslangic.year, s.personel)
        except Exception:                               # noqa: BLE001
            acilis = {}

        def is_(ilerleme):
            plan = plan_olustur(self.fabrika, s.siparisler, s.baslangic, s.ek_mesailer, s.ayarlar,
                                s.personel, acilis, ilerleme)
            ilerleme(1.0, "İş emirleri hazırlanıyor...")
            return plan, is_emirleri(plan)

        self._arka_planda("Hesap", is_, self._plan_geldi)

    def _plan_geldi(self, sonuc) -> None:
        self.plan, self.emirler = sonuc
        p = self.plan
        renk = "#15803d" if p.termine_uygun and p.mevzuata_uygun else "#b91c1c"
        self.sonuc_yazi.configure(
            foreground=renk,
            text=(f"Bitiş {p.bitis_tarihi:%d.%m.%Y} · "
                  + ("termine uygun" if p.termine_uygun else
                     f"{p.en_buyuk_gecikme:.1f} gün gecikme")
                  + ("" if p.mevzuata_uygun else " · atanamayan vardiya var")))
        self.ilerleme_yazi.configure(text="Tamamlandı.")
        self.v_yil.set(p.baslangic.year)
        self._sonuclari_goster()
        self.sekmeler.select(1)
        self._durum(f"Plan hazır: K={p.parti_sayisi}, r={p.ramp:g}, {p.ayar_sayisi} ayar, "
                    f"{len(self.emirler)} iş emri satırı.")

    def _sonuclari_goster(self) -> None:
        p = self.plan
        if not p:
            return
        t = self.uyari_metni
        t.delete("1.0", "end")
        t.insert("end", "PANO A · YASAL DURUM\n", "baslik")
        for x in mevzuat_panosu(p):
            t.insert("end", f"  {x}\n", x.durum)
        t.insert("end", "\nPANO B · CAPACITY CHECK\n", "baslik")
        gecikenler = geciken_siparisler(p)
        if not gecikenler:
            t.insert("end", f"  {SEMBOL['TAMAM']} Bütün siparişler termine yetişiyor.\n", "TAMAM")
        for g in gecikenler:
            t.insert("end", f"  {SEMBOL['İHLAL']} {g.kod}: {g.gecikme_gun:.1f} gün geç "
                     f"(termin {g.termin:%d.%m.%Y})\n", "İHLAL")
            if g.kritik and g.kritik.acik > 1e-3:
                t.insert("end", f"      Kritik grup {g.kritik.grup}: günde +{g.kritik.acik:.2f} "
                         f"saat gerekli\n")
            elif g.kritik:
                t.insert("end", "      Kararlı kapasite yeterli; gecikme ayar kayıpları ve "
                                "hattın dolma süresinden.\n")
        t.insert("end", "\n  Grup     Gerekli   Mevcut    Açık     Kullanım\n")
        for h in grup_aciklari(p)[:12]:
            t.insert("end", f"  {h.grup:8s} {h.gerekli_saat:6.2f}   {h.mevcut_saat:6.2f}   "
                     f"{h.acik:+6.2f}    %{100 * h.kullanim:.0f}\n",
                     "İHLAL" if h.acik > 1e-3 else "")
        t.insert("end", "\nUYARILAR\n", "baslik")
        for u in p.uyarilar:
            t.insert("end", f"  • {u}\n")

        self.v_ozet.goster([{"Gösterge": k, "Değer": v} for k, v in an.gostergeler(p).items()])
        self.v_siparis.goster(an.siparis_tablosu(p), lambda r: r["Durum"] != "Zamanında")
        self.v_tahsis.goster(an.tahsis_tablosu(p), lambda r: r["Not"] == "DARBOĞAZ")
        self.v_arama.goster(p.arama, lambda r: (r["Parti sayısı (K)"], r["Rampa (r)"])
                            == (p.parti_sayisi, p.ramp))
        for tuval in (self.tuval_gunluk, self.tuval_haftalik):
            tuval.yenile()
        self.tuval_genel.goster(gb.genel_bakis(p))
        kisiler = sorted({r.personel for r in self.emirler})
        self.cb_ie_personel.configure(values=["(hepsi)"] + kisiler)
        self._is_emirlerini_goster()
        self.v_personel_ozet.goster(an.personel_ozeti(p))
        self._defteri_goster()
        self._tabloyu_goster()

    def _is_emirlerini_goster(self) -> None:
        if not self.plan:
            return
        a = self.v_ie_atolye.get()
        k = self.v_ie_personel.get()
        secili = suz(self.emirler, atolye=None if a == "(hepsi)" else a,
                     personel=None if k == "(hepsi)" else k,
                     siparis=self.v_ie_siparis.get().strip() or None)
        self.v_is_emri.goster(tablo(self.plan, secili), lambda r: r["Personel"] == ATANAMADI)

    def _is_emri_csv(self) -> None:
        if not self.v_is_emri.veri:
            return
        yol = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if yol:
            tb.csv_yaz(yol, self.v_is_emri.veri, BASLIKLAR)
            self._durum(f"Kaydedildi: {yol}")

    def _tabloyu_goster(self) -> None:
        if self.plan:
            self.v_genel_tablo.goster(self._tablo_kaynaklari[self.v_tablo.get()](self.plan))

    def _xlsx_kaydet(self) -> None:
        if not self.plan:
            return
        yol = filedialog.asksaveasfilename(defaultextension=".xlsx",
                                           filetypes=[("Excel çalışma kitabı", "*.xlsx")])
        if yol:
            tb.plan_calisma_kitabi(self.plan, yol, self.emirler)
            self._durum(f"Kaydedildi: {yol}")

    # ---------------------------------------------------------------- defter
    def _defteri_goster(self) -> None:
        try:
            yil = int(self.v_yil.get())
            kadro = self._personel_listesi()
            bakiye = defter.bakiyeler(yil)
            tavan = self.fabrika.mevzuat.yillik_fazla_calisma_tavani
            adlar = sorted(set(kadro) | set(bakiye))
            self.v_bakiye.goster([{"Personel": p, "Bakiye (sa)": round(bakiye.get(p, 0.0), 1),
                                   "Kalan hak (sa)": round(tavan - bakiye.get(p, 0.0), 1),
                                   "Kadroda": EVET if p in kadro else "HAYIR"} for p in adlar],
                                 lambda r: r["Kadroda"] != EVET and r["Bakiye (sa)"] > 0)
            self.v_hareket.goster([{"Zaman": z, "Personel": p, "Yıl": y, "Saat": round(s, 2),
                                    "Açıklama": a} for z, p, y, s, a in defter.son_hareketler()])
        except Exception as h:                          # noqa: BLE001
            self._durum(f"Defter okunamadı: {h}")

    def _deftere_isle(self) -> None:
        p = self.plan
        if not p or not p.atama:
            messagebox.showinfo("Defter", "Önce personel denetimi açık bir plan hesaplayın.")
            return
        yillik: Dict[int, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
        for g in p.atama.gorevler:
            yillik[g.tarih.year][g.personel] += g.fazla_mesai
        toplam = sum(sum(v.values()) for v in yillik.values())
        if not messagebox.askyesno("Deftere işle", f"Bu plandaki {toplam:.1f} saat fazla çalışma "
                                   f"deftere eklenecek. Aynı planı iki kez işlemeyin. Devam?"):
            return
        aciklama = f"Plan {p.baslangic:%d.%m.%Y} ({p.urun_sayisi} adet)"
        for yil, saatler in yillik.items():
            defter.isle(yil, dict(saatler), aciklama)
        self._defteri_goster()
        self._durum("Plan deftere işlendi.")

    def _yili_sifirla(self) -> None:
        yil = int(self.v_yil.get())
        if messagebox.askyesno("Yılı sıfırla",
                               f"{yil} yılının bütün bakiyeleri silinecek. Emin misiniz?"):
            defter.yil_sil(yil)
            self._defteri_goster()

    def _bakiye_tasi(self) -> None:
        eski, yeni = self.v_eski.get().strip(), self.v_yeni.get().strip()
        if eski and yeni:
            saat = defter.ad_degistir(eski, yeni, int(self.v_yil.get()))
            self._defteri_goster()
            self._durum(f"{eski} → {yeni}: {saat:.1f} saat taşındı.")

    # ---------------------------------------------------------------- diğer
    def cikti_paketi_dugmesi(self) -> None:
        if not self.plan:
            messagebox.showinfo("Çıktı", "Önce bir plan hesaplayın.")
            return
        from rapor.paket import paket_olustur
        kok = Path(self.v_cikti.get())
        plan = self.plan

        def is_(ilerleme):
            return paket_olustur(plan, kok, pdf=self.v_pdf.get(), ilerleme=ilerleme)

        def bitti(sonuc) -> None:
            klasor, ozet = sonuc
            self._son_paket = klasor
            self.cikti_kaydi.insert("end", f"{datetime.now():%H:%M:%S}  {klasor}\n"
                                    f"          {ozet['belge']} belge · {ozet['pdf']} PDF · "
                                    f"{ozet['html']} HTML · tarayıcı: "
                                    f"{ozet['tarayici'] or 'bulunamadı'}\n")
            self.ilerleme_yazi.configure(text="Paket hazır.")
            if messagebox.askyesno("Çıktı paketi hazır", f"{klasor}\n\nKlasör açılsın mı?"):
                klasoru_ac(klasor)

        self.sekmeler.select(len(self.sekmeler.tabs()) - 1)
        self._arka_planda("Çıktı paketi", is_, bitti)

    def duzenleri_karsilastir(self) -> None:
        try:
            s = self.senaryoyu_oku()
        except (TanimHatasi, ValueError) as h:
            messagebox.showerror("Girdi hatası", str(h))
            return

        def is_(ilerleme):
            return duzen_karsilastir(self.fabrika, s.siparisler, s.baslangic, s.ek_mesailer,
                                     s.ayarlar, s.personel, ilerleme)

        def bitti(satirlar) -> None:
            pen = tk.Toplevel(self)
            pen.title("Çalışma düzeni karşılaştırması (bilgi amaçlı, uygulanmaz)")
            pen.geometry("900x260")
            v = VeriTablosu(pen, 6)
            v.pack(fill="both", expand=True, padx=8, pady=8)
            v.goster(satirlar, lambda r: r.get("Termine uygun") == "HAYIR")
            self.ilerleme_yazi.configure(text="Karşılaştırma hazır.")

        self._arka_planda("Karşılaştırma", is_, bitti)

    def hakkinda(self) -> None:
        messagebox.showinfo("Hakkında", (
            f"Üretim Çizelgeleme {SURUM}\n\n"
            "Endüstri mühendisliği yöntemleriyle üretim çizelgeleme ve personel tahsisi:\n"
            "min-maks personel tahsisi, P||Cmax dengeleme (LPT + local search), parti/kampanya "
            "planı, takım kısıtlı varyant planı, EDD + heijunka sıralama, kaynak takvimli akış "
            "hesabı ve yasal sınırlı personel çizelgeleme.\n\n"
            "Örnek fabrika verileri TAMAMEN HAYALİDİR."))

    def _durum(self, metin: str) -> None:
        self.durum.configure(text=metin)


def pencereyi_ac(fabrika: Optional[str] = None, senaryo: Optional[str] = None) -> None:
    Uygulama(fabrika, senaryo).mainloop()
