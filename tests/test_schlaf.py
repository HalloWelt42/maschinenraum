"""Schlaf des Rechners: Wächter gegen ein Schein-IOKit (nie die echte Energieverwaltung, außer einer Rauchprobe, die
sich nur an- und abmeldet) und Kanal gegen eine nachgestellte Leitstelle auf einem echten Port."""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

import pytest
import websockets

from maschinenraum import leitstelle as kanal_modul
from maschinenraum import schlaf
from maschinenraum.konfig import Einstellungen, Ordner, Schlaf, toml_schreiben
from maschinenraum.leitstelle import Leitstellenkanal, Verbindung
from maschinenraum.protokoll import Messwerte, Schlafgrund
from maschinenraum.prozesse import Verwalter
from maschinenraum.schlaf import KANN_SCHLAFEN, SCHLAEFT_EIN, SCHLAEFT_NICHT, WACH, Schlafwaechter
from maschinenraum.schlaf import bibliotheken as echte_bibliotheken

from conftest import ScheinCoreFoundation, ScheinIOKit


# ── Wächter ──────────────────────────────────────────────────────────────
class ScheinKanal:
    def __init__(self, dauer_s: float = 0.0) -> None:
        self.eingeschlafen: list[Schlafgrund] = []
        self.aufgewacht = 0
        self.dauer_s = dauer_s

    async def einschlafen(self, grund: Schlafgrund) -> None:
        await asyncio.sleep(self.dauer_s)
        self.eingeschlafen.append(grund)

    def aufwachen(self) -> None:
        self.aufgewacht += 1


class Lage:
    def __init__(self) -> None:
        self.durchleitungen = 0
        self.einstellung = Schlaf()


def waechter(kanal: ScheinKanal, lage: Lage, wach: bool = True) -> tuple[Schlafwaechter, ScheinIOKit, ScheinCoreFoundation]:
    io, cf = ScheinIOKit(), ScheinCoreFoundation()
    w = Schlafwaechter(kanal, lambda: lage.durchleitungen, lambda: lage.einstellung, laden=lambda: (io, cf, 0),
                       wach_pruefen=lambda: wach, system="darwin")
    return w, io, cf


async def nachricht(io: ScheinIOKit, art: int, kennung: int) -> None:
    """Wie IOKit: im eigenen Faden, über den echten Rückruf (CFUNCTYPE)."""
    await asyncio.to_thread(io.rueckruf, None, 0, art, kennung)


async def test_leerlauf_wird_nur_aufgeschoben_solange_durchgereicht_wird():
    kanal, lage = ScheinKanal(), Lage()
    w, io, cf = waechter(kanal, lage)
    assert w.starten(asyncio.get_running_loop()) and cf.laeuft.wait(2)
    try:
        await nachricht(io, KANN_SCHLAFEN, 1)
        lage.durchleitungen = 2
        await nachricht(io, KANN_SCHLAFEN, 2)
        lage.einstellung = Schlaf(leerlauf_aufschieben=False)
        await nachricht(io, KANN_SCHLAFEN, 3)
        assert io.erlaubt == [(io.WURZEL, 1), (io.WURZEL, 3)] and io.abgelehnt == [(io.WURZEL, 2)]
    finally:
        w.stoppen()


async def test_einschlafen_wird_gemeldet_und_immer_quittiert(monkeypatch):
    kanal, lage = ScheinKanal(), Lage()
    w, io, cf = waechter(kanal, lage)
    w.starten(asyncio.get_running_loop())
    try:
        await nachricht(io, KANN_SCHLAFEN, 1)
        await nachricht(io, SCHLAEFT_EIN, 2)                       # nach Leerlauf
        await nachricht(io, SCHLAEFT_EIN, 3)                       # von Hand (ohne Anfrage vorher)
        await nachricht(io, KANN_SCHLAFEN, 4)
        await nachricht(io, SCHLAEFT_NICHT, 0)                     # ein anderer Teilnehmer lehnte ab
        await nachricht(io, SCHLAEFT_EIN, 5)
        assert kanal.eingeschlafen == [Schlafgrund.LEERLAUF, Schlafgrund.ANGEFORDERT, Schlafgrund.ANGEFORDERT]
        assert [k for _, k in io.erlaubt] == [1, 2, 3, 4, 5]
        lage.einstellung = Schlaf(melden=False)
        await nachricht(io, SCHLAEFT_EIN, 6)
        assert len(kanal.eingeschlafen) == 3 and io.erlaubt[-1] == (io.WURZEL, 6)
        lage.einstellung = Schlaf()
        monkeypatch.setattr(schlaf, "MELDEN_S", 0.2)
        kanal.dauer_s = 5.0                                         # Leitstelle hängt: quittiert wird trotzdem, rechtzeitig
        beginn = time.monotonic()
        await nachricht(io, SCHLAEFT_EIN, 7)
        assert io.erlaubt[-1] == (io.WURZEL, 7) and time.monotonic() - beginn < 2
    finally:
        w.stoppen()
    assert io.abgemeldet and io.geschlossen and io.zerstoert


async def test_aufwachen_nur_ganz_wach(monkeypatch):
    monkeypatch.setattr(schlaf, "VOLL_WACH_ABSTAND_S", 0.01)
    kanal, lage = ScheinKanal(), Lage()
    w, io, _ = waechter(kanal, lage, wach=True)
    w.starten(asyncio.get_running_loop())
    try:
        await nachricht(io, WACH, 0)
        await asyncio.sleep(0.2)
        assert kanal.aufgewacht == 1
    finally:
        w.stoppen()
    kanal = ScheinKanal()
    w, io, _ = waechter(kanal, lage, wach=False)                   # Power Nap: ohne Bildschirm
    w.starten(asyncio.get_running_loop())
    try:
        await nachricht(io, WACH, 0)
        await asyncio.sleep(0.3)
        assert kanal.aufgewacht == 0
    finally:
        w.stoppen()


def test_anderes_system_tut_nichts():
    schleife = asyncio.new_event_loop()
    try:
        w = Schlafwaechter(ScheinKanal(), lambda: 0, Schlaf, system="linux")
        assert w.starten(schleife) is False and w._faden is None
    finally:
        schleife.close()


def test_ganz_wach_nach_pmset(monkeypatch):
    """Ganz wach heißt: Graphics unter den Fähigkeiten (Power Nap hat nur CPU, Netz und Ton)."""
    class Lauf:
        def __init__(self, ausgabe: str) -> None:
            self.stdout = ausgabe
    ausgaben = {"voll": "Current Power State: 4\nCurrent System Capabilities are: CPU Graphics Audio Network\n",
                "dunkel": "Current Power State: 4\nCurrent System Capabilities are: CPU Network Disk\n"}
    for art, erwartet in (("voll", True), ("dunkel", False)):
        monkeypatch.setattr(schlaf.subprocess, "run", lambda *_a, art=art, **_k: Lauf(ausgaben[art]))
        assert schlaf.voll_wach() is erwartet


@pytest.mark.skipif(sys.platform != "darwin", reason="nur auf dem Mac")
async def test_rauchprobe_echte_energieverwaltung_nur_an_und_ab():
    """Meldet sich bei der echten Energieverwaltung an und wieder ab; der Schlafzustand wird dabei nie berührt."""
    w = Schlafwaechter(ScheinKanal(), lambda: 0, Schlaf, laden=echte_bibliotheken)
    assert w.starten(asyncio.get_running_loop())
    w.stoppen()
    assert w._faden is None and w._runloop is None


# ── Kanal ────────────────────────────────────────────────────────────────
class ScheinLeitstelle:
    """Nimmt Agenten an, antwortet auf die Anmeldung und (wenn `antwortet`) auf knoten.schlaeft."""

    def __init__(self, antwortet: bool = True) -> None:
        self.antwortet = antwortet
        self.anmeldungen = 0
        self.schlaf: list[dict] = []
        self.geschlossen: list[tuple[int | None, str]] = []

    async def __call__(self, ws) -> None:
        try:
            async for text in ws:
                u = json.loads(text)
                if u["art"] == "knoten.anmelden":
                    self.anmeldungen += 1
                    await ws.send(json.dumps({"protokoll": "leitstelle/1", "art": "knoten.angemeldet", "id": "a", "zeit": "", "von": "leitstelle",
                                              "an": "agent", "bezug": u["id"], "nutzlast": {"knoten": "k", "name": "Mac Studio"}}))
                elif u["art"] == "knoten.schlaeft":
                    self.schlaf.append(u["nutzlast"])
                    if self.antwortet:
                        await ws.send(json.dumps({"protokoll": "leitstelle/1", "art": "knoten.schlaf_vermerkt", "id": "b", "zeit": "",
                                                  "von": "leitstelle", "an": "agent", "bezug": u["id"], "nutzlast": {}}))
        except websockets.exceptions.ConnectionClosed:
            pass
        self.geschlossen.append((ws.close_code, ws.close_reason or ""))


class ScheinMesser:
    def messwege(self) -> list[str]:
        return ["speicher"]

    def messen(self) -> Messwerte:
        return Messwerte(speicher_gesamt_gb=64.0, speicher_belegt_gb=20.0)


async def mit_kanal(tmp_path: Path, leitstelle: ScheinLeitstelle):
    server = await websockets.serve(leitstelle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    (tmp_path / "dienste").mkdir()
    (tmp_path / "einstellungen.toml").write_text(f'[leitstelle]\nadresse = "http://127.0.0.1:{port}"\nwiederverbindung_max_s = 1\n'
                                                 '[messung]\ntakt_s = 1\nmacmon = false\n')
    o = Ordner(tmp_path)
    o.schluessel_speichern("ms_probe")
    kanal = Leitstellenkanal(o, Verwalter(o, o.einstellungen()), ScheinMesser())
    kanal.starten()
    return server, kanal


async def warte_bis(bedingung, sekunden: float = 5.0) -> None:
    for _ in range(int(sekunden * 20)):
        if bedingung():
            return
        await asyncio.sleep(0.05)
    raise AssertionError("Bedingung nicht erreicht")


async def test_einschlafen_meldet_schliesst_und_ruht_bis_zum_aufwachen(tmp_path: Path):
    ls = ScheinLeitstelle()
    server, kanal = await mit_kanal(tmp_path, ls)
    try:
        await warte_bis(lambda: kanal.stand.zustand == Verbindung.VERBUNDEN)
        beginn = time.monotonic()
        await kanal.einschlafen(Schlafgrund.ANGEFORDERT)
        assert time.monotonic() - beginn < 1.0                   # die Leitstelle hat geantwortet
        assert ls.schlaf == [{"grund": "angefordert", "meldung": ""}]
        await warte_bis(lambda: ls.geschlossen == [(1000, "schlaeft")])
        await asyncio.sleep(2.5)                                   # keine neue Verbindung, solange er schläft
        assert ls.anmeldungen == 1 and kanal.stand.zustand == Verbindung.SCHLAEFT
        kanal.aufwachen()
        await warte_bis(lambda: ls.anmeldungen == 2 and kanal.stand.zustand == Verbindung.VERBUNDEN, 3)
    finally:
        await kanal.beenden()
        server.close()


async def test_alte_leitstelle_ohne_antwort_haelt_nicht_auf(tmp_path: Path):
    ls = ScheinLeitstelle(antwortet=False)
    server, kanal = await mit_kanal(tmp_path, ls)
    try:
        await warte_bis(lambda: kanal.stand.zustand == Verbindung.VERBUNDEN)
        beginn = time.monotonic()
        await kanal.einschlafen(Schlafgrund.LEERLAUF)
        assert time.monotonic() - beginn < kanal_modul.VERMERK_S + 1.5
        await warte_bis(lambda: ls.geschlossen == [(1000, "schlaeft")])
        assert kanal.stand.zustand == Verbindung.SCHLAEFT
    finally:
        await kanal.beenden()
        server.close()


async def test_waechter_gilt_nach_der_wachzeit_als_wach(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(kanal_modul, "WACHZEIT_S", 0.5)
    ls = ScheinLeitstelle()
    server, kanal = await mit_kanal(tmp_path, ls)
    try:
        await warte_bis(lambda: kanal.stand.zustand == Verbindung.VERBUNDEN)
        await kanal.einschlafen(Schlafgrund.LEERLAUF)
        await warte_bis(lambda: ls.anmeldungen == 2 and kanal.stand.zustand == Verbindung.VERBUNDEN, 4)
    finally:
        await kanal.beenden()
        server.close()


async def test_aufwachen_schliesst_eine_tote_verbindung(tmp_path: Path):
    """Ohne Meldung eingeschlafen (etwa melden aus): nach dem Aufwachen gleich neu, nicht erst nach dem Ping (bis 40 s)."""
    ls = ScheinLeitstelle()
    server, kanal = await mit_kanal(tmp_path, ls)
    try:
        await warte_bis(lambda: kanal.stand.zustand == Verbindung.VERBUNDEN)
        kanal.aufwachen()
        await warte_bis(lambda: ls.anmeldungen == 2, 3)
    finally:
        await kanal.beenden()
        server.close()


async def test_ohne_leitstelle_aendert_der_schlaf_nichts(tmp_path: Path):
    (tmp_path / "dienste").mkdir()
    o = Ordner(tmp_path)
    kanal = Leitstellenkanal(o, Verwalter(o, o.einstellungen()), ScheinMesser())
    kanal.starten()
    await kanal.einschlafen(Schlafgrund.LEERLAUF)
    assert kanal.stand.zustand == Verbindung.AUS
    kanal.aufwachen()
    await kanal.beenden()


def test_einstellung_schlaf_vorgaben_und_datei():
    e = Einstellungen()
    assert e.schlaf.melden and e.schlaf.leerlauf_aufschieben
    text = toml_schreiben(e.model_copy(update={"schlaf": Schlaf(leerlauf_aufschieben=False)}))
    assert "[schlaf]\nmelden = true\nleerlauf_aufschieben = false" in text


async def test_laufzeit_startet_und_stoppt_den_waechter(tmp_path: Path, schein_energie):
    from maschinenraum.api import Laufzeit
    io, cf = schein_energie
    (tmp_path / "dienste").mkdir()
    lz = Laufzeit(Ordner(tmp_path))
    await lz.starten()
    try:
        assert cf.laeuft.wait(2) and io.rueckruf is not None
        lz.durchleitungen = 1
        await nachricht(io, KANN_SCHLAFEN, 9)
        assert io.abgelehnt == [(io.WURZEL, 9)]                     # Vorgabe: Leerlaufschlaf aufschieben, solange durchgereicht wird
    finally:
        await lz.beenden()
    assert io.abgemeldet
