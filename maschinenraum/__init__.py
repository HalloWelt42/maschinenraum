"""Maschinenraum: verwaltet die KI-Dienste eines Rechners an einem Ort (starten, anhalten, messen) und meldet sie
der Leitstelle. Die Dienststeuerung kommt aus dem Dienstkern.

Die Fassung steht in `version.json` im Wurzelordner; bei einer Installation legt das Installationsskript sie
als `VERSION` ins Paket. Sie wird hier ohne Abhängigkeiten gelesen, weil das Bauen des Pakets sie schon braucht,
bevor die Abhängigkeiten (auch der Dienstkern) installiert sind.
"""

from __future__ import annotations

import json
from importlib import metadata
from pathlib import Path


def _fassung() -> str:
    hier = Path(__file__).resolve().parent
    datei = hier / "VERSION"
    if datei.is_file():
        return datei.read_text(encoding="utf-8").strip()
    quelle = hier.parent / "version.json"
    if quelle.is_file():
        return json.loads(quelle.read_text(encoding="utf-8"))["version"]
    try:
        return metadata.version("maschinenraum")
    except metadata.PackageNotFoundError:
        return "0.0.0"


__version__ = _fassung()
