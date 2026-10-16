"""Verbindung zur Leitstelle (optional): ausgehend, mit Schlüssel, mit wachsender Pause bei Abbruch.

Nach dem Verbinden: `knoten.anmelden`, dann Messwerte im Takt, die Dienstliste bei jeder Änderung (und
spätestens alle zehn Takte) und Antworten auf Befehle. Ohne Verbindung arbeitet der Maschinenraum
unverändert weiter. Der Zustand der Verbindung ist für die Oberfläche lesbar.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import platform
import socket
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

import websockets
from pydantic import BaseModel, Field, ValidationError

from . import __version__
from .konfig import Ordner
from .messen import Messer
from .protokoll import Befehl, KnotenAnmeldung
from .prozesse import Verwalter

log = logging.getLogger("maschinenraum")
PROTOKOLL = "leitstelle/1"
DIENSTLISTE_SPAETESTENS = 10                     # Takte


class Verbindung(str, Enum):
    AUS = "aus"                       # keine Leitstelle eingetragen
    OHNE_SCHLUESSEL = "ohne_schluessel"
    VERBINDET = "verbindet"
    VERBUNDEN = "verbunden"
    ABGEWIESEN = "abgewiesen"         # Schlüssel unbekannt oder erneuert
    NICHT_ERREICHBAR = "nicht_erreichbar"


class LeitstellenStand(BaseModel):
    adresse: str | None
    zustand: Verbindung
    meldung: str = ""
    seit: float | None = None         # Sekunden seit 1970, seit wann der Zustand gilt
    name: str | None = None           # Name, unter dem die Leitstelle diesen Rechner führt


class Umschlag(BaseModel):
    protokoll: str = PROTOKOLL
    art: str
    id: str = Field(default_factory=lambda: uuid4().hex)
    zeit: str = Field(default_factory=lambda: datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds"))
    von: str = "maschinenraum"
    an: str = "leitstelle"
    bezug: str | None = None
    nutzlast: dict[str, Any] = Field(default_factory=dict)


def _umschlag(art: str, nutzlast: BaseModel, bezug: str | None = None) -> str:
    return Umschlag(art=art, nutzlast=nutzlast.model_dump(mode="json"), bezug=bezug).model_dump_json()


class Leitstellenkanal:
    def __init__(self, ordner: Ordner, verwalter: Verwalter, messer: Messer) -> None:
        self.ordner, self.verwalter, self.messer = ordner, verwalter, messer
        self.stand = LeitstellenStand(adresse=None, zustand=Verbindung.AUS)
        self._aufgabe: asyncio.Task | None = None

    def _setzen(self, zustand: Verbindung, meldung: str = "") -> None:
        if zustand != self.stand.zustand or meldung != self.stand.meldung:
            self.stand = self.stand.model_copy(update={"zustand": zustand, "meldung": meldung, "seit": time.time()})

    # ── Lebenslauf ───────────────────────────────────────────────────────
    def starten(self) -> None:
        """(Neu) starten mit den aktuellen Einstellungen; ohne Adresse oder Schlüssel bleibt er aus."""
        self.anhalten_ohne_warten()
        e = self.ordner.einstellungen().leitstelle
        self.stand = LeitstellenStand(adresse=e.adresse, zustand=Verbindung.AUS, seit=time.time())
        if not e.kanal:
            return
        if not self.ordner.schluessel():
            self._setzen(Verbindung.OHNE_SCHLUESSEL, "Schlüssel aus der Leitstelle eintragen")
            return
        self._aufgabe = asyncio.create_task(self._schleife(e.kanal, e.wiederverbindung_max_s), name="leitstelle")

    def anhalten_ohne_warten(self) -> None:
        if self._aufgabe:
            self._aufgabe.cancel()
            self._aufgabe = None

    async def beenden(self) -> None:
        t, self._aufgabe = self._aufgabe, None
        if t:
            t.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await t

    # ── Verbindung ───────────────────────────────────────────────────────
    def anmeldung(self) -> KnotenAnmeldung:
        gesamt = self.messer.messen().speicher_gesamt_gb
        system = f"{platform.system()} {platform.mac_ver()[0] or platform.release()}"
        e = self.ordner.einstellungen()
        name = e.name or socket.gethostname().removesuffix(".local")
        return KnotenAnmeldung(name=name, betriebssystem=system, architektur=platform.machine(), speicher_gb=gesamt,
                               agent_version=__version__, messwege=self.messer.messwege(), durchleitung_port=e.durchleitung.port)

    async def _schleife(self, kanal: str, pause_max: float) -> None:
        pause = 1.0
        while True:
            self._setzen(Verbindung.VERBINDET)
            try:
                await self._verbunden(kanal)
                pause = 1.0
            except websockets.exceptions.InvalidStatus as f:
                self._setzen(Verbindung.ABGEWIESEN, f"Leitstelle lehnt ab (Status {f.response.status_code})")
                pause = pause_max
            except websockets.exceptions.ConnectionClosed as f:
                grund = f.rcvd.reason if f.rcvd else ""
                if grund in ("unbekannter_schluessel", "schluessel_erneuert"):
                    self._setzen(Verbindung.ABGEWIESEN, "Schlüssel unbekannt oder erneuert; neuen Schlüssel eintragen")
                    pause = pause_max
                else:
                    self._setzen(Verbindung.NICHT_ERREICHBAR, f"Verbindung beendet{': ' + grund if grund else ''}")
            except (OSError, asyncio.TimeoutError, websockets.exceptions.InvalidURI) as f:
                self._setzen(Verbindung.NICHT_ERREICHBAR, str(f)[:160])
            log.warning("Leitstelle: %s %s", self.stand.zustand.value, self.stand.meldung)
            await asyncio.sleep(pause)
            pause = min(pause * 2, pause_max)

    async def _verbunden(self, kanal: str) -> None:
        kopf = {"Authorization": f"Bearer {self.ordner.schluessel() or ''}"}
        async with websockets.connect(kanal, additional_headers=kopf, open_timeout=10, ping_interval=20) as ws:
            await ws.send(_umschlag("knoten.anmelden", await asyncio.to_thread(self.anmeldung)))
            sperre = asyncio.Lock()

            async def senden(text: str) -> None:
                async with sperre:
                    await ws.send(text)

            empfang = asyncio.create_task(self._empfangen(ws, senden))
            try:
                await self._senden_im_takt(senden, empfang)
            finally:
                empfang.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await empfang
            empfang.result()                                 # Verbindungsfehler des Empfangs weiterreichen

    async def _senden_im_takt(self, senden, empfang: asyncio.Task) -> None:
        takt = 0
        await senden(_umschlag("knoten.dienste", self.verwalter.liste()))
        while not empfang.done():
            await senden(_umschlag("knoten.messwerte", await asyncio.to_thread(self.messer.messen)))
            takt += 1
            if takt % DIENSTLISTE_SPAETESTENS == 0:
                await senden(_umschlag("knoten.dienste", self.verwalter.liste()))
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self._aenderung_abwarten(empfang), timeout=self.verwalter.einstellungen.messung.takt_s)
                await senden(_umschlag("knoten.dienste", self.verwalter.liste()))
                await asyncio.sleep(0.2)                     # mehrere Änderungen kurz hintereinander zusammenfassen

    async def _aenderung_abwarten(self, empfang: asyncio.Task) -> None:
        warten = asyncio.create_task(self.verwalter.aenderung.wait())
        try:
            await asyncio.wait({warten, empfang}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            warten.cancel()
        self.verwalter.aenderung.clear()
        if empfang.done():
            raise asyncio.TimeoutError

    async def _empfangen(self, ws, senden) -> None:
        aufgaben: set[asyncio.Task] = set()
        async for text in ws:
            try:
                u = Umschlag.model_validate_json(text)
            except ValidationError:
                log.warning("Unlesbare Nachricht der Leitstelle")
                continue
            if u.art == "knoten.befehl":
                t = asyncio.create_task(self._befehl(u, senden))
                aufgaben.add(t)
                t.add_done_callback(aufgaben.discard)
            elif u.art == "knoten.angemeldet":
                self.stand = self.stand.model_copy(update={"name": u.nutzlast.get("name")})
                self._setzen(Verbindung.VERBUNDEN)
                log.info("Bei der Leitstelle angemeldet als %s", u.nutzlast.get("name"))

    async def _befehl(self, u: Umschlag, senden) -> None:
        try:
            b = Befehl.model_validate(u.nutzlast)
        except ValidationError as f:
            log.warning("Ungültiger Befehl: %s", f.errors()[:1])
            return
        log.info("Befehl der Leitstelle: %s %s", b.befehl.value, b.ziel)
        ergebnis = await self.verwalter.befehl(b, von_leitstelle=True)
        with contextlib.suppress(websockets.exceptions.ConnectionClosed):
            await senden(_umschlag("knoten.befehl_ergebnis", ergebnis, bezug=u.id))
