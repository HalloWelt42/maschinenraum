"""Der Ordner des Maschinenraums: ein Ort je Rechner für alles, was er verwaltet.

    <ordner>/einstellungen.toml   Oberfläche, Messung, Neustartregeln, optional die Leitstelle
    <ordner>/schluessel           Schlüssel für die Leitstelle (nur für den Benutzer lesbar), wenn verbunden
    <ordner>/dienste/<name>.toml  je Dienst eine Datei; der Dateiname ist die Kennung
    <ordner>/betrieb/<name>.toml  Steuerprogramme des Rechners (etwa das Stellwerk): starten, anhalten, öffnen;
                                  keine KI, nie an die Leitstelle gemeldet. Das Programm trägt sich bei seiner Installation ein.
    <ordner>/protokolle/          Ausgabe des Maschinenraums und je Dienst eine Datei
    <ordner>/zustand.json         Sollzustand je Dienst (übersteht Neustarts) und gemessene Höchstwerte

Die Einstellungsdatei schreibt der Maschinenraum selbst (die Oberfläche ändert sie); Dienstdateien schreibt
der Mensch oder das Installationsskript eines Dienstes. Hier stehen nur KI-Dienste (mit Fähigkeiten); eigene Webapps
verwaltet das Stellwerk.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

from dienstkern.verwalter import Neustartregeln
from dienstkern.vorlage import Ladefehler, Vorlage, dateien_lesen
from pydantic import BaseModel, Field, model_validator

from .protokoll import Faehigkeit

STANDARD_ORDNER = "~/Maschinenraum"


# ── Einstellungen ────────────────────────────────────────────────────────
class Oberflaeche(BaseModel):
    adresse: str = Field(default="127.0.0.1", description="nur dieser Rechner; 0.0.0.0 öffnet die Oberfläche fürs Netz")
    port: int = Field(default=8540, ge=1, le=65535)


class Durchleitung(BaseModel):
    """Weg der Leitstelle zu den Diensten (wie bei einem Modell-Läufer); nur mit dem Schlüssel nutzbar."""

    adresse: str = Field(default="0.0.0.0", description="im Netz erreichbar, damit die Leitstelle Anfragen durchreichen kann")
    port: int = Field(default=8541, ge=1, le=65535)


class Leitstelle(BaseModel):
    adresse: str | None = Field(default=None, description="Basisadresse der Leitstelle, zum Beispiel http://leitstelle:8530; leer: ohne Leitstelle")
    wiederverbindung_max_s: float = Field(default=30, ge=1, description="längste Pause zwischen Verbindungsversuchen")

    @property
    def kanal(self) -> str | None:
        if not self.adresse:
            return None
        basis = self.adresse.rstrip("/")
        return "ws" + basis[4:] + "/agent/kanal" if basis.startswith("http") else basis + "/agent/kanal"


class Messung(BaseModel):
    takt_s: float = Field(default=5.0, ge=1, le=300, description="Abstand der Messungen und der Dienstprüfung")
    macmon: bool = Field(default=True, description="Zusatzmessungen (Grafik, Temperatur, Leistung) über macmon, wenn vorhanden")


class Nachbar(BaseModel):
    modell_laeufer: str | None = Field(default="http://127.0.0.1:1234", description="Modell-Läufer auf diesem Rechner, nur zur Anzeige; leer: keiner")


class Einstellungen(BaseModel):
    name: str | None = Field(default=None, description="Anzeigename des Rechners; sonst der Rechnername")
    oberflaeche: Oberflaeche = Field(default_factory=Oberflaeche)
    leitstelle: Leitstelle = Field(default_factory=Leitstelle)
    durchleitung: Durchleitung = Field(default_factory=Durchleitung)
    messung: Messung = Field(default_factory=Messung)
    neustart: Neustartregeln = Field(default_factory=Neustartregeln)
    nachbar: Nachbar = Field(default_factory=Nachbar)


def _toml_wert(w: object) -> str:
    if isinstance(w, bool):
        return "true" if w else "false"
    if isinstance(w, (int, float)):
        return repr(w)
    if isinstance(w, list):
        return "[" + ", ".join(_toml_wert(x) for x in w) + "]"
    return '"' + str(w).replace("\\", "\\\\").replace('"', '\\"') + '"'


def toml_schreiben(e: Einstellungen) -> str:
    """Einstellungen als TOML; leere Werte entfallen (gelten dann als Vorgabe)."""
    zeilen = ["# Einstellungen des Maschinenraums. Wird vom Programm geschrieben; Änderungen von Hand bleiben erhalten,",
              "# solange die Oberfläche nichts ändert. Dienste stehen im Ordner dienste/.", ""]
    daten = e.model_dump(mode="json", exclude_none=True)
    for k, w in daten.items():
        if not isinstance(w, dict):
            zeilen.append(f"{k} = {_toml_wert(w)}")
    for k, w in daten.items():
        if isinstance(w, dict):
            zeilen += ["", f"[{k}]"] + [f"{n} = {_toml_wert(x)}" for n, x in w.items()]
    return "\n".join(zeilen) + "\n"


# ── Dienste ──────────────────────────────────────────────────────────────
class DienstVorlage(Vorlage):
    """Eine Datei unter dienste/: ein KI-Dienst mit mindestens einer Fähigkeit, die die Leitstelle vermittelt.
    Was keine Fähigkeit hat (Webapps, ihre Datenbanken, Docker), gehört ins Stellwerk, nicht hierher."""

    faehigkeiten: set[Faehigkeit] = Field(min_length=1)
    leitstelle_anhalten: bool = Field(default=True, description="die Leitstelle darf ihn anhalten, um Speicher freizumachen; nein: nur von Hand")
    plaetze: int = Field(default=1, ge=1, le=64, description="so viele Anfragen nimmt der Dienst gleichzeitig an; die Leitstelle teilt danach zu")

    @model_validator(mode="before")
    @classmethod
    def _nur_ki_dienste(cls, daten: Any) -> Any:
        if isinstance(daten, dict) and not daten.get("faehigkeiten"):
            raise ValueError("ohne faehigkeiten: der Maschinenraum verwaltet nur Rechendienste (KI und Tonarbeit); Webapps und ihre Datenbanken gehören ins Stellwerk")
        return daten


class Ordner:
    def __init__(self, wurzel: Path) -> None:
        self.wurzel = wurzel.expanduser().resolve()

    @property
    def dienste_ordner(self) -> Path:
        return self.wurzel / "dienste"

    @property
    def protokolle(self) -> Path:
        return self.wurzel / "protokolle"

    @property
    def zustand_datei(self) -> Path:
        return self.wurzel / "zustand.json"

    @property
    def betrieb_ordner(self) -> Path:
        return self.wurzel / "betrieb"

    @property
    def betrieb_protokolle(self) -> Path:
        return self.protokolle / "betrieb"

    @property
    def betrieb_zustand_datei(self) -> Path:
        return self.wurzel / "betrieb.json"

    @property
    def einstellungsdatei(self) -> Path:
        return self.wurzel / "einstellungen.toml"

    @property
    def schluesseldatei(self) -> Path:
        return self.wurzel / "schluessel"

    def anlegen(self) -> None:
        for o in (self.wurzel, self.dienste_ordner, self.protokolle, self.betrieb_ordner):
            o.mkdir(parents=True, exist_ok=True)
        self.wurzel.chmod(0o700)
        if not self.einstellungsdatei.exists():
            self.einstellungen_speichern(Einstellungen())

    def einstellungen(self) -> Einstellungen:
        try:
            with open(self.einstellungsdatei, "rb") as f:
                return Einstellungen.model_validate(tomllib.load(f))
        except FileNotFoundError:
            return Einstellungen()

    def einstellungen_speichern(self, e: Einstellungen) -> None:
        neu = self.einstellungsdatei.with_suffix(".toml.neu")
        neu.write_text(toml_schreiben(e), encoding="utf-8")
        neu.replace(self.einstellungsdatei)

    def schluessel(self) -> str | None:
        try:
            return self.schluesseldatei.read_text(encoding="utf-8").strip() or None
        except FileNotFoundError:
            return None

    def schluessel_speichern(self, schluessel: str | None) -> None:
        if not schluessel:
            self.schluesseldatei.unlink(missing_ok=True)
            return
        fd = os.open(self.schluesseldatei, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(schluessel)

    def betrieb(self) -> tuple[list[Vorlage], list[Ladefehler]]:
        """Steuerprogramme unter betrieb/ (Vorlagen des Dienstkerns, ohne Fähigkeiten)."""
        return dateien_lesen(self.betrieb_ordner, Vorlage)

    def dienste(self) -> tuple[list[DienstVorlage], list[Ladefehler]]:
        """Alle Dienstdateien; fehlerhafte werden gemeldet und ausgelassen, nie geraten."""
        return dateien_lesen(self.dienste_ordner, DienstVorlage)
