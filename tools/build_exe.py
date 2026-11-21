"""Baut dist/NovaTally.exe mit PyInstaller.

Einzige Stelle mit den PyInstaller-Optionen – genutzt von build.bat und den GitHub-Workflows.
Aufruf (im Projektordner, mit installiertem PyInstaller):  python tools/build_exe.py
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    try:
        import PyInstaller.__main__
    except ImportError:
        sys.exit("PyInstaller fehlt: python -m pip install pyinstaller")
    os.chdir(ROOT)
    sep = ";" if sys.platform == "win32" else ":"
    web = os.path.join("novatally", "web")
    if not os.path.exists(os.path.join(web, "icon.ico")):
        import make_icon  # liegt im selben Ordner

        make_icon.make_ico(os.path.join(web, "icon.ico"))
    PyInstaller.__main__.run([
        "--noconfirm", "--clean", "--log-level", "WARN",
        "--noconsole", "--onefile", "--name", "NovaTally",
        "--icon", os.path.join(web, "icon.ico"),
        "--add-data", f"{web}{sep}{web}",
        "--hidden-import", "pystray._win32",
        "NovaTally.pyw",
    ])
    exe = ROOT / "dist" / ("NovaTally.exe" if sys.platform == "win32" else "NovaTally")
    print(f"Fertig: {exe}")


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    main()
