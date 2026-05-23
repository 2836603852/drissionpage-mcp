# -*- coding: utf-8 -*-
"""Pytest fixtures: ensure src/ is importable without installing the package."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
