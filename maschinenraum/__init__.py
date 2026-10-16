"""Maschinenraum: verwaltet die Dienste eines Rechners an einem Ort (starten, anhalten, messen).

Die Fassung steht in `version.json` im Wurzelordner; bei einer Installation legt das Installationsskript sie
als `VERSION` ins Paket.
"""

from __future__ import annotations

import json
from pathlib import Path


def _fassung() -> str:
    hier = Path(__file__).resolve().parent
    datei = hier / "VERSION"
    if datei.is_file():
        return datei.read_text(encoding="utf-8").strip()
    quelle = hier.parent / "version.json"
    if quelle.is_file():
        return json.loads(quelle.read_text(encoding="utf-8"))["version"]
    return "0.0.0"


__version__ = _fassung()
