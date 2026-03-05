# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the double-clickable GUI app (pywebview) — onedir mode.
# CLI binary is built with the existing WhatsAppWrapped.spec — unchanged.

a = Analysis(
    # Include whatsapp_wrapped.py alongside gui.py so PyInstaller
    # analyses its imports (sqlite3, jinja2, etc.) and bundles them.
    ['gui.py', 'whatsapp_wrapped.py'],
    pathex=[],
    binaries=[],
    datas=[
        # Also ship the raw .py so gui.py can load it via exec_module at runtime.
        ('whatsapp_wrapped.py', '.'),
        ('whatsapp_wrapped/templates/wrapped.html', 'whatsapp_wrapped/templates'),
        ('whatsapp_wrapped/analytics', 'whatsapp_wrapped/analytics'),
    ],
    hiddenimports=[
        'sqlite3',
        '_sqlite3',
        'jinja2',
        'jinja2.ext',
        'webview.platforms.cocoa',    # macOS
        'webview.platforms.winforms', # Windows
        'webview.platforms.gtk',      # Linux
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,   # binaries go into COLLECT for onedir mode
    name='WhatsApp Wrapped',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,           # no terminal window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icons/icon.ico',   # Windows .exe icon
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='WhatsApp Wrapped',
)

# macOS .app bundle (wraps the onedir COLLECT output)
app = BUNDLE(
    coll,
    name='WhatsApp Wrapped.app',
    icon='icons/icon.icns',
    bundle_identifier='com.whatsappwrapped.gui',
)
