"""Verbindung zur Leitstelle (optional): ausgehend, mit Schlüssel, mit wachsender Pause bei Abbruch.

Nach dem Verbinden: `knoten.anmelden`, dann Messwerte im Takt, die Dienstliste bei jeder Änderung (und
spätestens alle zehn Takte), im ruhigeren Takt der Beobachtung Zugriffe am Leitstand vorbei (`knoten.fremde`) und die
Last von Läufer, Rechner und Docker-Rechner (`knoten.last`), und Antworten auf Befehle. Ohne Verbindung arbeitet der Maschinenraum
unverändert weiter. Der Zustand der Verbindung ist für die Oberfläche lesbar.

Ausfall (die Leitstelle startet neu, das Netz bricht weg): neu verbinden mit wachsender Pause bis
`wiederverbindung_max_s`, nach einer gelungenen Anmeldung wieder ab einer Sekunde. Ins Protokoll kommt je Ausfall eine Warnung
(und eine weitere nur, wenn sich die Art ändert, etwa abgewiesen), die übrigen Versuche nur in die Fehlersuche, das
Wiederverbinden als Zeile mit Dauer und Versuchen. Was eine Verbindung an Aufgaben startet (Empfang, Beobachtung), endet
mit ihr; nach dem Neuverbinden kommt der aktuelle Stand neu (Anmeldung, Dienstliste, Messwerte, Beobachtung).

Schlaf (schlaf.py meldet ihn): vor dem Einschlafen `knoten.schlaeft`, höchstens `VERMERK_S` auf
`knoten.schlaf_vermerkt` warten (eine ältere Leitstelle antwortet nie), dann mit dem Grund `schlaeft` schließen. Bis zum
Aufwachen ruht die Verbindung; danach sofort neu, eine noch offen scheinende Verbindung wird geschlossen. Ein Wächter
hält es für aufgewacht, wenn `WACHZEIT_S` Wachzeit ohne Weckmeldung vergehen (time.monotonic zählt auf dem Mac den
Schlaf nicht mit).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import platform
import socket
import time
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

import websockets
import websockets.exceptions
from pydantic import BaseModel, Field, ValidationError

from .beobachtung import Beobachter
from . import __version__
from .dockerlast import Dockermesser
from .konfig import Ordner
from .laeuferlast import Laeuferaufsicht, Lastmesser
from .messen import Messer
from .protokoll import Befehl, Befehlsart, Fremdzugriffe, KnotenAnmeldung, KnotenLast, KnotenSchlaeft, Schlafgrund
from .prozesse import Verwalter

log = logging.getLogger("maschinenraum")
PROTOKOLL = "leitstelle/1"
DIENSTLISTE_SPAETESTENS = 10                     # Takte
VERMERK_S = 3.0                                  # so lange wartet das Einschlafen auf knoten.schlaf_vermerkt
WACHZEIT_S = 120.0                               # Wächter: so viel Wachzeit ohne Weckmeldung, dann gilt der Rechner als wach


class Verbindung(str, Enum):
    AUS = "aus"                       # keine Leitstelle eingetragen
    OHNE_SCHLUESSEL = "ohne_schluessel"
    VERBINDET = "verbindet"
    VERBUNDEN = "verbunden"
    ABGEWIESEN = "abgewiesen"         # Schlüssel unbekannt oder erneuert
    NICHT_ERREICHBAR = "nicht_erreichbar"
    SCHLAEFT = "schlaeft"             # der Rechner schläft; die Verbindung ruht bis zum Aufwachen


class Ausfall:
    """Ein Ausfall der Verbindung, vom ersten gescheiterten Versuch bis zur nächsten Anmeldung: entscheidet, welcher
    Versuch eine Warnung wert ist (der erste und jeder, dessen Art sich ändert), und zählt für die Zeile beim Wiederverbinden."""

    def __init__(self) -> None:
        self.seit: float | None = None
        self.versuche = 0
        self._art: Verbindung | None = None

    def gescheitert(self, art: Verbindung) -> bool:
        """Ein gescheiterter Versuch; True, wenn er ins Protokoll gehört."""
        if self.seit is None:
            self.seit = time.monotonic()
        self.versuche += 1
        neu, self._art = art != self._art, art
        return neu

    def beenden(self) -> tuple[float, int] | None:
        """Wieder verbunden: Dauer und Versuche des Ausfalls, None, wenn keiner war."""
        if self.seit is None:
            return None
        ergebnis = (time.monotonic() - self.seit, self.versuche)
        self.seit, self.versuche, self._art = None, 0, None
        return ergebnis


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


Senden = Callable[[str], Awaitable[None]]


class Leitstellenkanal:
    def __init__(self, ordner: Ordner, verwalter: Verwalter, messer: Messer) -> None:
        self.ordner, self.verwalter, self.messer = ordner, verwalter, messer
        self.beobachter = Beobachter(lambda: self.verwalter.einstellungen, lambda: self.verwalter.dienste.values())
        self.laeuferaufsicht = Laeuferaufsicht(self.beobachter)
        self.stand = LeitstellenStand(adresse=None, zustand=Verbindung.AUS)
        self._aufgabe: asyncio.Task | None = None
        self._ws: Any = None                         # die laufende Verbindung: Schlaf melden, beim Aufwachen schließen
        self._senden: Senden | None = None
        self._wach = asyncio.Event()                 # gelöscht, solange der Rechner schläft
        self._wach.set()
        self._unterbrechen = asyncio.Event()         # beendet die Pause vor dem nächsten Versuch (Aufwachen)
        self._pause_s = 1.0
        self._ausfall = Ausfall()
        self._vermerkt: dict[str, asyncio.Future[None]] = {}
        self._waechter: asyncio.Task | None = None
        verwalter.vor_speicherabbruch = self._speicherabbruch_melden

    async def _speicherabbruch_melden(self, _eingriff: Any) -> None:
        """Die Speicherwache beendet gleich einen Dienst: die Dienstliste mit seiner Sperre sofort an die Leitstelle, damit sie
        den Grund kennt, bevor die Verbindung zum Dienst abreißt (sie bricht den Auftrag dann ab, statt ihn zu wiederholen)."""
        if self._senden is not None:
            with contextlib.suppress(websockets.exceptions.ConnectionClosed, OSError):
                await self._senden(_umschlag("knoten.dienste", self.verwalter.liste()))

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
        for aufgabe in (t, self._waechter):
            if aufgabe:
                aufgabe.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await aufgabe
        self._waechter = None

    # ── Schlaf ───────────────────────────────────────────────────────────
    async def einschlafen(self, grund: Schlafgrund) -> None:
        """Der Rechner schläft gleich ein: der Leitstelle melden und die Verbindung schließen. Dauert höchstens etwa
        zweimal `VERMERK_S`; der Aufrufer quittiert danach den Schlaf bei macOS. Ohne Leitstelle gibt es nichts zu tun."""
        if self._aufgabe is None:
            return
        self._wach.clear()
        self._setzen(Verbindung.SCHLAEFT, "Rechner schläft" + (" nach Leerlauf" if grund == Schlafgrund.LEERLAUF else ""))
        ws, senden = self._ws, self._senden
        if ws is not None and senden is not None:
            await self._schlaf_melden(senden, grund)
            with contextlib.suppress(websockets.exceptions.WebSocketException, OSError, asyncio.TimeoutError):
                await asyncio.wait_for(ws.close(1000, "schlaeft"), VERMERK_S)
        if self._waechter is not None:
            self._waechter.cancel()
        self._waechter = asyncio.create_task(self._wachzeit(), name="leitstelle-wachzeit")

    async def _schlaf_melden(self, senden: Senden, grund: Schlafgrund) -> None:
        u = Umschlag(art="knoten.schlaeft", nutzlast=KnotenSchlaeft(grund=grund).model_dump(mode="json"))
        zukunft: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self._vermerkt[u.id] = zukunft
        try:
            await senden(u.model_dump_json())
            await asyncio.wait_for(zukunft, VERMERK_S)
            log.info("Leitstelle hat den Schlaf vermerkt")
        except asyncio.TimeoutError:
            log.info("Leitstelle antwortet nicht auf knoten.schlaeft (ältere Fassung?); die Verbindung wird trotzdem geschlossen")
        except (websockets.exceptions.ConnectionClosed, OSError) as f:
            log.warning("Schlaf nicht gemeldet: %s", type(f).__name__)
        finally:
            self._vermerkt.pop(u.id, None)

    def aufwachen(self) -> None:
        """Der Rechner ist wach: sofort neu verbinden (Pause zurück auf 1 s). Eine Verbindung, die noch offen scheint, ist
        nach dem Schlaf tot (die Leitstelle hat sie längst aufgegeben) und wird geschlossen."""
        if self._waechter is not None and self._waechter is not asyncio.current_task():
            self._waechter.cancel()
        self._waechter = None
        self._wach.set()
        self._pause_s = 1.0
        self._unterbrechen.set()
        if self._ws is not None:
            self._ws.transport.abort()

    async def _wachzeit(self) -> None:
        """Wächter: kommt keine Weckmeldung (verpasst, oder nur kurz erwacht und nicht wieder eingeschlafen), gilt der
        Rechner nach `WACHZEIT_S` Wachzeit als wach. asyncio misst mit time.monotonic, das während des Schlafs ruht."""
        await asyncio.sleep(WACHZEIT_S)
        if not self._wach.is_set():
            log.info("Leitstelle: keine Weckmeldung nach %.0f s Wachzeit; verbinde neu", WACHZEIT_S)
            self.aufwachen()

    # ── Verbindung ───────────────────────────────────────────────────────
    def anmeldung(self) -> KnotenAnmeldung:
        gesamt = self.messer.messen().speicher_gesamt_gb
        system = f"{platform.system()} {platform.mac_ver()[0] or platform.release()}"
        e = self.ordner.einstellungen()
        name = e.name or socket.gethostname().removesuffix(".local")
        return KnotenAnmeldung(name=name, betriebssystem=system, architektur=platform.machine(), speicher_gb=gesamt,
                               agent_version=__version__, messwege=self.messer.messwege(), durchleitung_port=e.durchleitung.port)

    async def _schleife(self, kanal: str, pause_max: float) -> None:
        self._pause_s = 1.0
        while True:
            await self._wach.wait()                          # schläft der Rechner, ruht die Verbindung bis zum Aufwachen
            self._setzen(Verbindung.VERBINDET)
            try:
                await self._verbunden(kanal)
                self._setzen(Verbindung.NICHT_ERREICHBAR, "Verbindung beendet")
            except websockets.exceptions.InvalidStatus as f:
                self._setzen(Verbindung.ABGEWIESEN, f"Leitstelle lehnt ab (Status {f.response.status_code})")
                self._pause_s = pause_max
            except websockets.exceptions.ConnectionClosed as f:
                grund = f.rcvd.reason if f.rcvd else ""
                if grund in ("unbekannter_schluessel", "schluessel_erneuert"):
                    self._setzen(Verbindung.ABGEWIESEN, "Schlüssel unbekannt oder erneuert; neuen Schlüssel eintragen")
                    self._pause_s = pause_max
                else:
                    self._setzen(Verbindung.NICHT_ERREICHBAR, f"Verbindung beendet{': ' + grund if grund else ''}")
            except (OSError, asyncio.TimeoutError, websockets.exceptions.InvalidURI) as f:
                self._setzen(Verbindung.NICHT_ERREICHBAR, str(f)[:160])
            if not self._wach.is_set():
                self._setzen(Verbindung.SCHLAEFT, self.stand.meldung if self.stand.zustand == Verbindung.SCHLAEFT else "Rechner schläft")
                continue                                     # eingeschlafen: kein Fehler, keine Pause
            self._ausfall_melden(pause_max)
            await self._pause(self._pause_s)
            self._pause_s = min(self._pause_s * 2, pause_max)

    def _ausfall_melden(self, pause_max: float) -> None:
        """Ein gescheiterter Versuch: die erste Warnung des Ausfalls (oder einer neuen Art) ins Protokoll, sonst nur in die
        Fehlersuche."""
        if self._ausfall.gescheitert(self.stand.zustand):
            log.warning("Leitstelle: %s %s; verbinde neu mit wachsender Pause bis %.0f s", self.stand.zustand.value,
                        self.stand.meldung, pause_max)
        else:
            log.debug("Leitstelle: Versuch %d gescheitert (%s %s), nächster in %.0f s", self._ausfall.versuche,
                      self.stand.zustand.value, self.stand.meldung, self._pause_s)

    def _angemeldet(self, name: str | None) -> None:
        """Die Leitstelle hat die Anmeldung angenommen: der Ausfall ist vorbei, die Pause beginnt wieder klein."""
        self.stand = self.stand.model_copy(update={"name": name})
        self._setzen(Verbindung.VERBUNDEN)
        self._pause_s = 1.0
        if (ausfall := self._ausfall.beenden()) is not None:
            log.info("Bei der Leitstelle angemeldet als %s, wieder verbunden nach %.0f s und %d Versuchen", name, *ausfall)
        else:
            log.info("Bei der Leitstelle angemeldet als %s", name)

    async def _pause(self, s: float) -> None:
        """Bis zum nächsten Versuch; das Aufwachen beendet die Pause sofort."""
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(self._unterbrechen.wait(), timeout=s)
        self._unterbrechen.clear()

    async def _verbunden(self, kanal: str) -> None:
        kopf = {"Authorization": f"Bearer {self.ordner.schluessel() or ''}"}
        async with websockets.connect(kanal, additional_headers=kopf, open_timeout=10, ping_interval=20) as ws:
            if not self._wach.is_set():
                return                                       # während des Verbindens eingeschlafen
            await ws.send(_umschlag("knoten.anmelden", await asyncio.to_thread(self.anmeldung)))
            sperre = asyncio.Lock()

            async def senden(text: str) -> None:
                async with sperre:
                    await ws.send(text)

            self._ws, self._senden = ws, senden
            empfang = asyncio.create_task(self._empfangen(ws, senden))
            beobachten = asyncio.create_task(self._beobachten_im_takt(senden))
            try:
                await self._senden_im_takt(senden, empfang)
            finally:
                self._ws = self._senden = None
                await _aufgaben_beenden(empfang, beobachten)
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

    async def _beobachten_im_takt(self, senden) -> None:
        """Zugriffe am Leitstand vorbei und Last von Läufer, Rechner und Docker-Rechner in eigenem, ruhigerem Takt: die
        Messung dauert (lsof, docker) und darf Messwerte und Dienstliste nicht aufhalten. Zugriffe und Last des Läufers
        nutzen eine Aufnahme je Takt; der Docker-Rechner wird im eigenen Faden daneben gemessen (seine Aufrufe dauern ein
        bis zwei Sekunden, unter Last länger, höchstens einen Takt) und kommt in dieselbe Meldung. Der Takt zählt von
        Beginn zu Beginn, damit eine lange Messung den Abstand der Meldungen nicht dehnt. Gemessen wird erst, wenn der
        Start alle laufenden Dienste übernommen hat; vorher hielte die Beobachtung sie für fremd. Die Messer gelten je
        Verbindung (die erste Messung danach hat noch keine Prozente). Ein Fehler der Beobachtung trennt die Verbindung
        nicht, ihr Ende beendet die Beobachtung (sie gehört zu genau einer Verbindung). Scheitert die Messung Takt für Takt
        gleich, steht der Stapel einmal im Protokoll."""
        await self.verwalter.hochgefahren.wait()
        lastmesser = Lastmesser(lambda: self.verwalter.einstellungen)
        dockermesser = Dockermesser(lambda: self.verwalter.einstellungen)
        fehler_vorher: str | None = None
        while True:
            beginn = time.monotonic()
            try:
                (fremde, last), docker = await asyncio.gather(asyncio.to_thread(self._beobachten, lastmesser),
                                                              asyncio.to_thread(dockermesser.messen))
                last.docker = docker
                await senden(_umschlag("knoten.fremde", fremde))
                await senden(_umschlag("knoten.last", last))
                if fehler_vorher is not None:
                    log.info("Beobachtung wieder gelungen")
                    fehler_vorher = None
            except websockets.exceptions.ConnectionClosed:
                return                                       # die Verbindung ist weg; die nächste bringt ihre eigene Beobachtung
            except Exception as f:
                fehler = f"{type(f).__name__}: {f}"
                if fehler != fehler_vorher:
                    log.exception("Beobachtung (am Leitstand vorbei, Last, Docker-Rechner) gescheitert")
                else:
                    log.debug("Beobachtung gescheitert wie zuvor: %s", fehler)
                fehler_vorher = fehler
            await asyncio.sleep(max(0.0, self.verwalter.einstellungen.beobachtung.takt_s - (time.monotonic() - beginn)))

    def _beobachten(self, lastmesser: Lastmesser) -> tuple[Fremdzugriffe, KnotenLast]:
        aufnahme = self.beobachter.aufnehmen()
        return self.beobachter.fremde(aufnahme), lastmesser.messen(aufnahme)

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
                self._angemeldet(u.nutzlast.get("name"))
            elif u.art == "knoten.schlaf_vermerkt":
                if (zukunft := self._vermerkt.get(u.bezug or "")) is not None and not zukunft.done():
                    zukunft.set_result(None)

    async def _befehl(self, u: Umschlag, senden) -> None:
        try:
            b = Befehl.model_validate(u.nutzlast)
        except ValidationError as f:
            log.warning("Ungültiger Befehl: %s", f.errors()[:1])
            return
        log.info("Befehl der Leitstelle: %s %s", b.befehl.value, b.ziel)
        if b.befehl == Befehlsart.LAEUFER_PROZESS_BEENDEN:
            ergebnis = await self.laeuferaufsicht.beenden(b.ziel)
        else:
            ergebnis = await self.verwalter.befehl(b, von_leitstelle=True)
        try:
            await senden(_umschlag("knoten.befehl_ergebnis", ergebnis, bezug=u.id))
        except websockets.exceptions.ConnectionClosed:
            log.warning("Ergebnis von %s %s nicht zugestellt: Verbindung zur Leitstelle beendet (die Dienstliste nach dem "
                        "Neuverbinden zeigt den Stand)", b.befehl.value, b.ziel)


async def _aufgaben_beenden(*aufgaben: asyncio.Task) -> None:
    """Erst alle abbrechen, dann auf alle warten: ein Fehler der einen (etwa der Empfang mit dem Schließgrund) darf das
    Beenden der anderen nicht überspringen, sonst sendet eine Beobachtung weiter auf die tote Verbindung."""
    for aufgabe in aufgaben:
        aufgabe.cancel()
    await asyncio.gather(*aufgaben, return_exceptions=True)
