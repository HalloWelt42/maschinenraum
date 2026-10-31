"""Neustart der Leitstelle (HELF-80): sie schließt den Kanal mit 1012 (service restart). Der Maschinenraum verbindet neu,
meldet den Ausfall einmal und lässt keine Beobachtung der alten Verbindung zurück, die weiter auf die tote Verbindung
sendet (vorher je Takt ein Stapel im Protokoll und je Neustart eine Beobachtung mehr, die lsof und Docker fragte)."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import pytest
import websockets
from websockets.frames import Close

from maschinenraum.konfig import Ordner
from maschinenraum.leitstelle import Leitstellenkanal, Umschlag, Verbindung
from maschinenraum.protokoll import Befehl, Befehlsart, Messwerte
from maschinenraum.prozesse import Verwalter

TAKT_S = 0.3                                     # Beobachtung im Test; die Einstellung erlaubt erst ab 5 s


class ScheinLeitstelle:
    """Nimmt Agenten an, antwortet auf die Anmeldung und merkt sich je Verbindung, welche Arten ankamen."""

    def __init__(self) -> None:
        self.verbindungen: list[tuple[object, list[str]]] = []

    async def __call__(self, ws) -> None:
        arten: list[str] = []
        self.verbindungen.append((ws, arten))
        try:
            async for text in ws:
                u = json.loads(text)
                arten.append(u["art"])
                if u["art"] == "knoten.anmelden":
                    await ws.send(json.dumps({"protokoll": "leitstelle/1", "art": "knoten.angemeldet", "id": "a", "zeit": "",
                                              "von": "leitstelle", "an": "agent", "bezug": u["id"], "nutzlast": {"name": "Mac"}}))
        except websockets.exceptions.ConnectionClosed:
            pass

    def arten(self, nr: int) -> list[str]:
        return self.verbindungen[nr][1] if len(self.verbindungen) > nr else []

    async def neu_starten(self) -> None:
        """Wie uvicorn beim Herunterfahren: jede offene Verbindung mit 1012 schließen."""
        await asyncio.gather(*(ws.close(1012, "service restart") for ws, _ in self.verbindungen))  # type: ignore[attr-defined]


class ScheinMesser:
    def messwege(self) -> list[str]:
        return ["speicher"]

    def messen(self) -> Messwerte:
        return Messwerte(speicher_gesamt_gb=64.0, speicher_belegt_gb=20.0)


async def kanal_bauen(tmp_path: Path, port: int) -> Leitstellenkanal:
    (tmp_path / "dienste").mkdir(exist_ok=True)
    (tmp_path / "einstellungen.toml").write_text(f'[leitstelle]\nadresse = "http://127.0.0.1:{port}"\nwiederverbindung_max_s = 1\n'
                                                 '[messung]\ntakt_s = 1\nmacmon = false\n')
    o = Ordner(tmp_path)
    o.schluessel_speichern("ms_probe")
    kanal = Leitstellenkanal(o, Verwalter(o, o.einstellungen()), ScheinMesser())
    kanal.verwalter.einstellungen.beobachtung.takt_s = TAKT_S
    kanal.beobachter.aufnehmen = lambda: None                                   # type: ignore[method-assign]
    await kanal.verwalter.hochfahren()
    return kanal


async def warte_bis(bedingung, sekunden: float = 5.0) -> None:
    for _ in range(int(sekunden * 20)):
        if bedingung():
            return
        await asyncio.sleep(0.05)
    raise AssertionError("Bedingung nicht erreicht")


def beobachtungen() -> int:
    return sum(1 for t in asyncio.all_tasks() if t.get_coro().__qualname__.endswith("_beobachten_im_takt"))  # type: ignore[union-attr]


def zeilen(caplog, stufe: int) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == "maschinenraum" and r.levelno == stufe]


async def test_neustart_der_leitstelle_laesst_keine_alte_beobachtung_zurueck(tmp_path: Path, caplog):
    caplog.set_level(logging.DEBUG, logger="maschinenraum")
    ls = ScheinLeitstelle()
    server = await websockets.serve(ls, "127.0.0.1", 0)
    kanal = await kanal_bauen(tmp_path, server.sockets[0].getsockname()[1])
    kanal.starten()
    try:
        await warte_bis(lambda: kanal.stand.zustand == Verbindung.VERBUNDEN and "knoten.last" in ls.arten(0))
        for _ in range(3):                                                      # drei Neustarts hintereinander
            n = len(ls.verbindungen)
            await ls.neu_starten()
            await warte_bis(lambda: len(ls.verbindungen) == n + 1 and kanal.stand.zustand == Verbindung.VERBUNDEN)
            await warte_bis(lambda: "knoten.last" in ls.arten(n))
        await asyncio.sleep(4 * TAKT_S)                                         # Zeit für Meldungen einer übrig gebliebenen Beobachtung
        assert beobachtungen() == 1
        assert zeilen(caplog, logging.ERROR) == []
        assert len(zeilen(caplog, logging.WARNING)) == 3                        # je Ausfall eine Warnung
        assert len([z for z in zeilen(caplog, logging.INFO) if "wieder verbunden" in z]) == 3
        neu = ls.arten(len(ls.verbindungen) - 1)                                # der aktuelle Stand kommt nach dem Neuverbinden neu
        assert neu[:2] == ["knoten.anmelden", "knoten.dienste"] and {"knoten.messwerte", "knoten.fremde", "knoten.last"} <= set(neu)
    finally:
        await kanal.beenden()
        server.close()
    await asyncio.sleep(0.05)
    assert beobachtungen() == 0


async def test_ein_ausfall_mit_vielen_versuchen_meldet_sich_einmal(tmp_path: Path, caplog):
    """Die Leitstelle bleibt eine Weile weg: viele Versuche, eine Warnung, danach eine Zeile beim Wiederverbinden; die Pause
    beginnt nach einer gelungenen Verbindung wieder klein."""
    caplog.set_level(logging.DEBUG, logger="maschinenraum")
    ls = ScheinLeitstelle()
    server = await websockets.serve(ls, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    kanal = await kanal_bauen(tmp_path, port)
    kanal.starten()
    try:
        await warte_bis(lambda: kanal.stand.zustand == Verbindung.VERBUNDEN)
        server.close()
        await ls.neu_starten()
        await server.wait_closed()
        await warte_bis(lambda: len([z for z in zeilen(caplog, logging.DEBUG) if z.startswith("Leitstelle: Versuch")]) >= 2, 6)
        assert kanal.stand.zustand == Verbindung.NICHT_ERREICHBAR
        server = await websockets.serve(ls, "127.0.0.1", port)
        await warte_bis(lambda: kanal.stand.zustand == Verbindung.VERBUNDEN, 6)
        assert len(zeilen(caplog, logging.WARNING)) == 1 and zeilen(caplog, logging.ERROR) == []
        assert any("wieder verbunden" in z for z in zeilen(caplog, logging.INFO))
        assert kanal._pause_s == 1.0
    finally:
        await kanal.beenden()
        server.close()


def _geschlossen() -> websockets.exceptions.ConnectionClosedError:
    return websockets.exceptions.ConnectionClosedError(Close(1012, "service restart"), Close(1012, "service restart"), True)


async def test_beobachtung_endet_mit_ihrer_verbindung(tmp_path: Path, caplog):
    """Auch ohne Abbruch von außen sendet eine Beobachtung nie weiter auf eine geschlossene Verbindung."""
    kanal = await kanal_bauen(tmp_path, 1)
    versuche = 0

    async def senden(_text: str) -> None:
        nonlocal versuche
        versuche += 1
        raise _geschlossen()
    await asyncio.wait_for(kanal._beobachten_im_takt(senden), 2)
    assert versuche == 1 and zeilen(caplog, logging.ERROR) == []


async def test_scheiternde_messung_einmal_mit_stapel(tmp_path: Path, caplog):
    """Scheitert die Messung Takt für Takt gleich, steht ihr Stapel einmal im Protokoll, nicht je Takt."""
    caplog.set_level(logging.INFO, logger="maschinenraum")
    kanal = await kanal_bauen(tmp_path, 1)

    def kaputt():
        raise RuntimeError("lsof hängt")
    kanal.beobachter.aufnehmen = kaputt                                         # type: ignore[method-assign]

    async def senden(_text: str) -> None:
        pass
    aufgabe = asyncio.create_task(kanal._beobachten_im_takt(senden))
    await asyncio.sleep(4 * TAKT_S)
    kanal.beobachter.aufnehmen = lambda: None                                   # type: ignore[method-assign]
    await asyncio.sleep(2 * TAKT_S)
    aufgabe.cancel()
    await asyncio.gather(aufgabe, return_exceptions=True)
    assert len(zeilen(caplog, logging.ERROR)) == 1
    assert any("wieder gelungen" in z for z in zeilen(caplog, logging.INFO))


async def test_ergebnis_eines_befehls_geht_nicht_still_verloren(tmp_path: Path, caplog):
    kanal = await kanal_bauen(tmp_path, 1)
    u = Umschlag(art="knoten.befehl", nutzlast=Befehl(befehl=Befehlsart.DIENST_STARTEN, ziel="unbekannt").model_dump(mode="json"))

    async def senden(_text: str) -> None:
        raise _geschlossen()
    await kanal._befehl(u, senden)
    assert any("nicht zugestellt" in z for z in zeilen(caplog, logging.WARNING))
