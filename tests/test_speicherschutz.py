"""Speicherschutz im Maschinenraum (HELF-85): ein Testdienst, der während eines Auftrags absichtlich Speicher belegt (höchstens
1,2 GB, weit unter dem, was der Rechner hat), wird über der Grenze beendet und gesperrt; die Leitstelle bekommt 507
`speicher` statt einer abgerissenen Verbindung, danach 423 `dienst_gesperrt`, und ihr Startbefehl wird abgelehnt.
Die Grenze steht auch in der Umgebung des Dienstes (für torch auf der Grafik als Marken)."""

from __future__ import annotations

import asyncio
import json
import sys
import threading
import time
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from maschinenraum import durchleitung
from maschinenraum.api import erstellen
from maschinenraum.konfig import Ordner
from maschinenraum.prozesse import GRENZE_VARIABLE, TORCH_HOCH, TORCH_NIEDRIG
from maschinenraum.protokoll import Befehl, Befehlsart

from test_dienste import freier_port

SCHLUESSEL = {"Authorization": "Bearer ls_probe"}
OBEN = {"X-Maschinenraum": "1"}

DIENST = '''
import json, os, sys, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
gehalten = []
class A(BaseHTTPRequestHandler):
    def do_GET(self):
        daten = json.dumps({k: v for k, v in os.environ.items() if k.startswith(("PYTORCH_", "MASCHINENRAUM_"))}).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(daten))); self.end_headers(); self.wfile.write(daten)
    def do_POST(self):
        for _ in range(12):                                   # 100 MB je Schritt, höchstens 1,2 GB, dann erst die Antwort
            b = bytearray(100 * 1024 * 1024); b[::4096] = b"\\x01" * len(range(0, len(b), 4096)); gehalten.append(b)
            time.sleep(0.15)
        self.send_response(200); self.send_header("Content-Length", "2"); self.end_headers(); self.wfile.write(b"ok")
    def log_message(self, *a): pass
ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), A).serve_forever()
'''


def ordner(tmp: Path, port: int) -> Ordner:
    (tmp / "dienste").mkdir(parents=True, exist_ok=True)
    (tmp / "dienst.py").write_text(DIENST)
    (tmp / "einstellungen.toml").write_text('[messung]\ntakt_s = 1\nmacmon = false\n[neustart]\npausen_s = [0.2]\n'
                                             '[speicherschutz]\ntakt_s = 0.2\nfaktor = 1.5\nzuschlag_gb = 0.2\nfrei_mindestens_prozent = 0\n'
                                             'swap_hoechstens_gb = 0\nswap_zuwachs_gb_je_min = 0\nswap_geduldet_gb = 4096\n')
    (tmp / "dienste" / "hoerer.toml").write_text("\n".join([
        'name = "Hörer"', f'ordner = "{tmp}"', f'befehl = ["{sys.executable}", "dienst.py", "{port}"]', f"port = {port}",
        'faehigkeiten = ["hoeren"]', "speicher_gb = 0.1", "startzeit_s = 15", "anhaltezeit_s = 5"]) + "\n")   # Grenze 0,35 GB
    return Ordner(tmp)


def test_wachsender_dienst_wird_mitten_im_auftrag_beendet_und_gesperrt(tmp_path: Path):
    port = freier_port()
    o = ordner(tmp_path, port)
    o.schluessel_speichern("ls_probe")
    app = erstellen(o)
    lz = app.state.laufzeit
    with TestClient(app, base_url="http://127.0.0.1:8540") as oben, TestClient(durchleitung.erstellen(lz)) as weg:
        assert lz.verwalter.vor_speicherabbruch is not None, "der Kanal zur Leitstelle sagt den Abbruch vorher weiter"
        e = oben.post("/api/dienste/hoerer/starten", headers=OBEN).json()
        assert e["erfolg"], e
        umgebung = weg.get("/hoerer/umgebung", headers=SCHLUESSEL).json()
        assert umgebung[GRENZE_VARIABLE] == "0.35"
        if TORCH_HOCH in umgebung:                            # nur mit Grafik (Mac): Marken für torch aus der Grenze
            assert 0 < float(umgebung[TORCH_NIEDRIG]) < float(umgebung[TORCH_HOCH]) < 0.05
        ansicht = next(d for d in oben.get("/api/stand").json()["dienste"] if d["kennung"] == "hoerer")
        assert ansicht["grenze_gb"] == 0.35 and ansicht["schaetzung_gb"] == 0.1 and ansicht["sperre"] is None

        r = weg.post("/hoerer/arbeit", headers=SCHLUESSEL, content=b"{}")       # wächst, bis die Wache eingreift
        assert r.status_code == 507, r.text
        assert r.json()["error"]["code"] == "speicher" and "abgebrochen: Speicher" in r.json()["error"]["message"]
        assert r.headers["x-maschinenraum-grund"] == "speicher"

        r = weg.get("/hoerer/umgebung", headers=SCHLUESSEL)
        assert r.status_code == 423 and r.json()["grund"] == "dienst_gesperrt"
        ende = time.monotonic() + 5                           # das Beenden wartet noch, bis die Gruppe weg ist
        while lz.verwalter.dienste["hoerer"].zustand.value != "gestoert" and time.monotonic() < ende:
            time.sleep(0.1)
        liste = {b.kennung: b for b in lz.verwalter.liste().dienste}
        assert liste["hoerer"].sperre and liste["hoerer"].sperre.startswith("abgebrochen: Speicher")
        assert liste["hoerer"].zustand.value == "gestoert" and liste["hoerer"].grenze_gb == 0.35

        # Die Leitstelle stößt denselben Auftrag wieder an (Geduld bei Ausfall): ihr Start wird abgelehnt
        e = asyncio.run(lz.verwalter.befehl(Befehl(befehl=Befehlsart.DIENST_STARTEN, ziel="hoerer"), von_leitstelle=True))
        assert not e.erfolg and "gesperrt" in e.meldung
        time.sleep(1.5)                                       # Runden der Dienstprüfung: nichts startet von selbst
        assert lz.verwalter.dienste["hoerer"].stand.gruppe is None
        assert weg.get("/hoerer/umgebung", headers=SCHLUESSEL).status_code == 423

        ansicht = next(d for d in oben.get("/api/stand").json()["dienste"] if d["kennung"] == "hoerer")
        assert ansicht["sperre"].startswith("abgebrochen: Speicher") and ansicht["sperre_seit"]
        assert "gesperrt" in ansicht["meldung"]
        assert "Speicherwache" in oben.get("/api/dienste/hoerer/protokoll").json()["zeilen"][-1]

        # Nur der Mensch hebt die Sperre auf (schreibend nur mit dem Kopf der Oberfläche); gestartet wird damit nichts
        assert oben.post("/api/dienste/hoerer/entsperren").status_code == 403
        e = oben.post("/api/dienste/hoerer/entsperren", headers=OBEN).json()
        assert e["erfolg"], e
        assert lz.verwalter.dienste["hoerer"].stand.gruppe is None
        ansicht = next(d for d in oben.get("/api/stand").json()["dienste"] if d["kennung"] == "hoerer")
        assert ansicht["sperre"] is None and ansicht["zustand"] == "aus"

        # Von Hand sperren (neuer Dienst bis zur Kurzmessung) und gemessene Spitzen verwerfen (nach einem Umbau)
        assert oben.post("/api/dienste/hoerer/sperren", json={"grund": "x"}).status_code == 403
        assert oben.post("/api/dienste/hoerer/sperren", headers=OBEN, json={"grund": ""}).status_code == 422
        e = oben.post("/api/dienste/hoerer/sperren", headers=OBEN, json={"grund": "neu eingerichtet, Kurzmessung steht aus"}).json()
        assert e["erfolg"], e
        ansicht = next(d for d in oben.get("/api/stand").json()["dienste"] if d["kennung"] == "hoerer")
        assert ansicht["sperre"] == "neu eingerichtet, Kurzmessung steht aus"
        e = asyncio.run(lz.verwalter.befehl(Befehl(befehl=Befehlsart.DIENST_STARTEN, ziel="hoerer"), von_leitstelle=True))
        assert not e.erfolg and "gesperrt" in e.meldung
        assert oben.post("/api/dienste/hoerer/entsperren", headers=OBEN).json()["erfolg"]
        lz.verwalter.dienste["hoerer"].stand.arbeitsspitzen = [4.27, 133.48]
        e = oben.post("/api/dienste/hoerer/spitzen_verwerfen", headers=OBEN).json()
        assert e["erfolg"] and "2 Arbeitsspitzen" in e["meldung"]
        ansicht = next(d for d in oben.get("/api/stand").json()["dienste"] if d["kennung"] == "hoerer")
        assert ansicht["spitze_gb"] is None
        assert oben.post("/api/dienste/gibtsnicht/spitzen_verwerfen", headers=OBEN).status_code == 404
    assert json.loads((tmp_path / "zustand.json").read_text())["dienste"]["hoerer"]["sperre"] is None
