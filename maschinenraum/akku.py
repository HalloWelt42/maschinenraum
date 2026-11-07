"""Akku eines tragbaren Mac messen (HELF-187): Ladestand, Netzteil, Laden, Restzeit, Zustand und Ladezyklen.

Quelle ist der Eintrag `AppleSmartBattery` der Energieverwaltung, gelesen mit `ioreg -rn AppleSmartBattery -a`
(Eigenschaftsliste, ohne neue Abhängigkeit). Der Akku ändert sich langsam: gefragt wird höchstens alle
`ABSTAND_S`, dazwischen gilt der letzte Wert. Rechner ohne Akku (Mac Studio, Mac mini, Linux) liefern None.

Fallen aus der Messung (07.11.2026, macOS 15 und 27):
- `CurrentCapacity` ist auf Apple Silicon schon der Ladestand in Prozent (`MaxCapacity` = 100); auf älteren Macs sind
  beide in mAh. Darum immer `CurrentCapacity / MaxCapacity`.
- 65535 bei `AvgTimeToFull` und `AvgTimeToEmpty` heißt: wird noch berechnet.
- `AppleRawMaxCapacity` und `DesignCapacity` fehlen unter macOS 27; dann bleibt der Zustand unbekannt.
"""

from __future__ import annotations

import plistlib
import subprocess
import sys
import time
from collections.abc import Callable
from typing import Any

from .protokoll import Akku

ABSTAND_S = 30.0
UNBEKANNT = 65535


def _zeit(wert: Any) -> int | None:
    return int(wert) if isinstance(wert, int) and 0 < wert < UNBEKANNT else None


def akku_aus_eintrag(e: dict[str, Any]) -> Akku | None:
    """Ein Eintrag `AppleSmartBattery` als Akku; None, wenn kein Akku eingebaut ist oder der Ladestand fehlt."""
    if not e.get("BatteryInstalled", True):
        return None
    jetzt, voll = e.get("CurrentCapacity"), e.get("MaxCapacity")
    if not isinstance(jetzt, int) or not isinstance(voll, int) or voll <= 0:
        return None
    netzteil, laedt = bool(e.get("ExternalConnected")), bool(e.get("IsCharging"))
    rest = _zeit(e.get("AvgTimeToFull")) if laedt else None if netzteil else _zeit(e.get("AvgTimeToEmpty"))
    roh, entwurf = e.get("AppleRawMaxCapacity"), e.get("DesignCapacity")
    kapazitaet = round(roh / entwurf * 100, 1) if isinstance(roh, int) and isinstance(entwurf, int) and entwurf > 0 else None
    zyklen = e.get("CycleCount")
    return Akku(prozent=max(0, min(100, round(jetzt / voll * 100))), netzteil=netzteil, laedt=laedt, rest_min=rest,
                kapazitaet_prozent=kapazitaet, zyklen=zyklen if isinstance(zyklen, int) else None)


def ioreg_lesen() -> list[dict[str, Any]]:
    """Die Einträge `AppleSmartBattery` (leer ohne Akku oder wenn ioreg fehlt)."""
    try:
        aus = subprocess.run(["ioreg", "-rn", "AppleSmartBattery", "-a"], capture_output=True, timeout=5).stdout
        return plistlib.loads(aus) if aus.strip() else []
    except (OSError, subprocess.SubprocessError, plistlib.InvalidFileException, ValueError):
        return []


class Akkumesser:
    """Misst den Akku höchstens alle `abstand_s`; dazwischen gilt der letzte Wert. Auf anderen Systemen immer None."""

    def __init__(self, lesen: Callable[[], list[dict[str, Any]]] = ioreg_lesen, abstand_s: float = ABSTAND_S,
                 system: str = sys.platform, uhr: Callable[[], float] = time.monotonic) -> None:
        self._lesen, self._abstand_s, self._uhr = lesen, abstand_s, uhr
        self._aktiv = system == "darwin"
        self._zuletzt: float | None = None
        self._wert: Akku | None = None
        self.vorhanden = self._aktiv and self.messen() is not None

    def messen(self) -> Akku | None:
        if not self._aktiv:
            return None
        jetzt = self._uhr()
        if self._zuletzt is None or jetzt - self._zuletzt >= self._abstand_s:
            self._zuletzt = jetzt
            self._wert = next((a for a in map(akku_aus_eintrag, self._lesen()) if a is not None), None)
        return self._wert
