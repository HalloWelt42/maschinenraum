"""Last des Modell-Läufers, der Apps des Stellwerks und des Rechners (`knoten.last`) und das Beenden eines Arbeiters des
Läufers auf Befehl der Leitstelle (`laeufer_prozess_beenden`). Der Maschinenraum misst und führt aus; ob ein Arbeiter hängt und beendet wird,
entscheidet die Leitstelle.

Der Läufer ist der Prozess, der am Läufer-Port lauscht (Hauptprozess), samt Nachfahren. Ein Arbeiter ist ein Prozess
darin, der eine Modelldatei offen hat (Endungen aus `beobachtung.modelldateien`) oder eine Bibliothek eines Rechenwerks
geladen hat (Ordnerteile aus `beobachtung.arbeiter_bibliotheken`): eine geladene Instanz. Das zweite Merkmal braucht es
für Rechenwerke, die das Modell ganz in den Speicher lesen und die Datei danach schließen. Alles andere, etwa das
Fenster, ist sonstig.

Prozessorlast zählt zeitbasiert: verbrauchte Rechenzeit seit der letzten Messung je Wandzeit, aus der Prozesstabelle.
Beim ersten Mal und bei einer neuen pid gibt es für den Läufer keinen Wert. Die Fremdlast ist die Last aller übrigen
Prozesse (ohne Läufer, ohne Dienste und Maschinenraum, ohne Apps des Stellwerks) als Anteil aller Kerne, also die Last,
die der Mensch und seine übrigen Programme erzeugen; ein Prozess, der seit der letzten Messung neu ist, zählt mit seiner
ganzen Rechenzeit. Die Arbeit, die die Leitstelle selbst auslöst, steckt nicht darin: drosselt sie danach ihren
Hintergrund, schaukelt sie sich nicht an der eigenen Last auf. Die Apps des Stellwerks stehen je Teil daneben
(`apps`), in Prozent eines Kerns und nach derselben Regel wie die Fremdlast: was aus der Fremdlast herausfällt, steht
dort, nichts doppelt und nichts verloren.

Beenden: nur ein Arbeiter des Läufers, unmittelbar vorher frisch geprüft (gegen wiederverwendete pids und
Fehlbedienung); den Hauptprozess und alles andere nie. Erst die Bitte (SIGTERM), nach `beobachtung.anhaltezeit_s` hart
(SIGKILL).
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import time
from collections.abc import Callable
from dataclasses import dataclass

from dienstkern.messen import GIB, prozess_bytes

from . import beobachtung
from .beobachtung import Aufnahme, Beobachter, aufnehmen, mit_eltern, programmname
from .konfig import Beobachtung, Einstellungen
from .protokoll import AppsLast, AppTeil, BefehlErgebnis, Befehlsart, KnotenLast, Laeuferprozess, Laeuferrolle

log = logging.getLogger("maschinenraum")
PRUEFABSTAND_S = 0.25                  # so oft wird beim Beenden nachgesehen, ob der Prozess weg ist
NACH_KILL_S = 2.0                      # so lange darf das Abräumen nach SIGKILL dauern
ROLLENFOLGE = {Laeuferrolle.HAUPT: 0, Laeuferrolle.ARBEITER: 1, Laeuferrolle.SONSTIG: 2}


@dataclass
class Merkmale:
    """Woran ein Prozess des Läufers als Arbeiter zu erkennen ist, aus seinen offenen Dateien."""

    modelldatei: str = ""             # die größte offene Modelldatei (~ für den Heimordner); leer: keine
    bibliothek: bool = False          # hat eine Bibliothek aus einem Ordnerteil von beobachtung.arbeiter_bibliotheken geladen

    @property
    def arbeiter(self) -> bool:
        return bool(self.modelldatei) or self.bibliothek


def merkmale_lesen(pids: set[int], b: Beobachtung) -> dict[int, Merkmale]:
    """Je Prozess die größte offene Modelldatei (auch eingeblendete Dateien zählen) und ob er eine Bibliothek eines
    Rechenwerks geladen hat (Spalte txt von lsof). Ein Aufruf von lsof für alle; Prozesse ohne beides fehlen, ohne lsof
    ist das Ergebnis leer."""
    liste = ",".join(str(p) for p in sorted(pids))
    aus = beobachtung._lsof("-p", liste, "-F", "pns") if liste else None
    endungen = tuple(e.lower() for e in b.modelldateien)
    ordnerteile = tuple(o.lower() for o in b.arbeiter_bibliotheken)
    groesste: dict[int, tuple[int, str]] = {}
    mit_bibliothek: set[int] = set()
    pid, art, groesse = 0, "", 0
    for zeile in (aus or "").splitlines():
        if zeile.startswith("p"):
            pid = int(zeile[1:])
        elif zeile.startswith("f"):
            art, groesse = zeile[1:], 0
        elif zeile.startswith("s") and zeile[1:].isdigit():
            groesse = int(zeile[1:])
        elif zeile.startswith("n") and pid:
            name = zeile[1:]
            klein = name.lower()
            if klein.endswith(endungen) and (pid not in groesste or groesse > groesste[pid][0]):
                groesste[pid] = (groesse, name)
            if art == "txt" and any(o in klein for o in ordnerteile):
                mit_bibliothek.add(pid)
    heim = os.path.expanduser("~")
    return {p: Merkmale(modelldatei=groesste[p][1].replace(heim, "~", 1) if p in groesste else "", bibliothek=p in mit_bibliothek)
            for p in groesste.keys() | mit_bibliothek}


def laeuferprozesse(a: Aufnahme, b: Beobachtung, prozent: Callable[[int], float | None]) -> list[Laeuferprozess]:
    """Die Prozesse des Läufers mit Rolle, Modelldatei, Prozessorlast und Speicher; Hauptprozess zuerst."""
    merkmale = merkmale_lesen(a.laeufer_pids, b)
    ergebnis = []
    for pid in a.laeufer_pids:
        m = merkmale.get(pid, Merkmale())
        rolle = Laeuferrolle.HAUPT if pid in a.lauschend else Laeuferrolle.ARBEITER if m.arbeiter else Laeuferrolle.SONSTIG
        befehl = a.tabelle.befehlszeile.get(pid, "")
        ergebnis.append(Laeuferprozess(pid=pid, name=mit_eltern(programmname(befehl) or str(pid), pid, a.tabelle), rolle=rolle,
                                       modelldatei=m.modelldatei if rolle == Laeuferrolle.ARBEITER else "",
                                       cpu_prozent=_gerundet(prozent(pid)), gb=round(prozess_bytes(pid) / GIB, 1)))
    return sorted(ergebnis, key=lambda p: (ROLLENFOLGE[p.rolle], p.pid))


def _gerundet(wert: float | None) -> float | None:
    return None if wert is None else round(wert, 1)


@dataclass
class _Stand:
    """Was von der letzten Messung gebraucht wird: Zeitpunkt, Rechenzeit und Befehlszeile je pid."""

    zeit_s: float
    rechenzeit_s: dict[int, float]
    befehlszeile: dict[int, str]


class Lastmesser:
    """Misst aus den Aufnahmen der Beobachtung die Last des Läufers und die Fremdlast; merkt sich dafür die letzte
    Messung. Je Verbindung zur Leitstelle neu, damit kein Wert über eine lange Pause gemittelt wird."""

    def __init__(self, einstellungen: Callable[[], Einstellungen]) -> None:
        self._einstellungen = einstellungen
        self._vorher: _Stand | None = None

    def messen(self, a: Aufnahme | None) -> KnotenLast:
        kerne = os.cpu_count() or 1
        if a is None:                                   # Beobachtung abgeschaltet: nichts gemessen, nichts gemerkt
            self._vorher = None
            return KnotenLast(gemessen=False, kerne=kerne)
        vorher = self._vorher
        self._vorher = _Stand(a.zeit_s, dict(a.tabelle.rechenzeit_s), dict(a.tabelle.befehlszeile))
        dauer = a.zeit_s - vorher.zeit_s if vorher else 0.0

        def prozent(pid: int) -> float | None:
            """Prozent eines Kerns seit der letzten Messung; None bei neuer (oder wiederverwendeter) pid."""
            if not vorher or dauer <= 0 or pid not in vorher.rechenzeit_s or vorher.befehlszeile.get(pid) != a.tabelle.befehlszeile.get(pid):
                return None
            return max(0.0, a.tabelle.rechenzeit_s.get(pid, 0.0) - vorher.rechenzeit_s[pid]) / dauer * 100

        laeufer = laeuferprozesse(a, self._einstellungen().beobachtung, prozent) if a.laeufer_gesehen else []
        bekannt = a.laeufer_gesehen or not a.port          # ohne lsof ist der Läufer nicht von der Fremdlast zu trennen
        seit = vorher if vorher and dauer > 0 else None
        fremd = _fremdlast(a, seit, dauer, kerne) if seit and bekannt else None
        return KnotenLast(gemessen=a.laeufer_gesehen, kerne=kerne, laeufer=laeufer, fremd_prozent=fremd, apps=_appslast(a, seit, dauer))


def _rechenzeit_seit(a: Aufnahme, vorher: _Stand, pid: int) -> float:
    """Rechenzeit eines Prozesses seit der letzten Messung; ein neuer (oder wiederverwendeter) zählt ganz."""
    sekunden, alt = a.tabelle.rechenzeit_s.get(pid, 0.0), vorher.rechenzeit_s.get(pid)
    return sekunden - alt if alt is not None and sekunden >= alt else sekunden


def _fremdlast(a: Aufnahme, vorher: _Stand, dauer: float, kerne: int) -> float:
    """Rechenzeit aller Prozesse ohne Läufer, eigene und Apps seit der letzten Messung als Anteil aller Kerne (0 bis 100)."""
    ohne = a.laeufer_pids | a.eigene | a.app_pids
    summe = sum(_rechenzeit_seit(a, vorher, pid) for pid in a.tabelle.rechenzeit_s if pid not in ohne)
    return round(min(100.0, max(0.0, summe / (dauer * kerne) * 100)), 1)


def _appslast(a: Aufnahme, vorher: _Stand | None, dauer: float) -> AppsLast | None:
    """Je laufendem nativem Teil einer App des Stellwerks Prozessorlast (Prozent eines Kerns, ohne Wert beim ersten Mal)
    und Speicher; None ohne eingetragenes Stellwerk, ohne Zuordnung nur der Vermerk."""
    if a.apps is None:
        return None
    if not a.apps.gelesen:
        return AppsLast(gemessen=False, meldung=a.apps.meldung)
    teile = []
    for t, pids in a.app_prozesse:
        cpu = sum(_rechenzeit_seit(a, vorher, p) for p in pids) / dauer * 100 if vorher else None
        teile.append(AppTeil(app=t.app, app_name=t.app_name, teil=t.teil, name=t.name, pids=pids, cpu_prozent=_gerundet(cpu),
                             gb=round(sum(prozess_bytes(p) for p in pids) / GIB, 2)))
    return AppsLast(teile=teile)


# ── Beenden ──────────────────────────────────────────────────────────────
def _signal(pid: int, sig: int) -> None:
    """Der einzige Ort, an dem ein Signal an einen Prozess des Läufers geht (in Tests nachgestellt)."""
    os.kill(pid, sig)


def _lebt(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class Laeuferaufsicht:
    """Führt den Befehl `laeufer_prozess_beenden` aus: frisch prüfen, dann beenden."""

    def __init__(self, beobachter: Beobachter) -> None:
        self.beobachter = beobachter

    def pruefen(self, pid: int) -> Laeuferprozess | str:
        """Der Arbeiter, wenn `pid` gerade einer ist; sonst der Grund der Ablehnung."""
        e = self.beobachter.einstellungen
        a = aufnehmen(e, self.beobachter.dienste())
        if not a.port:
            return "kein Modell-Läufer eingetragen (nachbar.modell_laeufer)"
        if not a.laeufer_gesehen:
            return "lsof fehlt; ohne Prüfung wird nichts beendet"
        if pid not in a.tabelle.befehlszeile:
            return f"Prozess {pid} läuft nicht (mehr)"
        if pid not in a.laeufer_pids:
            return f"Prozess {pid} gehört nicht zum Modell-Läufer"
        if pid in a.lauschend:
            return f"Prozess {pid} ist der Hauptprozess des Läufers; der wird nie beendet"
        prozess = next(p for p in laeuferprozesse(a, e.beobachtung, lambda _: None) if p.pid == pid)
        if prozess.rolle != Laeuferrolle.ARBEITER:
            return (f"Prozess {pid} ({prozess.name}) ist kein Arbeiter (weder Modelldatei offen noch Bibliothek eines Rechenwerks "
                    "geladen); nur Arbeiter werden beendet")
        return prozess

    async def beenden(self, ziel: str) -> BefehlErgebnis:
        art = Befehlsart.LAEUFER_PROZESS_BEENDEN

        def ergebnis(erfolg: bool, meldung: str) -> BefehlErgebnis:
            return BefehlErgebnis(befehl=art, ziel=ziel, erfolg=erfolg, meldung=meldung)

        if not ziel.isdigit():
            return ergebnis(False, f"{ziel!r} ist keine Prozessnummer")
        geprueft = await asyncio.to_thread(self.pruefen, int(ziel))
        if isinstance(geprueft, str):
            log.warning("Arbeiter des Läufers nicht beendet: %s", geprueft)
            return ergebnis(False, geprueft)
        erfolg, weg = await self._beenden(geprueft.pid)
        wer = f"{geprueft.name} mit {geprueft.modelldatei}" if geprueft.modelldatei else geprueft.name
        meldung = f"{wer} {'beendet' if erfolg else 'nicht beendet'}: {weg}"
        log.warning("Arbeiter des Läufers (Prozess %s): %s", geprueft.pid, meldung)
        return ergebnis(erfolg, meldung)

    async def _beenden(self, pid: int) -> tuple[bool, str]:
        """Bitte, nach der Anhaltezeit hart. Liefert Erfolg und Weg."""
        frist_s = self.beobachter.einstellungen.beobachtung.anhaltezeit_s
        try:
            _signal(pid, signal.SIGTERM)
        except ProcessLookupError:
            return True, "war schon beendet"
        except PermissionError:
            return False, "keine Berechtigung"
        if await _weg_binnen(pid, frist_s):
            return True, "auf Bitte (SIGTERM)"
        try:
            _signal(pid, signal.SIGKILL)
        except ProcessLookupError:
            return True, "auf Bitte (SIGTERM)"
        if await _weg_binnen(pid, NACH_KILL_S):
            return True, f"nach {frist_s:g} s hart (SIGKILL)"
        return False, "lebt nach SIGKILL noch"


async def _weg_binnen(pid: int, frist_s: float) -> bool:
    ende = time.monotonic() + frist_s
    while time.monotonic() < ende:
        await asyncio.sleep(PRUEFABSTAND_S)
        if not _lebt(pid):
            return True
    return not _lebt(pid)
