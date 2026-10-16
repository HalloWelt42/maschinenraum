"""Dienstverwaltung gegen echte kleine Prozesse: ein HTTP-Server aus der Standardbibliothek spielt den Dienst."""

from __future__ import annotations

import asyncio
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from maschinenraum.konfig import Leitstelle, Ordner
from maschinenraum.messen import Messer, rechenzeit, speicher, swap_mac
from maschinenraum.protokoll import Befehl, Befehlsart, Prozesszustand
from maschinenraum.prozesse import Soll, Verwalter


def freier_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def offen(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def ordner_mit_dienst(tmp: Path, port: int, **mehr: str) -> Ordner:
    (tmp / "dienste").mkdir(parents=True, exist_ok=True)
    (tmp / "einstellungen.toml").write_text('[messung]\ntakt_s = 1\nmacmon = false\n[neustart]\npausen_s = [0.2]\n')
    zeilen = [f'name = "Probe"', f'ordner = "{tmp}"', f'befehl = ["{sys.executable}", "-m", "http.server", "{port}", "--bind", "127.0.0.1"]',
              f"port = {port}", 'faehigkeiten = ["stimme"]', "speicher_gb = 0.5", "startzeit_s = 15", "anhaltezeit_s = 5",
              *(f"{k} = {v}" for k, v in mehr.items())]
    (tmp / "dienste" / "probe.toml").write_text("\n".join(zeilen) + "\n")
    return Ordner(tmp)


def verwalter(o: Ordner) -> Verwalter:
    return Verwalter(o, o.einstellungen())


async def test_starten_messen_anhalten(tmp_path: Path):
    port = freier_port()
    v = verwalter(ordner_mit_dienst(tmp_path, port))
    await v.runde()
    assert v.liste().dienste[0].zustand == Prozesszustand.AUS
    e = await v.befehl(Befehl(befehl=Befehlsart.DIENST_STARTEN, ziel="probe"))
    assert e.erfolg, e.meldung
    assert offen(port)
    await v.runde()
    b = v.liste().dienste[0]
    assert b.zustand == Prozesszustand.LAEUFT and b.gb_jetzt is not None and 0 < b.gb_jetzt < 2 and not b.fremd
    assert b.bedarf_gb >= max(b.gb_jetzt, 0.5)                    # mindestens die Schätzung der Dienstdatei
    assert (tmp_path / "protokolle" / "probe.log").exists()
    assert v.stand.dienste["probe"].soll == Soll.LAEUFT
    e = await v.befehl(Befehl(befehl=Befehlsart.DIENST_ANHALTEN, ziel="probe"))
    assert e.erfolg and e.meldung == "beendet"
    assert not offen(port)
    await v.runde()
    b = v.liste().dienste[0]
    assert b.zustand == Prozesszustand.AUS and b.gb_jetzt is None and not b.aktiv
    assert b.bedarf_gb == round(max(v.stand.dienste["probe"].spitze_gb, 0.5), 2)   # Bedarf bleibt nach dem Anhalten bekannt


async def test_absturz_fuehrt_zu_neustart(tmp_path: Path):
    port = freier_port()
    v = verwalter(ordner_mit_dienst(tmp_path, port))
    await v.runde()
    assert (await v.befehl(Befehl(befehl=Befehlsart.DIENST_STARTEN, ziel="probe"))).erfolg
    gruppe = v.stand.dienste["probe"].gruppe
    os.killpg(gruppe, signal.SIGKILL)
    await asyncio.sleep(0.3)
    await v.runde()
    d = v.dienste["probe"]
    assert d.zustand == Prozesszustand.GESTOERT and "Neustart" in d.meldung
    await asyncio.sleep(0.3)
    await v.runde()                       # fälliger Neustart wird angestoßen
    for _ in range(40):
        await asyncio.sleep(0.25)
        if d.zustand == Prozesszustand.LAEUFT:
            break
    assert d.zustand == Prozesszustand.LAEUFT and offen(port)
    await v.befehl(Befehl(befehl=Befehlsart.DIENST_ANHALTEN, ziel="probe"))


async def test_zu_viele_abstuerze_dienst_bleibt_aus(tmp_path: Path):
    port = freier_port()
    o = ordner_mit_dienst(tmp_path, port)
    (tmp_path / "einstellungen.toml").write_text('[neustart]\nim_fenster = 0\n')
    v = verwalter(o)
    await v.runde()
    assert (await v.befehl(Befehl(befehl=Befehlsart.DIENST_STARTEN, ziel="probe"))).erfolg
    os.killpg(v.stand.dienste["probe"].gruppe, signal.SIGKILL)
    await asyncio.sleep(0.3)
    await v.runde()
    d = v.dienste["probe"]
    assert d.zustand == Prozesszustand.GESTOERT and d.neustart_um is None and v.stand.dienste["probe"].soll == Soll.AUS


async def test_fremd_gestarteter_dienst_wird_uebernommen_und_angehalten(tmp_path: Path):
    port = freier_port()
    fremd = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(40):
            if offen(port):
                break
            time.sleep(0.1)
        v = verwalter(ordner_mit_dienst(tmp_path, port))
        await v.runde()
        b = v.liste().dienste[0]
        assert b.zustand == Prozesszustand.LAEUFT and b.fremd
        e = await v.befehl(Befehl(befehl=Befehlsart.DIENST_STARTEN, ziel="probe"))
        assert e.erfolg and "bereits" in e.meldung
        e = await v.befehl(Befehl(befehl=Befehlsart.DIENST_ANHALTEN, ziel="probe"))
        assert e.erfolg
        assert fremd.wait(timeout=5) is not None
    finally:
        if fremd.poll() is None:
            fremd.kill()


async def test_sollzustand_uebersteht_neustart_des_agenten(tmp_path: Path):
    port = freier_port()
    o = ordner_mit_dienst(tmp_path, port)
    v = verwalter(o)
    await v.runde()
    assert (await v.befehl(Befehl(befehl=Befehlsart.DIENST_STARTEN, ziel="probe"))).erfolg
    os.killpg(v.stand.dienste["probe"].gruppe, signal.SIGKILL)       # Dienst weg, Maschinenraum neu gestartet (neuer Verwalter)
    await asyncio.sleep(0.3)
    neu = verwalter(o)
    assert neu.stand.dienste["probe"].soll == Soll.LAEUFT
    await neu.hochfahren()
    for _ in range(40):
        await asyncio.sleep(0.25)
        if offen(port) and neu.dienste["probe"].zustand == Prozesszustand.LAEUFT:
            break
    assert neu.dienste["probe"].zustand == Prozesszustand.LAEUFT
    await neu.befehl(Befehl(befehl=Befehlsart.DIENST_ANHALTEN, ziel="probe"))


async def test_laufende_eigene_gruppe_wird_nach_neustart_des_agenten_wiedererkannt(tmp_path: Path):
    port = freier_port()
    o = ordner_mit_dienst(tmp_path, port)
    v = verwalter(o)
    await v.runde()
    assert (await v.befehl(Befehl(befehl=Befehlsart.DIENST_STARTEN, ziel="probe"))).erfolg
    neu = verwalter(o)
    await neu.runde()
    b = neu.liste().dienste[0]
    assert b.zustand == Prozesszustand.LAEUFT and not b.fremd
    assert (await neu.befehl(Befehl(befehl=Befehlsart.DIENST_ANHALTEN, ziel="probe"))).erfolg
    assert not offen(port)
    v.dienste["probe"].prozess.wait(timeout=5)


async def test_startzeit_ueberschritten_beendet_den_versuch(tmp_path: Path):
    port = freier_port()
    o = ordner_mit_dienst(tmp_path, port)
    datei = tmp_path / "dienste" / "probe.toml"
    datei.write_text(datei.read_text().replace(f'"-m", "http.server", "{port}", "--bind", "127.0.0.1"', '"-c", "import time; time.sleep(60)"')
                     .replace("startzeit_s = 15", "startzeit_s = 1"))
    v = verwalter(o)
    await v.runde()
    e = await v.befehl(Befehl(befehl=Befehlsart.DIENST_STARTEN, ziel="probe"))
    assert not e.erfolg and "nicht erreichbar" in e.meldung
    assert v.stand.dienste["probe"].gruppe is None


async def test_umgebung_ist_abgegrenzt(tmp_path: Path):
    port = freier_port()
    o = ordner_mit_dienst(tmp_path, port)
    (tmp_path / "geheim.env").write_text("# Kommentar\nAUS_DATEI='ja'\n")
    datei = tmp_path / "dienste" / "probe.toml"
    datei.write_text(datei.read_text() + f'umgebung_datei = "{tmp_path}/geheim.env"\n[umgebung]\nEIGENES = "1"\n')
    os.environ["NICHT_WEITERGEBEN"] = "x"
    v = verwalter(o)
    await v.runde()
    env = v.dienste["probe"]._umgebung()
    assert env["AUS_DATEI"] == "ja" and env["EIGENES"] == "1" and "NICHT_WEITERGEBEN" not in env


def test_variablen_kommen_aus_der_dienstumgebung(tmp_path: Path):
    o = ordner_mit_dienst(tmp_path, freier_port())
    vorlage = o.dienste()[0][0].model_copy(update={"befehl": ["$PROG", "--pfad", "${HOME}/x", "$UNBEKANNT"]})
    assert vorlage.programm({"PROG": "/opt/py", "HOME": "/h"}) == ["/opt/py", "--pfad", "/h/x", "$UNBEKANNT"]
    assert vorlage.model_copy(update={"befehl": ["bin/start"]}).programm({})[0] == str(tmp_path / "bin/start")


def test_fehlerhafte_dienstdatei_wird_gemeldet(tmp_path: Path):
    o = ordner_mit_dienst(tmp_path, freier_port())
    (tmp_path / "dienste" / "Kaputt.toml").write_text('name = "x"\n')
    vorlagen, fehler = o.dienste()
    assert [v.kennung for v in vorlagen] == ["probe"] and fehler[0].datei == "Kaputt.toml"


def test_speicher_und_messer():
    gesamt, belegt, swap, swap_gesamt = speicher()
    assert gesamt > 0 and 0 < belegt < gesamt
    m = Messer(takt_s=5, macmon=False).messen()
    assert m.speicher_gesamt_gb == pytest.approx(gesamt, rel=0.01) and m.platte_frei_gb > 0


def test_kanaladresse():
    assert Leitstelle(adresse="http://leitstelle:8530/").kanal == "ws://leitstelle:8530/agent/kanal"
    assert Leitstelle(adresse="https://leitstelle").kanal == "wss://leitstelle/agent/kanal"
    assert Leitstelle().kanal is None


def test_swap_auch_mit_dezimalkomma():
    assert swap_mac("total = 18432.00M  used = 17117.56M  free = 1314.44M  (encrypted)") == (17117.56 / 1024, 18.0)
    assert swap_mac("total = 18432,00M  used = 17117,56M  free = 1314,44M  (encrypted)") == (17117.56 / 1024, 18.0)
    assert swap_mac("unbekannt") == (None, None)


BESCHAEFTIGT = ("import socket, threading, time\n"
                "s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); s.bind(('127.0.0.1', {port})); s.listen()\n"
                "threading.Thread(target=lambda: [None for _ in iter(int, 1)], daemon=True).start()\n"
                "time.sleep(120)\n")


async def test_arbeit_wird_an_der_prozessorlast_erkannt(tmp_path: Path):
    port = freier_port()
    o = ordner_mit_dienst(tmp_path, port)
    (tmp_path / "last.py").write_text(BESCHAEFTIGT.format(port=port))
    datei = tmp_path / "dienste" / "probe.toml"
    datei.write_text(datei.read_text().replace(f'"-m", "http.server", "{port}", "--bind", "127.0.0.1"', f'"{tmp_path}/last.py"'))
    v = verwalter(o)
    await v.runde()
    assert (await v.befehl(Befehl(befehl=Befehlsart.DIENST_STARTEN, ziel="probe"))).erfolg
    await v.runde()
    await asyncio.sleep(1.0)
    await v.runde()
    d = v.dienste["probe"]
    assert d.cpu_prozent is not None and d.cpu_prozent > 50 and d.bericht().aktiv
    await v.befehl(Befehl(befehl=Befehlsart.DIENST_ANHALTEN, ziel="probe"))
    assert not d.bericht().aktiv


async def test_leitstelle_darf_nur_anhalten_was_erlaubt_ist(tmp_path: Path):
    port = freier_port()
    o = ordner_mit_dienst(tmp_path, port, leitstelle_anhalten="false")
    v = verwalter(o)
    await v.runde()
    assert not v.liste().dienste[0].anhalten_erlaubt
    assert (await v.befehl(Befehl(befehl=Befehlsart.DIENST_STARTEN, ziel="probe"), von_leitstelle=True)).erfolg   # starten darf sie
    e = await v.befehl(Befehl(befehl=Befehlsart.DIENST_ANHALTEN, ziel="probe"), von_leitstelle=True)
    assert not e.erfolg and "nur von Hand" in e.meldung and offen(port)
    assert (await v.befehl(Befehl(befehl=Befehlsart.DIENST_ANHALTEN, ziel="probe"))).erfolg                       # von Hand immer
    assert not offen(port)


def test_rechenzeit_aus_ps():
    assert rechenzeit("0:01.50") == 1.5
    assert rechenzeit("12:03.00") == 723.0
    assert rechenzeit("1:00:00") == 3600.0
    assert rechenzeit("2-01:00:00") == 2 * 86400 + 3600.0
