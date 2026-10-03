"""
Tablo bileşenleri (ttk.Treeview üzerine).

* ``DuzenlenebilirTablo``: çift tıkla hücre düzenleme; seçenekli sütunlarda
  açılır liste. Satır ekleme/silme düğmeleri.
* ``VeriTablosu``: salt okunur ``List[Dict]`` gösterimi; başlığa tıklayınca sıralar.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Dict, List, Optional, Sequence


class DuzenlenebilirTablo(ttk.Frame):
    def __init__(self, ust: tk.Misc, sutunlar: Sequence[str],
                 secenekler: Optional[Dict[str, Callable[[], Sequence[str]]]] = None,
                 genislikler: Optional[Dict[str, int]] = None,
                 varsayilan: Optional[Callable[[], Sequence[str]]] = None,
                 degisti: Optional[Callable[[], None]] = None, **kw):
        super().__init__(ust, **kw)
        self.sutunlar = list(sutunlar)
        self.secenekler = secenekler or {}
        self.varsayilan = varsayilan
        self.degisti = degisti
        arac = ttk.Frame(self)
        arac.pack(fill="x", pady=(0, 4))
        ttk.Button(arac, text="＋ Satır ekle", command=self.satir_ekle).pack(side="left")
        ttk.Button(arac, text="－ Seçiliyi sil", command=self.secileni_sil).pack(side="left", padx=4)
        ttk.Label(arac, text="Hücreyi değiştirmek için çift tıklayın.",
                  foreground="#78716c").pack(side="left", padx=8)
        govde = ttk.Frame(self)
        govde.pack(fill="both", expand=True)
        self.agac = ttk.Treeview(govde, columns=self.sutunlar, show="headings",
                                 selectmode="extended", height=10)
        for s in self.sutunlar:
            self.agac.heading(s, text=s)
            self.agac.column(s, width=(genislikler or {}).get(s, 110), anchor="w")
        ys = ttk.Scrollbar(govde, orient="vertical", command=self.agac.yview)
        self.agac.configure(yscrollcommand=ys.set)
        self.agac.pack(side="left", fill="both", expand=True)
        ys.pack(side="right", fill="y")
        self.agac.bind("<Double-1>", self._duzenle)
        self._editor: Optional[tk.Widget] = None

    # ----------------------------------------------------------------- veri
    def satirlar(self) -> List[List[str]]:
        return [list(self.agac.item(i, "values")) for i in self.agac.get_children()]

    def doldur(self, satirlar: Sequence[Sequence[object]]) -> None:
        self.agac.delete(*self.agac.get_children())
        for s in satirlar:
            self.agac.insert("", "end", values=[str(x) for x in s])

    def satir_ekle(self, degerler: Optional[Sequence[object]] = None) -> None:
        if degerler is None:
            degerler = self.varsayilan() if self.varsayilan else [""] * len(self.sutunlar)
        self.agac.insert("", "end", values=[str(x) for x in degerler])
        self._bildir()

    def secileni_sil(self) -> None:
        for i in self.agac.selection():
            self.agac.delete(i)
        self._bildir()

    def _bildir(self) -> None:
        if self.degisti:
            self.degisti()

    # -------------------------------------------------------------- düzenleme
    def _duzenle(self, olay) -> None:
        satir = self.agac.identify_row(olay.y)
        sutun = self.agac.identify_column(olay.x)
        if not satir or not sutun:
            return
        j = int(sutun[1:]) - 1
        ad = self.sutunlar[j]
        x, y, w, h = self.agac.bbox(satir, sutun)
        deger = self.agac.item(satir, "values")[j]
        if ad in self.secenekler:
            ed = ttk.Combobox(self.agac, values=list(self.secenekler[ad]()), state="normal")
        else:
            ed = ttk.Entry(self.agac)
        ed.insert(0, deger)
        ed.place(x=x, y=y, width=w, height=h)
        ed.focus_set()
        if isinstance(ed, ttk.Entry) and not isinstance(ed, ttk.Combobox):
            ed.select_range(0, "end")

        def kaydet(_=None) -> None:
            yeni = list(self.agac.item(satir, "values"))
            yeni[j] = ed.get()
            self.agac.item(satir, values=yeni)
            ed.destroy()
            self._bildir()

        ed.bind("<Return>", kaydet)
        ed.bind("<Escape>", lambda _: ed.destroy())
        ed.bind("<FocusOut>", kaydet)
        if isinstance(ed, ttk.Combobox):
            ed.bind("<<ComboboxSelected>>", kaydet)


class VeriTablosu(ttk.Frame):
    def __init__(self, ust: tk.Misc, yukseklik: int = 12, **kw):
        super().__init__(ust, **kw)
        self.agac = ttk.Treeview(self, show="headings", height=yukseklik)
        ys = ttk.Scrollbar(self, orient="vertical", command=self.agac.yview)
        xs = ttk.Scrollbar(self, orient="horizontal", command=self.agac.xview)
        self.agac.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        self.agac.grid(row=0, column=0, sticky="nsew")
        ys.grid(row=0, column=1, sticky="ns")
        xs.grid(row=1, column=0, sticky="ew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.agac.tag_configure("vurgu", background="#fee2e2")
        self._veri: List[Dict] = []
        self._ters = False

    def goster(self, veri: Sequence[Dict], vurgula: Optional[Callable[[Dict], bool]] = None
               ) -> None:
        self._veri = list(veri)
        self._vurgula = vurgula
        sutunlar = list(self._veri[0]) if self._veri else ["(veri yok)"]
        self.agac.configure(columns=sutunlar)
        for s in sutunlar:
            self.agac.heading(s, text=s, command=lambda s=s: self._sirala(s))
            veri = max([0] + [len(str(r.get(s, ""))) for r in self._veri[:200]])
            genislik = max(60, 8 * veri + 12, 9 * len(str(s)) + 20)
            self.agac.column(s, width=min(380, genislik), anchor="w", stretch=False)
        self._yaz()

    def _yaz(self) -> None:
        self.agac.delete(*self.agac.get_children())
        sutunlar = self.agac["columns"]
        for r in self._veri:
            etiket = ("vurgu",) if self._vurgula and self._vurgula(r) else ()
            self.agac.insert("", "end", values=[r.get(s, "") for s in sutunlar], tags=etiket)

    def _sirala(self, sutun: str) -> None:
        def anahtar(r):
            v = r.get(sutun, "")
            return (0, v) if isinstance(v, (int, float)) else (1, str(v))
        self._ters = not self._ters
        self._veri.sort(key=anahtar, reverse=self._ters)
        self._yaz()

    @property
    def veri(self) -> List[Dict]:
        return self._veri
