from pathlib import Path
# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    [str(Path(SPECPATH) / 'main.py')],
    pathex=[],
    binaries=[],
    datas=[(str(Path(SPECPATH) / 'app/dashboard/assets'), 'app/dashboard/assets'), (str(Path(SPECPATH) / 'app/dashboard/AI_CONNECTOR_ON_1.png'), 'app/dashboard'), (str(Path(SPECPATH) / 'app/dashboard/AI_CONNECTOR_ON_2.png'), 'app/dashboard')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
# Use Windows API-set libraries from the operating system, never bundled image-tool copies.
a.binaries = [entry for entry in a.binaries if '/dependencies/native/' not in entry[1].replace('\\', '/').lower() and Path(entry[0]).name.lower() != 'ucrtbase.dll' and not Path(entry[0]).name.lower().startswith(('api-ms-win-', 'ext-ms-win-'))]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='마비노비',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
