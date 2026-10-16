"""Lokale Schnittstelle: Stand, Schalten, Protokoll, Leitstelle eintragen, Schutz gegen fremde Seiten."""

from __future__ import annotations

import stat
import time
from pathlib import Path

from fastapi.testclient import TestClient

from maschinenraum.api import erstellen
from maschinenraum.konfig import Ordner

from test_dienste import freier_port, offen, ordner_mit_dienst

SCHREIBEN = {"X-Maschinenraum": "1"}


def client(o: Ordner) -> TestClient:
    return TestClient(erstellen(o), base_url="http://127.0.0.1:8540")


def test_stand_schalten_und_protokoll(tmp_path: Path):
    port = freier_port()
    with client(ordner_mit_dienst(tmp_path, port)) as c:
        for _ in range(30):
            s = c.get("/api/stand").json()
            if s["dienste"]:
                break
            time.sleep(0.1)
        d = s["dienste"][0]
        assert d["kennung"] == "probe" and d["zustand"] == "aus" and d["soll"] is None and d["faehigkeiten"] == ["stimme"]
        assert d["gb_jetzt"] is None and d["bedarf_gb"] == 0.5 and d["anhalten_erlaubt"] and not d["aktiv"]
        assert s["leitstelle"]["zustand"] == "aus" and s["version"]

        assert c.post("/api/dienste/probe/starten").status_code == 403          # ohne Kopf
        r = c.post("/api/dienste/probe/starten", headers=SCHREIBEN).json()
        assert r["erfolg"], r
        assert offen(port)
        r = c.post("/api/dienste/probe/neustarten", headers=SCHREIBEN).json()
        assert r["erfolg"] and offen(port)
        zeilen = c.get("/api/dienste/probe/protokoll?zeilen=50").json()["zeilen"]
        assert any("gestartet vom Maschinenraum" in z for z in zeilen)
        assert c.post("/api/dienste/probe/anhalten", headers=SCHREIBEN).json()["erfolg"]
        assert not offen(port)
        assert c.post("/api/dienste/gibtsnicht/starten", headers=SCHREIBEN).status_code == 404


def test_fremder_rechnername_wird_abgewiesen(tmp_path: Path):
    with client(ordner_mit_dienst(tmp_path, freier_port())) as c:
        assert c.get("/api/stand", headers={"host": "boese.example:8540"}).status_code == 403
        assert c.get("/api/stand", headers={"host": "localhost:8540"}).status_code == 200


def test_leitstelle_eintragen_und_entfernen(tmp_path: Path):
    o = ordner_mit_dienst(tmp_path, freier_port())
    with client(o) as c:
        r = c.put("/api/leitstelle", json={"adresse": "http://127.0.0.1:9/", "schluessel": "ls_probe"}, headers=SCHREIBEN)
        assert r.status_code == 200 and r.json()["adresse"] == "http://127.0.0.1:9"
        assert o.einstellungen().leitstelle.adresse == "http://127.0.0.1:9"
        assert o.schluessel() == "ls_probe" and stat.S_IMODE(o.schluesseldatei.stat().st_mode) == 0o600
        assert 'adresse = "http://127.0.0.1:9"' in o.einstellungsdatei.read_text()
        assert c.put("/api/leitstelle", json={"adresse": "leitstelle:8530"}, headers=SCHREIBEN).status_code == 422
        r = c.put("/api/leitstelle", json={"adresse": "", "schluessel": ""}, headers=SCHREIBEN).json()
        assert r["zustand"] == "aus" and o.schluessel() is None and o.einstellungen().leitstelle.adresse is None
