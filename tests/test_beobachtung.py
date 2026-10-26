"""Beobachtung: Zugriffe am Leitstand vorbei, mit nachgestellter Prozesstabelle und nachgestellter Ausgabe von lsof."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from maschinenraum import beobachtung
from maschinenraum.beobachtung import Beobachter, mit_eltern, programmname
from maschinenraum.konfig import Einstellungen
from maschinenraum.protokoll import Fremdart

GIB = 1024 ** 3
EIGEN = 4242          # der Maschinenraum selbst (seine Durchleitung für die Leitstelle)


class Tabelle:
    """Wie dienstkern.messen.Prozesstabelle: Eltern, Gruppen und Befehlszeilen einer Momentaufnahme."""

    def __init__(self) -> None:
        self.eltern = {807: 1, 808: 807, 900: 1, 901: 900, 950: 1, 960: 1, 970: 1, 980: 1, EIGEN: 1}
        self.gruppe = {p: p for p in self.eltern} | {808: 807, 901: 900}
        self.befehlszeile = {
            807: "/Applications/LM Studio.app/Contents/MacOS/LM Studio", 808: "/Users/a/.lmstudio/.internal/utils/node worker",
            900: "/Applications/pappagei.app/Contents/MacOS/pappagei", 901: "/usr/bin/python3 -m uvicorn server:app --port 8765",
            950: "/opt/python3 -m klangwerk hoeren --port 8783", 960: "/opt/python3 /Users/a/medienpool/werkzeuge/erzeugen.py",
            970: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", 980: "/usr/bin/python3 skript.py", EIGEN: "/opt/python3 -m maschinenraum",
        }

    def in_gruppe(self, g: int) -> list[int]:
        return [p for p, x in self.gruppe.items() if x == g]

    def mit_nachfahren(self, wurzel: int) -> list[int]:
        kinder: dict[int, list[int]] = {}
        for p, e in self.eltern.items():
            kinder.setdefault(e, []).append(p)
        ergebnis, offen = [], [wurzel]
        while offen:
            p = offen.pop()
            ergebnis.append(p)
            offen += kinder.get(p, [])
        return ergebnis


SPEICHER = {808: 40 * GIB, 901: 3.3 * GIB, 950: 4.7 * GIB, 960: 17 * GIB, 970: 6 * GIB, 980: 0.5 * GIB, EIGEN: 3 * GIB}

LSOF = "\n".join([
    "p807", "cLM Studio", "f20", "n*:1234", "TST=LISTEN",
    "f49", "n192.168.178.45:1234->192.168.178.49:38650", "TST=ESTABLISHED",
    "f50", "n192.168.178.45:1234->192.168.178.49:38651", "TST=ESTABLISHED",
    "f51", "n192.168.178.45:1234->192.168.178.51:50000", "TST=ESTABLISHED",
    "f52", "n127.0.0.1:1234->127.0.0.1:61000", "TST=ESTABLISHED",
    "f53", "n127.0.0.1:1234->127.0.0.1:61001", "TST=ESTABLISHED",
    "p980", "cPython", "f7", "n127.0.0.1:61000->127.0.0.1:1234", "TST=ESTABLISHED",
    f"p{EIGEN}", "cPython", "f9", "n127.0.0.1:61001->127.0.0.1:1234", "TST=ESTABLISHED",
])


@pytest.fixture
def nachgestellt(monkeypatch):
    def lsof(*args: str) -> str:
        if "cwd" in args:
            return "p960\nn/Users/a/medienpool\np980\nn/Users/a/devradar\n"
        return LSOF
    monkeypatch.setattr(beobachtung, "_lsof", lsof)
    monkeypatch.setattr(beobachtung, "Prozesstabelle", Tabelle)
    monkeypatch.setattr(beobachtung, "prozess_bytes", lambda pid: int(SPEICHER.get(pid, 0)))
    monkeypatch.setattr(beobachtung.os, "getpid", lambda: EIGEN)
    monkeypatch.setattr(beobachtung.socket, "gethostbyname", lambda name: "192.168.178.49")


def _beobachter() -> Beobachter:
    e = Einstellungen()
    e.leitstelle.adresse = "http://leitstelle:8530"
    klangwerk = SimpleNamespace(stand=SimpleNamespace(gruppe=950), fremd_pid=None)       # ein Dienst des Maschinenraums
    return Beobachter(lambda: e, lambda: [klangwerk])


def test_meldet_umgehungen_und_laesst_eigenes_weg(nachgestellt):
    r = _beobachter().messen()
    assert r.beobachtet
    laeufer = {z.wer: z for z in r.zugriffe if z.art == Fremdart.LAEUFER}
    # aus dem Netz je Adresse gezählt; der Rechner der Leitstelle ist kenntlich (auf dem direkten Weg ist sie es selbst)
    assert laeufer["192.168.178.49"].verbindungen == 2 and laeufer["192.168.178.49"].vom_rechner_der_leitstelle
    assert laeufer["192.168.178.51"].verbindungen == 1 and not laeufer["192.168.178.51"].vom_rechner_der_leitstelle
    # ein Programm auf diesem Rechner mit Arbeitsordner; die Durchleitung des Maschinenraums zählt nicht
    hier = laeufer["skript.py"]
    assert (hier.pid, hier.verbindungen, hier.ordner) == (980, 1, "/Users/a/devradar")
    assert set(laeufer) == {"192.168.178.49", "192.168.178.51", "skript.py"}
    speicher = [(z.wer, z.gb) for z in r.zugriffe if z.art == Fremdart.SPEICHER]
    # Läufer samt Kindern, Dienste, Ausnahmen (Browser) und Kleines fehlen; das Größte zuerst
    assert speicher == [("erzeugen.py", 17.0), ("uvicorn (pappagei)", 3.3)]


def test_ohne_lsof_ohne_aussage(nachgestellt, monkeypatch):
    monkeypatch.setattr(beobachtung, "_lsof", lambda *args: None)
    assert _beobachter().messen().beobachtet is False


def test_abgeschaltet(nachgestellt):
    b = _beobachter()
    b.einstellungen.beobachtung.aktiv = False
    r = b.messen()
    assert r.beobachtet is False and r.zugriffe == []


def test_namen():
    assert programmname("/opt/homebrew/bin/python3.13 -m klangwerk hoeren --port 8783") == "klangwerk"
    assert programmname("/usr/bin/python3 /pfad/zum/erzeugen.py --x") == "erzeugen.py"
    assert programmname("/Users/a/.lmstudio/.internal/utils/node /pfad/worker.js") == "worker.js"
    assert programmname("/Applications/pappagei.app/Contents/MacOS/pappagei") == "pappagei"
    t = Tabelle()
    assert mit_eltern("uvicorn", 901, t) == "uvicorn (pappagei)"
    assert mit_eltern("klangwerk", 950, t) == "klangwerk"                 # vom System gestartet: nichts dazu
