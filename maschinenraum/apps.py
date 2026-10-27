"""Apps des Stellwerks auf diesem Rechner (`nachbar.stellwerk`): welche Prozesse zu welchem Teil einer App gehören.

Das Stellwerk startet die Apps des Rechners (keine KI-Dienste). Ihre Prozesse sind weder ein Modell am Leitstand vorbei
noch Last, die der Mensch erzeugt; die Leitstelle soll sie aber sehen. Im Takt der Beobachtung liest der Maschinenraum
darum `GET <stellwerk>/api/stand` (nur lesend, kurze Frist) und ordnet jedem laufenden nativen Teil seine Prozesse samt
Nachfahren zu (`pids` je Teil, ab der Fassung des Stellwerks, die sie meldet). Docker-Teile bleiben weg: ihre Last steht
beim Docker-Rechner (`dockerlast.py`).

Ohne Antwort oder ohne Prozessnummern wird nichts zugeordnet; das steht als Vermerk in `knoten.last.apps`, und die
Beobachtung arbeitet weiter wie ohne Stellwerk. Spricht ein Prozess einer App den Modell-Läufer direkt an, bleibt das
eine Umgehung (beobachtung.py nimmt ihn dort nicht aus). Der Maschinenraum steuert die Apps nicht.
"""

from __future__ import annotations

import logging
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field

from dienstkern.messen import Prozesstabelle
from pydantic import BaseModel, Field, ValidationError

from .konfig import Einstellungen

log = logging.getLogger("maschinenraum")
FRIST_S = 2.0                         # so lange darf das Stellwerk für seinen Stand brauchen (wie beim Modell-Läufer)
DOCKER = "docker"                     # Art eines Teils, der im Docker-Rechner läuft


class _Teil(BaseModel):
    """Ein Teil einer App, so weit die Zuordnung ihn braucht (das Stellwerk meldet mehr)."""

    kennung: str
    name: str
    art: str
    pids: list[int] | None = None     # None: Fassung des Stellwerks ohne Prozessnummern


class _App(BaseModel):
    kennung: str
    name: str
    teile: list[_Teil] = Field(default_factory=list)


class _Stand(BaseModel):
    apps: list[_App] = Field(default_factory=list)


@dataclass
class Appteil:
    """Ein nativer Teil einer App mit den Prozessen, die das Stellwerk für ihn nennt."""

    app: str
    app_name: str
    teil: str
    name: str
    pids: list[int]


@dataclass
class Stellwerkstand:
    """Was das Stellwerk in diesem Takt gesagt hat. `gelesen` ist falsch ohne Antwort oder ohne Prozessnummern; dann
    sagt `teile` nichts und `meldung` sagt, warum."""

    gelesen: bool
    meldung: str = ""
    teile: list[Appteil] = field(default_factory=list)       # native Teile mit Prozessen, in der Reihenfolge des Stellwerks


def _holen(adresse: str) -> bytes:
    """Der Stand des Stellwerks, roh. Der einzige Ort, an dem der Maschinenraum das Stellwerk anspricht (in Tests
    nachgestellt)."""
    with urllib.request.urlopen(adresse.rstrip("/") + "/api/stand", timeout=FRIST_S) as antwort:
        return antwort.read()


def lesen(adresse: str) -> Stellwerkstand:
    """Die nativen Teile mit Prozessen aus dem Stand des Stellwerks unter `adresse`."""
    try:
        roh = _holen(adresse)
    except (OSError, urllib.error.URLError, ValueError) as f:
        grund = getattr(f, "reason", None) or f
        return Stellwerkstand(gelesen=False, meldung=f"Stellwerk unter {adresse} antwortet nicht ({grund})")
    try:
        stand = _Stand.model_validate_json(roh)
    except ValidationError:
        return Stellwerkstand(gelesen=False, meldung=f"Antwort des Stellwerks unter {adresse} unlesbar")
    nativ = [(a, t) for a in stand.apps for t in a.teile if t.art != DOCKER]
    if any(t.pids is None for _, t in nativ):
        return Stellwerkstand(gelesen=False, meldung="Stellwerk meldet keine Prozessnummern (Fassung ohne pids); seine Apps sind nicht zugeordnet")
    return Stellwerkstand(gelesen=True, teile=[Appteil(app=a.kennung, app_name=a.name, teil=t.kennung, name=t.name, pids=list(t.pids or []))
                                               for a, t in nativ if t.pids])


def zuordnen(teile: list[Appteil], tabelle: Prozesstabelle, vergeben: set[int]) -> list[tuple[Appteil, list[int]]]:
    """Je Teil seine lebenden Prozesse samt Nachfahren, jeder Prozess nur einmal: zuerst bekommt jeder Teil die Prozesse,
    die das Stellwerk für ihn nennt (beim ersten, der ihn nennt), dann deren Nachfahren bis zu einem Prozess, der schon
    vergeben ist. So bleibt ein Teil, den ein anderer gestartet hat, samt seinen Kindern bei sich. Was schon `vergeben`
    ist (Läufer, Maschinenraum und seine Dienste), zählt nicht. Teile ohne lebenden Prozess entfallen."""
    belegt = set(vergeben)
    eigene: list[list[int]] = []
    for t in teile:
        genannt = [p for p in dict.fromkeys(t.pids) if p in tabelle.befehlszeile and p not in belegt]
        belegt.update(genannt)
        eigene.append(genannt)
    kinder: dict[int, list[int]] = {}
    for p, eltern in tabelle.eltern.items():
        kinder.setdefault(eltern, []).append(p)
    for pids in eigene:
        offen = list(pids)
        while offen:
            for kind in kinder.get(offen.pop(), []):
                if kind not in belegt:
                    belegt.add(kind)
                    pids.append(kind)
                    offen.append(kind)
    return [(t, sorted(pids)) for t, pids in zip(teile, eigene) if pids]


class Stellwerkleser:
    """Liest das Stellwerk im Takt der Beobachtung, wenn `nachbar.stellwerk` eingetragen ist. Ins Protokoll kommt nur ein
    Wechsel (gelesen, nicht gelesen und warum), nicht jeder Takt."""

    def __init__(self, einstellungen: Callable[[], Einstellungen]) -> None:
        self._einstellungen = einstellungen
        self._meldung: str | None = None            # Meldung des letzten Lesens; "" gelesen, None noch keins

    def lesen(self) -> Stellwerkstand | None:
        """Der Stand dieses Takts; None, wenn kein Stellwerk eingetragen ist (dann wird nichts gefragt)."""
        adresse = self._einstellungen().nachbar.stellwerk
        if not adresse:
            self._meldung = None
            return None
        stand = lesen(adresse)
        if stand.meldung != self._meldung:
            if stand.meldung:
                log.info("Apps des Stellwerks nicht zugeordnet: %s", stand.meldung)
            elif self._meldung:
                log.info("Apps des Stellwerks wieder zugeordnet")
            self._meldung = stand.meldung
        return stand
