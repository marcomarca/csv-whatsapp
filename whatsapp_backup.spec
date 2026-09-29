# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

project_dir = Path.cwd()

# 1. Collect data files from dependencies
datas = []

# RapidOCR ONNX models and yaml config
datas += collect_data_files('rapidocr_onnxruntime')

# wa-crypt-tools protobufs and assets
datas += collect_data_files('wa_crypt_tools')

# Branding assets (icons, logo marks)
branding_dir = project_dir / "branding_numero_2"
if branding_dir.exists():
    for root, dirs, files in os.walk(branding_dir):
        for file in files:
            full_path = os.path.join(root, file)
            rel_dir = os.path.relpath(root, project_dir)
            datas.append((full_path, rel_dir))

# 2. Collect hidden imports
hiddenimports = [
    'keyring.backends',
    'keyring.backends.Windows',
    'keyring.backends.SecretService',
    'keyring.backends.chainer',
    'keyring.backends.null',
    'winocr',
    'Crypto',
    'Crypto.Cipher',
    'Crypto.Cipher.AES',
    'Cryptodome',
    'Cryptodome.Cipher',
    'Cryptodome.Cipher.AES',
    'cryptography',
    'PIL',
    'PIL.Image',
    'PIL.ImageTk',
    'PIL.ImageEnhance',
    'tkinter',
    'tkinter.ttk',
    'tkinter.messagebox',
    'tkinter.simpledialog',
    'tkinter.filedialog',
    'sqlite3',
    'pandas',
    'numpy',
    'colorama',
    'configobj',
    'google.protobuf',
]

hiddenimports += collect_submodules('wa_crypt_tools')
hiddenimports += collect_submodules('rapidocr_onnxruntime')
hiddenimports += collect_submodules('src')
hiddenimports += collect_submodules('keyring')
hiddenimports += collect_submodules('win32ctypes')
hiddenimports += collect_submodules('jaraco')

import glob

# Collect Python base DLLs (python313.dll, python3.dll, vcruntime140.dll)
binaries = []
for dll_path in glob.glob(os.path.join(sys.base_prefix, '*.dll')):
    binaries.append((dll_path, '.'))

a = Analysis(
    ['src/entrypoint.py'],
    pathex=[str(project_dir)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pytest', 'ruff', 'pip'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    noarchive=False,
)

from PyInstaller.building.datastruct import TOC

print(f"[*] TOTAL a.binaries before filter: {len(a.binaries)}")
filtered_binaries = []
for b in list(a.binaries):
    name = str(b[0]).lower()
    path = str(b[1]).lower() if len(b) > 1 else ""
    if any(k in name or k in path for k in ("api-ms-win", "ext-ms-win", "ucrtbase")):
        print(f"[*] Filtering out binary: {b[0]} ({path})")
    else:
        filtered_binaries.append(b)

a.binaries = TOC(filtered_binaries)
print(f"[*] TOTAL a.binaries after filter: {len(a.binaries)}")

filtered_datas = []
for d in list(a.datas):
    name = str(d[0]).lower()
    path = str(d[1]).lower() if len(d) > 1 else ""
    if any(k in name for k in (".dist-info", "egg-info", "installer", "record", "direct_url.json")):
        continue
    if any(k in name or k in path for k in ("api-ms-win", "ext-ms-win")):
        continue
    filtered_datas.append(d)
a.datas = TOC(filtered_datas)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='whatsapp-backup-csv',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Keeps console available for CLI and status while opening GUI
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(project_dir / 'branding_numero_2' / 'app-icon' / 'favicon.ico'),
)
