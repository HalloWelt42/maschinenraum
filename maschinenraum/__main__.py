"""Startpunkt: `maschinenraum [ordner]` (Vorgabe ~/Maschinenraum) startet Dienstverwaltung, Messung, Oberfläche
und, wenn eingetragen, die Verbindung zur Leitstelle. `--liste` zeigt nur den Stand der Dienste.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

import uvicorn
from dienstkern.web import protokoll_einrichten

from .konfig import STANDARD_ORDNER, Ordner
from .prozesse import Verwalter


async def _beide(oberflaeche: uvicorn.Server, durchleitung: uvicorn.Server) -> None:
    """Oberfläche (nur dieser Rechner) und Durchleitung (für die Leitstelle) in einem Prozess; endet einer, enden beide."""
    aufgaben = {asyncio.create_task(oberflaeche.serve()), asyncio.create_task(durchleitung.serve())}
    _, offen = await asyncio.wait(aufgaben, return_when=asyncio.FIRST_COMPLETED)
    oberflaeche.should_exit = durchleitung.should_exit = True
    await asyncio.gather(*offen, return_exceptions=True)


def laufen(ordner: Ordner) -> None:
    from . import durchleitung
    from .api import erstellen
    ordner.anlegen()
    protokoll_einrichten(ordner.protokolle / "maschinenraum.log")
    e = ordner.einstellungen()
    app = erstellen(ordner)
    weg = durchleitung.erstellen(app.state.laufzeit)
    asyncio.run(_beide(uvicorn.Server(uvicorn.Config(app, host=e.oberflaeche.adresse, port=e.oberflaeche.port, log_level="warning", access_log=False)),
                       uvicorn.Server(uvicorn.Config(weg, host=e.durchleitung.adresse, port=e.durchleitung.port, log_level="warning", access_log=False))))


async def liste(ordner: Ordner) -> None:
    verwalter = Verwalter(ordner, ordner.einstellungen())
    await verwalter.runde()
    for f in verwalter.ladefehler:
        print(f"FEHLER  {f.datei}: {f.meldung}")
    for b in verwalter.liste().dienste:
        soll = verwalter.stand.dienste[b.kennung].soll
        jetzt = f"{b.gb_jetzt:6.1f}" if b.gb_jetzt is not None else "     -"
        print(f"{b.zustand.value:9} {b.kennung:22} jetzt {jetzt} GB  Bedarf {b.bedarf_gb:6.1f} GB  Port {b.port or '-':>5}  soll {soll.value if soll else '-':7} {b.meldung}")


def main() -> None:
    p = argparse.ArgumentParser(prog="maschinenraum", description="Maschinenraum: startet, hält an und misst die Dienste dieses Rechners")
    p.add_argument("ordner", nargs="?", default=STANDARD_ORDNER, help="Ordner mit einstellungen.toml und dienste/")
    p.add_argument("--liste", action="store_true", help="nur den Stand der Dienste zeigen")
    a = p.parse_args()
    ordner = Ordner(Path(a.ordner))
    if a.liste:
        logging.basicConfig(level=logging.WARNING)
        asyncio.run(liste(ordner))
    else:
        laufen(ordner)


if __name__ == "__main__":
    main()
