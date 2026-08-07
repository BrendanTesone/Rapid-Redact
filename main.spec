# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for Rapid Redact
# PDF redaction tool for searching/redacting sensitive info in clinical PDFs


a = Analysis(
    ['main.py'],                          # Entry point
    pathex=[],                            # Additional search paths (empty = use defaults)
    binaries=[],                          # Binary dependencies (auto-detected)
    datas=[                               # Data files to include
        ('.env', '.'),                    # Environment variables (if exists)
    ],
    hiddenimports=[                       # Modules PyInstaller can't auto-detect
        'certifi',                        # SSL certificates
        'requests',                       # HTTP library
        'urllib3',                        # HTTP library (explicit import)
        'openpyxl',                       # Excel file reading (search terms)
        'fitz',                           # PyMuPDF (PDF handling)
        'pymupdf',                        # PyMuPDF alternate import
        'flet',                           # GUI framework
        'flet_desktop',                   # Flet desktop support
        'dotenv',                         # Environment variables (.env support)
    ],
    hookspath=[],                         # Custom PyInstaller hooks (none)
    hooksconfig={},                       # Hook configuration (none)
    runtime_hooks=[],                     # Custom runtime hooks (none)
    excludes=[],                          # Modules to exclude (none)
    noarchive=False,                      # Use PYZ archive for .pyc files
    optimize=2,                           # Bytecode optimization level (2 = remove docstrings + asserts)
)
pyz = PYZ(a.pure)                        # Create Python bytecode archive

exe = EXE(
    pyz,                                  # Bytecode archive
    a.scripts,                            # Scripts to include
    [],                                   # Additional scripts (none)
    exclude_binaries=True,                # ← ONEDIR mode: binaries go in COLLECT
    name='Rapid-Redact',                  # Output executable name
    debug=False,                          # No debug output
    bootloader_ignore_signals=False,      # Handle signals normally
    strip=False,                          # Don't strip symbols (better debugging)
    upx=True,                             # Compress with UPX
    console=False,                        # ← GUI mode: no console window
    disable_windowed_traceback=False,     # Show tracebacks
    argv_emulation=False,                 # No argv emulation (macOS only)
    target_arch=None,                     # Auto-detect architecture
    codesign_identity=None,               # No code signing (macOS)
    entitlements_file=None,               # No entitlements (macOS)
)
coll = COLLECT(                          # ← ONEDIR: collect all files into directory
    exe,                                  # The executable
    a.binaries,                           # All DLLs and shared libraries
    a.datas,                              # All data files
    strip=False,                          # Don't strip symbols
    upx=True,                             # Compress binaries
    upx_exclude=[],                       # Don't exclude any files from UPX
    name='Rapid-Redact',                  # Output directory name
)
