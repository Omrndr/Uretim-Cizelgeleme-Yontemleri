"""
Masaüstü uygulamasını tek dosyalık çalıştırılabilir pakete çevirir (PyInstaller).

    pip install pyinstaller
    python paketle.py

Windows'ta ``dist/UretimCizelgeleme.exe`` üretir (macOS/Linux'ta aynı adla yerel
ikili). Uygulama yalnızca standart kütüphaneyi (tkinter, sqlite3, zipfile...)
kullandığı için paket küçüktür ve hedef bilgisayarda Python gerekmez.

Depodaki GitHub Actions iş akışı (.github/workflows/derle.yml) bu betiği
Windows üzerinde çalıştırır ve .exe'yi sürüm (release) ekine koyar.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJE = Path(__file__).resolve().parent
AD = "UretimCizelgeleme"


def main() -> int:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller bulunamadı:  pip install pyinstaller")
        return 1
    for klasor in ("build", "dist"):
        shutil.rmtree(PROJE / klasor, ignore_errors=True)
    komut = [
        sys.executable, "-m", "PyInstaller", str(PROJE / "baslat.py"),
        "--name", AD, "--onefile", "--windowed", "--noconfirm", "--clean",
        "--add-data", f"{PROJE / 'veri'}{os.pathsep}veri",
        "--hidden-import", "tkinter", "--hidden-import", "sqlite3",
        # Kullanılmayan büyük modüller pakete girmesin
        "--exclude-module", "numpy", "--exclude-module", "pandas",
        "--exclude-module", "matplotlib", "--exclude-module", "PIL",
    ]
    simge = PROJE / "veri" / "simge.ico"
    if simge.exists():
        komut += ["--icon", str(simge)]
    print(" ".join(komut))
    sonuc = subprocess.run(komut, cwd=PROJE)
    if sonuc.returncode != 0:
        return sonuc.returncode
    cikti = next((PROJE / "dist").glob(f"{AD}*"), None)
    if cikti:
        print(f"\nHazır: {cikti}  ({cikti.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
