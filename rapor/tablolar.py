"""
Tablo dışa aktarımı — CSV ve XLSX (yalnız standart kütüphane).

XLSX bir ZIP arşividir (Office Open XML, ECMA-376). En küçük geçerli çalışma
kitabı beş parçadan oluşur: içerik türleri, paket ilişkileri, workbook, workbook
ilişkileri ve her sayfa için bir worksheet. Metinler "inline string" olarak
yazılır; böylece paylaşılan metin tablosuna gerek kalmaz. Excel, LibreOffice ve
Google E-Tablolar bu biçimi açar.
"""
from __future__ import annotations

import csv
import re
import zipfile
from pathlib import Path
from typing import Dict, List, Sequence, Tuple, Union
from xml.sax.saxutils import escape

Tablo = List[Dict[str, object]]


def csv_yaz(yol: Union[str, Path], tablo: Tablo, basliklar: Sequence[str] = ()) -> int:
    basliklar = list(basliklar) or (list(tablo[0]) if tablo else [])
    with open(yol, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(basliklar)
        for r in tablo:
            w.writerow([r.get(b, "") for b in basliklar])
    return len(tablo)


def _sutun_harfi(i: int) -> str:
    s = ""
    i += 1
    while i:
        i, k = divmod(i - 1, 26)
        s = chr(65 + k) + s
    return s


def _hucre(ref: str, deger: object, stil: int = 0) -> str:
    s = f' s="{stil}"' if stil else ""
    if isinstance(deger, bool):
        deger = "EVET" if deger else "HAYIR"
    if isinstance(deger, (int, float)) and deger == deger and abs(deger) != float("inf"):
        return f'<c r="{ref}"{s}><v>{deger}</v></c>'
    metin = escape("" if deger is None else str(deger))
    return f'<c r="{ref}"{s} t="inlineStr"><is><t xml:space="preserve">{metin}</t></is></c>'


def _sayfa_xml(tablo: Tablo) -> str:
    basliklar = list(tablo[0]) if tablo else ["(boş)"]
    genislik = [max([len(str(b))] + [len(str(r.get(b, ""))) for r in tablo[:300]])
                for b in basliklar]
    cols = "".join(f'<col min="{i + 1}" max="{i + 1}" width="{min(60, max(8, g + 2))}" '
                   f'customWidth="1"/>' for i, g in enumerate(genislik))
    satirlar = ['<row r="1">' + "".join(_hucre(f"{_sutun_harfi(i)}1", b, 1)
                                        for i, b in enumerate(basliklar)) + "</row>"]
    for n, r in enumerate(tablo, start=2):
        satirlar.append(f'<row r="{n}">' + "".join(
            _hucre(f"{_sutun_harfi(i)}{n}", r.get(b, "")) for i, b in enumerate(basliklar))
            + "</row>")
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" '
            'activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
            f'<cols>{cols}</cols><sheetData>{"".join(satirlar)}</sheetData></worksheet>')


def _sayfa_adi(ad: str, kullanilan: set) -> str:
    ad = re.sub(r"[\[\]:*?/\\]", "-", ad)[:31] or "Sayfa"
    aday, n = ad, 2
    while aday in kullanilan:
        aday = f"{ad[:28]}-{n}"
        n += 1
    kullanilan.add(aday)
    return aday


def xlsx_yaz(yol: Union[str, Path], sayfalar: Sequence[Tuple[str, Tablo]]) -> Path:
    yol = Path(yol)
    kullanilan: set = set()
    adlar = [_sayfa_adi(ad, kullanilan) for ad, _ in sayfalar]
    ns = "http://schemas.openxmlformats.org"
    with zipfile.ZipFile(yol, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   f'<Types xmlns="{ns}/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-'
                   'package.relationships+xml"/><Default Extension="xml" '
                   'ContentType="application/xml"/>'
                   '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.'
                   'openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                   '<Override PartName="/xl/styles.xml" ContentType="application/vnd.'
                   'openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
                   + "".join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" '
                             'ContentType="application/vnd.openxmlformats-officedocument.'
                             'spreadsheetml.worksheet+xml"/>'
                             for i in range(1, len(sayfalar) + 1)) + "</Types>")
        z.writestr("_rels/.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   f'<Relationships xmlns="{ns}/package/2006/relationships">'
                   f'<Relationship Id="rId1" Type="{ns}/officeDocument/2006/relationships/'
                   'officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr("xl/workbook.xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   f'<workbook xmlns="{ns}/spreadsheetml/2006/main" '
                   f'xmlns:r="{ns}/officeDocument/2006/relationships"><sheets>'
                   + "".join(f'<sheet name="{escape(ad)}" sheetId="{i}" r:id="rId{i}"/>'
                             for i, ad in enumerate(adlar, start=1))
                   + "</sheets></workbook>")
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   f'<Relationships xmlns="{ns}/package/2006/relationships">'
                   + "".join(f'<Relationship Id="rId{i}" Type="{ns}/officeDocument/2006/'
                             f'relationships/worksheet" Target="worksheets/sheet{i}.xml"/>'
                             for i in range(1, len(sayfalar) + 1))
                   + f'<Relationship Id="rId{len(sayfalar) + 1}" Type="{ns}/officeDocument/'
                   '2006/relationships/styles" Target="styles.xml"/></Relationships>')
        z.writestr("xl/styles.xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   f'<styleSheet xmlns="{ns}/spreadsheetml/2006/main">'
                   '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
                   '<font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>'
                   '</fonts><fills count="3"><fill><patternFill patternType="none"/></fill>'
                   '<fill><patternFill patternType="gray125"/></fill><fill><patternFill '
                   'patternType="solid"><fgColor rgb="FF0F766E"/></patternFill></fill></fills>'
                   '<borders count="1"><border/></borders><cellStyleXfs count="1"><xf/>'
                   '</cellStyleXfs><cellXfs count="2"><xf xfId="0"/><xf xfId="0" fontId="1" '
                   'fillId="2" applyFont="1" applyFill="1"/></cellXfs><cellStyles count="1">'
                   '<cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
                   '</styleSheet>')
        for i, (_, tablo) in enumerate(sayfalar, start=1):
            z.writestr(f"xl/worksheets/sheet{i}.xml", _sayfa_xml(tablo))
    return yol


def plan_calisma_kitabi(plan, yol: Union[str, Path], emirler=None) -> Path:
    """Planın bütün tablolarını tek XLSX dosyasına yazar."""
    from motor import analiz as an
    from rapor.is_emirleri import is_emirleri, tablo
    emirler = emirler if emirler is not None else is_emirleri(plan)
    sayfalar = [
        ("Özet", [{"Gösterge": k, "Değer": v} for k, v in an.gostergeler(plan).items()]),
        ("Siparişler", an.siparis_tablosu(plan)),
        ("Tahsis", an.tahsis_tablosu(plan)),
        ("Makine dengeleme", an.dengeleme_tablosu(plan)),
        ("Parti araması", plan.arama),
        ("İş emirleri", tablo(plan, emirler)),
        ("Kaynak kullanımı", an.kaynak_kullanimi(plan)),
        ("Günlük çıkış", an.gunluk_cikis(plan)),
        ("Günlük personel", an.gunluk_personel(plan)),
        ("Ayarlar", an.ayar_tablosu(plan)),
        ("Kısıt analizi", an.kisit_tablosu(plan)),
        ("Ek mesai", an.ek_mesai_ozeti(plan)),
        ("Personel özeti", an.personel_ozeti(plan)),
        ("Görevlendirmeler", an.gorev_tablosu(plan)),
        ("Atanamayan", an.atanamayan_tablosu(plan)),
    ]
    return xlsx_yaz(yol, sayfalar)
