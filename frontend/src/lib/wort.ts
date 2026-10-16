// Wörter, Symbole und Farben zu den Schlüsseln der Schnittstelle. Schlüssel werden nie gedruckt.
import type { Faehigkeit, Prozesszustand, Verbindung } from './typen.gen';

export const FAEHIGKEIT: Record<Faehigkeit, { wort: string; symbol: string; klasse: string; farbe: string }> = {
  text: { wort: 'Text', symbol: 'fa-comment-dots', klasse: 'text', farbe: 'var(--mr-himmel)' },
  einbettung: { wort: 'Einbettung', symbol: 'fa-diagram-project', klasse: 'einbettung', farbe: 'var(--mr-petrol)' },
  uebersetzen: { wort: 'Übersetzen', symbol: 'fa-language', klasse: 'uebersetzen', farbe: 'var(--mr-tuerkis)' },
  hoeren: { wort: 'Hören', symbol: 'fa-ear-listen', klasse: 'hoeren', farbe: 'var(--mr-minze)' },
  bild_beschreiben: { wort: 'Bild beschreiben', symbol: 'fa-image', klasse: 'bild', farbe: 'var(--mr-flieder)' },
  bild_erzeugen: { wort: 'Bild erzeugen', symbol: 'fa-palette', klasse: 'bild', farbe: 'var(--mr-flieder)' },
  stimme: { wort: 'Stimme', symbol: 'fa-microphone-lines', klasse: 'stimme', farbe: 'var(--mr-rose)' },
  stimme_klonen: { wort: 'Stimmklon', symbol: 'fa-clone', klasse: 'stimme', farbe: 'var(--mr-rose)' },
  sprecher_erkennen: { wort: 'Sprecher erkennen', symbol: 'fa-fingerprint', klasse: 'hoeren', farbe: 'var(--mr-minze)' },
  sprecher_trennen: { wort: 'Sprecher trennen', symbol: 'fa-people-arrows', klasse: 'hoeren', farbe: 'var(--mr-minze)' },
  musik: { wort: 'Musik', symbol: 'fa-music', klasse: 'musik', farbe: 'var(--mr-violett)' },
  werkzeug: { wort: 'Werkzeuge', symbol: 'fa-screwdriver-wrench', klasse: 'werkzeug', farbe: 'var(--mr-sand)' },
};

/** Farbe eines Dienstes in der Speicheranzeige: nach seiner ersten Fähigkeit, sonst neutral */
export const dienstfarbe = (f: Faehigkeit[]): string => (f.length ? FAEHIGKEIT[f[0]].farbe : 'var(--mr-sand)');

export const ZUSTAND: Record<Prozesszustand, { wort: string; klasse: string; symbol: string }> = {
  aus: { wort: 'Aus', klasse: 'aus', symbol: 'fa-power-off' },
  startet: { wort: 'Startet', klasse: 'wartet', symbol: 'fa-circle-notch fa-spin' },
  laeuft: { wort: 'Läuft', klasse: 'fertig', symbol: 'fa-circle' },
  stoppt: { wort: 'Hält an', klasse: 'auslaufend', symbol: 'fa-circle-notch fa-spin' },
  gestoert: { wort: 'Gestört', klasse: 'fehler', symbol: 'fa-triangle-exclamation' },
};

/** klasse: Zustandsmarke; lage: Klasse der Kopfanzeige (ruhig, angespannt, engpass wie in der Leitstelle) */
export const VERBINDUNG: Record<Verbindung, { wort: string; klasse: string; lage: string }> = {
  aus: { wort: 'Ohne Leitstelle', klasse: 'aus', lage: 'aus' },
  ohne_schluessel: { wort: 'Schlüssel fehlt', klasse: 'auslaufend', lage: 'angespannt' },
  verbindet: { wort: 'Verbindet', klasse: 'wartet', lage: 'angespannt' },
  verbunden: { wort: 'Mit Leitstelle verbunden', klasse: 'fertig', lage: 'ruhig' },
  abgewiesen: { wort: 'Von der Leitstelle abgewiesen', klasse: 'fehler', lage: 'engpass' },
  nicht_erreichbar: { wort: 'Leitstelle nicht erreichbar', klasse: 'auslaufend', lage: 'angespannt' },
};
