# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
from pathlib import Path


def app_dir() -> Path:
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base)
    return Path(__file__).resolve().parents[1]


def resource_path(rel: str) -> str:
    return str(app_dir() / rel)
