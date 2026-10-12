# Configuration PyInstaller — compiler avec : pyinstaller mes_finances.spec
#   macOS   -> dist/Mes Finances.app
#   Windows -> dist/Mes Finances.exe (fichier unique)
import os
import sys

APP_NAME = "Mes Finances"
VERSION = os.environ.get("APP_VERSION", "0.0.0").lstrip("v")

a = Analysis(
    ["desktop.py"],
    datas=[("static", "static")],
    excludes=["tkinter"],
)
pyz = PYZ(a.pure)

if sys.platform == "darwin":
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name=APP_NAME, console=False, upx=False)
    coll = COLLECT(exe, a.binaries, a.datas, name=APP_NAME, upx=False)
    app = BUNDLE(
        coll,
        name=f"{APP_NAME}.app",
        bundle_identifier="com.ivanmozina.mesfinances",
        version=VERSION,
        info_plist={
            "CFBundleShortVersionString": VERSION,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
        },
    )
else:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, name=APP_NAME, console=False, upx=False)
