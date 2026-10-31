"""Lokale Schnittstelle und Oberfläche des Maschinenraums.

Standardmäßig nur auf diesem Rechner erreichbar (127.0.0.1). Schutz gegen fremde Webseiten im selben Browser (aus dem
Dienstkern): nur bekannte Rechnernamen im Host-Kopf (gegen DNS-Rebinding) und schreibende Aufrufe nur mit dem Kopf
`X-Maschinenraum: 1` (den ein fremder Ursprung ohne Freigabe nicht setzen darf).
"""

from __future__ import annotations

import asyncio
import logging
import socket
import time
from contextlib import asynccontextmanager
from pathlib import Path

from dienstkern.dienst import Dienst
from dienstkern.verwalter import Ergebnis
from dienstkern.verwalter import Verwalter as Kernverwalter
from dienstkern.vorlage import Ladefehler
from dienstkern.zustand import Zustand
from dienstkern.web import Protokollauszug, oberflaeche_ausliefern, protokoll_ende, schutz_einrichten
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from . import __version__, nachbar
from .konfig import Einstellungen, Ordner
from .leitstelle import Leitstellenkanal, LeitstellenStand
from .messen import Messer
from .protokoll import Befehl, BefehlErgebnis, Befehlsart, Faehigkeit, Messwerte, Prozesszustand
from .prozesse import Soll, Verwalter, bericht
from .schlaf import Schlafwaechter

log = logging.getLogger("maschinenraum")
OBERFLAECHE = Path(__file__).resolve().parent / "oberflaeche"


class DienstAnsicht(BaseModel):
    kennung: str
    name: str
    beschreibung: str
    faehigkeiten: list[Faehigkeit]
    port: int | None
    oberflaeche: str | None
    zustand: Prozesszustand
    fremd: bool
    gb_jetzt: float | None          # gemessen, solange er läuft
    bedarf_gb: float                # was er laufend braucht; damit plant die Leitstelle
    spitze_gb: float | None         # höchste gemessene Arbeitsspitze (neben der Anmeldung, damit Abweichungen auffallen)
    schaetzung_gb: float            # angemeldet in der Dienstdatei (speicher_gb)
    grenze_gb: float | None         # harte Grenze der Speicherwache; None: Wache aus
    sperre: str | None              # nach einem Speicherabbruch gesperrt: der Grund
    sperre_seit: str | None
    aktiv: bool
    cpu_prozent: float | None
    anhalten_erlaubt: bool
    soll: Soll | None
    meldung: str
    datei: str
    protokolldatei: str
    ordner: str


class BetriebAnsicht(BaseModel):
    """Ein Steuerprogramm des Rechners (etwa das Stellwerk): nur starten, anhalten, öffnen; keine KI."""

    kennung: str
    name: str
    beschreibung: str
    oberflaeche: str | None
    zustand: Zustand
    soll: Soll | None
    gb_jetzt: float | None
    meldung: str
    datei: str
    protokolldatei: str


class Stand(BaseModel):
    version: str
    rechner: str
    zeit: float
    ordner: str
    einstellungen: Einstellungen      # ohne Geheimnisse; der Schlüssel liegt in einer eigenen Datei
    messwerte: Messwerte | None
    dienste: list[DienstAnsicht]
    betrieb: list[BetriebAnsicht]
    ladefehler: list[Ladefehler]
    leitstelle: LeitstellenStand
    nachbar: nachbar.NachbarStand


class Fassung(BaseModel):
    """Fassung des laufenden Programms; die Oberfläche vergleicht sie mit ihrer eingebauten und lädt bei Abweichung neu."""

    version: str


class LeitstellenDaten(BaseModel):
    adresse: str | None = Field(default=None, max_length=255, description="leer: ohne Leitstelle")
    schluessel: str | None = Field(default=None, max_length=200, description="None: unverändert; leer: entfernen")


class Laufzeit:
    """Alles, was während des Betriebs lebt; einmal je Anwendung."""

    def __init__(self, ordner: Ordner) -> None:
        self.ordner = ordner
        e = ordner.einstellungen()
        self.messer = Messer(e.messung.takt_s, e.messung.macmon)
        self.verwalter = Verwalter(ordner, e)
        # Steuerprogramme (Stellwerk ...) mit derselben Dienststeuerung, aber eigenem Stand; die Leitstelle sieht sie nie
        self.betrieb = Kernverwalter(ordner.betrieb, ordner.betrieb_protokolle, ordner.betrieb_zustand_datei, e.neustart,
                                     e.messung.takt_s, herkunft="vom Maschinenraum")
        self.kanal = Leitstellenkanal(ordner, self.verwalter, self.messer)
        self.messwerte: Messwerte | None = None
        self.nachbar = nachbar.NachbarStand(adresse=e.nachbar.modell_laeufer)
        self.aufgaben: list[asyncio.Task] = []
        self.durchleitungen = 0               # Anfragen der Leitstelle, die gerade zu einem Dienst durchgereicht werden
        # Schlaf des Rechners: der Leitstelle melden; solange durchgereicht wird, keinen Leerlaufschlaf (Einstellung schlaf)
        self.schlaf = Schlafwaechter(self.kanal, lambda: self.durchleitungen, lambda: self.verwalter.einstellungen.schlaf)

    async def _messen(self) -> None:
        while True:
            try:
                self.messwerte = await asyncio.to_thread(self.messer.messen)
                self.nachbar = await asyncio.to_thread(nachbar.lesen, self.verwalter.einstellungen.nachbar.modell_laeufer)
            except Exception:                                   # die Messung darf nie sterben
                log.exception("Fehler beim Messen")
            await asyncio.sleep(self.verwalter.einstellungen.messung.takt_s)

    async def starten(self) -> None:
        self.aufgaben = [asyncio.create_task(self.verwalter.schleife(), name="dienste"), asyncio.create_task(self.betrieb.schleife(), name="betrieb"),
                         asyncio.create_task(self._messen(), name="messen")]
        self.kanal.starten()
        await asyncio.to_thread(self.schlaf.starten, asyncio.get_running_loop())

    async def beenden(self) -> None:
        await asyncio.to_thread(self.schlaf.stoppen)
        await self.kanal.beenden()
        for t in self.aufgaben:
            t.cancel()
        await asyncio.gather(*self.aufgaben, return_exceptions=True)
        await self.verwalter.beenden()
        await self.betrieb.beenden()
        self.messer.beenden()

    def betrieb_ansicht(self) -> list[BetriebAnsicht]:
        aus = []
        for d in self.betrieb.dienste.values():
            b = d.bericht()
            aus.append(BetriebAnsicht(kennung=b.kennung, name=b.name, beschreibung=d.vorlage.beschreibung, oberflaeche=d.vorlage.oberflaeche,
                                      zustand=b.zustand, soll=b.soll, gb_jetzt=b.gb_jetzt, meldung=b.meldung,
                                      datei=str(self.ordner.betrieb_ordner / f"{b.kennung}.toml"), protokolldatei=str(d.protokolldatei())))
        return aus

    def ansicht(self) -> list[DienstAnsicht]:
        ergebnis = []
        for d in self.verwalter.dienste.values():
            b, k, v = bericht(d, self.verwalter.speicherschutz), d.bericht(), d.vorlage
            ergebnis.append(DienstAnsicht(kennung=b.kennung, name=b.name, beschreibung=v.beschreibung, faehigkeiten=sorted(b.faehigkeiten, key=lambda f: f.value),
                                          port=b.port, oberflaeche=v.oberflaeche, zustand=b.zustand, fremd=b.fremd, gb_jetzt=b.gb_jetzt,
                                          bedarf_gb=b.bedarf_gb, spitze_gb=k.spitze_gb, schaetzung_gb=v.speicher_gb, grenze_gb=b.grenze_gb,
                                          sperre=b.sperre, sperre_seit=d.stand.sperre.seit if d.stand.sperre else None, aktiv=b.aktiv,
                                          cpu_prozent=k.cpu_prozent, anhalten_erlaubt=b.anhalten_erlaubt, soll=k.soll, meldung=b.meldung,
                                          datei=str(self.ordner.dienste_ordner / f"{b.kennung}.toml"), protokolldatei=str(d.protokolldatei()),
                                          ordner=str(v.ordner)))
        return ergebnis

    def stand(self) -> Stand:
        e = self.verwalter.einstellungen
        return Stand(version=__version__, rechner=e.name or socket.gethostname().removesuffix(".local"), zeit=time.time(), ordner=str(self.ordner.wurzel),
                     einstellungen=self.ordner.einstellungen(),
                     messwerte=self.messwerte, dienste=self.ansicht(), betrieb=self.betrieb_ansicht(),
                     ladefehler=self.verwalter.ladefehler + [f.model_copy(update={"datei": f"betrieb/{f.datei}"}) for f in self.betrieb.ladefehler], leitstelle=self.kanal.stand, nachbar=self.nachbar)


def erstellen(ordner: Ordner) -> FastAPI:
    ordner.anlegen()
    lz = Laufzeit(ordner)

    @asynccontextmanager
    async def lebenslauf(app: FastAPI):
        await lz.starten()
        log.info("Maschinenraum %s, Ordner %s", __version__, ordner.wurzel)
        try:
            yield
        finally:
            await lz.beenden()

    app = FastAPI(title="Maschinenraum", version=__version__, lifespan=lebenslauf)
    app.state.laufzeit = lz

    schutz_einrichten(app, lambda: lz.verwalter.einstellungen.oberflaeche.adresse, "X-Maschinenraum")

    def dienst(kennung: str):
        d = lz.verwalter.dienste.get(kennung)
        if d is None:
            raise HTTPException(404, "Diesen Dienst gibt es nicht.")
        return d

    @app.get("/api/stand")
    async def stand() -> Stand:
        return lz.stand()

    @app.get("/api/version")
    async def fassung() -> Fassung:
        return Fassung(version=__version__)

    @app.get("/api/durchleitungen")
    async def durchleitungen() -> dict[str, int]:
        """Wie viele Anfragen gerade durchgereicht werden; ein Neustart wartet, bis es keine sind (installieren.sh)."""
        return {"laufend": lz.durchleitungen}

    @app.post("/api/dienste/{kennung}/starten")
    async def starten(kennung: str) -> BefehlErgebnis:
        dienst(kennung)
        return await lz.verwalter.befehl(Befehl(befehl=Befehlsart.DIENST_STARTEN, ziel=kennung))

    @app.post("/api/dienste/{kennung}/anhalten")
    async def anhalten(kennung: str) -> BefehlErgebnis:
        dienst(kennung)
        return await lz.verwalter.befehl(Befehl(befehl=Befehlsart.DIENST_ANHALTEN, ziel=kennung))

    @app.post("/api/dienste/{kennung}/neustarten")
    async def neustarten(kennung: str) -> BefehlErgebnis:
        dienst(kennung)
        return await lz.verwalter.neu_starten_befehl(kennung)

    @app.post("/api/dienste/{kennung}/entsperren")
    async def entsperren(kennung: str) -> Ergebnis:
        """Nur von Hand (die Leitstelle kann das nicht): die Sperre nach einem Speicherabbruch aufheben; startet nichts."""
        return lz.verwalter.entsperren(dienst(kennung).kennung)

    @app.get("/api/dienste/{kennung}/protokoll")
    async def protokoll(kennung: str, zeilen: int = 200) -> Protokollauszug:
        datei = dienst(kennung).protokolldatei()
        return Protokollauszug(datei=str(datei), zeilen=await asyncio.to_thread(protokoll_ende, datei, zeilen))

    def steuerprogramm(kennung: str) -> Dienst:
        d = lz.betrieb.dienste.get(kennung)
        if d is None:
            raise HTTPException(404, "Dieses Steuerprogramm gibt es nicht.")
        return d

    @app.post("/api/betrieb/{kennung}/starten")
    async def betrieb_starten(kennung: str) -> Ergebnis:
        return await lz.betrieb.starten(steuerprogramm(kennung).kennung)

    @app.post("/api/betrieb/{kennung}/anhalten")
    async def betrieb_anhalten(kennung: str) -> Ergebnis:
        return await lz.betrieb.anhalten(steuerprogramm(kennung).kennung)

    @app.post("/api/betrieb/{kennung}/neustarten")
    async def betrieb_neustarten(kennung: str) -> Ergebnis:
        return await lz.betrieb.neu_starten(steuerprogramm(kennung).kennung)

    @app.get("/api/betrieb/{kennung}/protokoll")
    async def betrieb_protokoll(kennung: str, zeilen: int = 200) -> Protokollauszug:
        datei = steuerprogramm(kennung).protokolldatei()
        return Protokollauszug(datei=str(datei), zeilen=await asyncio.to_thread(protokoll_ende, datei, zeilen))

    @app.get("/api/protokoll")
    async def eigenes_protokoll(zeilen: int = 200) -> Protokollauszug:
        datei = ordner.protokolle / "maschinenraum.log"
        return Protokollauszug(datei=str(datei), zeilen=await asyncio.to_thread(protokoll_ende, datei, zeilen))

    @app.put("/api/leitstelle")
    async def leitstelle(daten: LeitstellenDaten) -> LeitstellenStand:
        e = ordner.einstellungen()
        adresse = (daten.adresse or "").strip().rstrip("/") or None
        if adresse and not adresse.startswith(("http://", "https://")):
            raise HTTPException(422, "Die Adresse beginnt mit http:// oder https://.")
        e.leitstelle.adresse = adresse
        ordner.einstellungen_speichern(e)
        lz.verwalter.einstellungen = e
        if daten.schluessel is not None:
            ordner.schluessel_speichern(daten.schluessel.strip())
        lz.kanal.starten()
        return lz.kanal.stand

    oberflaeche_ausliefern(app, OBERFLAECHE)
    return app
