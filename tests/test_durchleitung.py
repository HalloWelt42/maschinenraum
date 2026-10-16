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
        assert c.get("/", headers=SCHLUESSEL).json()["dienste"] == ["probe"]
        asyncio.run(lz.verwalter.befehl(Befehl(befehl=Befehlsart.DIENST_ANHALTEN, ziel="probe")))
