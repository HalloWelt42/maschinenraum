"""Befehlsdienste (Start kehrt zurück, Prüfen und Anhalten per Befehl) und Abhängigkeiten, gegen echte Prozesse."""

from __future__ import annotations

import sys
from pathlib import Path

from maschinenraum.konfig import Ordner
from maschinenraum.protokoll import Befehl, Befehlsart, Prozesszustand
from maschinenraum.prozesse import Verwalter

from test_dienste import freier_port, offen

STARTEN = ("import subprocess, sys; p = subprocess.Popen([sys.executable, '-m', 'http.server', '{port}', '--bind', '127.0.0.1'], "
           "start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); open('pid', 'w').write(str(p.pid))")
ANHALTEN = "import os, signal; os.kill(int(open('pid').read()), signal.SIGTERM)"


def befehlsdienst(tmp: Path, port: int, mehr: str = "") -> None:
    (tmp / "dienste").mkdir(parents=True, exist_ok=True)
    (tmp / "einstellungen.toml").write_text("[messung]\ntakt_s = 1\nmacmon = false\n")
    (tmp / "dienste" / "laufzeit.toml").write_text(
        f'name = "Laufzeit"\nordner = "{tmp}"\nsteuerung = "befehle"\nport = {port}\nspeicher_gb = 0.5\nstartzeit_s = 15\nanhaltezeit_s = 10\n'
        f'prozessmuster = "http.server {port}"\n'
        f'befehl = ["{sys.executable}", "-c", "{STARTEN.format(port=port)}"]\nanhaltebefehl = ["{sys.executable}", "-c", "{ANHALTEN}"]\n{mehr}')


async def test_befehlsdienst_starten_messen_anhalten(tmp_path: Path):
    port = freier_port()
    befehlsdienst(tmp_path, port)
    v = Verwalter(Ordner(tmp_path), Ordner(tmp_path).einstellungen())
    await v.runde()
    assert v.liste().dienste[0].zustand == Prozesszustand.AUS
    e = await v.befehl(Befehl(befehl=Befehlsart.DIENST_STARTEN, ziel="laufzeit"))
    assert e.erfolg, e.meldung
    assert offen(port)
    await v.runde()
    b = v.liste().dienste[0]
    assert b.zustand == Prozesszustand.LAEUFT and b.gb_jetzt is not None and b.gb_jetzt > 0 and not b.fremd
    e = await v.befehl(Befehl(befehl=Befehlsart.DIENST_ANHALTEN, ziel="laufzeit"))
    assert e.erfolg and e.meldung == "beendet" and not offen(port)
    await v.runde()
    assert v.liste().dienste[0].zustand == Prozesszustand.AUS


async def test_abhaengigkeit_wird_zuerst_gestartet(tmp_path: Path):
    port_a, port_b = freier_port(), freier_port()
    befehlsdienst(tmp_path, port_a)
    (tmp_path / "dienste" / "datenbank.toml").write_text(
        f'name = "Datenbank"\nordner = "{tmp_path}"\nbefehl = ["{sys.executable}", "-m", "http.server", "{port_b}", "--bind", "127.0.0.1"]\n'
        f'port = {port_b}\nbraucht = ["laufzeit"]\nstartzeit_s = 15\nanhaltezeit_s = 5\n')
    v = Verwalter(Ordner(tmp_path), Ordner(tmp_path).einstellungen())
    await v.runde()
    e = await v.befehl(Befehl(befehl=Befehlsart.DIENST_STARTEN, ziel="datenbank"))
    assert e.erfolg, e.meldung
    assert offen(port_a) and offen(port_b)
    assert v.stand.dienste["laufzeit"].soll.value == "laeuft"
    for k in ("datenbank", "laufzeit"):
        await v.befehl(Befehl(befehl=Befehlsart.DIENST_ANHALTEN, ziel=k))
    assert not offen(port_a) and not offen(port_b)


async def test_abhaengigkeit_im_kreis_und_unbekannt(tmp_path: Path):
    port = freier_port()
    befehlsdienst(tmp_path, port, mehr='braucht = ["laufzeit"]\n')
    v = Verwalter(Ordner(tmp_path), Ordner(tmp_path).einstellungen())
    await v.runde()
    e = await v.befehl(Befehl(befehl=Befehlsart.DIENST_STARTEN, ziel="laufzeit"))
    assert not e.erfolg and "Kreis" in e.meldung and not offen(port)


def test_befehlsdienst_braucht_anhaltebefehl_und_pruefung(tmp_path: Path):
    (tmp_path / "dienste").mkdir()
    (tmp_path / "dienste" / "halb.toml").write_text(f'name = "Halb"\nordner = "{tmp_path}"\nsteuerung = "befehle"\nbefehl = ["true"]\nport = 1\n')
    (tmp_path / "dienste" / "blind.toml").write_text(f'name = "Blind"\nordner = "{tmp_path}"\nsteuerung = "befehle"\nbefehl = ["true"]\nanhaltebefehl = ["true"]\n')
    vorlagen, fehler = Ordner(tmp_path).dienste()
    assert not vorlagen and sorted(f.datei for f in fehler) == ["blind.toml", "halb.toml"]
    meldungen = {f.datei: f.meldung for f in fehler}
    assert "anhaltebefehl" in meldungen["halb.toml"] and "port, pruefadresse oder pruefbefehl" in meldungen["blind.toml"]
