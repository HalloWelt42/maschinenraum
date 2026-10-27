"""Apps des Stellwerks in der Beobachtung: Stand des Stellwerks lesen (nachgestellt), Prozesse den Teilen zuordnen, Last
und Speicher je Teil in `knoten.last.apps`, Fremdlast ohne die Apps. Kein Test fragt das echte Stellwerk (conftest.py)."""

from __future__ import annotations

import itertools
import json
from types import SimpleNamespace

import pytest

from maschinenraum import apps, beobachtung, laeuferlast
from maschinenraum.apps import Appteil, lesen, zuordnen
from maschinenraum.beobachtung import Beobachter
from maschinenraum.konfig import Einstellungen
from maschinenraum.laeuferlast import Lastmesser
from maschinenraum.protokoll import KnotenLast

GIB = 1024 ** 3
EIGEN = 4242          # der Maschinenraum selbst
STELLWERK = "http://127.0.0.1:8550"


def _teil(kennung: str, name: str, art: str, pids: list[int] | None) -> dict:
    """Ein Teil, wie das Stellwerk ihn meldet (mit Feldern, die die Zuordnung nicht braucht)."""
    t = {"kennung": kennung, "name": name, "art": art, "port": 6433, "zustand": "laeuft", "fremd": False, "gb_jetzt": 0.1,
         "cpu_prozent": 0.0, "ordner": "/Users/a/fundus", "meldung": ""}
    return t if pids is None else t | {"pids": pids}


def _stand(mit_pids: bool = True) -> bytes:
    def p(liste: list[int]) -> list[int] | None:
        return liste if mit_pids else None
    return json.dumps({"version": "0.2.0", "rechner": "Mac", "apps": [
        {"kennung": "fundus", "name": "Fundus", "zustand": "laeuft",
         "teile": [_teil("qdrant", "Vektorspeicher", "nativ", p([960])), _teil("vorne", "Vektorspeicher fürs Heimnetz", "nativ", p([961]))]},
        {"kennung": "zusage", "name": "Zusage (Betrieb)", "zustand": "laeuft",
         "teile": [_teil("datenbank", "Datenbank", "docker", p([]))]},           # Docker: steht beim Docker-Rechner
        {"kennung": "kellerwolke", "name": "Kellerwolke", "zustand": "aus",
         "teile": [_teil("backend", "Backend", "nativ", p([]))]},                # aus: ohne Prozess
    ], "docker": None, "ladefehler": []}).encode()


@pytest.fixture
def stellwerk(monkeypatch):
    """Nachgestelltes Stellwerk: antwortet mit `antwort` und merkt sich, wer gefragt wurde."""
    zustand = SimpleNamespace(antwort=_stand(), gefragt=[])

    def holen(adresse: str) -> bytes:
        zustand.gefragt.append(adresse)
        if isinstance(zustand.antwort, Exception):
            raise zustand.antwort
        return zustand.antwort
    monkeypatch.setattr(apps, "_holen", holen)
    return zustand


# ── Lesen ────────────────────────────────────────────────────────────────
def test_liest_native_teile_mit_prozessen(stellwerk):
    s = lesen(STELLWERK)
    assert s.gelesen and s.meldung == ""
    assert [(t.app, t.app_name, t.teil, t.name, t.pids) for t in s.teile] == [
        ("fundus", "Fundus", "qdrant", "Vektorspeicher", [960]), ("fundus", "Fundus", "vorne", "Vektorspeicher fürs Heimnetz", [961])]
    assert stellwerk.gefragt == [STELLWERK]


def test_ohne_pids_nur_ein_vermerk(stellwerk):
    """Eine Fassung des Stellwerks ohne Prozessnummern: keine Zuordnung, nur der Vermerk."""
    stellwerk.antwort = _stand(mit_pids=False)
    s = lesen(STELLWERK)
    assert not s.gelesen and s.teile == [] and "keine Prozessnummern" in s.meldung


@pytest.mark.parametrize("antwort, grund", [(OSError("Verbindung abgelehnt"), "antwortet nicht"), (b"<html>", "unlesbar")])
def test_ohne_antwort_nur_ein_vermerk(stellwerk, antwort, grund):
    stellwerk.antwort = antwort
    s = lesen(STELLWERK)
    assert not s.gelesen and s.teile == [] and grund in s.meldung


# ── Zuordnen ─────────────────────────────────────────────────────────────
class Baum:
    """Prozesstabelle, so weit die Zuordnung sie braucht: Eltern und lebende Prozesse."""

    def __init__(self, eltern: dict[int, int]) -> None:
        self.eltern = eltern
        self.befehlszeile = {p: f"prozess {p}" for p in eltern}


def _teil_mit(teil: str, pids: list[int]) -> Appteil:
    return Appteil(app="a", app_name="A", teil=teil, name=teil.title(), pids=pids)


def test_jeder_prozess_nur_einmal_und_beim_eigenen_teil():
    # 10 startet 20 (ein eigener Teil) und hat das Kind 11; 20 hat das Kind 21; 30 nennen zwei Teile; 40 lebt nicht mehr;
    # 50 gehört schon dem Läufer, sein Kind 51 auch
    baum = Baum({10: 1, 11: 10, 20: 10, 21: 20, 30: 1, 31: 30, 50: 1, 51: 50})
    teile = [_teil_mit("eins", [10]), _teil_mit("zwei", [20]), _teil_mit("drei", [30]), _teil_mit("vier", [30, 40]),
             _teil_mit("fuenf", [50]), _teil_mit("sechs", [40])]
    ergebnis = {t.teil: pids for t, pids in zuordnen(teile, baum, vergeben={50, 51})}
    assert ergebnis == {"eins": [10, 11], "zwei": [20, 21], "drei": [30, 31]}


# ── Last und Fremdlast ───────────────────────────────────────────────────
#: zwei Momentaufnahmen, 15 s auseinander: Eltern, Befehlszeile und verbrauchte Rechenzeit je pid
VORHER = {
    960: (1, "/Users/a/fundus/qdrant --config-path x", 100.0),      # Fundus, Vektorspeicher
    962: (960, "/Users/a/fundus/qdrant helfer", 5.0),               # sein Kind
    961: (1, "/Users/a/fundus/qdrant --config-path vorne", 10.0),   # Fundus, fürs Heimnetz
    970: (1, "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", 300.0),
    EIGEN: (1, "/opt/python3 -m maschinenraum", 30.0),
}
NACHHER = {
    960: (1, VORHER[960][1], 107.5),          # 7,5 s
    962: (960, VORHER[962][1], 6.5),          # 1,5 s
    961: (1, VORHER[961][1], 10.15),          # 0,15 s
    970: (1, VORHER[970][1], 304.5),          # 4,5 s, fremd
    EIGEN: (1, VORHER[EIGEN][1], 30.5),
    990: (1, "/usr/bin/cc -c gross.c", 3.0),  # neu, fremd: ganz
}
SPEICHER = {960: 4.0 * GIB, 962: 0.03 * GIB, 961: 0.03 * GIB}


class Tabelle:
    jetzt: dict = VORHER

    def __init__(self) -> None:
        self.eltern = {p: e for p, (e, _, _) in self.jetzt.items()}
        self.befehlszeile = {p: b for p, (_, b, _) in self.jetzt.items()}
        self.rechenzeit_s = {p: s for p, (_, _, s) in self.jetzt.items()}
        self.gruppe = {p: p for p in self.eltern}

    def in_gruppe(self, g: int) -> list[int]:
        return [p for p, x in self.gruppe.items() if x == g]

    def mit_nachfahren(self, wurzel: int) -> list[int]:
        kinder: dict[int, list[int]] = {}
        for p, e in self.eltern.items():
            kinder.setdefault(e, []).append(p)
        ergebnis, offen = [], [wurzel]
        while offen:
            p = offen.pop()
            if p in self.eltern or p == wurzel:
                ergebnis.append(p)
                offen += kinder.get(p, [])
        return ergebnis


@pytest.fixture
def rechner(monkeypatch, stellwerk):
    """Ein Rechner ohne Modell-Läufer (dann braucht die Fremdlast kein lsof) mit den Momentaufnahmen oben."""
    zeiten = itertools.count(100.0, 15.0)
    monkeypatch.setattr(Tabelle, "jetzt", VORHER)
    monkeypatch.setattr(beobachtung, "Prozesstabelle", Tabelle)
    monkeypatch.setattr(beobachtung, "monotonic", lambda: next(zeiten))
    monkeypatch.setattr(beobachtung, "_lsof", lambda *args: "")
    monkeypatch.setattr(beobachtung.os, "getpid", lambda: EIGEN)
    monkeypatch.setattr(laeuferlast, "prozess_bytes", lambda pid: int(SPEICHER.get(pid, 0.1 * GIB)))
    monkeypatch.setattr(laeuferlast.os, "cpu_count", lambda: 10)
    e = Einstellungen()
    e.nachbar.modell_laeufer = None
    return SimpleNamespace(einstellungen=e, stellwerk=stellwerk)


def _zweimal(e: Einstellungen, monkeypatch) -> tuple[KnotenLast, KnotenLast]:
    b = Beobachter(lambda: e, lambda: [])
    m = Lastmesser(lambda: e)
    erste = m.messen(b.aufnehmen())
    monkeypatch.setattr(Tabelle, "jetzt", NACHHER)
    return erste, m.messen(b.aufnehmen())


def test_last_je_teil_und_fremdlast_ohne_apps(rechner, monkeypatch):
    erste, zweite = _zweimal(rechner.einstellungen, monkeypatch)
    assert erste.apps is not None and erste.apps.gemessen
    assert [(t.teil, t.pids, t.cpu_prozent, t.gb) for t in erste.apps.teile] == [("qdrant", [960, 962], None, 4.03), ("vorne", [961], None, 0.03)]
    assert zweite.apps is not None
    teile = {t.teil: t for t in zweite.apps.teile}
    assert (teile["qdrant"].app, teile["qdrant"].app_name, teile["qdrant"].name) == ("fundus", "Fundus", "Vektorspeicher")
    assert teile["qdrant"].cpu_prozent == 60.0 and teile["vorne"].cpu_prozent == 1.0      # 9 s und 0,15 s in 15 s
    assert zweite.fremd_prozent == 5.0                                                    # (4,5 + 3) s in 15 s auf 10 Kernen
    # nichts doppelt, nichts verloren: Fremdlast und Apps zusammen sind die Fremdlast ohne Stellwerk
    rechner.einstellungen.nachbar.stellwerk = ""
    monkeypatch.setattr(Tabelle, "jetzt", VORHER)
    _, ohne = _zweimal(rechner.einstellungen, monkeypatch)
    assert ohne.apps is None and ohne.fremd_prozent == pytest.approx(zweite.fremd_prozent + (60.0 + 1.0) / 10, abs=0.05)


def test_ohne_pids_vermerk_und_fremdlast_wie_ohne_stellwerk(rechner, monkeypatch):
    rechner.stellwerk.antwort = _stand(mit_pids=False)
    _, zweite = _zweimal(rechner.einstellungen, monkeypatch)
    assert zweite.apps is not None and not zweite.apps.gemessen and zweite.apps.teile == []
    assert "keine Prozessnummern" in zweite.apps.meldung
    assert zweite.fremd_prozent == pytest.approx((7.5 + 1.5 + 0.15 + 4.5 + 3) / 150 * 100, abs=0.05)


def test_ohne_eingetragenes_stellwerk_wird_nicht_gefragt(rechner, monkeypatch):
    rechner.einstellungen.nachbar.stellwerk = ""
    erste, zweite = _zweimal(rechner.einstellungen, monkeypatch)
    assert erste.apps is None and zweite.apps is None and rechner.stellwerk.gefragt == []


def test_abgeschaltete_beobachtung_fragt_nicht(rechner):
    rechner.einstellungen.beobachtung.aktiv = False
    assert Beobachter(lambda: rechner.einstellungen, lambda: []).aufnehmen() is None and rechner.stellwerk.gefragt == []


def test_die_meldung_traegt_die_apps(rechner, monkeypatch):
    """`knoten.last` als JSON, wie es zur Leitstelle geht: das Feld apps mit allen Angaben je Teil."""
    _, zweite = _zweimal(rechner.einstellungen, monkeypatch)
    daten = json.loads(zweite.model_dump_json())
    assert daten["apps"]["gemessen"] is True and daten["apps"]["meldung"] == ""
    assert daten["apps"]["teile"][0] == {"app": "fundus", "app_name": "Fundus", "teil": "qdrant", "name": "Vektorspeicher",
                                         "pids": [960, 962], "cpu_prozent": 60.0, "gb": 4.03}
