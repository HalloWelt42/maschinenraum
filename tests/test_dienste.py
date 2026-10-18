"""Dienstverwaltung des Maschinenraums gegen echte kleine Prozesse: ein HTTP-Server aus der Standardbibliothek spielt
den Dienst. Starten, Anhalten, Neustarts und Abhängigkeiten prüft der Dienstkern selbst; hier geht es um das, was der
Maschinenraum dazutut: nur KI-Dienste, Berichte für die Leitstelle, Rechte der Leitstelle, Messung des Rechners."""

from __future__ import annotations

import socket
import sys
from pathlib import Path

import pytest

from maschinenraum.konfig import Leitstelle, Ordner
from maschinenraum.messen import Messer, leistung_w, speicher, swap_mac
from maschinenraum.protokoll import Befehl, Befehlsart, Faehigkeit, Prozesszustand
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
    assert bericht(v.dienste["probe"]).plaetze == 4
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
    a = bericht(v.dienste["probe"]).selbstauskunft
    assert a.zweck == "Sprechen mit fester Stimme, für Vorlesen" and a.eignung == [Eignung.SCHNELL] and a.sprachen == ["de", "en"]
    try:
        DienstVorlage.model_validate({"kennung": "x", "name": "x", "ordner": str(tmp_path), "befehl": ["x"], "faehigkeiten": ["stimme"], "sprachen": ["Deutsch"]})
        raise AssertionError("Sprachkürzel nach ISO 639-1 verlangt")
    except ValueError as f:
        assert "ISO 639-1" in str(f)
