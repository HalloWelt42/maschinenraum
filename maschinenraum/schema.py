"""JSON-Schema aller Daten, die die Oberfläche sieht. Eine Wahrheit: die Pydantic-Modelle.

`python -m maschinenraum.schema` schreibt ein Schema mit allen Modellen unter `$defs`; die Oberfläche erzeugt
daraus ihre Typen (frontend/werkzeuge/typen.mjs).
"""

from __future__ import annotations

import json
import sys

from pydantic import BaseModel
from pydantic.json_schema import models_json_schema

from .api import LeitstellenDaten, Protokollauszug, Stand
from .protokoll import BefehlErgebnis

# Antworten: jedes Feld wird immer mitgeschickt, auch mit Vorgabewert (auch in eingebetteten Modellen)
AUSGABE: list[type[BaseModel]] = [Stand, BefehlErgebnis, Protokollauszug]
# Eingaben: Felder mit Vorgabewert dürfen fehlen
EINGABE: list[type[BaseModel]] = [LeitstellenDaten]


def schema() -> dict:
    paare = [(m, "serialization") for m in AUSGABE] + [(m, "validation") for m in EINGABE]
    _, defs = models_json_schema(paare, title="Maschinenraum")
    eingaben = {m.__name__ for m in EINGABE}
    for name, d in defs.get("$defs", {}).items():
        if name not in eingaben and "properties" in d:
            d["required"] = list(d["properties"])
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", "title": "Maschinenraum", "type": "object",
            "properties": {m.__name__: {"$ref": f"#/$defs/{m.__name__}"} for m in AUSGABE + EINGABE}, **defs}


if __name__ == "__main__":
    json.dump(schema(), sys.stdout, ensure_ascii=False, indent=1)
