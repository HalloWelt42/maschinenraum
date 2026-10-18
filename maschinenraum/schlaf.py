"""Schlaf des Rechners erkennen (macOS): der Maschinenraum meldet der Leitstelle, wenn der Rechner einschläft, und
verbindet sich beim Aufwachen sofort neu. Die Menüleiste ist abwählbar, darum erkennt der Python-Prozess es selbst.

IOKit über `ctypes` in einem eigenen Faden, ohne neue Abhängigkeit: `IORegisterForSystemPower` liefert die
Nachrichten der Energieverwaltung in einen CFRunLoop dieses Fadens.

- `kIOMessageCanSystemSleep` kommt nur vor einem Schlaf nach Leerlauf und darf abgelehnt werden. Abgelehnt wird nur
  mit der Einstellung `schlaf.leerlauf_aufschieben`, solange die Leitstelle über diesen Rechner rechnen lässt
  (Durchleitungen); sonst erlaubt. Deckel, Menü und Ein-Taste fragen nicht und wirken immer.
- `kIOMessageSystemWillSleep` kommt sicher und muss quittiert werden; macOS wartet bis zu 30 s. In der Zeit meldet der
  Kanal `knoten.schlaeft` (höchstens 8 s); quittiert wird immer, auch wenn das scheitert.
- `kIOMessageSystemHasPoweredOn`: aufgewacht. Neu verbunden wird nur bei vollem Erwachen (mit Bildschirm), nicht bei
  einem kurzen Erwachen ohne Bildschirm (Power Nap); das sagt `pmset -g systemstate`. Den Rest deckt der Wächter
  des Kanals (Wachzeit ohne Weckmeldung).

Auf anderen Systemen tut der Wächter nichts.
"""

from __future__ import annotations

import asyncio
import ctypes
import logging
import subprocess
import sys
import threading
from collections.abc import Callable
from typing import Any, Protocol

from .konfig import Schlaf
from .protokoll import Schlafgrund

log = logging.getLogger("maschinenraum")

KANN_SCHLAFEN = 0xE0000270        # kIOMessageCanSystemSleep: Schlaf nach Leerlauf, darf abgelehnt werden
SCHLAEFT_EIN = 0xE0000280         # kIOMessageSystemWillSleep: kommt sicher, muss quittiert werden
SCHLAEFT_NICHT = 0xE0000290       # kIOMessageSystemWillNotSleep: ein angefragter Leerlaufschlaf fällt aus
WACH = 0xE0000300                 # kIOMessageSystemHasPoweredOn
MELDEN_S = 8.0                    # so lange darf das Melden dauern; macOS wartet höchstens 30 s auf die Quittung
VOLL_WACH_VERSUCHE = 5            # nach der Weckmeldung so oft prüfen, ob der Bildschirm an ist
VOLL_WACH_ABSTAND_S = 2.0

IOKIT = "/System/Library/Frameworks/IOKit.framework/IOKit"
CORE_FOUNDATION = "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
# void (*IOServiceInterestCallback)(void *refcon, io_service_t service, natural_t messageType, void *messageArgument)
RUECKRUF = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p)


class Kanal(Protocol):
    """Was der Wächter vom Kanal zur Leitstelle braucht (leitstelle.Leitstellenkanal)."""

    async def einschlafen(self, grund: Schlafgrund) -> None: ...
    def aufwachen(self) -> None: ...


def bibliotheken() -> tuple[Any, Any, int]:
    """IOKit und CoreFoundation mit den Signaturen für arm64 (io_connect_t: uint32, Kennung der Nachricht: intptr_t)."""
    io = ctypes.CDLL(IOKIT)
    cf = ctypes.CDLL(CORE_FOUNDATION)
    zeiger, port, intptr = ctypes.c_void_p, ctypes.c_uint32, ctypes.c_long
    io.IORegisterForSystemPower.argtypes = [zeiger, ctypes.POINTER(zeiger), RUECKRUF, ctypes.POINTER(port)]
    io.IORegisterForSystemPower.restype = port
    io.IONotificationPortGetRunLoopSource.argtypes = [zeiger]
    io.IONotificationPortGetRunLoopSource.restype = zeiger
    io.IOAllowPowerChange.argtypes = [port, intptr]
    io.IOAllowPowerChange.restype = ctypes.c_int
    io.IOCancelPowerChange.argtypes = [port, intptr]
    io.IOCancelPowerChange.restype = ctypes.c_int
    io.IODeregisterForSystemPower.argtypes = [ctypes.POINTER(port)]
    io.IODeregisterForSystemPower.restype = ctypes.c_int
    io.IOServiceClose.argtypes = [port]
    io.IOServiceClose.restype = ctypes.c_int
    io.IONotificationPortDestroy.argtypes = [zeiger]
    io.IONotificationPortDestroy.restype = None
    cf.CFRunLoopGetCurrent.argtypes = []
    cf.CFRunLoopGetCurrent.restype = zeiger
    cf.CFRunLoopAddSource.argtypes = [zeiger, zeiger, zeiger]
    cf.CFRunLoopAddSource.restype = None
    cf.CFRunLoopRemoveSource.argtypes = [zeiger, zeiger, zeiger]
    cf.CFRunLoopRemoveSource.restype = None
    cf.CFRunLoopRun.argtypes = []
    cf.CFRunLoopRun.restype = None
    cf.CFRunLoopStop.argtypes = [zeiger]
    cf.CFRunLoopStop.restype = None
    modus = ctypes.c_void_p.in_dll(cf, "kCFRunLoopDefaultMode").value
    return io, cf, modus


def voll_wach() -> bool:
    """Ist der Rechner ganz wach (mit Bildschirm)? Bei Power Nap fehlt Graphics in den Fähigkeiten."""
    try:
        aus = subprocess.run(["pmset", "-g", "systemstate"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return True                   # unklar: lieber verbinden als bis zum Wächter warten
    zeile = next((z for z in aus.splitlines() if "Capabilities" in z), "")
    return "Graphics" in zeile


class Schlafwaechter:
    def __init__(self, kanal: Kanal, durchleitungen: Callable[[], int], einstellung: Callable[[], Schlaf],
                 laden: Callable[[], tuple[Any, Any, int]] | None = None, wach_pruefen: Callable[[], bool] = voll_wach,
                 system: str = sys.platform) -> None:
        """`laden` liefert IOKit, CoreFoundation und den Modus des CFRunLoop (Vorgabe: `bibliotheken`, zur Laufzeit
        nachgeschlagen, damit Tests sie ersetzen können)."""
        self.kanal, self.durchleitungen, self.einstellung = kanal, durchleitungen, einstellung
        self._laden, self._wach_pruefen, self._system = laden, wach_pruefen, system
        self._schleife: asyncio.AbstractEventLoop | None = None
        self._faden: threading.Thread | None = None
        self._bereit = threading.Event()
        self._io: Any = None
        self._cf: Any = None
        self._runloop: int | None = None
        self._wurzel = 0              # io_connect_t der Energieverwaltung
        self._leerlauf = False        # der laufende Schlaf kam nach Leerlauf (KANN_SCHLAFEN ging voraus)
        self._rueckruf = RUECKRUF(self._nachricht)   # Verweis halten: sonst räumt Python ihn weg und IOKit ruft ins Leere

    # ── Lebenslauf ───────────────────────────────────────────────────────
    def starten(self, schleife: asyncio.AbstractEventLoop) -> bool:
        """Startet den Faden; False auf anderen Systemen oder wenn IOKit nicht mitmacht (dann wie bisher)."""
        if self._system != "darwin" or self._faden is not None:
            return False
        self._schleife = schleife
        self._faden = threading.Thread(target=self._laufen, name="schlafwaechter", daemon=True)
        self._faden.start()
        self._bereit.wait(5)
        return self._runloop is not None

    def stoppen(self) -> None:
        """Hält den CFRunLoop an; wiederholt, falls er beim ersten Mal noch nicht lief."""
        faden, self._faden = self._faden, None
        for _ in range(50):
            if faden is None or not faden.is_alive():
                return
            if self._cf is not None and self._runloop is not None:
                self._cf.CFRunLoopStop(self._runloop)
            faden.join(0.1)

    def _laufen(self) -> None:
        try:
            self._io, self._cf, modus = (self._laden or bibliotheken)()
            port_ref, abmelder = ctypes.c_void_p(), ctypes.c_uint32()
            self._wurzel = self._io.IORegisterForSystemPower(None, ctypes.byref(port_ref), self._rueckruf, ctypes.byref(abmelder))
            if not self._wurzel:
                log.warning("Schlaf: Anmeldung bei der Energieverwaltung abgelehnt; der Schlaf wird nicht gemeldet")
                return
            quelle = self._io.IONotificationPortGetRunLoopSource(port_ref)
            self._runloop = self._cf.CFRunLoopGetCurrent()
            self._cf.CFRunLoopAddSource(self._runloop, quelle, modus)
        except (OSError, AttributeError, ValueError) as f:
            log.warning("Schlaf: IOKit nicht nutzbar (%s); der Schlaf wird nicht gemeldet", f)
            return
        finally:
            self._bereit.set()
        log.info("Schlaf: Wächter läuft")
        try:
            self._cf.CFRunLoopRun()               # bis stoppen()
        finally:
            self._cf.CFRunLoopRemoveSource(self._runloop, quelle, modus)
            self._io.IODeregisterForSystemPower(ctypes.byref(abmelder))
            self._io.IOServiceClose(self._wurzel)
            self._io.IONotificationPortDestroy(port_ref)
            self._runloop = None

    # ── Nachrichten der Energieverwaltung (im Faden des Wächters) ────────
    def _nachricht(self, _refcon: Any, _dienst: int, art: int, argument: Any) -> None:
        kennung = argument or 0
        try:
            if art == KANN_SCHLAFEN:
                self._kann_schlafen(kennung)
            elif art == SCHLAEFT_EIN:
                self._schlaeft_ein(kennung)
            elif art == SCHLAEFT_NICHT:
                self._leerlauf = False
            elif art == WACH:
                self._wach()
        except Exception:                               # nie in IOKit hinein werfen; quittiert ist dann schon
            log.exception("Schlaf: Fehler bei Nachricht %#x", art)

    def _kann_schlafen(self, kennung: int) -> None:
        if self.einstellung().leerlauf_aufschieben and self.durchleitungen() > 0:
            log.info("Schlaf: Leerlaufschlaf aufgeschoben, die Leitstelle lässt gerade rechnen (%d Durchleitungen)", self.durchleitungen())
            self._io.IOCancelPowerChange(self._wurzel, kennung)
            return
        self._leerlauf = True
        self._io.IOAllowPowerChange(self._wurzel, kennung)

    def _schlaeft_ein(self, kennung: int) -> None:
        grund = Schlafgrund.LEERLAUF if self._leerlauf else Schlafgrund.ANGEFORDERT
        self._leerlauf = False
        try:
            if self.einstellung().melden and self._schleife is not None:
                log.info("Schlaf: der Rechner schläft ein (%s)", grund.value)
                asyncio.run_coroutine_threadsafe(self.kanal.einschlafen(grund), self._schleife).result(timeout=MELDEN_S)
        except Exception as f:                          # auch Zeitüberschreitung: quittiert wird trotzdem
            log.warning("Schlaf: Melden an die Leitstelle gescheitert (%s)", type(f).__name__)
        finally:
            self._io.IOAllowPowerChange(self._wurzel, kennung)

    def _wach(self) -> None:
        if self.einstellung().melden and self._schleife is not None:
            asyncio.run_coroutine_threadsafe(self._geweckt(), self._schleife)

    async def _geweckt(self) -> None:
        """Nach der Weckmeldung: verbinden, sobald der Rechner ganz wach ist; bleibt er ohne Bildschirm, übernimmt der
        Wächter des Kanals."""
        for versuch in range(VOLL_WACH_VERSUCHE):
            if await asyncio.to_thread(self._wach_pruefen):
                log.info("Schlaf: der Rechner ist wach")
                self.kanal.aufwachen()
                return
            if versuch < VOLL_WACH_VERSUCHE - 1:
                await asyncio.sleep(VOLL_WACH_ABSTAND_S)
        log.info("Schlaf: kurz erwacht ohne Bildschirm (Power Nap); keine neue Verbindung")
