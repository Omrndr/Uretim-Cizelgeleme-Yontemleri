"""
Fazla çalışma defteri — yıllık bakiyelerin kalıcı kaydı (SQLite).

Yıllık fazla çalışma tavanı (4857 s. İş K. m.41: 270 saat) TAKVİM YILI boyunca
birikir. Tek bir plan koşusu bunu bilemez; bu yüzden her onaylanan plan deftere
işlenir ve bir sonraki plan açılış bakiyesini buradan okur.

Tablolar:
    bakiye(personel, yil, saat, guncellendi)          -> personel × yıl bakiyesi
    hareket(id, personel, yil, saat, aciklama, zaman) -> her işlemin günlüğü

Veritabanı kullanıcının veri klasöründe durur (paketlenmiş .exe'de de yazılabilir).
"""
from __future__ import annotations

import os
import sqlite3
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

_SEMA = """
CREATE TABLE IF NOT EXISTS bakiye (
    personel    TEXT NOT NULL,
    yil         INTEGER NOT NULL,
    saat        REAL NOT NULL DEFAULT 0,
    guncellendi TEXT NOT NULL,
    PRIMARY KEY (personel, yil)
);
CREATE TABLE IF NOT EXISTS hareket (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    personel  TEXT NOT NULL,
    yil       INTEGER NOT NULL,
    saat      REAL NOT NULL,
    aciklama  TEXT,
    zaman     TEXT NOT NULL
);
"""


def kullanici_klasoru() -> Path:
    """Platforma uygun, yazılabilir uygulama veri klasörü."""
    if sys.platform.startswith("win"):
        kok = Path(os.environ.get("APPDATA", Path.home()))
    else:
        kok = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    yol = kok / "UretimCizelgeleme"
    yol.mkdir(parents=True, exist_ok=True)
    return yol


def varsayilan_yol() -> Path:
    return kullanici_klasoru() / "fazla_mesai_defteri.db"


@contextmanager
def _baglanti(yol: Optional[os.PathLike] = None):
    con = sqlite3.connect(str(yol or varsayilan_yol()))
    try:
        con.executescript(_SEMA)
        yield con
        con.commit()
    finally:
        con.close()


def _simdi() -> str:
    return datetime.now().isoformat(timespec="seconds")


def bakiyeler(yil: int, personel: Optional[Iterable[str]] = None,
              yol: Optional[os.PathLike] = None) -> Dict[str, float]:
    with _baglanti(yol) as con:
        satir = con.execute("SELECT personel, saat FROM bakiye WHERE yil = ?", (yil,))
        hepsi = {p: float(s) for p, s in satir}
    if personel is None:
        return hepsi
    return {p: hepsi.get(p, 0.0) for p in personel}


def isle(yil: int, saatler: Dict[str, float], aciklama: str = "",
         yol: Optional[os.PathLike] = None) -> int:
    """Plandaki fazla çalışmayı bakiyelere ekler. Dönüş: güncellenen kişi sayısı."""
    n = 0
    zaman = _simdi()
    with _baglanti(yol) as con:
        for p, s in saatler.items():
            if abs(s) < 1e-9:
                continue
            con.execute(
                "INSERT INTO bakiye(personel, yil, saat, guncellendi) VALUES(?,?,?,?) "
                "ON CONFLICT(personel, yil) DO UPDATE SET saat = saat + excluded.saat, "
                "guncellendi = excluded.guncellendi", (p, yil, float(s), zaman))
            con.execute("INSERT INTO hareket(personel, yil, saat, aciklama, zaman) "
                        "VALUES(?,?,?,?,?)", (p, yil, float(s), aciklama, zaman))
            n += 1
    return n


def ad_degistir(eski: str, yeni: str, yil: int, yol: Optional[os.PathLike] = None) -> float:
    """Bir personelin bakiyesini yeni adına taşır (ad düzeltmesi için)."""
    with _baglanti(yol) as con:
        r = con.execute("SELECT saat FROM bakiye WHERE personel=? AND yil=?",
                        (eski, yil)).fetchone()
        if not r:
            return 0.0
        saat = float(r[0])
        con.execute("DELETE FROM bakiye WHERE personel=? AND yil=?", (eski, yil))
    isle(yil, {yeni: saat}, f"{eski} -> {yeni} bakiye taşıma", yol)
    return saat


def yil_sil(yil: int, yol: Optional[os.PathLike] = None) -> int:
    with _baglanti(yol) as con:
        n = con.execute("DELETE FROM bakiye WHERE yil = ?", (yil,)).rowcount
        con.execute("INSERT INTO hareket(personel, yil, saat, aciklama, zaman) "
                    "VALUES('*', ?, 0, 'Yıl sıfırlandı', ?)", (yil, _simdi()))
    return n


def son_hareketler(limit: int = 200, yol: Optional[os.PathLike] = None
                   ) -> List[Tuple[str, str, int, float, str]]:
    with _baglanti(yol) as con:
        return list(con.execute(
            "SELECT zaman, personel, yil, saat, COALESCE(aciklama,'') FROM hareket "
            "ORDER BY id DESC LIMIT ?", (limit,)))
