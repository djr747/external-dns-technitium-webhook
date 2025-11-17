"""Pytest configuration for integration tests"""

import sys
from pathlib import Path

# Ensure venv site-packages are in sys.path
venv_site_packages = Path(__file__).parent.parent.parent / ".venv" / "lib"
python_version_dir = (
    list(venv_site_packages.glob("python*"))[0]
    if list(venv_site_packages.glob("python*"))
    else None
)

if python_version_dir:
    site_packages = python_version_dir / "site-packages"
    if site_packages not in sys.path:
        sys.path.insert(0, str(site_packages))
