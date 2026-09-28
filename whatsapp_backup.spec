# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

project_dir = Path.cwd()

# 1. Collect data files from dependencies
datas = []

# RapidOCR ONNX models and yaml config
datas += collect_data_files('rapidocr_onnxruntime')

# wa-crypt-tools protobufs and assets
datas += collect_data_files('wa_crypt_tools')

# Bundled platform-tools (ADB, dlls)
vendor_pt = project_dir / 'vendor' / 'platform-tools'
if vendor_pt.exists():
    datas.append((str(vendor_pt), 'vendor/platform-tools'))

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

a = Analysis(
    ['src/entrypoint.py'],
    pathex=[str(project_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pytest', 'ruff', 'pip'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
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
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
