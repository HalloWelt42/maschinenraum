"""Startpunkt: `maschinenraum [ordner]` (Vorgabe ~/Maschinenraum) startet Dienstverwaltung, Messung, Oberfläche
und, wenn eingetragen, die Verbindung zur Leitstelle. `--liste` zeigt nur den Stand der Dienste.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import logging.handlers
from pathlib import Path

import uvicorn

from .konfig import STANDARD_ORDNER, Ordner
from .prozesse import Verwalter


def protokoll_einrichten(ordner: Ordner) -> None:
    """Ausgabe in protokolle/maschinenraum.log (rotierend) und auf die Konsole."""
    ordner.protokolle.mkdir(parents=True, exist_ok=True)
    form = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    datei = logging.handlers.RotatingFileHandler(ordner.protokolle / "maschinenraum.log", maxBytes=5 * 1024 * 1024, backupCount=2, encoding="utf-8")
    konsole = logging.StreamHandler()
    for h in (datei, konsole):
        h.setFormatter(form)
    wurzel = logging.getLogger()
    wurzel.setLevel(logging.INFO)
    wurzel.handlers = [datei, konsole]


def laufen(ordner: Ordner) -> None:
    from .api import erstellen
    ordner.anlegen()
    protokoll_einrichten(ordner)
    e = ordner.einstellungen().oberflaeche
    uvicorn.run(erstellen(ordner), host=e.adresse, port=e.port, log_level="warning", access_log=False)


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
