"""Nutzlasten der Knoten-Agenten (PROTOKOLL.md Abschnitt 4.2).

Spiegel von `backend/leitstelle/protokoll/knoten.py` in der Leitstelle; der Maschinenraum spielt dort die Rolle des
Knoten-Agenten und hängt nicht von ihr ab. Ein Test in der Leitstelle
hält beide Seiten deckungsgleich.
Fehlende Messwerte bleiben None (weggelassen, nicht genullt).
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Faehigkeit(str, Enum):
    TEXT = "text"
    EINBETTUNG = "einbettung"
    UEBERSETZEN = "uebersetzen"
    HOEREN = "hoeren"
    BILD_BESCHREIBEN = "bild_beschreiben"
    BILD_ERZEUGEN = "bild_erzeugen"
    STIMME = "stimme"
    STIMME_KLONEN = "stimme_klonen"
    SPRECHER_ERKENNEN = "sprecher_erkennen"
    SPRECHER_TRENNEN = "sprecher_trennen"
    MUSIK = "musik"
    WERKZEUG = "werkzeug"
    TON = "ton"                       # Tonarbeit ohne Modell (wandeln, messen, mischen)


class Eignung(str, Enum):
    """Wofür ein Modell oder Dienst besonders taugt, über seine Fähigkeiten hinaus (Selbstauskunft, PROTOKOLL 4.8 der Leitstelle)."""

    DENKEN = "denken"                 # schließt schrittweise; für schwierige Fragen, dauert länger
    PROGRAMMIEREN = "programmieren"
    LANGE_TEXTE = "lange_texte"       # großer Kontext (ab 100 000 Token)
    SCHNELL = "schnell"               # kurze Wartezeit, auch auf Kosten der Tiefe
    GRUENDLICH = "gruendlich"         # beste Ergebnisse, auch auf Kosten der Zeit


class KnotenAnmeldung(BaseModel):
    """`knoten.anmelden`: wer der Agent ist und was er messen kann."""

    name: str
    betriebssystem: str
    architektur: str
    speicher_gb: float
    agent_version: str
    messwege: list[str] = Field(default_factory=list)
    durchleitung_port: int | None = None    # Port, über den die Leitstelle Anfragen an die Dienste durchreicht


class Messwerte(BaseModel):
    """`knoten.messwerte`: im Takt des Agenten."""

    speicher_gesamt_gb: float
    speicher_belegt_gb: float
    swap_belegt_gb: float | None = None
    swap_gesamt_gb: float | None = None
    cpu_prozent: float | None = None
    last_1m: float | None = None
    platte_frei_gb: float | None = None
    grafik_prozent: float | None = None
    temperatur_c: float | None = None
    leistung_w: float | None = None


class Prozesszustand(str, Enum):
    AUS = "aus"
    STARTET = "startet"
    LAEUFT = "laeuft"
    STOPPT = "stoppt"
    GESTOERT = "gestoert"


class Selbstauskunft(BaseModel):
    """Was ein Dienst über sich oder sein Modell sagt (PROTOKOLL 4.8): wofür er gemacht ist. Leer heißt: sagt nichts."""

    zweck: str = ""                                          # ein Satz: wofür gemacht oder optimiert
    eignung: list[Eignung] = Field(default_factory=list)
    sprachen: list[str] = Field(default_factory=list)        # ISO 639-1; leer: nicht angegeben
    quantisierung: str | None = None                         # wie der Dienst sie nennt, etwa 4bit, FP8


class ProzessBericht(BaseModel):
    """Ein Dienst, den der Agent verwaltet (eine Datei in seinem Ordner `dienste/`)."""

    kennung: str
    name: str
    faehigkeiten: set[Faehigkeit]
    port: int | None = None
    zustand: Prozesszustand
    fremd: bool = False                 # läuft, aber nicht vom Agenten gestartet
    gb_jetzt: float | None = None       # gemessen, solange er läuft; sonst None
    bedarf_gb: float                    # was er bei der Arbeit braucht (80-%-Wert seiner Arbeitsspitzen, mindestens die Schätzung)
    aktiv: bool = False                 # arbeitet gerade (Prozessorlast über der Schwelle des Dienstes)
    anhalten_erlaubt: bool = True       # darf die Leitstelle ihn anhalten, um Speicher freizumachen
    plaetze: int = 1                    # so viele Anfragen nimmt er gleichzeitig an
    selbstauskunft: Selbstauskunft = Field(default_factory=Selbstauskunft)   # aus seiner Dienstdatei
    instanz_von: str | None = None      # weitere Instanz dieses Dienstes (Kennung <grund>.<n>); None: Grundinstanz
    instanzen: int = 1                  # so viele Instanzen darf die Leitstelle höchstens starten
    meldung: str = ""


class Dienstliste(BaseModel):
    """`knoten.dienste`: vollständiger Stand aller verwalteten Dienste, bei jeder Änderung."""

    dienste: list[ProzessBericht] = Field(default_factory=list)


class Befehlsart(str, Enum):
    DIENST_STARTEN = "dienst_starten"
    DIENST_ANHALTEN = "dienst_anhalten"
    LAEUFER_PROZESS_BEENDEN = "laeufer_prozess_beenden"   # ziel: pid eines Arbeiters des Modell-Läufers; nie der Hauptprozess


class Befehl(BaseModel):
    """`knoten.befehl`: begrenzt auf die Dienstverwaltung und das Beenden eines Arbeiters des Modell-Läufers."""

    befehl: Befehlsart
    ziel: str


class BefehlErgebnis(BaseModel):
    """`knoten.befehl_ergebnis`, mit `bezug` auf den Befehl."""

    befehl: Befehlsart
    ziel: str
    erfolg: bool
    meldung: str = ""


class Schlafgrund(str, Enum):
    LEERLAUF = "leerlauf"             # nach der Leerlaufzeit des Rechners
    ANGEFORDERT = "angefordert"       # von Hand: Menü, Deckel, Ein-Taste, pmset sleepnow


class KnotenSchlaeft(BaseModel):
    """`knoten.schlaeft`: der Rechner schläft gleich ein. Die Leitstelle antwortet mit `knoten.schlaf_vermerkt` (mit `bezug`)
    und wartet, bis er wach ist; danach schließt der Agent die Verbindung mit dem Grund `schlaeft`."""

    grund: Schlafgrund
    meldung: str = ""


class Fremdart(str, Enum):
    LAEUFER = "laeufer"               # Verbindung zum Modell-Läufer dieses Rechners, die nicht vom Maschinenraum selbst kommt
    SPEICHER = "speicher"             # Programm mit viel Speicher, das weder Dienst noch Läufer ist (etwa ein Modell im eigenen Prozess)


class Fremdzugriff(BaseModel):
    """Ein Zugriff am Leitstand vorbei, so wie der Agent ihn sieht."""

    art: Fremdart
    wer: str                          # Programmname auf diesem Rechner oder Adresse im Netz
    pid: int | None = None            # nur auf diesem Rechner
    befehl: str = ""                  # Befehlszeile, gekürzt
    ordner: str = ""                  # Arbeitsordner des Programms (verrät meist das Projekt)
    verbindungen: int = 0             # bei laeufer: so viele offene Verbindungen
    gb: float | None = None           # bei speicher: gemessener Speicher
    vom_rechner_der_leitstelle: bool = False   # Adresse im Netz ist die des Rechners, auf dem die Leitstelle läuft


class Fremdzugriffe(BaseModel):
    """`knoten.fremde`: was am Leitstand vorbei auf Modelle dieses Rechners zugreift, im Takt der Messung; leer heißt
    nichts gefunden. `beobachtet` ist falsch, wenn der Rechner das nicht messen kann (dann ist die Liste ohne Aussage)."""

    beobachtet: bool = True
    zugriffe: list[Fremdzugriff] = Field(default_factory=list)


class Laeuferrolle(str, Enum):
    HAUPT = "haupt"                   # lauscht am Port des Läufers; wird nie beendet
    ARBEITER = "arbeiter"             # hat eine Modelldatei offen oder eine Bibliothek eines Rechenwerks geladen: eine geladene Instanz
    SONSTIG = "sonstig"               # alles andere im Baum des Läufers, etwa das Fenster


class Laeuferprozess(BaseModel):
    """Ein Prozess des Modell-Läufers (der Prozess am Läufer-Port samt Nachfahren)."""

    pid: int
    name: str                         # Programmname wie bei der Beobachtung
    rolle: Laeuferrolle
    modelldatei: str = ""             # bei arbeiter: die offene Modelldatei (Pfad, ~ für den Heimordner); sonst und bei einem Arbeiter ohne offene Modelldatei leer
    cpu_prozent: float | None = None  # Rechenzeit seit der letzten Messung je Wandzeit, in Prozent eines Kerns; leer beim ersten Mal und bei neuer pid
    gb: float | None = None           # Speicher wie bei den Diensten


class KnotenLast(BaseModel):
    """`knoten.last`: Last des Modell-Läufers je Prozess und die Fremdlast des Rechners, im Takt der Beobachtung.
    Zeitbasiert (Rechenzeit je Wandzeit), nicht mit `cpu_prozent` der Messwerte zu mischen. `gemessen` ist falsch ohne
    lsof oder ohne Läufer-Port; dann sagt `laeufer` nichts (statt "keine Prozesse")."""

    gemessen: bool = True
    kerne: int                        # logische Kerne des Rechners
    laeufer: list[Laeuferprozess] = Field(default_factory=list)
    fremd_prozent: float | None = None   # Last ohne Läufer und ohne Dienste des Maschinenraums, Anteil aller Kerne (0 bis 100); leer beim ersten Mal
