"""
Wrapper to disable SSL verification for PyInstaller build.
Required for corporate networks with TLS inspection.
"""

import ssl
import sys

# Disable SSL verification globally
ssl._create_default_https_context = ssl._create_unverified_context  # type: ignore[assignment]

# Now run pyinstaller
if __name__ == "__main__":
    from PyInstaller.__main__ import run

    sys.exit(run())
