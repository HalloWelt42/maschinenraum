"""Dienstverwaltung des Maschinenraums auf dem Dienstkern: die KI-Dienste aus dienste/, Befehle von Hand und von der
Leitstelle, Berichte im Format des Leitstellen-Protokolls.

Starten, Anhalten, Abhängigkeiten, begrenzte Neustarts, Sollzustand und Prozessmessung kommen aus dem Dienstkern
(gemeinsam mit dem Stellwerk). Hier steht nur, was dem Maschinenraum eigen ist: die Leitstelle darf nur anhalten, was
die Dienstdatei ihr erlaubt, und sieht Fähigkeiten und Speicherbedarf.
"""

from __future__ import annotations

import logging
from pathlib import Path

from dienstkern.dienst import Dienst
from dienstkern.verwalter import Ergebnis, Neustartregeln
from dienstkern.verwalter import Verwalter as Kernverwalter
from dienstkern.zustand import Soll

from dienstkern.vorlage import Ladefehler

from .konfig import HF_ORDNER, INSTANZ_PORT_ABSTAND, MODELLE_VARIABLE, PORT_VARIABLE, DienstVorlage, Einstellungen, Ordner
from .protokoll import Befehl, BefehlErgebnis, Befehlsart, Dienstliste, ProzessBericht, Prozesszustand, Selbstauskunft

__all__ = ["Soll", "Verwalter", "bericht"]

log = logging.getLogger("maschinenraum")


def grund_und_stufe(kennung: str) -> tuple[str, int]:
    """'klangwerk-hoeren.2' -> ('klangwerk-hoeren', 2); ohne Stufe ist es die Grundinstanz (1)."""
    grund, _, stufe = kennung.rpartition(".")
    return (grund, int(stufe)) if grund and stufe.isdigit() else (kennung, 1)


def mit_port(v: DienstVorlage, stufe: int = 1) -> DienstVorlage:
    """Die Vorlage der Instanz `stufe`: eigener Port (auch in der Umgebung), eigene Kennung und eigener Name."""
    if v.port is None:
        return v
    port = v.port + INSTANZ_PORT_ABSTAND * (stufe - 1)
    aenderung: dict = {"umgebung": {**v.umgebung, PORT_VARIABLE: str(port)}}
    if stufe > 1:
        aenderung |= {"kennung": f"{v.kennung}.{stufe}", "name": f"{v.name} ({stufe})", "port": port,
                      "pruefadresse": v.pruefadresse.replace(f":{v.port}", f":{port}") if v.pruefadresse else None}
    return v.model_copy(update=aenderung)


def mit_ablage(v: DienstVorlage, modelle: Path) -> DienstVorlage:
    """Jeder Dienst findet die Modellablage des Rechners: $MASCHINENRAUM_MODELLE und darin den Zwischenspeicher von Hugging
    Face (nur die Modelle; Anmeldedaten bleiben im Benutzerordner). Einträge der Dienstdatei gehen vor und dürfen
    $MASCHINENRAUM_MODELLE nutzen."""
    ablage = {MODELLE_VARIABLE: str(modelle), "HF_HUB_CACHE": str(modelle / HF_ORDNER)}
    return v.model_copy(update={"umgebung": {**ablage, **v.umgebung}})


def bericht(d: Dienst) -> ProzessBericht:
    """Stand eines Dienstes im Format, das die Leitstelle erwartet."""
    b, v = d.bericht(), d.vorlage
    assert isinstance(v, DienstVorlage)
    grund, stufe = grund_und_stufe(b.kennung)
    return ProzessBericht(kennung=b.kennung, name=b.name, faehigkeiten=set(v.faehigkeiten), port=b.port, zustand=Prozesszustand(b.zustand.value),
                          fremd=b.fremd, gb_jetzt=b.gb_jetzt, bedarf_gb=b.bedarf_gb, aktiv=b.aktiv, anhalten_erlaubt=v.leitstelle_anhalten,
                          plaetze=v.plaetze, selbstauskunft=Selbstauskunft(zweck=v.beschreibung, eignung=list(v.eignung), sprachen=list(v.sprachen)),
                          instanz_von=grund if stufe > 1 else None, instanzen=v.instanzen, meldung=b.meldung)


def _als_befehlergebnis(art: Befehlsart, e: Ergebnis) -> BefehlErgebnis:
    return BefehlErgebnis(befehl=art, ziel=e.ziel, erfolg=e.erfolg, meldung=e.meldung)


class Verwalter(Kernverwalter):
    """Alle KI-Dienste des Ordners. Läuft unabhängig von Oberfläche und Leitstelle."""

    def __init__(self, ordner: Ordner, einstellungen: Einstellungen) -> None:
        self.ordner = ordner
        self.einstellungen = einstellungen
        self.weitere: set[str] = set()       # weitere Instanzen (<grund>.<n>), nur im Speicher; die Leitstelle startet sie
        super().__init__(self._vorlagen, ordner.protokolle, ordner.zustand_datei, herkunft="vom Maschinenraum")

    def _vorlagen(self) -> tuple[list[DienstVorlage], list[Ladefehler]]:
        """Die Dienstdateien und die weiteren Instanzen, abgeleitet aus der jeweils gültigen Datei (folgen ihr)."""
        vorlagen, fehler = self.ordner.dienste()
        vorlagen = [mit_ablage(v, self.ordner.modelle) for v in vorlagen]
        gruende = {v.kennung: v for v in vorlagen}
        for k in list(self.weitere):
            grund, stufe = grund_und_stufe(k)
            if grund not in gruende or stufe > gruende[grund].instanzen:
                self.weitere.discard(k)          # Datei weg oder Höchstzahl gesenkt: die Instanz geht mit
        return [mit_port(v) for v in vorlagen] + [mit_port(gruende[grund_und_stufe(k)[0]], grund_und_stufe(k)[1]) for k in sorted(self.weitere)], fehler

    @property
    def regeln(self) -> Neustartregeln:
        return self.einstellungen.neustart

    @property
    def takt_s(self) -> float:
        return self.einstellungen.messung.takt_s

    async def befehl(self, b: Befehl, von_leitstelle: bool = False) -> BefehlErgebnis:
        """Starten oder anhalten. Die Leitstelle darf nur anhalten, was die Dienstdatei ihr erlaubt; von Hand geht immer."""
        d = self.dienste.get(b.ziel)
        if von_leitstelle and b.befehl == Befehlsart.DIENST_ANHALTEN and d is not None and not d.vorlage.leitstelle_anhalten:
            log.info("Leitstelle wollte %s anhalten; laut Dienstdatei nur von Hand", d.vorlage.name)
            return BefehlErgebnis(befehl=b.befehl, ziel=b.ziel, erfolg=False, meldung="Anhalten nur von Hand (Dienstdatei: leitstelle_anhalten = false)")
        grund, stufe = grund_und_stufe(b.ziel)
        if b.befehl == Befehlsart.DIENST_STARTEN:     # ein Start der Leitstelle ist kein Start von Hand (Abstürze bleiben)
            if stufe > 1 and b.ziel not in self.dienste:
                g = self.dienste.get(grund)
                if g is None or stufe > g.vorlage.instanzen:
                    return BefehlErgebnis(befehl=b.befehl, ziel=b.ziel, erfolg=False,
                                          meldung=f"keine Instanz {stufe}: die Dienstdatei erlaubt {g.vorlage.instanzen if g else 0}")
                self.weitere.add(b.ziel)
                self._vorlagen_lesen()
            return _als_befehlergebnis(b.befehl, await self.starten(b.ziel, von_hand=not von_leitstelle))
        ergebnis = _als_befehlergebnis(b.befehl, await self.anhalten(b.ziel))
        if stufe > 1 and ergebnis.erfolg:
            self.weitere.discard(b.ziel)             # angehalten heißt bei weiteren Instanzen: weg
            self._vorlagen_lesen()
        return ergebnis

    async def neu_starten_befehl(self, kennung: str) -> BefehlErgebnis:
        """Anhalten und wieder starten; nur aus der eigenen Oberfläche, nicht Teil des Leitstellen-Protokolls."""
        return _als_befehlergebnis(Befehlsart.DIENST_STARTEN, await self.neu_starten(kennung))

    def liste(self) -> Dienstliste:
        return Dienstliste(dienste=[bericht(d) for d in self.dienste.values()])
