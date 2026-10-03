"""
Sahne → Tkinter Canvas. Yazdırılan SVG ile aynı çizim, ekranda.

Fare tekerleği kaydırır, Ctrl + tekerlek (ya da +/− düğmeleri) yakınlaştırır.
Bir çubuğun üzerine gelince ayrıntısı alt satırda görünür.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk
from typing import Dict, Optional

from rapor.cizim import Sahne

_HIZA = {"start": "sw", "middle": "s", "end": "se"}


def _aile(kok: tk.Misc) -> str:
    mevcut = set(tkfont.families(kok))
    for ad in ("Segoe UI", "DejaVu Sans", "Helvetica", "Arial"):
        if ad in mevcut:
            return ad
    return "TkDefaultFont"


class SahneTuvali(ttk.Frame):
    def __init__(self, ust: tk.Misc, **kw):
        super().__init__(ust, **kw)
        self.sahne: Optional[Sahne] = None
        self.olcek = 1.0
        self._ipuclari: Dict[int, str] = {}
        arac = ttk.Frame(self)
        arac.pack(fill="x")
        ttk.Button(arac, text="−", width=3,
                   command=lambda: self.yakinlas(1 / 1.2)).pack(side="left")
        ttk.Button(arac, text="+", width=3, command=lambda: self.yakinlas(1.2)).pack(side="left")
        ttk.Button(arac, text="Sığdır", command=self.uydur).pack(side="left", padx=4)
        self.bilgi = ttk.Label(arac, text="", foreground="#57534e")
        self.bilgi.pack(side="left", padx=8)
        govde = ttk.Frame(self)
        govde.pack(fill="both", expand=True)
        self.tuval = tk.Canvas(govde, background="#e7e5e4", highlightthickness=0)
        ys = ttk.Scrollbar(govde, orient="vertical", command=self.tuval.yview)
        xs = ttk.Scrollbar(govde, orient="horizontal", command=self.tuval.xview)
        self.tuval.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        self.tuval.grid(row=0, column=0, sticky="nsew")
        ys.grid(row=0, column=1, sticky="ns")
        xs.grid(row=1, column=0, sticky="ew")
        govde.rowconfigure(0, weight=1)
        govde.columnconfigure(0, weight=1)
        self.aile = _aile(self)
        self.tuval.bind("<MouseWheel>", self._teker)
        self.tuval.bind("<Button-4>", lambda e: self.tuval.yview_scroll(-3, "units"))
        self.tuval.bind("<Button-5>", lambda e: self.tuval.yview_scroll(3, "units"))
        self.tuval.bind("<Control-MouseWheel>", self._ctrl_teker)
        self.tuval.bind("<Motion>", self._uzerinde)

    # ---------------------------------------------------------------- olaylar
    def _teker(self, olay) -> None:
        self.tuval.yview_scroll(-1 if olay.delta > 0 else 1, "units")

    def _ctrl_teker(self, olay) -> None:
        self.yakinlas(1.1 if olay.delta > 0 else 1 / 1.1)

    def _uzerinde(self, olay) -> None:
        x, y = self.tuval.canvasx(olay.x), self.tuval.canvasy(olay.y)
        for oge in reversed(self.tuval.find_overlapping(x, y, x, y)):
            if oge in self._ipuclari:
                self.bilgi.configure(text=self._ipuclari[oge])
                return
        self.bilgi.configure(text="")

    # ---------------------------------------------------------------- çizim
    def goster(self, sahne: Optional[Sahne]) -> None:
        self.sahne = sahne
        self.ciz()

    def yakinlas(self, oran: float) -> None:
        self.olcek = max(0.3, min(3.0, self.olcek * oran))
        self.ciz()

    def uydur(self) -> None:
        if self.sahne:
            w = max(200, self.tuval.winfo_width() - 24)
            self.olcek = max(0.3, min(3.0, w / self.sahne.genislik))
            self.ciz()

    def ciz(self) -> None:
        t = self.tuval
        t.delete("all")
        self._ipuclari.clear()
        if not self.sahne:
            t.create_text(20, 20, anchor="nw", text="Önce HESAPLA'ya basın.",
                          font=(self.aile, 12), fill="#57534e")
            return
        k = self.olcek
        ox = oy = 12
        t.create_rectangle(ox, oy, ox + self.sahne.genislik * k, oy + self.sahne.yukseklik * k,
                           fill="#ffffff", outline="#a8a29e")
        for o in self.sahne.ogeler:
            if o.tur == "dik":
                x0, y0 = ox + o.x * k, oy + o.y * k
                x1, y1 = x0 + max(0.5, o.w * k), y0 + max(0.5, o.h * k)
                kimlik = t.create_rectangle(x0, y0, x1, y1, fill=o.dolgu or "",
                                            outline=o.renk or "", width=o.kalinlik if o.renk else 0)
                if o.tarama:
                    t.create_rectangle(x0, y0, x1, y1, fill="#ffffff", stipple="gray25",
                                       outline="")
                if o.ipucu:
                    self._ipuclari[kimlik] = o.ipucu
            elif o.tur == "cizgi":
                t.create_line(ox + o.x * k, oy + o.y * k, ox + (o.x + o.w) * k,
                              oy + (o.y + o.h) * k, fill=o.renk, width=max(1, o.kalinlik * k),
                              dash=(4, 3) if o.kesikli else None)
            else:
                boyut = max(5, int(round(o.boyut * k * 0.78)))
                t.create_text(ox + o.x * k, oy + o.y * k + 2 * k, text=o.metin,
                              anchor=_HIZA.get(o.hiza, "sw"), fill=o.renk,
                              font=(self.aile, boyut, "bold" if o.kalin else "normal"))
        t.configure(scrollregion=(0, 0, self.sahne.genislik * k + 24,
                                  self.sahne.yukseklik * k + 24))
