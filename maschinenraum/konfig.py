"""Der Ordner des Maschinenraums: ein Ort je Rechner für alles, was er verwaltet.

    <ordner>/einstellungen.toml   Oberfläche, Messung, Neustartregeln, Schlaf, optional die Leitstelle
    <ordner>/schluessel           Schlüssel für die Leitstelle (nur für den Benutzer lesbar), wenn verbunden
    <ordner>/dienste/<name>.toml  je Dienst eine Datei; der Dateiname ist die Kennung
    <ordner>/betrieb/<name>.toml  Steuerprogramme des Rechners (etwa das Stellwerk): starten, anhalten, öffnen;
                                  keine KI, nie an die Leitstelle gemeldet. Das Programm trägt sich bei seiner Installation ein.
    <ordner>/protokolle/          Ausgabe des Maschinenraums und je Dienst eine Datei
    <ordner>/zustand.json         Sollzustand je Dienst (übersteht Neustarts) und gemessene Höchstwerte
    <ordner>/modelle/             Modellablage des Rechners: alle Modelldateien der Dienste an einem Ort (nach Art geordnet,
                                  dazu huggingface/ als Zwischenspeicher von Hugging Face); jeder Dienst findet sie über
                                  $MASCHINENRAUM_MODELLE und HF_HUB_CACHE

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
from pydantic import BaseModel, Field, field_validator, model_validator

from .protokoll import Eignung, Faehigkeit

STANDARD_ORDNER = "~/Maschinenraum"
MODELLE_VARIABLE = "MASCHINENRAUM_MODELLE"
HF_ORDNER = "huggingface"


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


class Schlaf(BaseModel):
    """Schlaf des Rechners (macOS): der Leitstelle melden und, solange sie über ihn rechnen lässt, aufschieben."""

    melden: bool = Field(default=True, description="beim Einschlafen der Leitstelle melden; Aufträge warten dann in den Apps, "
                                                     "bis der Rechner wach ist, statt zu scheitern")
    leerlauf_aufschieben: bool = Field(default=True, description="solange die Leitstelle über diesen Rechner rechnen lässt, schläft er "
                                                                   "nicht nach Leerlauf ein; Deckel, Menü und Ein-Taste wirken weiter")


class Nachbar(BaseModel):
    modell_laeufer: str | None = Field(default="http://127.0.0.1:1234", description="Modell-Läufer auf diesem Rechner: angezeigt und "
                                       "beobachtet (Zugriffe am Leitstand vorbei, Last seiner Prozesse); leer: keiner")


class Beobachtung(BaseModel):
    """Was die Leitstelle über diesen Rechner zum Entscheiden braucht, im eigenen Takt: Zugriffe am Leitstand vorbei
    (Verbindungen zum Modell-Läufer, die nicht vom Maschinenraum selbst kommen, und Programme mit viel Speicher außerhalb von
    Diensten und Läufer) und die Last (je Prozess des Läufers, die Fremdlast des Rechners und der Docker-Rechner mit seinen
    Containern). Dazu, woran ein Arbeiter des Läufers zu erkennen ist und wie er auf Befehl der Leitstelle beendet wird."""

    aktiv: bool = Field(default=True, description="der Leitstelle melden, was an ihr vorbei auf Modelle dieses Rechners zugreift und wie "
                                                   "belastet Läufer und Rechner sind")
    takt_s: float = Field(default=15, ge=5, le=600, description="Abstand der Beobachtungen; eigener Takt, weil eine Messung dauert")
    docker: bool = Field(default=True, description="mit der Last die des Docker-Rechners melden: Kerne, Speicher und je Container "
                                                    "Prozessorlast und Speicher (nur lesend über die Befehlszeile von Docker)")
    schwelle_gb: float = Field(default=2.0, ge=0.5, le=512, description="ab so viel Speicher gilt ein Programm als möglicher Modellträger")
    ausnahmen: list[str] = Field(default_factory=lambda: ["com.apple.Virtualization", "Google Chrome", "Brave Browser", "Safari.app", "firefox",
                                                          "Xcode", "WindowServer", "Claude.app", "Code Helper", "JetBrains", "Docker"],
                                 description="Teile der Befehlszeile, die nie als Speicherverbraucher gemeldet werden (Browser, virtuelle Maschinen)")
    modelldateien: list[str] = Field(default_factory=lambda: [".gguf", ".safetensors"], min_length=1,
                                     description="Endungen von Modelldateien: ein Prozess des Läufers, der eine davon offen hat, ist ein "
                                                 "Arbeiter (eine geladene Instanz)")
    arbeiter_bibliotheken: list[str] = Field(default_factory=lambda: ["/extensions/backends/"],
                                             description="Ordnerteile im Pfad von Bibliotheken eines Rechenwerks: ein Prozess des Läufers, "
                                                         "der eine Bibliothek daraus geladen hat, ist ein Arbeiter, auch ohne offene "
                                                         "Modelldatei (ein Rechenwerk, das das Modell ganz in den Speicher liest)")
    anhaltezeit_s: float = Field(default=10, ge=1, le=120, description="so lange darf ein Arbeiter des Läufers nach der Bitte um Beenden "
                                                                     "aufräumen, dann wird er hart beendet")

    @field_validator("modelldateien")
    @classmethod
    def _endungen(cls, werte: list[str]) -> list[str]:
        """Nur echte Endungen (".gguf"): eine leere passte auf jede Datei, und jeder Prozess des Läufers wäre ein Arbeiter."""
        falsch = [w for w in werte if len(w) < 2 or not w.startswith(".") or w.strip() != w]
        if falsch:
            raise ValueError(f"Endungen mit Punkt und ohne Leerzeichen (.gguf, .safetensors), nicht {', '.join(repr(w) for w in falsch)}")
        return werte

    @field_validator("arbeiter_bibliotheken")
    @classmethod
    def _ordnerteile(cls, werte: list[str]) -> list[str]:
        """Nur Ordnerteile mit Schrägstrich vorn und hinten ("/extensions/backends/"): ein leerer Teil oder "/" passte auf jede
        Bibliothek, und jeder Prozess des Läufers wäre ein Arbeiter."""
        falsch = [w for w in werte if len(w) < 3 or not (w.startswith("/") and w.endswith("/")) or w.strip() != w or "//" in w]
        if falsch:
            raise ValueError(f"Ordnerteile mit Schrägstrich vorn und hinten (/extensions/backends/), nicht {', '.join(repr(w) for w in falsch)}")
        return werte


class Einstellungen(BaseModel):
    name: str | None = Field(default=None, description="Anzeigename des Rechners; sonst der Rechnername")
    oberflaeche: Oberflaeche = Field(default_factory=Oberflaeche)
    leitstelle: Leitstelle = Field(default_factory=Leitstelle)
    durchleitung: Durchleitung = Field(default_factory=Durchleitung)
    messung: Messung = Field(default_factory=Messung)
    neustart: Neustartregeln = Field(default_factory=Neustartregeln)
    nachbar: Nachbar = Field(default_factory=Nachbar)
    schlaf: Schlaf = Field(default_factory=Schlaf)
    beobachtung: Beobachtung = Field(default_factory=Beobachtung)


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
PORT_VARIABLE = "MASCHINENRAUM_PORT"   # Umgebung jeder Instanz: ihr Port
PORT_PLATZHALTER = "$" + PORT_VARIABLE
INSTANZ_PORT_ABSTAND = 100             # Instanz n läuft auf port + 100 (n-1)

class DienstVorlage(Vorlage):
    """Eine Datei unter dienste/: ein KI-Dienst mit mindestens einer Fähigkeit, die die Leitstelle vermittelt.
    Was keine Fähigkeit hat (Webapps, ihre Datenbanken, Docker), gehört ins Stellwerk, nicht hierher."""

    faehigkeiten: set[Faehigkeit] = Field(min_length=1)
    leitstelle_anhalten: bool = Field(default=True, description="die Leitstelle darf ihn anhalten, um Speicher freizumachen; nein: nur von Hand")
    plaetze: int = Field(default=1, ge=1, le=64, description="so viele Anfragen nimmt der Dienst gleichzeitig an; die Leitstelle teilt danach zu")
    instanzen: int = Field(default=1, ge=1, le=8, description="so viele Prozesse darf die Leitstelle bei Andrang starten; Instanz n "
                           "läuft auf port + 100 (n-1), ihren Port nimmt der befehl als $MASCHINENRAUM_PORT")
    eignung: list[Eignung] = Field(default_factory=list, description="wofür er besonders taugt (denken, programmieren, lange_texte, schnell, gruendlich); geht mit der beschreibung als Selbstauskunft an die Leitstelle")
    sprachen: list[str] = Field(default_factory=list, description="Sprachen, die er kann (ISO 639-1, etwa de, en); leer heißt nicht angegeben")

    @model_validator(mode="after")
    def _instanzen_brauchen_port(self) -> "DienstVorlage":
        if self.instanzen > 1:
            if self.port is None or not any(PORT_PLATZHALTER in teil or "${" + PORT_VARIABLE + "}" in teil for teil in self.befehl):
                raise ValueError(f"instanzen > 1 braucht port und ${PORT_VARIABLE} im befehl (jede Instanz hat ihren eigenen Port)")
            if "." in self.kennung:
                raise ValueError("instanzen > 1 nur für Dienste ohne Punkt in der Kennung (Instanzen heißen <kennung>.<n>)")
        return self

    @field_validator("sprachen")
    @classmethod
    def _sprachkuerzel(cls, werte: list[str]) -> list[str]:
        falsch = [w for w in werte if not (len(w) == 2 and w.isascii() and w.isalpha() and w.islower())]
        if falsch:
            raise ValueError(f"Sprachen als zwei Kleinbuchstaben nach ISO 639-1 (de, en, fr), nicht {', '.join(falsch)}")
        return werte

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
    def modelle(self) -> Path:
        return self.wurzel / "modelle"

    @property
    def einstellungsdatei(self) -> Path:
        return self.wurzel / "einstellungen.toml"

    @property
    def schluesseldatei(self) -> Path:
        return self.wurzel / "schluessel"

    def anlegen(self) -> None:
        for o in (self.wurzel, self.dienste_ordner, self.protokolle, self.betrieb_ordner, self.modelle):
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
