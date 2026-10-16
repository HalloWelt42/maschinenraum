"""Maschinenraum: verwaltet die KI-Dienste eines Rechners an einem Ort (starten, anhalten, messen) und meldet sie
der Leitstelle. Die Dienststeuerung kommt aus dem Dienstkern.

Die Fassung steht in `version.json` im Wurzelordner; bei einer Installation legt das Installationsskript sie
als `VERSION` ins Paket.
"""

from __future__ import annotations

from pathlib import Path

from dienstkern import fassung

__version__ = fassung(Path(__file__).resolve().parent)
