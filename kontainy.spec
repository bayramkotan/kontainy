# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_dynamic_libs
from PyInstaller.utils.hooks import collect_submodules

binaries = []
hiddenimports = ['PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets', 'kontainy.core.catalog.docker', 'kontainy.core.catalog.podman', 'kontainy.core.catalog.run_flags', 'kontainy.core.catalog.quadlet', 'kontainy.rules.catalog', 'kontainy.learn.content', 'kontainy.core.templates']
binaries += collect_dynamic_libs('PySide6')
hiddenimports += collect_submodules('kontainy')


a = Analysis(
    ['/mnt/user-data/outputs/kontainy_v2/main.py'],
    pathex=['/mnt/user-data/outputs/kontainy_v2'],
    binaries=binaries,
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'PySide6.QtQuick', 'PySide6.QtQml', 'PySide6.Qt3DCore', 'PySide6.QtMultimedia', 'PySide6.QtCharts', 'PySide6.QtDataVisualization', 'PySide6.QtNetworkAuth', 'PySide6.QtBluetooth', 'PySide6.QtSensors', 'PySide6.QtPositioning', 'PySide6.QtSerialPort', 'PySide6.QtTest', 'tkinter', 'matplotlib', 'numpy', 'scipy', 'pandas', 'PIL'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='kontainy',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['/mnt/user-data/outputs/kontainy_v2/assets/icon.png'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='kontainy',
)
