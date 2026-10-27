"""Last des Docker-Rechners (`knoten.last`, Feld `docker`), mit nachgestellten Ausgaben der Befehlszeile von Docker. Kein
Test fragt das echte Docker (conftest.py); die Tests für die Aufrufe selbst nehmen ein nachgestelltes docker aus einem
eigenen Ordner."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
from pathlib import Path

import pytest
from pydantic import BaseModel, Field

from maschinenraum import dockerlast
from maschinenraum.dockerlast import INFO, LISTE, STATS, Dockermesser
from maschinenraum.konfig import Einstellungen, Ordner
from maschinenraum.leitstelle import Leitstellenkanal
from maschinenraum.protokoll import DockerContainer, DockerLast, KnotenLast, Laeuferprozess, Laeuferrolle, Messwerte
from maschinenraum.prozesse import Verwalter

ECHTES_AUFRUFEN = dockerlast._aufrufen        # vor der Nachstellung aus conftest.py gemerkt
GIB = 1024 ** 3

#: so antwortet Docker am 27.10.2026 auf dem Mac (Messung beim Einsortieren der Masseneinbettung des Fundus)
AUSGABE_INFO = "8\t16746086400\n"
AUSGABE_LISTE = "\n".join([
    "d43b7984326f\tfundus", "0a0c2f96a220\tzusage-852777624", "77e4792720a7\tzusage-852777624", "6895988a73fa\tbuchbote",
    "ab12cd34ef56\t",                                                     # ohne Compose gestartet
]) + "\n"
AUSGABE_STATS = "\n".join([
    "d43b7984326f\tfundus-qdrant-1\t206.76%\t6.127GiB / 15.6GiB",
    "0a0c2f96a220\tzusage-852777624-datenbank\t39.67%\t274.7MiB / 15.6GiB",
    "77e4792720a7\tzusage-852777624-browser\t2.95%\t65.06MiB / 15.6GiB",
    "6895988a73fa\tbuchbote-datenbank-1\t0.00%\t17.79MiB / 15.6GiB",
    "ab12cd34ef56\tbastelkiste\t--\t-- / --",                               # startet gerade: Docker hat noch keine Werte
    "99aa88bb77cc\tganz-neu\t1.50%\t0B / 15.6GiB",                           # erst nach docker ps gestartet: ohne Projekt
]) + "\n"


@pytest.fixture
def docker(monkeypatch):
    """Nachgestelltes Docker: Ausgabe je Befehl (None: scheitert), merkt sich die Aufrufe."""
    stand = {"ausgaben": {"info": AUSGABE_INFO, "ps": AUSGABE_LISTE, "stats": AUSGABE_STATS}, "da": True, "aufrufe": []}

    def aufrufen(befehle, frist_s):
        stand["aufrufe"].append(befehle)
        stand["frist_s"] = frist_s
        return [stand["ausgaben"][b[0]] for b in befehle] if stand["da"] else None
    monkeypatch.setattr(dockerlast, "_aufrufen", aufrufen)
    return stand


def _messer(e: Einstellungen | None = None) -> Dockermesser:
    e = e or Einstellungen()
    return Dockermesser(lambda: e)


def test_kerne_speicher_und_container(docker):
    d = _messer().messen()
    assert d.gemessen and d.kerne == 8 and d.speicher_gb == 15.6
    nach_name = {c.name: c for c in d.container}
    assert [c.name for c in d.container] == sorted(nach_name)
    assert nach_name["fundus-qdrant-1"] == DockerContainer(name="fundus-qdrant-1", projekt="fundus", cpu_prozent=206.8, gb=6.13)
    assert nach_name["zusage-852777624-datenbank"].projekt == "zusage-852777624"
    assert nach_name["zusage-852777624-datenbank"].gb == round(274.7 * 1024 ** 2 / GIB, 2)
    assert nach_name["buchbote-datenbank-1"].cpu_prozent == 0.0
    assert nach_name["bastelkiste"] == DockerContainer(name="bastelkiste", projekt="", cpu_prozent=None, gb=None)
    assert nach_name["ganz-neu"] == DockerContainer(name="ganz-neu", projekt="", cpu_prozent=1.5, gb=0.0)


def test_fragt_nur_lesend_und_nur_nach_den_noetigen_feldern(docker):
    """docker inspect und docker compose config zeigten die Umgebung der Container mit Schlüsseln: gefragt wird nur mit
    --format nach Zahlen, Namen und dem Projekt."""
    _messer().messen()
    assert docker["aufrufe"] == [[INFO, LISTE, STATS]]
    assert [b[0] for b in docker["aufrufe"][0]] == ["info", "ps", "stats"]
    for befehl in docker["aufrufe"][0]:
        assert "--format" in befehl and "{{json" not in " ".join(befehl) and "Env" not in " ".join(befehl)
    assert "--no-stream" in STATS


@pytest.mark.parametrize("fehlt, grund", [
    ("info", "antwortet nicht (docker info, Frist 15 s)"),
    ("ps", "nicht vollständig (docker ps, Frist 15 s)"),
    ("stats", "nicht vollständig (docker stats, Frist 15 s)"),
])
def test_ohne_vollstaendige_antwort_ohne_aussage(docker, fehlt, grund):
    docker["ausgaben"][fehlt] = None
    d, warum = dockerlast.messen(15)
    assert d == DockerLast(gemessen=False) and grund in warum      # keine halbe Liste, die wie "keine Container" aussähe


def test_ohne_docker_ohne_aussage(docker):
    docker["da"] = False
    d, warum = dockerlast.messen(15)
    assert d == DockerLast(gemessen=False) and "nicht zu finden" in warum


def test_unlesbare_antwort_ohne_aussage(docker):
    docker["ausgaben"]["info"] = "viele\n"
    assert dockerlast.messen(15)[0] == DockerLast(gemessen=False)


def test_ohne_container_ist_eine_aussage(docker):
    docker["ausgaben"]["ps"] = docker["ausgaben"]["stats"] = ""
    d = _messer().messen()
    assert d.gemessen and d.kerne == 8 and d.container == []


@pytest.mark.parametrize("schalter", ["aktiv", "docker"])
def test_abgeschaltet_wird_nicht_gefragt(docker, schalter):
    e = Einstellungen()
    setattr(e.beobachtung, schalter, False)
    assert _messer(e).messen() is None and docker["aufrufe"] == []


def test_ins_protokoll_nur_der_wechsel(docker, caplog):
    m = _messer()
    with caplog.at_level(logging.INFO, logger="maschinenraum"):
        m.messen()
        docker["ausgaben"]["info"] = None
        m.messen()
        m.messen()
        docker["ausgaben"]["info"] = AUSGABE_INFO
        m.messen()
        m.messen()
    assert [r.getMessage() for r in caplog.records] == ["Docker-Rechner nicht gemessen: Docker antwortet nicht (docker info, Frist 15 s)",
                                                        "Docker-Rechner wieder gemessen"]


def test_einstellung_docker_vorgabe_an():
    assert Einstellungen().beobachtung.docker is True


def test_frist_ist_ein_takt_der_beobachtung(docker):
    e = Einstellungen()
    e.beobachtung.takt_s = 40
    _messer(e).messen()
    assert docker["frist_s"] == 40


# ── Verträglichkeit mit der Leitstelle ───────────────────────────────────
class KnotenLastBis015(BaseModel):
    """`knoten.last`, wie eine Leitstelle es vor dem Feld `docker` kennt (Spiegel bis Maschinenraum 0.15.0)."""

    gemessen: bool = True
    kerne: int
    laeufer: list[Laeuferprozess] = Field(default_factory=list)
    fremd_prozent: float | None = None


def test_aeltere_leitstelle_nimmt_die_meldung_an(docker):
    """Das Feld ist neu und darf fehlen; eine Leitstelle mit älterem Spiegel übergeht es (Pydantic verwirft unbekannte
    Felder, solange das Modell sie nicht ausdrücklich verbietet)."""
    last = KnotenLast(kerne=10, laeufer=[Laeuferprozess(pid=807, name="Läufer", rolle=Laeuferrolle.HAUPT)], fremd_prozent=12.0,
                      docker=_messer().messen())
    roh = json.loads(json.dumps(last.model_dump(mode="json")))
    alt = KnotenLastBis015.model_validate(roh)
    assert alt.kerne == 10 and alt.fremd_prozent == 12.0 and not hasattr(alt, "docker")
    assert KnotenLast.model_validate({"kerne": 10}).docker is None                # Meldung einer älteren Fassung
    assert KnotenLast.model_config.get("extra") in (None, "ignore")


# ── Im Takt der Beobachtung ──────────────────────────────────────────────
class ScheinMesser:
    def messwege(self) -> list[str]:
        return ["speicher"]

    def messen(self) -> Messwerte:
        return Messwerte(speicher_gesamt_gb=64.0, speicher_belegt_gb=20.0)


async def test_docker_daneben_in_eigenem_faden_und_in_derselben_meldung(tmp_path: Path, docker, monkeypatch):
    """Die Aufnahme des Läufers wartet, bis Docker gefragt ist: liefen beide nacheinander, wartete sie vergeblich."""
    o = Ordner(tmp_path)
    o.anlegen()
    kanal = Leitstellenkanal(o, Verwalter(o, o.einstellungen()), ScheinMesser())
    gefragt = threading.Event()
    nebeneinander: list[bool] = []
    kanal.beobachter.aufnehmen = lambda: nebeneinander.append(gefragt.wait(5))     # type: ignore[method-assign]
    aufrufen = dockerlast._aufrufen

    def docker_fragen(befehle, frist_s):
        gefragt.set()
        return aufrufen(befehle, frist_s)
    monkeypatch.setattr(dockerlast, "_aufrufen", docker_fragen)
    gesendet: list[dict] = []

    async def senden(text: str) -> None:
        gesendet.append(json.loads(text))
    await kanal.verwalter.hochfahren()
    aufgabe = asyncio.create_task(kanal._beobachten_im_takt(senden))
    try:
        for _ in range(100):
            if len(gesendet) >= 2:
                break
            await asyncio.sleep(0.05)
    finally:
        aufgabe.cancel()
        await asyncio.gather(aufgabe, return_exceptions=True)
    assert nebeneinander == [True]
    assert [g["art"] for g in gesendet[:2]] == ["knoten.fremde", "knoten.last"]
    d = gesendet[1]["nutzlast"]["docker"]
    assert d["gemessen"] and d["kerne"] == 8 and {"name": "fundus-qdrant-1", "projekt": "fundus", "cpu_prozent": 206.8, "gb": 6.13} in d["container"]


# ── Die Aufrufe selbst, mit nachgestelltem docker ────────────────────────
@pytest.fixture
def schein_docker(tmp_path: Path, monkeypatch):
    """Ein docker im eigenen Ordner, der je Befehl wartet und antwortet (Wartezeiten in Sekunden je Befehl)."""
    def anlegen(warten: dict[str, float], ausgabe: dict[str, str]) -> None:
        zeilen = ["#!/bin/sh", 'case "$1" in']
        for befehl in ("info", "ps", "stats"):
            zeilen.append(f"  {befehl}) /bin/sleep {warten.get(befehl, 0)}; printf '{ausgabe.get(befehl, '')}' ;;")
        zeilen += ["  *) exit 9 ;;", "esac"]
        datei = tmp_path / "docker"
        datei.write_text("\n".join(zeilen) + "\n")
        datei.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}/usr/bin{os.pathsep}/bin")
    return anlegen


def test_aufrufe_laufen_nebeneinander(schein_docker):
    schein_docker({"info": 1, "ps": 1, "stats": 1}, {"info": "8\\t1024\\n", "ps": "abc\\tfundus\\n", "stats": ""})
    beginn = time.monotonic()
    ausgaben = ECHTES_AUFRUFEN([INFO, LISTE, STATS], frist_s=10)
    assert time.monotonic() - beginn < 2.5                       # nacheinander wären es drei Sekunden
    assert ausgaben == ["8\t1024\n", "abc\tfundus\n", ""]


def test_frist_beendet_einen_haengenden_aufruf(schein_docker):
    schein_docker({"stats": 30}, {"info": "8\\t1024\\n", "ps": ""})
    beginn = time.monotonic()
    ausgaben = ECHTES_AUFRUFEN([INFO, LISTE, STATS], frist_s=1.0)
    assert time.monotonic() - beginn < 5 and ausgaben == ["8\t1024\n", "", None]


def test_gescheiterter_aufruf_ohne_ausgabe(schein_docker):
    schein_docker({}, {})
    assert ECHTES_AUFRUFEN([["version"], INFO], frist_s=10) == [None, ""]


def test_ohne_docker_auf_dem_rechner(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))
    assert ECHTES_AUFRUFEN([INFO], frist_s=10) is None


async def test_takt_zaehlt_von_beginn_zu_beginn(tmp_path: Path, docker, monkeypatch):
    """Eine lange Messung des Docker-Rechners dehnt den Abstand der Meldungen nicht (vorher: Takt plus Messdauer)."""
    o = Ordner(tmp_path)
    o.anlegen()
    kanal = Leitstellenkanal(o, Verwalter(o, o.einstellungen()), ScheinMesser())
    kanal.verwalter.einstellungen.beobachtung.takt_s = 0.8                     # unter der Untergrenze, nur für den Test
    kanal.beobachter.aufnehmen = lambda: None                                  # type: ignore[method-assign]
    aufrufen = dockerlast._aufrufen

    def langsam(befehle, frist_s):
        time.sleep(0.5)
        return aufrufen(befehle, frist_s)
    monkeypatch.setattr(dockerlast, "_aufrufen", langsam)
    zeiten: list[float] = []

    async def senden(text: str) -> None:
        if json.loads(text)["art"] == "knoten.last":
            zeiten.append(time.monotonic())
    await kanal.verwalter.hochfahren()
    aufgabe = asyncio.create_task(kanal._beobachten_im_takt(senden))
    try:
        for _ in range(100):
            if len(zeiten) >= 3:
                break
            await asyncio.sleep(0.05)
    finally:
        aufgabe.cancel()
        await asyncio.gather(aufgabe, return_exceptions=True)
    abstaende = [b - a for a, b in zip(zeiten, zeiten[1:])]
    assert len(abstaende) == 2 and all(0.7 < x < 1.1 for x in abstaende), abstaende   # nacheinander wären es 1,3 s
