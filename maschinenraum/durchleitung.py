"""Durchleitung: der Weg der Leitstelle zu den Diensten dieses Rechners, wie bei einem Modell-Läufer.

Die Dienste lauschen nur auf diesem Rechner (127.0.0.1); niemand im Netz spricht sie direkt an. Die Leitstelle
ruft `/<dienst>/<pfad>` mit ihrem Schlüssel als Bearer auf, der Maschinenraum reicht Anfrage und Antwort
unverändert weiter (Körper und Antwort als Strom, ohne Lese-Zeitgrenze: Arbeit darf dauern). Ohne Schlüssel,
mit falschem Schlüssel oder an einen Dienst, der nicht läuft, gibt es eine klare Absage mit Grundwort. Ein Dienst, den die
Speicherwache gesperrt hat, antwortet mit 423 `dienst_gesperrt`; beendet sie ihn mitten in einem Auftrag, bevor er
geantwortet hat, kommt 507 `speicher` mit dem Grund (beides endgültig, nicht zum Wiederholen).

Abbruch reicht durch: schließt die Leitstelle ihre Verbindung, schließt die Durchleitung ihre zum Dienst, auch solange
der Dienst noch rechnet und noch nichts geantwortet hat (ein Bilddienst antwortet erst mit dem fertigen Bild). Der Dienst
sieht das und hört auf; vorher rechnete er bis zum Ende weiter und hielt die Grafik fest.

Den Modell-Läufer des Rechners spricht die Leitstelle direkt an; durch den Maschinenraum gehen nur seine Dienste.
"""

from __future__ import annotations

import asyncio
import hmac
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

import httpx
from dienstkern.zustand import Zustand
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from starlette.background import BackgroundTask
from starlette.requests import ClientDisconnect

from . import __version__

log = logging.getLogger("maschinenraum")
# Köpfe, die nur für eine Verbindung gelten oder die die Durchleitung selbst setzt
OHNE_KOPF = {"host", "authorization", "content-length", "connection", "keep-alive", "transfer-encoding", "te", "trailer", "upgrade",
             "proxy-authorization", "proxy-connection"}


def _absage(status: int, grund: str, meldung: str) -> JSONResponse:
    """Grundwort und Satz, dazu im Fehlerformat der Leitstelle (`error.code`), das Apps auch roh durchgereicht lesen."""
    return JSONResponse({"grund": grund, "meldung": meldung, "error": {"code": grund, "message": meldung}}, status_code=status,
                        headers={"X-Maschinenraum-Grund": grund})


async def _koerper(request: Request, gesendet: asyncio.Event) -> AsyncIterator[bytes]:
    """Der Körper der Leitstelle als Strom; `gesendet`, sobald er ganz beim Dienst ist."""
    async for teil in request.stream():
        yield teil
    gesendet.set()


async def _bis_getrennt(request: Request, gesendet: asyncio.Event) -> None:
    """Endet, wenn die Leitstelle ihre Verbindung schließt. Erst nach dem Körper: vorher gehören die Nachrichten der
    Verbindung dem Körper. Danach kommt auf dieser Verbindung nur noch die Nachricht, dass sie zu ist."""
    await gesendet.wait()
    while (await request.receive())["type"] != "http.disconnect":
        await asyncio.sleep(0.1)


async def _senden_bis_getrennt(client: httpx.AsyncClient, anfrage: httpx.Request, request: Request,
                               gesendet: asyncio.Event) -> httpx.Response | None:
    """Die Anfrage an den Dienst, bis seine Antwortköpfe da sind; None, wenn die Leitstelle vorher gegangen ist. Dann wird
    das Senden abgebrochen und die Verbindung zum Dienst geschlossen, sodass der Dienst den Abbruch sieht."""
    senden = asyncio.ensure_future(client.send(anfrage, stream=True))
    wache = asyncio.ensure_future(_bis_getrennt(request, gesendet))
    try:
        await asyncio.wait({senden, wache}, return_when=asyncio.FIRST_COMPLETED)
    except BaseException:
        senden.cancel()
        wache.cancel()
        raise
    wache.cancel()
    if senden.done():
        return senden.result()
    senden.cancel()
    with suppress(asyncio.CancelledError, httpx.HTTPError, ClientDisconnect):
        await senden
    return None


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
        if d.stand.sperre is not None:
            return _absage(423, "dienst_gesperrt", f"{d.vorlage.name} {d.sperrsatz}.")
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
        gesendet = asyncio.Event()
        try:
            antwort = await _senden_bis_getrennt(client, client.build_request(request.method, ziel, headers=kopf, content=_koerper(request, gesendet)),
                                                 request, gesendet)
        except (httpx.HTTPError, ClientDisconnect) as f:
            laufzeit.durchleitungen -= 1
            d = laufzeit.verwalter.dienste.get(dienst)
            if d is not None and d.stand.sperre is not None:     # die Speicherwache hat ihn mitten im Auftrag beendet
                return _absage(507, "speicher", f"{name}: {d.stand.sperre.grund}")
            return _absage(502, "dienst_nicht_erreichbar", f"{name}: {type(f).__name__} {f}".strip())
        if antwort is None:
            laufzeit.durchleitungen -= 1
            log.info("Durchleitung zu %s abgebrochen: die Leitstelle hat die Verbindung geschlossen", name)
            return Response(status_code=499)  # liest niemand mehr; die Verbindung ist zu

        async def fertig() -> None:
            laufzeit.durchleitungen -= 1
            await antwort.aclose()

        zurueck = {k: v for k, v in antwort.headers.items() if k.lower() not in OHNE_KOPF}
        return StreamingResponse(antwort.aiter_raw(), status_code=antwort.status_code, headers=zurueck, background=BackgroundTask(fertig))

    return app
