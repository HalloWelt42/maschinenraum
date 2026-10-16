"""Lokale Schnittstelle und Oberfläche des Maschinenraums.

Standardmäßig nur auf diesem Rechner erreichbar (127.0.0.1). Schutz gegen fremde Webseiten im selben Browser:
nur bekannte Rechnernamen im Host-Kopf (gegen DNS-Rebinding) und schreibende Aufrufe nur mit dem Kopf
`X-Maschinenraum: 1` (den ein fremder Ursprung ohne Freigabe nicht setzen darf).
"""

from __future__ import annotations

import asyncio
import logging
import socket
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from . import __version__, nachbar
from .konfig import Ladefehler, Ordner
from .leitstelle import Leitstellenkanal, LeitstellenStand
from .messen import Messer
from .protokoll import Befehl, BefehlErgebnis, Befehlsart, Faehigkeit, Messwerte, Prozesszustand
from .prozesse import Soll, Verwalter

log = logging.getLogger("maschinenraum")
OBERFLAECHE = Path(__file__).resolve().parent / "oberflaeche"
LOKALE_NAMEN = {"127.0.0.1", "localhost", "[::1]"}
PROTOKOLL_LESEN_BYTES = 256 * 1024


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
    spitze_gb: float | None
    schaetzung_gb: float
    aktiv: bool
    cpu_prozent: float | None
    anhalten_erlaubt: bool
    soll: Soll | None
    meldung: str
    datei: str
    protokolldatei: str
    ordner: str


class Stand(BaseModel):
    version: str
    rechner: str
    zeit: float
    ordner: str
    messwerte: Messwerte | None
    dienste: list[DienstAnsicht]
    ladefehler: list[Ladefehler]
    leitstelle: LeitstellenStand
    nachbar: nachbar.NachbarStand


class LeitstellenDaten(BaseModel):
    adresse: str | None = Field(default=None, max_length=255, description="leer: ohne Leitstelle")
    schluessel: str | None = Field(default=None, max_length=200, description="None: unverändert; leer: entfernen")


class Protokollauszug(BaseModel):
    datei: str
    zeilen: list[str]


class Laufzeit:
    """Alles, was während des Betriebs lebt; einmal je Anwendung."""

    def __init__(self, ordner: Ordner) -> None:
        self.ordner = ordner
        e = ordner.einstellungen()
        self.messer = Messer(e.messung.takt_s, e.messung.macmon)
        self.verwalter = Verwalter(ordner, e)
        self.kanal = Leitstellenkanal(ordner, self.verwalter, self.messer)
        self.messwerte: Messwerte | None = None
        self.nachbar = nachbar.NachbarStand(adresse=e.nachbar.modell_laeufer)
        self.aufgaben: list[asyncio.Task] = []

    async def _messen(self) -> None:
        while True:
            try:
                self.messwerte = await asyncio.to_thread(self.messer.messen)
                self.nachbar = await asyncio.to_thread(nachbar.lesen, self.verwalter.einstellungen.nachbar.modell_laeufer)
            except Exception:                                   # die Messung darf nie sterben
                log.exception("Fehler beim Messen")
            await asyncio.sleep(self.verwalter.einstellungen.messung.takt_s)

    async def starten(self) -> None:
        self.aufgaben = [asyncio.create_task(self.verwalter.schleife(), name="dienste"), asyncio.create_task(self._messen(), name="messen")]
        self.kanal.starten()

    async def beenden(self) -> None:
        await self.kanal.beenden()
        for t in self.aufgaben:
            t.cancel()
        await asyncio.gather(*self.aufgaben, return_exceptions=True)
        await self.verwalter.beenden()
        self.messer.beenden()

    def ansicht(self) -> list[DienstAnsicht]:
        ergebnis = []
        for d in self.verwalter.dienste.values():
            b, v = d.bericht(), d.vorlage
            ergebnis.append(DienstAnsicht(kennung=b.kennung, name=b.name, beschreibung=v.beschreibung, faehigkeiten=sorted(b.faehigkeiten, key=lambda f: f.value),
                                          port=b.port, oberflaeche=v.oberflaeche, zustand=b.zustand, fremd=b.fremd, gb_jetzt=b.gb_jetzt,
                                          bedarf_gb=b.bedarf_gb, spitze_gb=d.stand.spitze_gb, schaetzung_gb=v.speicher_gb, aktiv=b.aktiv,
                                          cpu_prozent=d.cpu_prozent if b.gb_jetzt is not None else None, anhalten_erlaubt=b.anhalten_erlaubt,
                                          soll=d.stand.soll, meldung=b.meldung,
                                          datei=str(self.ordner.dienste_ordner / f"{b.kennung}.toml"), protokolldatei=str(d._protokolldatei()),
                                          ordner=str(v.ordner)))
        return ergebnis

    def stand(self) -> Stand:
        e = self.verwalter.einstellungen
        return Stand(version=__version__, rechner=e.name or socket.gethostname().removesuffix(".local"), zeit=time.time(), ordner=str(self.ordner.wurzel),
                     messwerte=self.messwerte, dienste=self.ansicht(), ladefehler=self.verwalter.ladefehler, leitstelle=self.kanal.stand, nachbar=self.nachbar)


def _protokoll_ende(datei: Path, zeilen: int) -> list[str]:
    try:
        with open(datei, "rb") as f:
            f.seek(0, 2)
            groesse = f.tell()
            f.seek(max(0, groesse - PROTOKOLL_LESEN_BYTES))
            text = f.read().decode("utf-8", errors="replace")
    except FileNotFoundError:
        return []
    return text.splitlines()[-zeilen:]


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

    @app.middleware("http")
    async def schutz(request: Request, weiter):
        e = lz.verwalter.einstellungen.oberflaeche
        host = (request.headers.get("host") or "").rsplit(":", 1)[0]
        if e.adresse in ("127.0.0.1", "::1", "localhost") and host not in LOKALE_NAMEN:
            return JSONResponse({"grund": "herkunft_nicht_erlaubt", "meldung": "Nur auf diesem Rechner erreichbar."}, status_code=403)
        if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get("x-maschinenraum") != "1":
            return JSONResponse({"grund": "kopf_fehlt", "meldung": "Schreibende Aufrufe brauchen den Kopf X-Maschinenraum: 1."}, status_code=403)
        return await weiter(request)

    def dienst(kennung: str):
        d = lz.verwalter.dienste.get(kennung)
        if d is None:
            raise HTTPException(404, "Diesen Dienst gibt es nicht.")
        return d

    @app.get("/api/stand")
    async def stand() -> Stand:
        return lz.stand()

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
        return await lz.verwalter.neu_starten(kennung)

    @app.get("/api/dienste/{kennung}/protokoll")
    async def protokoll(kennung: str, zeilen: int = 200) -> Protokollauszug:
        d = dienst(kennung)
        datei = d._protokolldatei()
        return Protokollauszug(datei=str(datei), zeilen=await asyncio.to_thread(_protokoll_ende, datei, max(1, min(zeilen, 2000))))

    @app.get("/api/protokoll")
    async def eigenes_protokoll(zeilen: int = 200) -> Protokollauszug:
        datei = ordner.protokolle / "maschinenraum.log"
        return Protokollauszug(datei=str(datei), zeilen=await asyncio.to_thread(_protokoll_ende, datei, max(1, min(zeilen, 2000))))

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

    _oberflaeche(app)
    return app


def _oberflaeche(app: FastAPI) -> None:
    """Liefert die gebaute Oberfläche aus; unbekannte Pfade bekommen index.html."""
    wurzel = OBERFLAECHE
    if not (wurzel / "index.html").exists():
        @app.get("/", include_in_schema=False)
        async def ohne():
            return JSONResponse({"meldung": "Oberfläche nicht gebaut; Schnittstelle unter /api/stand"})
        return

    @app.get("/{pfad:path}", include_in_schema=False)
    async def seite(pfad: str):
        datei = (wurzel / pfad).resolve()
        if pfad and datei.is_file() and datei.is_relative_to(wurzel):
            kopf = {"Cache-Control": "public, max-age=604800, immutable"} if pfad.startswith("assets/") else {"Cache-Control": "no-cache"}
            return FileResponse(datei, headers=kopf)
        return FileResponse(wurzel / "index.html", headers={"Cache-Control": "no-cache"})

