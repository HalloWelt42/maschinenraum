"""Last des Docker-Rechners für `knoten.last` (Feld `docker`): Kerne und Speicher des Docker-Rechners und je laufendem
Container Name, Compose-Projekt, Prozessorlast und Speicher. Der Maschinenraum misst nur; wem ein Container gehört und
was aus seiner Last folgt, entscheidet die Leitstelle.

Auf dem Mac laufen die Container in einer virtuellen Maschine, die auf dem Rechner als ein einziger Prozess erscheint;
was darin welcher Container rechnet, weiß nur Docker. Gemessen wird darum mit der Befehlszeile von Docker, nur lesend:
`docker info` (Kerne, Speicher), `docker ps` (Compose-Projekt aus dem Label) und `docker stats --no-stream`
(Prozessorlast in Prozent eines Kerns, wie Docker sie rechnet, und belegter Speicher). Die drei laufen nebeneinander;
`docker stats` allein braucht ein bis zwei Sekunden, weil es zweimal misst, bei voll ausgelastetem Docker-Rechner auch
vier bis sieben (gemessen am 27.10.2026). Zusammen dürfen sie höchstens einen Takt der Beobachtung dauern
(`beobachtung.takt_s`): öfter, als Docker antworten kann, lohnt keine Messung. Jeder Aufruf fragt mit `--format` nur
nach den Feldern, die gebraucht werden: Umgebung und Einstellungen der Container kommen nie heraus.

Ohne Docker, wenn es nicht antwortet oder ein Aufruf scheitert, ist `gemessen` falsch und die übrigen Felder sagen
nichts: eine halbe Messung (Container ohne Projekt) ließe deren Last keiner Anwendung zuordnen.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from collections.abc import Callable
from time import monotonic

from dienstkern.messen import GIB

from .konfig import Einstellungen
from .protokoll import DockerContainer, DockerLast

log = logging.getLogger("maschinenraum")
PROJEKT_LABEL = "com.docker.compose.project"
# Je Zeile die Felder mit Tabulator getrennt (Namen, Kennungen und Projekte enthalten keinen)
INFO = ["info", "--format", "{{.NCPU}}\t{{.MemTotal}}"]
LISTE = ["ps", "--format", '{{.ID}}\t{{.Label "' + PROJEKT_LABEL + '"}}']
STATS = ["stats", "--no-stream", "--format", "{{.ID}}\t{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"]

#: Einheiten, wie Docker Speicher schreibt (meist binär: MiB, GiB)
EINHEITEN = {"b": 1, "kb": 1e3, "mb": 1e6, "gb": 1e9, "tb": 1e12,
             "kib": 1024, "mib": 1024 ** 2, "gib": 1024 ** 3, "tib": 1024 ** 4}
GROESSE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([a-z]+)\s*$", re.IGNORECASE)


def _aufrufen(befehle: list[list[str]], frist_s: float) -> list[str | None] | None:
    """Startet die Aufrufe von docker nebeneinander und sammelt ihre Ausgaben: None für einen, der scheitert oder die
    gemeinsame Frist überschreitet (er wird dann beendet). None insgesamt, wenn es docker auf diesem Rechner nicht gibt.
    Der einzige Ort, an dem docker aufgerufen wird (in Tests nachgestellt)."""
    programm = shutil.which("docker")
    if not programm:
        return None
    laeufe: list[subprocess.Popen[str] | None] = []
    for befehl in befehle:
        try:
            laeufe.append(subprocess.Popen([programm, *befehl], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                           stderr=subprocess.DEVNULL, text=True))
        except OSError:
            laeufe.append(None)
    ende = monotonic() + frist_s
    ausgaben: list[str | None] = []
    for lauf in laeufe:
        if lauf is None:
            ausgaben.append(None)
            continue
        try:
            aus, _ = lauf.communicate(timeout=max(0.0, ende - monotonic()))
            ausgaben.append(aus if lauf.returncode == 0 else None)
        except subprocess.TimeoutExpired:
            lauf.kill()
            lauf.wait()
            ausgaben.append(None)
        finally:
            if lauf.stdout:
                lauf.stdout.close()
    return ausgaben


def _bytes(text: str) -> float | None:
    """Speicher, wie Docker ihn schreibt ("6.127GiB", "274.7MiB", "0B"), in Bytes; None ohne Wert (Docker schreibt dann
    Striche) oder bei unbekannter Einheit."""
    treffer = GROESSE.match(text)
    faktor = EINHEITEN.get(treffer.group(2).lower()) if treffer else None
    return float(treffer.group(1)) * faktor if treffer and faktor else None


def _prozent(text: str) -> float | None:
    """Prozent, wie Docker sie schreibt ("206.76%"), als Zahl; None ohne Wert (Docker schreibt dann Striche)."""
    try:
        return round(float(text.strip().removesuffix("%")), 1)
    except ValueError:
        return None


def auswerten(info: str, liste: str, stats: str) -> DockerLast:
    """Die drei Ausgaben als Messung; ValueError, wenn `docker info` nicht wie erwartet antwortet."""
    kerne, speicher = info.strip().split("\t")
    projekte: dict[str, str] = {}
    for zeile in liste.splitlines():
        kennung, _, projekt = zeile.partition("\t")
        if kennung.strip():
            projekte[kennung.strip()] = projekt.strip()
    container = []
    for zeile in stats.splitlines():
        teile = zeile.split("\t")
        if len(teile) != 4:
            continue
        kennung, name, cpu, belegt = (t.strip() for t in teile)
        b = _bytes(belegt.split("/")[0])
        container.append(DockerContainer(name=name, projekt=projekte.get(kennung, ""), cpu_prozent=_prozent(cpu),
                                         gb=None if b is None else round(b / GIB, 2)))
    return DockerLast(kerne=int(kerne), speicher_gb=round(int(speicher) / GIB, 1), container=sorted(container, key=lambda c: c.name))


def messen(frist_s: float) -> tuple[DockerLast, str]:
    """Eine Messung jetzt, höchstens `frist_s` lang, und, wenn sie nicht gelang, warum (für das Protokoll)."""
    ausgaben = _aufrufen([INFO, LISTE, STATS], frist_s)
    if ausgaben is None:
        return DockerLast(gemessen=False), "docker ist auf diesem Rechner nicht zu finden"
    info, liste, stats = ausgaben
    if info is None:
        return DockerLast(gemessen=False), f"Docker antwortet nicht (docker info, Frist {frist_s:g} s)"
    if liste is None or stats is None:
        return DockerLast(gemessen=False), f"Docker antwortet nicht vollständig (docker {'ps' if liste is None else 'stats'}, Frist {frist_s:g} s)"
    try:
        return auswerten(info, liste, stats), ""
    except ValueError:
        return DockerLast(gemessen=False), "Antwort von docker info unlesbar"


class Dockermesser:
    """Misst im Takt der Beobachtung den Docker-Rechner, wenn Beobachtung und `beobachtung.docker` an sind. Ins Protokoll
    kommt nur ein Wechsel (gemessen, nicht gemessen und warum), nicht jeder Takt."""

    def __init__(self, einstellungen: Callable[[], Einstellungen]) -> None:
        self._einstellungen = einstellungen
        self._grund: str | None = None              # Grund der letzten Messung; "" gelungen, None noch keine

    def messen(self) -> DockerLast | None:
        """Die Messung dieses Takts; None, wenn abgeschaltet (dann wird gar nicht gemessen)."""
        b = self._einstellungen().beobachtung
        if not (b.aktiv and b.docker):
            self._grund = None
            return None
        ergebnis, grund = messen(b.takt_s)
        if grund != self._grund:
            if grund:
                log.info("Docker-Rechner nicht gemessen: %s", grund)
            elif self._grund:
                log.info("Docker-Rechner wieder gemessen")
            self._grund = grund
        return ergebnis
