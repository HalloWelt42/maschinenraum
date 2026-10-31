"""Durchleitung: nur mit Schlüssel, nur an laufende Dienste, Anfrage und Antwort unverändert."""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from maschinenraum import durchleitung
from maschinenraum.api import erstellen
from maschinenraum.protokoll import Befehl, Befehlsart

from test_dienste import freier_port, ordner_mit_dienst

SCHLUESSEL = {"Authorization": "Bearer ls_probe"}


def test_durchleitung(tmp_path: Path):
    port = freier_port()
    o = ordner_mit_dienst(tmp_path, port)
    (tmp_path / "hallo.txt").write_text("Grüße aus dem Dienst")
    app = erstellen(o)
    with TestClient(app, base_url="http://127.0.0.1:8540"), TestClient(durchleitung.erstellen(app.state.laufzeit)) as c:
        assert c.get("/probe/hallo.txt").status_code == 401                                  # ohne Schlüssel im Maschinenraum
        o.schluessel_speichern("ls_probe")
        assert c.get("/probe/hallo.txt", headers={"Authorization": "Bearer falsch"}).status_code == 401
        lz = app.state.laufzeit
        asyncio.run(lz.verwalter.runde())
        r = c.get("/probe/hallo.txt", headers=SCHLUESSEL)
        assert r.status_code == 409 and r.json()["grund"] == "dienst_aus"
        assert c.get("/gibtsnicht/x", headers=SCHLUESSEL).status_code == 404
        e = asyncio.run(lz.verwalter.befehl(Befehl(befehl=Befehlsart.DIENST_STARTEN, ziel="probe")))
        assert e.erfolg, e.meldung
        r = c.get("/probe/hallo.txt?a=1", headers=SCHLUESSEL)
        assert r.status_code == 200 and r.content.decode() == "Grüße aus dem Dienst"
        assert c.get("/probe/fehlt.txt", headers=SCHLUESSEL).status_code == 404               # Antwort des Dienstes, unverändert
        assert lz.durchleitungen == 0, "jede durchgereichte Anfrage ist wieder abgezählt"
        with TestClient(app, base_url="http://127.0.0.1:8540") as oben:
            assert oben.get("/api/durchleitungen").json() == {"laufend": 0}
        assert c.get("/", headers=SCHLUESSEL).json()["dienste"] == ["probe"]
        asyncio.run(lz.verwalter.befehl(Befehl(befehl=Befehlsart.DIENST_ANHALTEN, ziel="probe")))



# ── Abbruch reicht bis zum Dienst ────────────────────────────────────────────
# Mit echten Servern: der Testclient kennt kein Schließen der Verbindung. Ein Dienst, der wie ein Bilddienst erst am Ende
# antwortet (keine Köpfe vorher), merkt sich, ob sein Aufrufer gegangen ist.

import threading
import time
from types import SimpleNamespace

import httpx
import uvicorn
from dienstkern.zustand import Zustand
from fastapi import FastAPI, Request


def _server(app, port: int) -> uvicorn.Server:
    s = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", lifespan="on"))
    threading.Thread(target=s.run, daemon=True).start()
    ende = time.monotonic() + 10
    while not s.started and time.monotonic() < ende:
        time.sleep(0.05)
    assert s.started
    return s


def _langsamer_dienst(merker: dict) -> FastAPI:
    app = FastAPI()

    @app.post("/rechnen")
    async def rechnen(request: Request):
        await request.body()
        merker["begonnen"] = time.monotonic()
        for _ in range(200):                                  # höchstens 20 s, wie eine lange Rechnung
            if await request.is_disconnected():
                merker["getrennt"] = time.monotonic()
                return {"ok": False}
            await asyncio.sleep(0.1)
        return {"ok": True}

    return app


def _laufzeit(port: int) -> SimpleNamespace:
    dienst = SimpleNamespace(kennung="bild", zustand=Zustand.LAEUFT, vorlage=SimpleNamespace(port=port, name="Bilddienst"), stand=SimpleNamespace(sperre=None))
    return SimpleNamespace(ordner=SimpleNamespace(schluessel=lambda: "ls_probe"), verwalter=SimpleNamespace(dienste={"bild": dienst}),
                           durchleitungen=0)


def test_abbruch_der_leitstelle_erreicht_den_dienst():
    """Schließt die Leitstelle die Verbindung, solange der Dienst noch rechnet (noch keine Antwortköpfe), schließt die
    Durchleitung ihre Verbindung zum Dienst: er sieht das und hört auf. Vorher wartete sie bis zu seiner Antwort."""
    merker: dict = {}
    dienst_port, port = freier_port(), freier_port()
    dienst = _server(_langsamer_dienst(merker), dienst_port)
    lz = _laufzeit(dienst_port)
    tor = _server(durchleitung.erstellen(lz), port)
    try:
        async def anfragen_und_gehen() -> None:
            async with httpx.AsyncClient(timeout=None) as c:
                aufgabe = asyncio.ensure_future(c.post(f"http://127.0.0.1:{port}/bild/rechnen", json={"prompt": "x"}, headers=SCHLUESSEL))
                ende = time.monotonic() + 5
                while "begonnen" not in merker and time.monotonic() < ende:
                    await asyncio.sleep(0.05)
                assert "begonnen" in merker, "der Dienst hat die Anfrage nicht bekommen"
                aufgabe.cancel()                               # die Leitstelle bricht ab: Verbindung zu
                try:
                    await aufgabe
                except asyncio.CancelledError:
                    pass

        asyncio.run(anfragen_und_gehen())
        gegangen = time.monotonic()
        ende = gegangen + 5
        while "getrennt" not in merker and time.monotonic() < ende:
            time.sleep(0.05)
        assert "getrennt" in merker, "der Dienst rechnet weiter, obwohl die Leitstelle gegangen ist"
        assert merker["getrennt"] - gegangen < 3
        ende = time.monotonic() + 3
        while lz.durchleitungen and time.monotonic() < ende:
            time.sleep(0.05)
        assert lz.durchleitungen == 0, "die abgebrochene Durchleitung ist wieder abgezählt"
    finally:
        tor.should_exit = dienst.should_exit = True
