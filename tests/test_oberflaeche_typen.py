"""Oberfläche und Schnittstelle sprechen dieselben Schlüssel: die erzeugten Typen (frontend/src/lib/typen.gen.ts, aus
`npm run typen`) sind auf dem Stand der Python-Modelle, und jede Fähigkeit hat Wort, Symbol und Farbe (wort.ts). Sonst
stürzt die Oberfläche bei einer neuen Fähigkeit ab (18.10.2026: Fähigkeit ton, "Lade den Stand" blieb stehen)."""

from __future__ import annotations

import re
from pathlib import Path

from maschinenraum.protokoll import Faehigkeit

OBERFLAECHE = Path(__file__).resolve().parents[1] / "frontend" / "src" / "lib"


def _union(ts: str, name: str) -> list[str]:
    treffer = re.search(rf"export type {name} =([^;]+);", ts)
    assert treffer, f"{name} fehlt in typen.gen.ts"
    return re.findall(r"'([a-z_]+)'", treffer.group(1))


def test_erzeugte_typen_kennen_jede_faehigkeit():
    ts = (OBERFLAECHE / "typen.gen.ts").read_text(encoding="utf-8")
    assert _union(ts, "Faehigkeit") == [f.value for f in Faehigkeit], "typen.gen.ts veraltet: npm run typen"


def test_jede_faehigkeit_hat_wort_symbol_und_farbe():
    wort = (OBERFLAECHE / "wort.ts").read_text(encoding="utf-8")
    block = wort[wort.index("export const FAEHIGKEIT"):wort.index("};", wort.index("export const FAEHIGKEIT"))]
    for f in Faehigkeit:
        assert re.search(rf"^\s*{f.value}: {{ wort: '[^']+', symbol: 'fa-[a-z-]+', klasse: '[a-z]+', farbe: 'var\(--mr-[a-z]+\)' }},$",
                         block, re.M), f"wort.ts: {f.value} fehlt"
