"""Pathlib constants for ThreatLens, resolved relative to this package.

All other modules import from here so that ``cd src && streamlit run app.py``
and ``cd src && pytest`` both resolve paths correctly.
"""
from pathlib import Path

# Directory containing this file: src/threatlens/
PKG_DIR: Path = Path(__file__).parent.resolve()

# src/threatlens/sample_data/
SAMPLE_DATA: Path = PKG_DIR / "sample_data"

# src/templates/
TEMPLATES: Path = PKG_DIR.parent / "templates"

# src/outputs/
OUTPUTS: Path = PKG_DIR.parent / "outputs"
