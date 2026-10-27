"""Last des Läufers und des Rechners (`knoten.last`) und Beenden eines Arbeiters, mit nachgestellter Prozesstabelle,
nachgestelltem lsof und nachgestellten Signalen. Kein Test schickt ein echtes Signal: `_signal` ist für jeden Test
ersetzt und schlägt fehl, wenn ein Test es nicht ausdrücklich erwartet."""

from __future__ import annotations

import asyncio
import itertools
import json
import os
import signal
from pathlib import Path
from types import SimpleNamespace

import pytest

from maschinenraum import beobachtung, laeuferlast
from maschinenraum.beobachtung import Beobachter
from maschinenraum.konfig import Beobachtung, Einstellungen, Ordner
from maschinenraum.laeuferlast import Laeuferaufsicht, Lastmesser
from maschinenraum.leitstelle import Leitstellenkanal, Umschlag
from maschinenraum.protokoll import Befehlsart, Laeuferrolle, Messwerte
from maschinenraum.prozesse import Verwalter

GIB = 1024 ** 3
EIGEN = 4242          # der Maschinenraum selbst
HEIM = os.path.expanduser("~")
BGE = f"{HEIM}/.lmstudio/models/lmstudio-community/bge-m3-GGUF/bge-m3-Q8_0.gguf"
MLX = f"{HEIM}/.lmstudio/models/mlx-community/Qwen3-8B-4bit/model.safetensors"
RECHENWERK = f"{HEIM}/.lmstudio/extensions/backends/mlx-llm-mac-arm64-apple-metal-advsimd-1.11.0/libllm_engine.dylib"
GGUF_RECHENWERK = f"{HEIM}/.lmstudio/extensions/backends/llama.cpp-mac-arm64-apple-metal-advsimd-2.47.0/libllama.dylib"

#: zwei Momentaufnahmen, 15 s auseinander: Eltern, Befehlszeile und verbrauchte Rechenzeit je pid
VORHER = {
    807: (1, "/Applications/LM Studio.app/Contents/MacOS/LM Studio", 100.0),        # Hauptprozess, lauscht am Port
    808: (807, "/Users/a/.lmstudio/.internal/utils/node worker", 1000.0),          # Arbeiter, bge-m3 (1)
    809: (807, "/Users/a/.lmstudio/.internal/utils/node worker", 2000.0),          # Arbeiter, bge-m3 (2)
    810: (807, "/Applications/LM Studio.app/Contents/Frameworks/LM Studio Helper (Renderer).app/Contents/MacOS/LM Studio Helper (Renderer)", 50.0),
    811: (807, "/Users/a/.lmstudio/.internal/utils/node worker", 10.0),            # Arbeiter, MLX
    813: (807, "/Users/a/.lmstudio/.internal/utils/node worker", 400.0),           # Arbeiter ohne offene Modelldatei (Rechenwerk)
    950: (1, "/opt/python3 -m klangwerk hoeren --port 8783", 500.0),               # Dienst des Maschinenraums
    EIGEN: (1, "/opt/python3 -m maschinenraum", 30.0),
    4243: (EIGEN, "lsof -nP", 0.1),                                                  # Kind des Maschinenraums
    960: (1, "/opt/python3 /Users/a/medienpool/werkzeuge/erzeugen.py", 200.0),
    970: (1, "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", 300.0),
    980: (1, "/usr/bin/python3 skript.py", 5.0),
}
NACHHER = {
    807: (1, VORHER[807][1], 100.3),            # 2 % eines Kerns
    808: (807, VORHER[808][1], 1015.0),         # 100 %
    809: (807, VORHER[809][1], 2000.75),        # 5 %
    810: (807, VORHER[810][1], 50.15),          # 1 %
    811: (807, VORHER[811][1], 10.0),           # 0 %
    813: (807, VORHER[813][1], 406.0),          # 40 %
    812: (807, VORHER[808][1], 7.0),            # neu: ohne Prozent
    950: (1, VORHER[950][1], 530.0),            # Dienst: zählt nicht zur Fremdlast
    EIGEN: (1, VORHER[EIGEN][1], 30.5),         # Maschinenraum: zählt nicht
    4244: (EIGEN, "ps -A", 0.05),               # sein Kind: zählt nicht
    960: (1, VORHER[960][1], 207.5),            # 7,5 s
    970: (1, VORHER[970][1], 304.5),            # 4,5 s
    980: (1, VORHER[980][1], 5.0),
    990: (1, "/usr/bin/cc -c gross.c", 3.0),    # neu seit der letzten Messung: ganz (3 s)
}
# Fremdlast: (7,5 + 4,5 + 3) s in 15 s auf 10 Kernen = 10 %


class Tabelle:
    """Wie dienstkern.messen.Prozesstabelle, aus einer der Momentaufnahmen oben."""

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


PORT_LSOF = "\n".join(["p807", "cLM Studio", "f20", "n*:1234", "TST=LISTEN"])
DATEIEN_LSOF = "\n".join([
    "p807", "ftxt", "s1000", "n/Applications/LM Studio.app/Contents/MacOS/LM Studio",
    "p808", "ftxt", "s605000000", f"n{BGE}", "ftxt", "s900000", f"n{HEIM}/.lmstudio/models/x/mmproj-klein.gguf", "f12", "s0", "n/dev/null",
    "ftxt", "s3000000", f"n{GGUF_RECHENWERK}",
    "p809", "ftxt", "s605000000", f"n{BGE}",
    "p810", "ftxt", "s2000", "n/usr/lib/libSystem.B.dylib",
    "ftxt", "s5000", "n/System/Library/Extensions/AGXMetalG16X.bundle/Contents/MacOS/AGXMetalG16X",   # Systemordner: kein Rechenwerk
    "f31", "s900", f"n{HEIM}/.lmstudio/extensions/backends/backends.json",                         # offen, aber nicht geladen (nicht txt)
    "p811", "ftxt", "s4300000000", f"n{MLX}",
    "p812", "ftxt", "s605000000", f"n{BGE}",
    "p813", "fcwd", "s704", "n/", "ftxt", "s52000000", f"n{RECHENWERK}", "f14", "s0", "n/dev/null",
])


@pytest.fixture
def nachgestellt(monkeypatch):
    aufrufe: list[tuple[str, ...]] = []

    def lsof(*args: str) -> str:
        aufrufe.append(args)
        if "cwd" in args:
            return ""
        if "pns" in args:
            return DATEIEN_LSOF
        return PORT_LSOF
    zeiten = itertools.count(100.0, 15.0)
    monkeypatch.setattr(Tabelle, "jetzt", VORHER)
    monkeypatch.setattr(beobachtung, "_lsof", lsof)
    monkeypatch.setattr(beobachtung, "Prozesstabelle", Tabelle)
    monkeypatch.setattr(beobachtung, "monotonic", lambda: next(zeiten))
    monkeypatch.setattr(beobachtung.os, "getpid", lambda: EIGEN)
    monkeypatch.setattr(laeuferlast, "prozess_bytes", lambda pid: int({808: 1.2, 809: 1.2, 811: 4.6}.get(pid, 0.1) * GIB))
    monkeypatch.setattr(laeuferlast.os, "cpu_count", lambda: 10)
    return aufrufe


@pytest.fixture(autouse=True)
def keine_echten_signale(monkeypatch):
    def verboten(pid: int, sig: int) -> None:
        raise AssertionError(f"unerwartetes Signal {sig} an {pid}")
    monkeypatch.setattr(laeuferlast, "_signal", verboten)
    monkeypatch.setattr(laeuferlast, "_lebt", lambda pid: True)


def _einstellungen() -> Einstellungen:
    return Einstellungen()


def _beobachter(e: Einstellungen | None = None) -> Beobachter:
    e = e or _einstellungen()
    klangwerk = SimpleNamespace(stand=SimpleNamespace(gruppe=950), fremd_pid=None)
    return Beobachter(lambda: e, lambda: [klangwerk])


def _messen_zweimal(b: Beobachter, monkeypatch):
    m = Lastmesser(lambda: b.einstellungen)
    erste = m.messen(b.aufnehmen())
    monkeypatch.setattr(Tabelle, "jetzt", NACHHER)
    return erste, m.messen(b.aufnehmen())


def test_rollen_modelldateien_und_prozente(nachgestellt, monkeypatch):
    erste, zweite = _messen_zweimal(_beobachter(), monkeypatch)
    assert erste.gemessen and erste.kerne == 10 and erste.fremd_prozent is None
    assert all(p.cpu_prozent is None for p in erste.laeufer)              # beim ersten Mal ohne Prozente
    rollen = {p.pid: (p.rolle, p.modelldatei) for p in erste.laeufer}
    assert rollen == {807: (Laeuferrolle.HAUPT, ""), 808: (Laeuferrolle.ARBEITER, BGE.replace(HEIM, "~")),
                      809: (Laeuferrolle.ARBEITER, BGE.replace(HEIM, "~")), 810: (Laeuferrolle.SONSTIG, ""),
                      811: (Laeuferrolle.ARBEITER, MLX.replace(HEIM, "~")), 813: (Laeuferrolle.ARBEITER, "")}
    assert [p.pid for p in erste.laeufer] == [807, 808, 809, 811, 813, 810]     # Hauptprozess, Arbeiter, Sonstiges
    assert erste.laeufer[1].name == "node (LM Studio)" and erste.laeufer[1].gb == 1.2

    assert zweite.gemessen and zweite.fremd_prozent == 10.0              # ohne Läufer, Dienste und Maschinenraum
    prozent = {p.pid: p.cpu_prozent for p in zweite.laeufer}
    assert prozent == {807: 2.0, 808: 100.0, 809: 5.0, 811: 0.0, 812: None, 813: 40.0, 810: 1.0}


def test_ein_aufruf_von_lsof_fuer_alle_modelldateien(nachgestellt):
    Lastmesser(lambda: _einstellungen()).messen(_beobachter().aufnehmen())
    dateien = [a for a in nachgestellt if "pns" in a]
    assert len(dateien) == 1 and dateien[0][dateien[0].index("-p") + 1] == "807,808,809,810,811,813"


def test_endungen_aus_der_einstellung(nachgestellt):
    e = _einstellungen()
    e.beobachtung.modelldateien = [".safetensors"]
    e.beobachtung.arbeiter_bibliotheken = []
    r = Lastmesser(lambda: e).messen(_beobachter(e).aufnehmen())
    assert [p.pid for p in r.laeufer if p.rolle == Laeuferrolle.ARBEITER] == [811]


def test_arbeiter_an_der_geladenen_bibliothek(nachgestellt):
    """Befund vom 27.10.2026: der Arbeiter des 80B-Modells hält keine Modelldatei offen (das Rechenwerk liest das Modell
    ganz in den Speicher) und zählte als sonstig. Er hat aber die Bibliothek seines Rechenwerks geladen (Spalte txt)."""
    e = _einstellungen()
    r = Lastmesser(lambda: e).messen(_beobachter(e).aufnehmen())
    rollen = {p.pid: (p.rolle, p.modelldatei) for p in r.laeufer}
    assert rollen[813] == (Laeuferrolle.ARBEITER, "")                       # Modelldatei bleibt leer
    assert rollen[808] == (Laeuferrolle.ARBEITER, BGE.replace(HEIM, "~"))   # beides: die Modelldatei steht da
    assert rollen[810] == (Laeuferrolle.SONSTIG, "")                        # nur offen oder im Systemordner: kein Arbeiter

    e.beobachtung.arbeiter_bibliotheken = []                                # nur noch Modelldateien
    r = Lastmesser(lambda: e).messen(_beobachter(e).aufnehmen())
    assert {p.pid: p.rolle for p in r.laeufer}[813] == Laeuferrolle.SONSTIG

    e.beobachtung.arbeiter_bibliotheken = ["/MLX-LLM-mac-arm64-apple-metal-advsimd-1.11.0/"]   # Groß und klein gleich
    e.beobachtung.modelldateien = [".gibtsnicht"]
    r = Lastmesser(lambda: e).messen(_beobachter(e).aufnehmen())
    assert [p.pid for p in r.laeufer if p.rolle == Laeuferrolle.ARBEITER] == [813]


def test_ohne_lsof_ohne_aussage(nachgestellt, monkeypatch):
    monkeypatch.setattr(beobachtung, "_lsof", lambda *args: None)
    erste, zweite = _messen_zweimal(_beobachter(), monkeypatch)
    for r in (erste, zweite):
        # der Läufer ist nicht von der Fremdlast zu trennen: weder Liste noch Fremdlast
        assert r.gemessen is False and r.laeufer == [] and r.fremd_prozent is None


def test_ohne_laeufer_nur_fremdlast(nachgestellt, monkeypatch):
    e = _einstellungen()
    e.nachbar.modell_laeufer = None
    _, zweite = _messen_zweimal(_beobachter(e), monkeypatch)
    # ohne eingetragenen Läufer gibt es keinen, der herauszurechnen wäre: was er rechnet, ist fremd
    assert zweite.gemessen is False and zweite.laeufer == []
    assert zweite.fremd_prozent == pytest.approx(10.0 + (0.3 + 15 + 0.75 + 0.15 + 0 + 7 + 6) / 150 * 100, abs=0.05)


def test_abgeschaltet_misst_nichts(nachgestellt):
    b = _beobachter()
    b.einstellungen.beobachtung.aktiv = False
    assert b.aufnehmen() is None
    r = Lastmesser(lambda: b.einstellungen).messen(None)
    assert r.gemessen is False and r.laeufer == [] and r.fremd_prozent is None and nachgestellt == []


def test_endungen_brauchen_einen_punkt():
    with pytest.raises(ValueError):
        Beobachtung(modelldateien=[""])
    with pytest.raises(ValueError):
        Beobachtung(modelldateien=["gguf"])
    with pytest.raises(ValueError):
        Beobachtung(modelldateien=[])
    assert Beobachtung().modelldateien == [".gguf", ".safetensors"]


@pytest.mark.parametrize("falsch", ["", "/", "//", "backends", "/extensions/backends", "extensions/backends/", " /backends/", "/a//b/"])
def test_bibliotheken_sind_ordnerteile(falsch):
    with pytest.raises(ValueError):
        Beobachtung(arbeiter_bibliotheken=[falsch])


def test_bibliotheken_vorgabe_und_leer():
    assert Beobachtung().arbeiter_bibliotheken == ["/extensions/backends/"]
    assert Beobachtung(arbeiter_bibliotheken=[]).arbeiter_bibliotheken == []


# ── Beenden ──────────────────────────────────────────────────────────────
@pytest.fixture
def signale(monkeypatch):
    """Nachgestellte Signale: der Prozess geht auf SIGTERM (oder erst auf SIGKILL, wenn `haengt`)."""
    zustand = SimpleNamespace(gesendet=[], haengt=False, lebend=True)

    def senden(pid: int, sig: int) -> None:
        zustand.gesendet.append((pid, sig))
        if sig == signal.SIGKILL or not zustand.haengt:
            zustand.lebend = False
    monkeypatch.setattr(laeuferlast, "_signal", senden)
    monkeypatch.setattr(laeuferlast, "_lebt", lambda pid: zustand.lebend)
    monkeypatch.setattr(laeuferlast, "PRUEFABSTAND_S", 0.01)
    return zustand


async def test_beendet_einen_arbeiter_auf_bitte(nachgestellt, signale):
    r = await Laeuferaufsicht(_beobachter()).beenden("808")
    assert r.erfolg and r.befehl == Befehlsart.LAEUFER_PROZESS_BEENDEN and r.ziel == "808"
    assert signale.gesendet == [(808, signal.SIGTERM)]
    assert r.meldung == f"node (LM Studio) mit {BGE.replace(HEIM, '~')} beendet: auf Bitte (SIGTERM)"


async def test_haengender_arbeiter_nach_der_anhaltezeit_hart(nachgestellt, signale):
    e = _einstellungen()
    e.beobachtung.anhaltezeit_s = 1
    signale.haengt = True
    r = await Laeuferaufsicht(_beobachter(e)).beenden("811")
    assert r.erfolg and signale.gesendet == [(811, signal.SIGTERM), (811, signal.SIGKILL)]
    assert r.meldung.endswith("beendet: nach 1 s hart (SIGKILL)") and "model.safetensors" in r.meldung


@pytest.mark.parametrize("ziel, grund", [
    ("807", "Hauptprozess des Läufers"),
    ("810", "ist kein Arbeiter"),
    ("960", "gehört nicht zum Modell-Läufer"),
    ("12345", "läuft nicht (mehr)"),
    ("abc", "keine Prozessnummer"),
])
async def test_beendet_nur_arbeiter(nachgestellt, ziel, grund):
    r = await Laeuferaufsicht(_beobachter()).beenden(ziel)      # ein Signal ließe keine_echten_signale scheitern
    assert not r.erfolg and grund in r.meldung


async def test_beendet_einen_arbeiter_ohne_modelldatei(nachgestellt, signale):
    r = await Laeuferaufsicht(_beobachter()).beenden("813")
    assert r.erfolg and signale.gesendet == [(813, signal.SIGTERM)]
    assert r.meldung == "node (LM Studio) beendet: auf Bitte (SIGTERM)"


async def test_ohne_lsof_wird_nichts_beendet(nachgestellt, monkeypatch):
    monkeypatch.setattr(beobachtung, "_lsof", lambda *args: None)
    r = await Laeuferaufsicht(_beobachter()).beenden("808")
    assert not r.erfolg and "lsof fehlt" in r.meldung


async def test_prueft_auch_bei_abgeschalteter_beobachtung(nachgestellt, signale):
    e = _einstellungen()
    e.beobachtung.aktiv = False
    r = await Laeuferaufsicht(_beobachter(e)).beenden("809")
    assert r.erfolg and signale.gesendet == [(809, signal.SIGTERM)]


class ScheinMesser:
    def messwege(self) -> list[str]:
        return ["speicher"]

    def messen(self) -> Messwerte:
        return Messwerte(speicher_gesamt_gb=64.0, speicher_belegt_gb=20.0)


async def test_befehl_der_leitstelle_geht_an_die_aufsicht(tmp_path: Path):
    o = Ordner(tmp_path)
    o.anlegen()
    kanal = Leitstellenkanal(o, Verwalter(o, o.einstellungen()), ScheinMesser())
    gerufen: list[str] = []

    async def beenden(ziel: str):
        gerufen.append(ziel)
        return laeuferlast.BefehlErgebnis(befehl=Befehlsart.LAEUFER_PROZESS_BEENDEN, ziel=ziel, erfolg=True, meldung="beendet")
    kanal.laeuferaufsicht = SimpleNamespace(beenden=beenden)
    gesendet: list[dict] = []

    async def senden(text: str) -> None:
        gesendet.append(json.loads(text))
    u = Umschlag(art="knoten.befehl", nutzlast={"befehl": "laeufer_prozess_beenden", "ziel": "808"})
    await kanal._befehl(u, senden)
    assert gerufen == ["808"]
    assert gesendet[0]["art"] == "knoten.befehl_ergebnis" and gesendet[0]["bezug"] == u.id and gesendet[0]["nutzlast"]["erfolg"]


async def test_beobachtung_misst_erst_nach_der_uebernahme(tmp_path: Path):
    """Befund vom 27.10.2026: direkt nach dem Neustart meldete die Beobachtung eigene Dienste als Speicher am Leitstand
    vorbei, eine Messung später als nicht mehr gesehen; sie hatte gemessen, bevor die Dienste übernommen waren. Jetzt
    misst sie erst, wenn der Start alles Laufende übernommen hat."""
    o = Ordner(tmp_path)
    o.anlegen()
    kanal = Leitstellenkanal(o, Verwalter(o, o.einstellungen()), ScheinMesser())
    aufnahmen: list[int] = []
    kanal.beobachter.aufnehmen = lambda: aufnahmen.append(1)                 # type: ignore[method-assign]
    gesendet: list[str] = []

    async def senden(text: str) -> None:
        gesendet.append(json.loads(text)["art"])
    aufgabe = asyncio.create_task(kanal._beobachten_im_takt(senden))
    try:
        await asyncio.sleep(0.3)
        assert aufnahmen == [] and gesendet == []
        await kanal.verwalter.hochfahren()
        for _ in range(50):
            if gesendet:
                break
            await asyncio.sleep(0.05)
        assert aufnahmen == [1] and gesendet == ["knoten.fremde", "knoten.last"]
    finally:
        aufgabe.cancel()
        await asyncio.gather(aufgabe, return_exceptions=True)
