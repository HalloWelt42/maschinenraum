"""Durchleitung: der Weg der Leitstelle zu den Diensten dieses Rechners, wie bei einem Modell-Läufer.

Die Dienste lauschen nur auf diesem Rechner (127.0.0.1); niemand im Netz spricht sie direkt an. Die Leitstelle
ruft `/<dienst>/<pfad>` mit ihrem Schlüssel als Bearer auf, der Maschinenraum reicht Anfrage und Antwort
unverändert weiter (Körper und Antwort als Strom, ohne Lese-Zeitgrenze: Arbeit darf dauern). Ohne Schlüssel,
mit falschem Schlüssel oder an einen Dienst, der nicht läuft, gibt es eine klare Absage mit Grundwort.

Den Modell-Läufer des Rechners spricht die Leitstelle direkt an; durch den Maschinenraum gehen nur seine Dienste.
"""

from __future__ import annotations

import hmac
import logging
from contextlib import asynccontextmanager

import httpx
from dienstkern.zustand import Zustand
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.background import BackgroundTask

from . import __version__

log = logging.getLogger("maschinenraum")
# Köpfe, die nur für eine Verbindung gelten oder die die Durchleitung selbst setzt
OHNE_KOPF = {"host", "authorization", "content-length", "connection", "keep-alive", "transfer-encoding", "te", "trailer", "upgrade",
             "proxy-authorization", "proxy-connection"}


def _absage(status: int, grund: str, meldung: str) -> JSONResponse:
    return JSONResponse({"grund": grund, "meldung": meldung}, status_code=status)


def erstellen(laufzeit) -> FastAPI:
    """`laufzeit` ist die Laufzeit der Oberfläche (api.Laufzeit); beide teilen Dienste und Schlüssel."""
    client = httpx.AsyncClient(timeout=httpx.Timeout(connect=10.0, read=None, write=None, pool=None))

    @asynccontextmanager
    async def lebenslauf(_app: FastAPI):
        try:
            yield
        finally:
            await client.aclose()

    app = FastAPI(title="Maschinenraum Durchleitung", version=__version__, docs_url=None, redoc_url=None, openapi_url=None, lifespan=lebenslauf)

    def berechtigt(request: Request) -> bool:
        erwartet = laufzeit.ordner.schluessel()
        kopf = request.headers.get("authorization", "")
        gegeben = kopf[7:].strip() if kopf.lower().startswith("bearer ") else ""
        return bool(erwartet) and hmac.compare_digest(gegeben.encode(), erwartet.encode())

    @app.get("/")
    async def stand(request: Request):
        if not berechtigt(request):
            return _absage(401, "unbekannter_schluessel", "Nur die Leitstelle mit dem Schlüssel dieses Maschinenraums.")
        return {"maschinenraum": __version__, "dienste": [d.kennung for d in laufzeit.verwalter.dienste.values()]}

    def ziel_des_dienstes(dienst: str) -> tuple[str, str] | JSONResponse:
        d = laufzeit.verwalter.dienste.get(dienst)
        if d is None:
            return _absage(404, "unbekannt", f"Diesen Dienst gibt es hier für die Leitstelle nicht: {dienst}")
        if d.vorlage.port is None:
            return _absage(409, "ohne_port", f"{d.vorlage.name} hat keinen Port, an den man Anfragen richten kann.")
        if d.zustand != Zustand.LAEUFT:
            return _absage(409, "dienst_aus", f"{d.vorlage.name} läuft nicht ({d.zustand.value}).")
        return f"http://127.0.0.1:{d.vorlage.port}", d.vorlage.name

    @app.api_route("/{dienst}/{pfad:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    async def weiterreichen(dienst: str, pfad: str, request: Request):
        if not berechtigt(request):
            return _absage(401, "unbekannter_schluessel", "Nur die Leitstelle mit dem Schlüssel dieses Maschinenraums.")
        gefunden = ziel_des_dienstes(dienst)
        if isinstance(gefunden, JSONResponse):
            return gefunden
        basis, name = gefunden
        kopf = {k: v for k, v in request.headers.items() if k.lower() not in OHNE_KOPF}
        ziel = httpx.URL(f"{basis}/{pfad}", query=request.url.query.encode())
        laufzeit.durchleitungen += 1          # gezählt bis die Antwort ganz durch ist (Neustart nur ohne laufende)
        try:
            antwort = await client.send(client.build_request(request.method, ziel, headers=kopf, content=request.stream()), stream=True)
        except httpx.HTTPError as f:
            laufzeit.durchleitungen -= 1
            return _absage(502, "dienst_nicht_erreichbar", f"{name}: {type(f).__name__} {f}".strip())

        async def fertig() -> None:
            laufzeit.durchleitungen -= 1
            await antwort.aclose()

        zurueck = {k: v for k, v in antwort.headers.items() if k.lower() not in OHNE_KOPF}
        return StreamingResponse(antwort.aiter_raw(), status_code=antwort.status_code, headers=zurueck, background=BackgroundTask(fertig))

    return app
