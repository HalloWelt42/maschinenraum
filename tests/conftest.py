"""Gemeinsam für alle Tests: kein Test meldet sich bei der echten Energieverwaltung an (Schein-IOKit statt ctypes).
Nur die Rauchprobe in test_schlaf.py nimmt die echte Bibliothek, ausdrücklich."""

from __future__ import annotations

import threading

import pytest

from maschinenraum import schlaf


class ScheinIOKit:
    """Die Aufrufe von IOKit, wie der Wächter sie macht; merkt sich, was erlaubt, abgelehnt und abgemeldet wurde."""

    WURZEL = 4711

    def __init__(self) -> None:
        self.rueckruf = None
        self.erlaubt: list[tuple[int, int]] = []
        self.abgelehnt: list[tuple[int, int]] = []
        self.abgemeldet = self.geschlossen = self.zerstoert = False

    def IORegisterForSystemPower(self, _refcon, _port, rueckruf, _abmelder) -> int:
        self.rueckruf = rueckruf
        return self.WURZEL

    def IONotificationPortGetRunLoopSource(self, _port) -> int:
        return 11

    def IOAllowPowerChange(self, wurzel: int, kennung: int) -> int:
        self.erlaubt.append((wurzel, kennung))
        return 0

    def IOCancelPowerChange(self, wurzel: int, kennung: int) -> int:
        self.abgelehnt.append((wurzel, kennung))
        return 0

    def IODeregisterForSystemPower(self, _abmelder) -> int:
        self.abgemeldet = True
        return 0

    def IOServiceClose(self, _wurzel) -> int:
        self.geschlossen = True
        return 0

    def IONotificationPortDestroy(self, _port) -> None:
        self.zerstoert = True


class ScheinCoreFoundation:
    """Ein CFRunLoop, der läuft, bis er angehalten wird."""

    def __init__(self) -> None:
        self.halt = threading.Event()
        self.laeuft = threading.Event()

    def CFRunLoopGetCurrent(self) -> int:
        return 5

    def CFRunLoopAddSource(self, _runloop, _quelle, _modus) -> None:
        pass

    def CFRunLoopRemoveSource(self, _runloop, _quelle, _modus) -> None:
        pass

    def CFRunLoopRun(self) -> None:
        self.laeuft.set()
        self.halt.wait()

    def CFRunLoopStop(self, _runloop) -> None:
        self.halt.set()


@pytest.fixture(autouse=True)
def schein_energie(monkeypatch):
    """Jede Laufzeit, die ein Test startet, bekommt den Schein statt der echten Energieverwaltung."""
    io, cf = ScheinIOKit(), ScheinCoreFoundation()
    monkeypatch.setattr(schlaf, "bibliotheken", lambda: (io, cf, 0))
    return io, cf
