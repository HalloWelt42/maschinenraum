// Ansicht je Gerät: Thema und Schriftstufe, gemerkt im Browser. Blauart wie in der Leitstelle,
// fest in index.html.

export type Thema = 'dunkel' | 'hell';
export type Schrift = 'normal' | 'gross' | 'sehr-gross';

function lesen<T extends string>(schluessel: string, erlaubt: readonly T[], vorgabe: T): T {
  try {
    const wert = localStorage.getItem(`maschinenraum-${schluessel}`);
    return erlaubt.includes(wert as T) ? (wert as T) : vorgabe;
  } catch {
    return vorgabe;
  }
}

function merken(schluessel: string, wert: string): void {
  try {
    localStorage.setItem(`maschinenraum-${schluessel}`, wert);
  } catch {
    /* privater Modus: dann gilt die Wahl nur bis zum Neuladen */
  }
}

class Ansicht {
  thema = $state<Thema>(lesen('thema', ['dunkel', 'hell'] as const, 'dunkel'));
  schrift = $state<Schrift>(lesen('schrift', ['normal', 'gross', 'sehr-gross'] as const, 'normal'));

  setzeThema(t: Thema): void {
    this.thema = t;
    merken('thema', t);
    ansichtAnwenden();
  }

  setzeSchrift(s: Schrift): void {
    this.schrift = s;
    merken('schrift', s);
    ansichtAnwenden();
  }
}

export const ansicht = new Ansicht();

export function ansichtAnwenden(): void {
  document.documentElement.dataset.theme = ansicht.thema;
  document.documentElement.dataset.schrift = ansicht.schrift;
}
