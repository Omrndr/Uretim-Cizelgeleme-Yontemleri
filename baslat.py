"""
Masaüstü uygulamasını başlatır.

    python baslat.py                         örnek fabrika + örnek senaryo
    python baslat.py fabrika.json            başka bir fabrika tanımı
    python baslat.py fabrika.json senaryo.json
"""
import sys


def _yuksek_dpi() -> None:
    """Windows'ta bulanık yazıyı önler."""
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:                               # noqa: BLE001
            pass


if __name__ == "__main__":
    _yuksek_dpi()
    from arayuz.uygulama import pencereyi_ac
    pencereyi_ac(*(sys.argv[1:3]))
