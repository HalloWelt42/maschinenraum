"""Der Modell-Läufer auf demselben Rechner, nur zur Anzeige: was er geladen hat und wie viel Speicher das ist.

Der Maschinenraum verwaltet ihn nicht; Laden und Entladen bleiben beim Modell-Läufer selbst (oder bei der
Leitstelle). Er zeigt ihn, damit die Speicheranzeige vollständig ist.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from pydantic import BaseModel, Field

GIB = 1024**3


class NachbarModell(BaseModel):
    name: str
    gb: float
    geladen: bool


class NachbarStand(BaseModel):
    adresse: str | None
    erreichbar: bool = False
    modelle: list[NachbarModell] = Field(default_factory=list)   # nur geladene
    geladen_gb: float = 0.0


def lesen(adresse: str | None) -> NachbarStand:
    if not adresse:
        return NachbarStand(adresse=None)
    try:
        with urllib.request.urlopen(adresse.rstrip("/") + "/api/v1/models", timeout=2) as antwort:
            daten = json.load(antwort)
    except (OSError, urllib.error.URLError, ValueError):
        return NachbarStand(adresse=adresse)
    modelle = [NachbarModell(name=m.get("display_name") or m.get("key", "?"), gb=round(m.get("size_bytes", 0) / GIB, 2), geladen=True)
               for m in daten.get("models", []) if m.get("loaded_instances")]
    return NachbarStand(adresse=adresse, erreichbar=True, modelle=modelle, geladen_gb=round(sum(m.gb for m in modelle), 2))
