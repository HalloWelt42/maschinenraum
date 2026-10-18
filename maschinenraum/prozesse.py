"""Dienstverwaltung des Maschinenraums auf dem Dienstkern: die KI-Dienste aus dienste/, Befehle von Hand und von der
Leitstelle, Berichte im Format des Leitstellen-Protokolls.

Starten, Anhalten, Abhängigkeiten, begrenzte Neustarts, Sollzustand und Prozessmessung kommen aus dem Dienstkern
(gemeinsam mit dem Stellwerk). Hier steht nur, was dem Maschinenraum eigen ist: die Leitstelle darf nur anhalten, was
die Dienstdatei ihr erlaubt, und sieht Fähigkeiten und Speicherbedarf.
"""

from __future__ import annotations

import logging

from dienstkern.dienst import Dienst
from dienstkern.verwalter import Ergebnis, Neustartregeln
from dienstkern.verwalter import Verwalter as Kernverwalter
from dienstkern.zustand import Soll

from .konfig import DienstVorlage, Einstellungen, Ordner
from .protokoll import Befehl, BefehlErgebnis, Befehlsart, Dienstliste, ProzessBericht, Prozesszustand

__all__ = ["Soll", "Verwalter", "bericht"]

log = logging.getLogger("maschinenraum")


def bericht(d: Dienst) -> ProzessBericht:
    """Stand eines Dienstes im Format, das die Leitstelle erwartet."""
    b, v = d.bericht(), d.vorlage
    assert isinstance(v, DienstVorlage)
    return ProzessBericht(kennung=b.kennung, name=b.name, faehigkeiten=set(v.faehigkeiten), port=b.port, zustand=Prozesszustand(b.zustand.value),
                          fremd=b.fremd, gb_jetzt=b.gb_jetzt, bedarf_gb=b.bedarf_gb, aktiv=b.aktiv, anhalten_erlaubt=v.leitstelle_anhalten,
                          plaetze=v.plaetze, meldung=b.meldung)


def _als_befehlergebnis(art: Befehlsart, e: Ergebnis) -> BefehlErgebnis:
    return BefehlErgebnis(befehl=art, ziel=e.ziel, erfolg=e.erfolg, meldung=e.meldung)


class Verwalter(Kernverwalter):
    """Alle KI-Dienste des Ordners. Läuft unabhängig von Oberfläche und Leitstelle."""

    def __init__(self, ordner: Ordner, einstellungen: Einstellungen) -> None:
        self.ordner = ordner
        self.einstellungen = einstellungen
        super().__init__(ordner.dienste, ordner.protokolle, ordner.zustand_datei, herkunft="vom Maschinenraum")

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
        if b.befehl == Befehlsart.DIENST_STARTEN:     # ein Start der Leitstelle ist kein Start von Hand (Abstürze bleiben)
            return _als_befehlergebnis(b.befehl, await self.starten(b.ziel, von_hand=not von_leitstelle))
        return _als_befehlergebnis(b.befehl, await self.anhalten(b.ziel))

    async def neu_starten_befehl(self, kennung: str) -> BefehlErgebnis:
        """Anhalten und wieder starten; nur aus der eigenen Oberfläche, nicht Teil des Leitstellen-Protokolls."""
        return _als_befehlergebnis(Befehlsart.DIENST_STARTEN, await self.neu_starten(kennung))

    def liste(self) -> Dienstliste:
        return Dienstliste(dienste=[bericht(d) for d in self.dienste.values()])
