"""Dienstverwaltung des Maschinenraums gegen echte kleine Prozesse: ein HTTP-Server aus der Standardbibliothek spielt
den Dienst. Starten, Anhalten, Neustarts und Abhängigkeiten prüft der Dienstkern selbst; hier geht es um das, was der
Maschinenraum dazutut: nur KI-Dienste, Berichte für die Leitstelle, Rechte der Leitstelle, Messung des Rechners."""

from __future__ import annotations

import asyncio
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from maschinenraum.konfig import Leitstelle, Ordner
from maschinenraum.messen import Messer, leistung_w, speicher, swap_mac
from maschinenraum.protokoll import Befehl, Befehlsart, Faehigkeit, Prozesszustand
from dienstkern.zustand import DienstStand

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


async def test_starten_berichten_anhalten(tmp_path: Path):
    port = freier_port()
    v = verwalter(ordner_mit_dienst(tmp_path, port))
    await v.runde()
    assert v.liste().dienste[0].zustand == Prozesszustand.AUS
    e = await v.befehl(Befehl(befehl=Befehlsart.DIENST_STARTEN, ziel="probe"))
    assert e.erfolg and e.befehl == Befehlsart.DIENST_STARTEN, e.meldung
    await v.runde()
    b = v.liste().dienste[0]
    assert b.zustand == Prozesszustand.LAEUFT and b.faehigkeiten == {Faehigkeit.STIMME} and b.gb_jetzt is not None and b.anhalten_erlaubt
    assert b.bedarf_gb >= max(b.gb_jetzt, 0.5)
    assert "gestartet vom Maschinenraum" in (tmp_path / "protokolle" / "probe.log").read_text()
    assert v.stand.dienste["probe"].soll == Soll.LAEUFT
    e = await v.neu_starten_befehl("probe")
    assert e.erfolg and offen(port)
    e = await v.befehl(Befehl(befehl=Befehlsart.DIENST_ANHALTEN, ziel="probe"))
    assert e.erfolg and e.meldung == "beendet" and not offen(port)


async def test_unbekannter_dienst(tmp_path: Path):
    v = verwalter(ordner_mit_dienst(tmp_path, freier_port()))
    await v.runde()
    e = await v.befehl(Befehl(befehl=Befehlsart.DIENST_STARTEN, ziel="gibtsnicht"), von_leitstelle=True)
    assert not e.erfolg and "unbekannt" in e.meldung


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


def test_nur_ki_dienste(tmp_path: Path):
    """Ohne Fähigkeit wird eine Datei abgelehnt: Webapps und ihre Datenbanken gehören ins Stellwerk."""
    o = ordner_mit_dienst(tmp_path, freier_port())
    datei = tmp_path / "dienste" / "probe.toml"
    (tmp_path / "dienste" / "webapp.toml").write_text(datei.read_text().replace('faehigkeiten = ["stimme"]\n', ""))
    (tmp_path / "dienste" / "leer.toml").write_text(datei.read_text().replace('faehigkeiten = ["stimme"]', "faehigkeiten = []"))
    (tmp_path / "dienste" / "Kaputt.toml").write_text('name = "x"\n')
    vorlagen, fehler = o.dienste()
    assert [v.kennung for v in vorlagen] == ["probe"]
    meldungen = {f.datei: f.meldung for f in fehler}
    assert set(meldungen) == {"webapp.toml", "leer.toml", "Kaputt.toml"}
    assert "Stellwerk" in meldungen["webapp.toml"] and "Stellwerk" in meldungen["leer.toml"]


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


def test_leistung_wie_macmon_total():
    """macmon zeigt bei "Total" sys_power (ganzer Rechner); all_power ist nur Prozessor, Grafik, Neural Engine."""
    assert leistung_w({"all_power": 2.2258, "sys_power": 15.8748}) == 15.9
    assert leistung_w({"all_power": 2.2258, "sys_power": 0.0}) == 2.2
    assert leistung_w({}) is None


async def test_plaetze_aus_der_dienstdatei_und_start_der_leitstelle(tmp_path: Path):
    """Die Dienstdatei nennt die Plätze (Vorgabe 1), der Bericht an die Leitstelle trägt sie. Ein Start der Leitstelle
    löscht keine Abstürze: bleibt ein Dienst nach zu vielen aus, startet sie ihn nicht."""
    from maschinenraum.prozesse import bericht
    from maschinenraum.protokoll import Befehl, Befehlsart

    port = freier_port()
    o = ordner_mit_dienst(tmp_path, port, plaetze="4")
    v = verwalter(o)
    await v.runde()
    assert bericht(v.dienste["probe"], v.speicherschutz).plaetze == 4
    v.dienste["probe"].abstuerze.extend([0.0] * (v.regeln.im_fenster + 1))
    e = await v.befehl(Befehl(befehl=Befehlsart.DIENST_STARTEN, ziel="probe"), von_leitstelle=True)
    assert not e.erfolg and "bleibt nach" in e.meldung


async def test_selbstauskunft_aus_der_dienstdatei(tmp_path: Path):
    """Die Dienstdatei sagt, wofür der Dienst gemacht ist (beschreibung, eignung, sprachen); der Bericht an die Leitstelle
    trägt es als Selbstauskunft (PROTOKOLL 4.8 der Leitstelle). Falsche Sprachkürzel lehnt die Datei ab."""
    from maschinenraum.konfig import DienstVorlage
    from maschinenraum.protokoll import Eignung
    from maschinenraum.prozesse import bericht

    port = freier_port()
    o = ordner_mit_dienst(tmp_path, port, beschreibung='"Sprechen mit fester Stimme, für Vorlesen"', eignung='["schnell"]', sprachen='["de", "en"]')
    v = verwalter(o)
    await v.runde()
    a = bericht(v.dienste["probe"], v.speicherschutz).selbstauskunft
    assert a.zweck == "Sprechen mit fester Stimme, für Vorlesen" and a.eignung == [Eignung.SCHNELL] and a.sprachen == ["de", "en"]
    try:
        DienstVorlage.model_validate({"kennung": "x", "name": "x", "ordner": str(tmp_path), "befehl": ["x"], "faehigkeiten": ["stimme"], "sprachen": ["Deutsch"]})
        raise AssertionError("Sprachkürzel nach ISO 639-1 verlangt")
    except ValueError as f:
        assert "ISO 639-1" in str(f)


def ordner_mit_instanzen(tmp: Path, instanzen: int = 2) -> tuple[Ordner, int]:
    """Dienst probe mit mehreren Instanzen: Instanz n auf port + 100 (n-1), den Port nimmt der Befehl aus $MASCHINENRAUM_PORT."""
    while True:
        port = freier_port()
        if port + 100 * (instanzen - 1) < 65536 and not any(offen(port + 100 * n) for n in range(1, instanzen)):
            break
    (tmp / "dienste").mkdir(parents=True, exist_ok=True)
    (tmp / "einstellungen.toml").write_text('[messung]\ntakt_s = 1\nmacmon = false\n[neustart]\npausen_s = [0.2]\n')
    instanzen_schreiben(tmp, port, instanzen)
    return Ordner(tmp), port


def instanzen_schreiben(tmp: Path, port: int, instanzen: int) -> None:
    (tmp / "dienste" / "probe.toml").write_text(
        f'name = "Probe"\nordner = "{tmp}"\nbefehl = ["{sys.executable}", "-m", "http.server", "$MASCHINENRAUM_PORT", "--bind", "127.0.0.1"]\n'
        f'port = {port}\nfaehigkeiten = ["hoeren"]\nspeicher_gb = 0.5\nstartzeit_s = 15\nanhaltezeit_s = 5\ninstanzen = {instanzen}\n')


async def test_weitere_instanz_auf_eigenem_port(tmp_path: Path):
    """Dienstdatei mit instanzen = 2: die Leitstelle startet die zweite Instanz (probe.2) auf port + 100, ihren Port
    bekommt der Befehl aus $MASCHINENRAUM_PORT; eine dritte gibt es nicht; angehalten ist die Instanz weg."""
    o, port = ordner_mit_instanzen(tmp_path)
    v = verwalter(o)
    await v.runde()
    e = await v.befehl(Befehl(befehl=Befehlsart.DIENST_STARTEN, ziel="probe.2"), von_leitstelle=True)
    assert e.erfolg, e.meldung
    await v.runde()
    b = next(x for x in v.liste().dienste if x.kennung == "probe.2")
    assert b.port == port + 100 and b.instanz_von == "probe" and b.instanzen == 2 and b.zustand == Prozesszustand.LAEUFT and b.name == "Probe (2)"
    assert next(x for x in v.liste().dienste if x.kennung == "probe").instanz_von is None
    e = await v.befehl(Befehl(befehl=Befehlsart.DIENST_STARTEN, ziel="probe.3"), von_leitstelle=True)
    assert not e.erfolg and "erlaubt 2" in e.meldung
    e = await v.befehl(Befehl(befehl=Befehlsart.DIENST_ANHALTEN, ziel="probe.2"), von_leitstelle=True)
    assert e.erfolg
    await v.runde()
    assert [x.kennung for x in v.liste().dienste] == ["probe"]


async def _instanz_starten(o: Ordner) -> Verwalter:
    v = verwalter(o)
    await v.runde()
    e = await v.befehl(Befehl(befehl=Befehlsart.DIENST_STARTEN, ziel="probe.2"), von_leitstelle=True)
    assert e.erfolg, e.meldung
    return v


async def test_weitere_instanz_nach_neustart_wiedergefunden(tmp_path: Path):
    """Befund vom 27.10.2026: eine weitere Instanz (klangwerk-hoeren.2) lief nach dem Neustart des Maschinenraums sieben
    Tage verwaist weiter; er kannte sie nicht mehr, meldete sie der Leitstelle nicht, und die Beobachtung zeigte sie als
    fremd. Jetzt findet ein neuer Lauf sie über ihre Gruppe im Stand wieder, meldet sie und kann sie anhalten."""
    o, port = ordner_mit_instanzen(tmp_path)
    await _instanz_starten(o)
    neu = verwalter(o)                                                        # derselbe Ordner: wie nach einem Neustart
    assert not neu.hochgefahren.is_set()
    await neu.hochfahren()
    assert neu.hochgefahren.is_set()
    b = next(x for x in neu.liste().dienste if x.kennung == "probe.2")
    assert b.zustand == Prozesszustand.LAEUFT and b.instanz_von == "probe" and not b.fremd and b.gb_jetzt is not None
    assert not offen(port)                                                    # die Grundinstanz soll nicht laufen: nicht gestartet
    e = await neu.befehl(Befehl(befehl=Befehlsart.DIENST_ANHALTEN, ziel="probe.2"), von_leitstelle=True)
    assert e.erfolg and not offen(port + 100)


async def test_weitere_instanz_ohne_stand_ueber_den_port_wiedergefunden(tmp_path: Path):
    """Fehlt der Stand (etwa nach einem Rückspielen ohne zustand.json), findet der Port die Instanz, wie bei der Grundinstanz."""
    o, port = ordner_mit_instanzen(tmp_path)
    await _instanz_starten(o)
    o.zustand_datei.unlink()
    neu = verwalter(o)
    await neu.hochfahren()
    b = next(x for x in neu.liste().dienste if x.kennung == "probe.2")
    assert b.zustand == Prozesszustand.LAEUFT and b.fremd
    e = await neu.befehl(Befehl(befehl=Befehlsart.DIENST_ANHALTEN, ziel="probe.2"), von_leitstelle=True)
    assert e.erfolg and not offen(port + 100)


async def test_weitere_instanz_die_nicht_mehr_laeuft_wird_vergessen(tmp_path: Path):
    """Steht eine Instanz im Stand, läuft aber nicht mehr, startet der neue Lauf sie nicht von selbst (die Leitstelle
    entscheidet über Instanzen) und vergisst sie."""
    o, port = ordner_mit_instanzen(tmp_path)
    v = await _instanz_starten(o)
    assert (await v.befehl(Befehl(befehl=Befehlsart.DIENST_ANHALTEN, ziel="probe.2"), von_leitstelle=True)).erfolg
    v.stand.dienste["probe.2"].soll = Soll.LAEUFT                            # wie nach einem Absturz mit dem Rechner
    v._stand_speichern()
    neu = verwalter(o)
    await neu.hochfahren()
    await asyncio.sleep(0.5)
    assert [x.kennung for x in neu.liste().dienste] == ["probe"] and not offen(port + 100)
    assert "probe.2" not in neu.stand.dienste


async def test_instanz_ueber_der_hoechstzahl_wird_beendet(tmp_path: Path):
    """Die Höchstzahl der Dienstdatei sank, während der Maschinenraum aus war: die Instanz aus eigener Gruppe wird beendet."""
    o, port = ordner_mit_instanzen(tmp_path)
    await _instanz_starten(o)
    instanzen_schreiben(tmp_path, port, 1)
    neu = verwalter(o)
    await neu.hochfahren()
    assert not offen(port + 100) and [x.kennung for x in neu.liste().dienste] == ["probe"]
    assert "probe.2" not in neu.stand.dienste


async def test_fremdes_programm_auf_dem_port_einer_unerlaubten_stufe_bleibt(tmp_path: Path):
    """Lauscht auf dem Port einer Stufe über der Höchstzahl ein Programm, das nicht nachweislich von hier stammt (keine
    Gruppe im Stand), fasst der Maschinenraum es nicht an."""
    o, port = ordner_mit_instanzen(tmp_path, instanzen=1)
    fremd = subprocess.Popen([sys.executable, "-m", "http.server", str(port + 100), "--bind", "127.0.0.1"], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            if offen(port + 100):
                break
            await asyncio.sleep(0.1)
        neu = verwalter(o)
        neu.stand.dienste["probe.2"] = DienstStand(soll=Soll.LAEUFT)        # Rest eines früheren Laufs ohne Gruppe
        await neu.hochfahren()
        assert offen(port + 100) and fremd.poll() is None and [x.kennung for x in neu.liste().dienste] == ["probe"]
    finally:
        fremd.terminate()
        fremd.wait()


def test_instanzen_brauchen_den_port_im_befehl(tmp_path: Path):
    from maschinenraum.konfig import DienstVorlage
    grund = {"kennung": "x", "name": "x", "ordner": str(tmp_path), "faehigkeiten": ["hoeren"], "port": 9000, "instanzen": 2}
    try:
        DienstVorlage.model_validate({**grund, "befehl": ["dienst", "--port", "9000"]})
        raise AssertionError("ohne $MASCHINENRAUM_PORT können Instanzen nicht auf eigenen Ports laufen")
    except ValueError as f:
        assert "MASCHINENRAUM_PORT" in str(f)
    assert DienstVorlage.model_validate({**grund, "befehl": ["dienst", "--port", "$MASCHINENRAUM_PORT"]}).instanzen == 2


async def test_dienste_finden_die_modellablage(tmp_path: Path):
    o = ordner_mit_dienst(tmp_path, freier_port(), umgebung='{ EIGEN = "$MASCHINENRAUM_MODELLE/bild" }')
    v = verwalter(o)
    await v.runde()
    env = v.dienste["probe"]._umgebung()
    assert env["MASCHINENRAUM_MODELLE"] == str(o.modelle) and env["HF_HUB_CACHE"] == str(o.modelle / "huggingface")
    assert env["EIGEN"] == str(o.modelle / "bild")
    assert "HF_HOME" not in env      # Anmeldedaten von Hugging Face bleiben, wo sie sind


async def test_dienstdatei_geht_vor_der_ablage(tmp_path: Path):
    v = verwalter(ordner_mit_dienst(tmp_path, freier_port(), umgebung='{ HF_HUB_CACHE = "/anderswo" }'))
    await v.runde()
    assert v.dienste["probe"]._umgebung()["HF_HUB_CACHE"] == "/anderswo"
