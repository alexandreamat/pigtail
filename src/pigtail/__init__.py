"""pigtail -- house wiring as code: model a home's electrical system, draw it, and check it
against the NEC."""

import os

# SKiDL scans for KiCad symbol/footprint libraries at import time and warns
# loudly when they are absent. We only build library-free ad-hoc parts, so
# silence that before anything imports skidl.
for _var in ("KICAD_SYMBOL_DIR", *(f"KICAD{_n}_SYMBOL_DIR" for _n in range(5, 11))):
    os.environ.setdefault(_var, "")
