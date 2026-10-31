// Erzeugt aus den Pydantic-Modellen des Maschinenraums (npm run typen). Nicht von Hand ändern.

/**
 * This interface was referenced by `Maschinenraum`'s JSON-Schema
 * via the `definition` "Faehigkeit".
 */
export type Faehigkeit =
  | 'text'
  | 'einbettung'
  | 'uebersetzen'
  | 'hoeren'
  | 'bild_beschreiben'
  | 'bild_erzeugen'
  | 'stimme'
  | 'stimme_klonen'
  | 'sprecher_erkennen'
  | 'sprecher_trennen'
  | 'musik'
  | 'werkzeug'
  | 'ton';
/**
 * This interface was referenced by `Maschinenraum`'s JSON-Schema
 * via the `definition` "Prozesszustand".
 */
export type Prozesszustand = 'aus' | 'startet' | 'laeuft' | 'stoppt' | 'gestoert';
/**
 * This interface was referenced by `Maschinenraum`'s JSON-Schema
 * via the `definition` "Soll".
 */
export type Soll = 'laeuft' | 'aus';
/**
 * This interface was referenced by `Maschinenraum`'s JSON-Schema
 * via the `definition` "Zustand".
 */
export type Zustand = 'aus' | 'startet' | 'laeuft' | 'stoppt' | 'gestoert';
/**
 * This interface was referenced by `Maschinenraum`'s JSON-Schema
 * via the `definition` "Verbindung".
 */
export type Verbindung = 'aus' | 'ohne_schluessel' | 'verbindet' | 'verbunden' | 'abgewiesen' | 'nicht_erreichbar' | 'schlaeft';
/**
 * This interface was referenced by `Maschinenraum`'s JSON-Schema
 * via the `definition` "Befehlsart".
 */
export type Befehlsart = 'dienst_starten' | 'dienst_anhalten' | 'laeufer_prozess_beenden';

export interface Maschinenraum {
  Stand?: Stand;
  Fassung?: Fassung;
  BefehlErgebnis?: BefehlErgebnis;
  Ergebnis?: Ergebnis;
  Protokollauszug?: Protokollauszug;
  LeitstellenDaten?: LeitstellenDaten;
}
/**
 * This interface was referenced by `Maschinenraum`'s JSON-Schema
 * via the `definition` "Stand".
 */
export interface Stand {
  version: string;
  rechner: string;
  zeit: number;
  ordner: string;
  einstellungen: Einstellungen;
  messwerte: Messwerte | null;
  dienste: DienstAnsicht[];
  betrieb: BetriebAnsicht[];
  ladefehler: Ladefehler[];
  leitstelle: LeitstellenStand;
  nachbar: NachbarStand;
}
/**
 * This interface was referenced by `Maschinenraum`'s JSON-Schema
 * via the `definition` "Einstellungen".
 */
export interface Einstellungen {
  /**
   * Anzeigename des Rechners; sonst der Rechnername
   */
  name: string | null;
  oberflaeche: Oberflaeche;
  leitstelle: Leitstelle;
  durchleitung: Durchleitung;
  messung: Messung;
  neustart: Neustartregeln;
  speicherschutz: Speicherschutz;
  nachbar: Nachbar;
  schlaf: Schlaf;
  beobachtung: Beobachtung;
}
/**
 * This interface was referenced by `Maschinenraum`'s JSON-Schema
 * via the `definition` "Oberflaeche".
 */
export interface Oberflaeche {
  /**
   * nur dieser Rechner; 0.0.0.0 öffnet die Oberfläche fürs Netz
   */
  adresse: string;
  port: number;
}
/**
 * This interface was referenced by `Maschinenraum`'s JSON-Schema
 * via the `definition` "Leitstelle".
 */
export interface Leitstelle {
  /**
   * Basisadresse der Leitstelle, zum Beispiel http://leitstelle:8530; leer: ohne Leitstelle
   */
  adresse: string | null;
  /**
   * längste Pause zwischen Verbindungsversuchen
   */
  wiederverbindung_max_s: number;
}
/**
 * Weg der Leitstelle zu den Diensten (wie bei einem Modell-Läufer); nur mit dem Schlüssel nutzbar.
 *
 * This interface was referenced by `Maschinenraum`'s JSON-Schema
 * via the `definition` "Durchleitung".
 */
export interface Durchleitung {
  /**
   * im Netz erreichbar, damit die Leitstelle Anfragen durchreichen kann
   */
  adresse: string;
  port: number;
}
/**
 * This interface was referenced by `Maschinenraum`'s JSON-Schema
 * via the `definition` "Messung".
 */
export interface Messung {
  /**
   * Abstand der Messungen und der Dienstprüfung
   */
  takt_s: number;
  /**
   * Zusatzmessungen (Grafik, Temperatur, Leistung) über macmon, wenn vorhanden
   */
  macmon: boolean;
}
/**
 * This interface was referenced by `Maschinenraum`'s JSON-Schema
 * via the `definition` "Neustartregeln".
 */
export interface Neustartregeln {
  /**
   * Pausen vor dem 1., 2., 3. Neustart nach einem Absturz
   *
   * @minItems 1
   */
  pausen_s: [number, ...number[]];
  /**
   * Zeitraum, in dem Abstürze gezählt werden
   */
  fenster_s: number;
  /**
   * mehr Abstürze im Zeitraum: der Dienst bleibt aus
   */
  im_fenster: number;
}
/**
 * Harte Grenze je Dienst und Notaus bei knappem Rechner (Speicherwache des Dienstkerns, HELF-85), dazu die Grenze im
 * Prozess selbst: ein Dienst, der sie kennt, scheitert mit einem Fehler statt weiterzuwachsen.
 *
 * This interface was referenced by `Maschinenraum`'s JSON-Schema
 * via the `definition` "Speicherschutz".
 */
export interface Speicherschutz {
  /**
   * Dienste über ihrer Höchstgrenze oder bei knappem Rechner sofort beenden und sperren
   */
  aktiv: boolean;
  /**
   * so oft wird gemessen, solange ein Dienst läuft
   */
  takt_s: number;
  /**
   * Höchstgrenze ohne eigene Angabe: speicher_gb mal diesen Faktor ...
   */
  faktor: number;
  /**
   * ... plus diesen Zuschlag
   */
  zuschlag_gb: number;
  /**
   * darunter (freier Anteil, wie das System ihn nennt) gilt der Rechner als knapp; 0 schaltet diese Prüfung ab
   */
  frei_mindestens_prozent: number;
  /**
   * kritischer Speicherdruck des Systems gilt ebenfalls als knapp
   */
  druck_kritisch: boolean;
  /**
   * ist der Rechner knapp, wird nur ein Dienst beendet, der mindestens so weit über seinem angemeldeten Speicher liegt
   */
  ueberschuss_mindestens_gb: number;
  /**
   * mehr Auslagerung gilt als knapp; 0 schaltet ab
   */
  swap_hoechstens_gb: number;
  /**
   * so viel Auslagerung wird geduldet ...
   */
  swap_geduldet_gb: number;
  /**
   * ... höchstens so lange am Stück (bei Speicherdruck)
   */
  swap_geduldet_s: number;
  /**
   * dauerhafte Auslagerung zählt nur, solange das System dabei Speicherdruck meldet (alte, ruhende Auslagerung baut macOS nur langsam ab)
   */
  swap_dauer_nur_bei_druck: boolean;
  /**
   * wächst die Auslagerung schneller, gilt der Rechner als knapp; 0 schaltet ab
   */
  swap_zuwachs_gb_je_min: number;
  /**
   * über diesen Zeitraum wird der Zuwachs gemessen
   */
  swap_zuwachs_fenster_s: number;
  /**
   * jeder Dienst bekommt seine Grenze beim Start auch selbst: MASCHINENRAUM_SPEICHER_GRENZE_GB, für torch auf der Grafik PYTORCH_MPS_HIGH_WATERMARK_RATIO (Grenze je empfohlener Arbeitsmenge der Grafik) und PYTORCH_MPS_LOW_WATERMARK_RATIO; Einträge der Dienstdatei gehen vor; wirkt beim nächsten Start des Dienstes
   */
  grenze_im_prozess: boolean;
  /**
   * torch räumt seine Puffer ab diesem Anteil der Grenze auf (untere Marke); ohne Angabe erst weit über der Grenze
   */
  aufraeumen_anteil: number;
}
/**
 * This interface was referenced by `Maschinenraum`'s JSON-Schema
 * via the `definition` "Nachbar".
 */
export interface Nachbar {
  /**
   * Modell-Läufer auf diesem Rechner: angezeigt und beobachtet (Zugriffe am Leitstand vorbei, Last seiner Prozesse); leer: keiner
   */
  modell_laeufer: string | null;
  /**
   * Stellwerk auf diesem Rechner: im Takt der Beobachtung gelesen (nur lesend), damit die Prozesse seiner Apps weder als fremder Speicher noch als Fremdlast zählen und ihre Last der Leitstelle gemeldet wird; leer: keins
   */
  stellwerk: string | null;
}
/**
 * Schlaf des Rechners (macOS): der Leitstelle melden und, solange sie über ihn rechnen lässt, aufschieben.
 *
 * This interface was referenced by `Maschinenraum`'s JSON-Schema
 * via the `definition` "Schlaf".
 */
export interface Schlaf {
  /**
   * beim Einschlafen der Leitstelle melden; Aufträge warten dann in den Apps, bis der Rechner wach ist, statt zu scheitern
   */
  melden: boolean;
  /**
   * solange die Leitstelle über diesen Rechner rechnen lässt, schläft er nicht nach Leerlauf ein; Deckel, Menü und Ein-Taste wirken weiter
   */
  leerlauf_aufschieben: boolean;
}
/**
 * Was die Leitstelle über diesen Rechner zum Entscheiden braucht, im eigenen Takt: Zugriffe am Leitstand vorbei
 * (Verbindungen zum Modell-Läufer, die nicht vom Maschinenraum selbst kommen, und Programme mit viel Speicher außerhalb von
 * Diensten und Läufer) und die Last (je Prozess des Läufers, die Fremdlast des Rechners und der Docker-Rechner mit seinen
 * Containern). Dazu, woran ein Arbeiter des Läufers zu erkennen ist und wie er auf Befehl der Leitstelle beendet wird.
 *
 * This interface was referenced by `Maschinenraum`'s JSON-Schema
 * via the `definition` "Beobachtung".
 */
export interface Beobachtung {
  /**
   * der Leitstelle melden, was an ihr vorbei auf Modelle dieses Rechners zugreift und wie belastet Läufer und Rechner sind
   */
  aktiv: boolean;
  /**
   * Abstand der Beobachtungen; eigener Takt, weil eine Messung dauert
   */
  takt_s: number;
  /**
   * mit der Last die des Docker-Rechners melden: Kerne, Speicher und je Container Prozessorlast und Speicher (nur lesend über die Befehlszeile von Docker)
   */
  docker: boolean;
  /**
   * ab so viel Speicher gilt ein Programm als möglicher Modellträger
   */
  schwelle_gb: number;
  /**
   * Teile der Befehlszeile, die nie als Speicherverbraucher gemeldet werden (Browser, virtuelle Maschinen)
   */
  ausnahmen: string[];
  /**
   * Endungen von Modelldateien: ein Prozess des Läufers, der eine davon offen hat, ist ein Arbeiter (eine geladene Instanz)
   *
   * @minItems 1
   */
  modelldateien: [string, ...string[]];
  /**
   * Ordnerteile im Pfad von Bibliotheken eines Rechenwerks: ein Prozess des Läufers, der eine Bibliothek daraus geladen hat, ist ein Arbeiter, auch ohne offene Modelldatei (ein Rechenwerk, das das Modell ganz in den Speicher liest)
   */
  arbeiter_bibliotheken: string[];
  /**
   * so lange darf ein Arbeiter des Läufers nach der Bitte um Beenden aufräumen, dann wird er hart beendet
   */
  anhaltezeit_s: number;
}
/**
 * `knoten.messwerte`: im Takt des Agenten.
 *
 * This interface was referenced by `Maschinenraum`'s JSON-Schema
 * via the `definition` "Messwerte".
 */
export interface Messwerte {
  speicher_gesamt_gb: number;
  speicher_belegt_gb: number;
  swap_belegt_gb: number | null;
  swap_gesamt_gb: number | null;
  cpu_prozent: number | null;
  last_1m: number | null;
  platte_frei_gb: number | null;
  grafik_prozent: number | null;
  temperatur_c: number | null;
  leistung_w: number | null;
}
/**
 * This interface was referenced by `Maschinenraum`'s JSON-Schema
 * via the `definition` "DienstAnsicht".
 */
export interface DienstAnsicht {
  kennung: string;
  name: string;
  beschreibung: string;
  faehigkeiten: Faehigkeit[];
  port: number | null;
  oberflaeche: string | null;
  zustand: Prozesszustand;
  fremd: boolean;
  gb_jetzt: number | null;
  bedarf_gb: number;
  spitze_gb: number | null;
  schaetzung_gb: number;
  grenze_gb: number | null;
  sperre: string | null;
  sperre_seit: string | null;
  aktiv: boolean;
  cpu_prozent: number | null;
  anhalten_erlaubt: boolean;
  soll: Soll | null;
  meldung: string;
  datei: string;
  protokolldatei: string;
  ordner: string;
}
/**
 * Ein Steuerprogramm des Rechners (etwa das Stellwerk): nur starten, anhalten, öffnen; keine KI.
 *
 * This interface was referenced by `Maschinenraum`'s JSON-Schema
 * via the `definition` "BetriebAnsicht".
 */
export interface BetriebAnsicht {
  kennung: string;
  name: string;
  beschreibung: string;
  oberflaeche: string | null;
  zustand: Zustand;
  soll: Soll | null;
  gb_jetzt: number | null;
  meldung: string;
  datei: string;
  protokolldatei: string;
}
/**
 * This interface was referenced by `Maschinenraum`'s JSON-Schema
 * via the `definition` "Ladefehler".
 */
export interface Ladefehler {
  datei: string;
  meldung: string;
}
/**
 * This interface was referenced by `Maschinenraum`'s JSON-Schema
 * via the `definition` "LeitstellenStand".
 */
export interface LeitstellenStand {
  adresse: string | null;
  zustand: Verbindung;
  meldung: string;
  seit: number | null;
  name: string | null;
}
/**
 * This interface was referenced by `Maschinenraum`'s JSON-Schema
 * via the `definition` "NachbarStand".
 */
export interface NachbarStand {
  adresse: string | null;
  erreichbar: boolean;
  modelle: NachbarModell[];
  geladen_gb: number;
}
/**
 * This interface was referenced by `Maschinenraum`'s JSON-Schema
 * via the `definition` "NachbarModell".
 */
export interface NachbarModell {
  name: string;
  gb: number;
  geladen: boolean;
}
/**
 * Fassung des laufenden Programms; die Oberfläche vergleicht sie mit ihrer eingebauten und lädt bei Abweichung neu.
 *
 * This interface was referenced by `Maschinenraum`'s JSON-Schema
 * via the `definition` "Fassung".
 */
export interface Fassung {
  version: string;
}
/**
 * `knoten.befehl_ergebnis`, mit `bezug` auf den Befehl.
 *
 * This interface was referenced by `Maschinenraum`'s JSON-Schema
 * via the `definition` "BefehlErgebnis".
 */
export interface BefehlErgebnis {
  befehl: Befehlsart;
  ziel: string;
  erfolg: boolean;
  meldung: string;
}
/**
 * This interface was referenced by `Maschinenraum`'s JSON-Schema
 * via the `definition` "Ergebnis".
 */
export interface Ergebnis {
  ziel: string;
  erfolg: boolean;
  meldung: string;
}
/**
 * This interface was referenced by `Maschinenraum`'s JSON-Schema
 * via the `definition` "Protokollauszug".
 */
export interface Protokollauszug {
  datei: string;
  zeilen: string[];
}
/**
 * This interface was referenced by `Maschinenraum`'s JSON-Schema
 * via the `definition` "LeitstellenDaten".
 */
export interface LeitstellenDaten {
  /**
   * leer: ohne Leitstelle
   */
  adresse?: string | null;
  /**
   * None: unverändert; leer: entfernen
   */
  schluessel?: string | null;
}
