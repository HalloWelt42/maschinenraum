"""Beobachtung: Zugriffe auf die Modelle dieses Rechners, die nicht über die Leitstelle laufen.

Zwei Arten (Grundsatz des Nutzers: alles nur über die Leitstelle; was daran vorbeigeht, soll sichtbar sein):
- Verbindungen zum Modell-Läufer (`nachbar.modell_laeufer`), die nicht vom Maschinenraum selbst kommen: von einem
  Programm auf diesem Rechner (mit Name und Kennung) oder aus dem Netz (mit Adresse; ob es der Rechner der Leitstelle
  ist, steht dabei, denn die Leitstelle spricht den Läufer direkt an). Was davon eine Umgehung ist, deutet die
  Leitstelle.
- Programme mit viel Speicher, die weder Dienst des Maschinenraums noch Teil des Läufers sind, etwa ein Bildmodell im
  eigenen Prozess. Was dauerhaft dazugehört (Browser, virtuelle Maschinen), steht in den Ausnahmen der Einstellung.

Gemessen mit lsof (Verbindungen) und der Prozesstabelle samt Speicher je Prozess aus dem Dienstkern. Ohne lsof bleibt
die Beobachtung aus und meldet das, statt eine leere Liste als "nichts gefunden" auszugeben.

Je Takt wird einmal aufgenommen (`Aufnahme`: Prozesstabelle, Verbindungen am Läufer-Port); daraus entstehen die
Zugriffe am Leitstand vorbei hier und die Last von Läufer und Rechner in `laeuferlast.py`.
"""

from __future__ import annotations

import ipaddress
import os
import re
import shutil
import socket
import subprocess
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from time import monotonic
from urllib.parse import urlparse

from dienstkern.messen import GIB, Prozesstabelle, prozess_bytes

from .konfig import Einstellungen
from .protokoll import Fremdart, Fremdzugriff, Fremdzugriffe

BEFEHL_HOECHSTENS = 160


@dataclass
class Verbindung:
    """Eine Zeile aus lsof: Prozess und Endpunkte einer offenen TCP-Verbindung."""

    pid: int
    programm: str
    lokal: tuple[str, int]
    gegen: tuple[str, int]


def _endpunkt(text: str) -> tuple[str, int]:
    adresse, _, port = text.rpartition(":")
    return adresse.strip("[]"), int(port)


def verbindungen_lesen(port: int) -> tuple[list[Verbindung], set[int]] | None:
    """Offene TCP-Verbindungen, an denen `port` beteiligt ist (beide Enden, auch die der Programme auf diesem Rechner),
    und die Prozesse, die auf `port` lauschen; ein Aufruf von lsof für beides. None, wenn lsof fehlt."""
    aus = _lsof("-iTCP:%d" % port, "-sTCP:LISTEN,ESTABLISHED", "-F", "pcnT")
    if aus is None:
        return None
    verbindungen: list[Verbindung] = []
    lauschend: set[int] = set()
    pid, programm, name = 0, "", ""
    for zeile in aus.splitlines():
        if zeile.startswith("p"):
            pid = int(zeile[1:])
        elif zeile.startswith("c"):
            programm = zeile[1:]
        elif zeile.startswith("n"):
            name = zeile[1:]
        elif zeile == "TST=LISTEN":
            lauschend.add(pid)
        elif zeile == "TST=ESTABLISHED" and "->" in name:
            lokal, gegen = name.split("->", 1)
            try:
                verbindungen.append(Verbindung(pid, programm, _endpunkt(lokal), _endpunkt(gegen)))
            except ValueError:
                continue
    return verbindungen, lauschend


def arbeitsordner(pids: Iterable[int]) -> dict[int, str]:
    """Arbeitsordner der genannten Prozesse (ein Aufruf von lsof); fehlende bleiben weg."""
    liste = ",".join(str(p) for p in pids)
    aus = _lsof("-a", "-p", liste, "-d", "cwd", "-F", "pn") if liste else None
    ordner: dict[int, str] = {}
    pid = 0
    for zeile in (aus or "").splitlines():
        if zeile.startswith("p"):
            pid = int(zeile[1:])
        elif zeile.startswith("n") and pid:
            ordner[pid] = zeile[1:].replace(os.path.expanduser("~"), "~", 1)
    return ordner


def _lsof(*args: str) -> str | None:
    if not shutil.which("lsof"):
        return None
    try:
        return subprocess.run(["lsof", "-nP", "-b", "-w", *args], capture_output=True, text=True, timeout=10,
                              env={**os.environ, "LC_ALL": "C"}).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None


def _ist_hier(adresse: str) -> bool:
    try:
        return ipaddress.ip_address(adresse).is_loopback
    except ValueError:
        return False


def _adresse_von(url: str | None) -> str | None:
    """IP-Adresse des Rechners hinter einer Adresse (etwa der Leitstelle); None, wenn sie sich nicht auflösen lässt."""
    rechner = urlparse(url or "").hostname
    if not rechner:
        return None
    try:
        return socket.gethostbyname(rechner)
    except OSError:
        return None


def _kurz(befehl: str) -> str:
    return befehl if len(befehl) <= BEFEHL_HOECHSTENS else befehl[: BEFEHL_HOECHSTENS - 3] + "..."


#: Programm in einem Paket des Mac: der Name nach Contents/MacOS/ bis zum ersten Schalter (Namen enthalten Leerzeichen)
PAKET = re.compile(r"\.app/Contents/MacOS/(.+?)(?:\s+-|$)")


def programmname(befehl: str) -> str:
    """Lesbarer Name aus der Befehlszeile: bei Python und Node das Modul (-m) oder Skript statt des Interpreters, bei
    einem Programm im Paket des Mac der ganze Name (auch mit Leerzeichen)."""
    if paket := PAKET.search(befehl):
        return paket.group(1).strip()
    teile = befehl.split()
    if not teile:
        return ""
    name = os.path.basename(teile[0])
    if name.lower().startswith(("python", "node")):
        for i, t in enumerate(teile[1:], start=1):
            if t == "-m" and i + 1 < len(teile):
                return teile[i + 1]
            if t.endswith((".py", ".js", ".mjs")):
                return os.path.basename(t)
    return name


def eigene_pids(dienste, tabelle: Prozesstabelle) -> set[int]:
    """Prozesse der Dienste, die der Maschinenraum verwaltet: eigene Prozessgruppe oder übernommener Prozess samt
    Nachfahren."""
    pids: set[int] = set()
    for d in dienste:
        gruppe = getattr(getattr(d, "stand", None), "gruppe", None)
        if gruppe:
            pids.update(tabelle.in_gruppe(gruppe))
        fremd = getattr(d, "fremd_pid", None)
        if fremd:
            pids.update(tabelle.mit_nachfahren(fremd))
    return pids


#: Eltern, die nichts über ein Programm verraten (Start aus der Shell oder vom System)
NICHTSSAGENDE_ELTERN = {"launchd", "zsh", "bash", "sh", "fish", "login", "Terminal", "tmux", "screen", "nohup", "env", "python", "Python"}


def mit_eltern(name: str, pid: int, tabelle: Prozesstabelle) -> str:
    """Name mit dem Programm, das ihn gestartet hat, wenn das mehr verrät (etwa "uvicorn (pappagei)")."""
    eltern = tabelle.eltern.get(pid)
    vater = programmname(tabelle.befehlszeile.get(eltern, "")) if eltern and eltern > 1 else ""
    return f"{name} ({vater})" if vater and vater != name and vater not in NICHTSSAGENDE_ELTERN else name


@dataclass
class Aufnahme:
    """Was ein Takt einmal misst und Zugriffe am Leitstand vorbei wie Last gemeinsam nutzen: die Prozesstabelle (ein
    Aufruf von ps) und die Verbindungen am Läufer-Port samt lauschendem Prozess (ein Aufruf von lsof)."""

    tabelle: Prozesstabelle
    zeit_s: float                                       # time.monotonic() der Prozesstabelle
    port: int | None                                    # Port des Modell-Läufers; None: keiner eingetragen
    laeufer_gesehen: bool                               # Port eingetragen und mit lsof gelesen; sonst sagt der Läufer-Teil nichts
    verbindungen: list[Verbindung] = field(default_factory=list)
    lauschend: set[int] = field(default_factory=set)    # Hauptprozess des Läufers (lauscht am Port)
    laeufer_pids: set[int] = field(default_factory=set) # lauschende Prozesse samt Nachfahren
    eigene: set[int] = field(default_factory=set)       # Dienste des Maschinenraums und er selbst samt Nachfahren


def aufnehmen(einstellungen: Einstellungen, dienste: Iterable) -> Aufnahme:
    """Eine Aufnahme jetzt (auch ohne aktive Beobachtung, etwa für die Prüfung vor dem Beenden eines Arbeiters)."""
    port = urlparse(einstellungen.nachbar.modell_laeufer or "").port
    tabelle, zeit_s = Prozesstabelle(), monotonic()
    gelesen = verbindungen_lesen(port) if port else None
    verbindungen, lauschend = gelesen if gelesen is not None else ([], set())
    return Aufnahme(tabelle=tabelle, zeit_s=zeit_s, port=port, laeufer_gesehen=gelesen is not None,
                    verbindungen=verbindungen, lauschend=lauschend,
                    laeufer_pids={p for server in lauschend for p in tabelle.mit_nachfahren(server)},
                    eigene=eigene_pids(dienste, tabelle) | set(tabelle.mit_nachfahren(os.getpid())))


class Beobachter:
    """Misst im Takt der Beobachtung, was am Leitstand vorbei auf Modelle dieses Rechners zugreift. Einstellungen und
    Dienste werden je Messung abgerufen (die Oberfläche kann beide ändern)."""

    def __init__(self, einstellungen: Callable[[], Einstellungen], dienste: Callable[[], Iterable]) -> None:
        self._einstellungen = einstellungen
        self.dienste = dienste

    @property
    def einstellungen(self) -> Einstellungen:
        return self._einstellungen()

    def aufnehmen(self) -> Aufnahme | None:
        """Die Aufnahme dieses Takts; None, wenn die Beobachtung abgeschaltet ist (dann wird gar nicht gemessen)."""
        e = self.einstellungen
        return aufnehmen(e, self.dienste()) if e.beobachtung.aktiv else None

    def fremde(self, a: Aufnahme | None) -> Fremdzugriffe:
        """Zugriffe am Leitstand vorbei aus der Aufnahme. Ohne Aufnahme oder, bei eingetragenem Läufer, ohne lsof ohne
        Aussage."""
        if a is None or (a.port and not a.laeufer_gesehen):
            return Fremdzugriffe(beobachtet=False)
        zugriffe: list[Fremdzugriff] = []
        if a.port:
            zugriffe += self._laeuferzugriffe(a.verbindungen, a.port, a.laeufer_pids, a.tabelle)
        zugriffe += self._speicherzugriffe(a.tabelle, a.laeufer_pids | a.eigene | {os.getpid()})
        ordner = arbeitsordner(z.pid for z in zugriffe if z.pid)
        for z in zugriffe:
            if z.pid:
                z.ordner = ordner.get(z.pid, "")
                z.wer = mit_eltern(z.wer, z.pid, a.tabelle)
        return Fremdzugriffe(zugriffe=zugriffe)

    def _laeuferzugriffe(self, verbindungen: list[Verbindung], port: int, laeufer_pids: set[int], tabelle: Prozesstabelle) -> list[Fremdzugriff]:
        """Programme auf diesem Rechner als Kunde (Gegenende ist der Läufer-Port), Gegenstellen im Netz von der Seite des
        Läufers aus (sein Ende ist der Port, das Gegenende nicht dieser Rechner). Der Maschinenraum selbst zählt nicht."""
        hier: dict[int, Fremdzugriff] = {}
        netz: dict[str, Fremdzugriff] = {}
        leitstelle = _adresse_von(self.einstellungen.leitstelle.adresse)
        for v in verbindungen:
            if v.gegen[1] == port and v.pid not in laeufer_pids:
                if v.pid == os.getpid():
                    continue
                befehl = tabelle.befehlszeile.get(v.pid, "")
                z = hier.setdefault(v.pid, Fremdzugriff(art=Fremdart.LAEUFER, wer=programmname(befehl) or v.programm, pid=v.pid, befehl=_kurz(befehl)))
                z.verbindungen += 1
            elif v.lokal[1] == port and not _ist_hier(v.gegen[0]):
                z = netz.setdefault(v.gegen[0], Fremdzugriff(art=Fremdart.LAEUFER, wer=v.gegen[0],
                                                              vom_rechner_der_leitstelle=v.gegen[0] == leitstelle))
                z.verbindungen += 1
        return [*hier.values(), *netz.values()]

    def _speicherzugriffe(self, tabelle: Prozesstabelle, bekannt: set[int]) -> list[Fremdzugriff]:
        b = self.einstellungen.beobachtung
        ausnahmen = [a.lower() for a in b.ausnahmen]
        ergebnis = []
        for pid, befehl in tabelle.befehlszeile.items():
            if pid in bekannt or any(a in befehl.lower() for a in ausnahmen):
                continue
            gb = prozess_bytes(pid) / GIB
            if gb >= b.schwelle_gb:
                ergebnis.append(Fremdzugriff(art=Fremdart.SPEICHER, wer=programmname(befehl) or str(pid), pid=pid, befehl=_kurz(befehl), gb=round(gb, 1)))
        return sorted(ergebnis, key=lambda z: -(z.gb or 0))
