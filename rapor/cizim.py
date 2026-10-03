"""
Çizim ilkelleri — tek sahne, iki çıktı.

Şemalar önce araçtan bağımsız bir ``Sahne`` nesnesine (dikdörtgen, çizgi, yazı)
çizilir. Aynı sahne:

  * ``svg()`` ile yazdırılabilir SVG/HTML'e (PDF paketi),
  * ``arayuz/tuval.py`` ile Tkinter Canvas'a (masaüstü önizleme)

dönüştürülür. Böylece ekranda görülen ile kâğıda basılan birebir aynıdır ve
ek grafik kütüphanesi gerekmez.

Koordinatlar CSS pikselidir (96 dpi): A4 yatay 1123×794, A3 yatay 1587×1123.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from html import escape
from typing import List, Optional, Sequence

A4_YATAY = (1123, 794)
A3_YATAY = (1587, 1123)

YAZI_AILESI = "Segoe UI, Roboto, Helvetica, Arial, sans-serif"

# Renkler — atölyeler akış sırasına göre bu listeden renk alır
ATOLYE_RENKLERI = ("#0f766e", "#4338ca", "#b45309", "#be185d", "#15803d", "#7c3aed")
AYAR_RENGI = "#3f3f46"
MOLA_RENGI = "#e7e5e4"
MESAI_RENGI = "#fef3c7"
KAPALI_RENGI = "#f5f5f4"
IZGARA = "#d6d3d1"
KOYU = "#1c1917"
GRI = "#78716c"
IYI = "#15803d"
KOTU = "#b91c1c"


@dataclass
class Oge:
    tur: str                       # "dik" | "cizgi" | "yazi"
    x: float
    y: float
    w: float = 0.0
    h: float = 0.0
    dolgu: Optional[str] = None
    renk: Optional[str] = None
    kalinlik: float = 1.0
    metin: str = ""
    boyut: float = 11.0
    hiza: str = "start"            # start | middle | end
    kalin: bool = False
    tarama: bool = False
    kesikli: bool = False
    ipucu: str = ""


@dataclass
class Sahne:
    genislik: float
    yukseklik: float
    ogeler: List[Oge] = field(default_factory=list)
    baslik: str = ""

    def dik(self, x, y, w, h, dolgu=None, renk=None, kalinlik=1.0, tarama=False, ipucu=""):
        self.ogeler.append(Oge("dik", x, y, w, h, dolgu, renk, kalinlik,
                               tarama=tarama, ipucu=ipucu))

    def cizgi(self, x1, y1, x2, y2, renk=IZGARA, kalinlik=1.0, kesikli=False):
        self.ogeler.append(Oge("cizgi", x1, y1, x2 - x1, y2 - y1, renk=renk,
                               kalinlik=kalinlik, kesikli=kesikli))

    def yazi(self, x, y, metin, boyut=11.0, renk=KOYU, hiza="start", kalin=False):
        self.ogeler.append(Oge("yazi", x, y, metin=str(metin), boyut=boyut, renk=renk,
                               hiza=hiza, kalin=kalin))

    # ------------------------------------------------------------------ SVG
    def svg(self) -> str:
        p = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.genislik:.0f}" '
             f'height="{self.yukseklik:.0f}" viewBox="0 0 {self.genislik:.0f} '
             f'{self.yukseklik:.0f}" font-family="{YAZI_AILESI}">',
             '<defs><pattern id="tarama" width="6" height="6" patternUnits="userSpaceOnUse" '
             'patternTransform="rotate(45)"><rect width="6" height="6" fill="#ffffff" '
             'fill-opacity="0"/><line x1="0" y1="0" x2="0" y2="6" stroke="#ffffff" '
             'stroke-width="2" stroke-opacity="0.45"/></pattern></defs>',
             '<rect width="100%" height="100%" fill="#ffffff"/>']
        for o in self.ogeler:
            if o.tur == "dik":
                stil = f'fill="{o.dolgu or "none"}"'
                if o.renk:
                    stil += f' stroke="{o.renk}" stroke-width="{o.kalinlik:g}"'
                ipucu = f"<title>{escape(o.ipucu)}</title>" if o.ipucu else ""
                p.append(f'<rect x="{o.x:.1f}" y="{o.y:.1f}" width="{max(0, o.w):.1f}" '
                         f'height="{max(0, o.h):.1f}" {stil}>{ipucu}</rect>')
                if o.tarama:
                    p.append(f'<rect x="{o.x:.1f}" y="{o.y:.1f}" width="{max(0, o.w):.1f}" '
                             f'height="{max(0, o.h):.1f}" fill="url(#tarama)"/>')
            elif o.tur == "cizgi":
                kesik = ' stroke-dasharray="4 3"' if o.kesikli else ""
                p.append(f'<line x1="{o.x:.1f}" y1="{o.y:.1f}" x2="{o.x + o.w:.1f}" '
                         f'y2="{o.y + o.h:.1f}" stroke="{o.renk}" '
                         f'stroke-width="{o.kalinlik:g}"{kesik}/>')
            else:
                agirlik = ' font-weight="600"' if o.kalin else ""
                p.append(f'<text x="{o.x:.1f}" y="{o.y:.1f}" font-size="{o.boyut:g}" '
                         f'fill="{o.renk}" text-anchor="{o.hiza}"{agirlik}>'
                         f'{escape(o.metin)}</text>')
        p.append("</svg>")
        return "\n".join(p)


def metin_genisligi(metin: str, boyut: float) -> float:
    """Yaklaşık yazı genişliği (orantılı yazı tipleri için ortalama 0,56 em)."""
    return 0.56 * boyut * len(metin)


def uydur(metin: str, genislik: float, boyut: float) -> str:
    """Metni verilen genişliğe sığacak şekilde kısaltır ('…' ile)."""
    if metin_genisligi(metin, boyut) <= genislik:
        return metin
    n = int(genislik / (0.56 * boyut)) - 1
    return (metin[:max(0, n)] + "…") if n > 0 else ""


def html_belgesi(sahneler: Sequence[Sahne], baslik: str, kagit: str = "A4",
                 ek_html: str = "") -> str:
    """Sahneleri, her biri tam sayfa olacak şekilde yazdırılabilir HTML'e gömer."""
    sayfalar = "\n".join(f'<section class="sayfa">{s.svg()}</section>' for s in sahneler)
    w, h = {"A3": (420, 297), "A4": (297, 210)}.get(kagit, (297, 210))
    return f"""<!doctype html>
<html lang="tr"><head><meta charset="utf-8">
<title>{escape(baslik)}</title>
<style>
  @page {{ size: {kagit} landscape; margin: 0; }}
  html, body {{ margin: 0; padding: 0; background: #ffffff; }}
  .sayfa {{ page-break-after: always; break-after: page; overflow: hidden;
            width: {w}mm; height: {h - 0.5}mm; }}
  .sayfa:last-child {{ page-break-after: auto; break-after: auto; }}
  svg {{ display: block; width: 100%; height: 100%; }}
  body {{ font-family: {YAZI_AILESI}; color: {KOYU}; }}
  table {{ border-collapse: collapse; font-size: 11px; }}
  th, td {{ border: 1px solid {IZGARA}; padding: 3px 6px; text-align: left; }}
  th {{ background: #f5f5f4; }}
  .liste {{ padding: 24px; }}
  @media screen {{ body {{ background: #e7e5e4; }} .sayfa {{ margin: 12px auto;
     box-shadow: 0 1px 4px rgba(0,0,0,.2); background: #fff; }} }}
</style></head>
<body>
{sayfalar}
{ek_html}
</body></html>"""


def tablo_html(basliklar: Sequence[str], satirlar: Sequence[Sequence[object]],
               baslik: str = "", aciklama: str = "") -> str:
    th = "".join(f"<th>{escape(str(b))}</th>" for b in basliklar)
    tr = "\n".join("<tr>" + "".join(f"<td>{escape(str(h))}</td>" for h in s) + "</tr>"
                   for s in satirlar)
    return (f'<section class="liste"><h2>{escape(baslik)}</h2>'
            f'<p>{escape(aciklama)}</p><table><thead><tr>{th}</tr></thead>'
            f'<tbody>{tr}</tbody></table></section>')


def atolye_rengi(atolyeler: Sequence[str], atolye: str) -> str:
    try:
        return ATOLYE_RENKLERI[list(atolyeler).index(atolye) % len(ATOLYE_RENKLERI)]
    except ValueError:
        return ATOLYE_RENKLERI[0]
