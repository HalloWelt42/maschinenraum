// Neue Fassung des Maschinenraums: nie ein hartes Neuladen verlangen (Muster aus Orbit).
// Die Startseite kommt ohne Zwischenspeicher, Skripte und Gestaltung tragen Prüfsummen im Namen. Meldet der Dienst eine
// andere Fassung als die eingebaute, lädt die Seite von selbst neu: in den ersten Sekunden nach dem Start sofort,
// später beim nächsten Seitenwechsel oder wenn das Fenster wieder nach vorn kommt. Nie, solange etwas in Arbeit ist
// (lib/arbeit.svelte.ts); dann wartet sie bis danach. Dazwischen steht ein Band mit Knopf (teile/NeueFassung.svelte).
// Je Fassung des Dienstes nur ein selbsttätiger Versuch (Merker in der Sitzung), damit ein hängender Zwischenspeicher
// keine Schleife auslöst.
import { tick } from 'svelte';
import { api } from './api';
import { arbeit } from './arbeit.svelte';

export const OBERFLAECHE_FASSUNG = __FASSUNG__;
const MERKER = 'maschinenraum.neu_geladen';
const START_FENSTER_MS = 10_000;
const PRUEFEN_MS = 60_000;

export const fassung = $state<{ neu: string | null }>({ neu: null });

export type Anlass = 'start' | 'takt' | 'ortswechsel' | 'sichtbar';

/** Nichts in Arbeit, das ein Neuladen abbräche: kein schreibender Aufruf unterwegs, keine offene Bearbeitung. */
export function ruhig(): boolean {
  return arbeit.ruhig();
}

function erlaubt(neu: string): boolean {
  try {
    if (sessionStorage.getItem(MERKER) === neu) return false;
    sessionStorage.setItem(MERKER, neu);
  } catch {
    // ohne Sitzungsspeicher kein Merker: dann lieber einmal laden als nie
  }
  return true;
}

export function vielleichtNeuLaden(anlass: Anlass): void {
  const neu = fassung.neu;
  if (!neu || anlass === 'takt' || !ruhig()) return;
  if (anlass === 'start' && performance.now() > START_FENSTER_MS) return;
  if (erlaubt(neu)) location.reload();
}

/** Nach einem Seitenwechsel: erst prüfen, wenn die neue Seite steht; die verlassene hat ihre Bearbeitung dann abgemeldet. */
export function nachOrtswechsel(): void {
  void tick().then(() => vielleichtNeuLaden('ortswechsel'));
}

/** Ob Fassung `a` neuer ist als `b` (Haupt-, Neben-, Fehlernummer). Läuft der Dienst noch mit einer älteren als die
 *  ausgelieferte Oberfläche (eingespielt, aber noch nicht neu gestartet), gibt es nichts nachzuladen. */
export function neuer(a: string, b: string): boolean {
  const teile = (v: string) => v.split('.').map((x) => parseInt(x, 10) || 0);
  const [x, y] = [teile(a), teile(b)];
  for (let i = 0; i < Math.max(x.length, y.length); i++) {
    if ((x[i] ?? 0) !== (y[i] ?? 0)) return (x[i] ?? 0) > (y[i] ?? 0);
  }
  return false;
}

export async function fassungPruefen(anlass: Anlass): Promise<void> {
  try {
    const { version } = await api.version();
    fassung.neu = neuer(version, OBERFLAECHE_FASSUNG) ? version : null;
  } catch {
    return; // ohne Verbindung meldet die Seite, dass der Maschinenraum nicht antwortet
  }
  vielleichtNeuLaden(anlass);
}

function sichtbar(): void {
  if (document.visibilityState === 'visible') void fassungPruefen('sichtbar');
}

/** Einmal beim Start der Oberfläche; gibt das Aufräumen zurück. */
export function fassungVerfolgen(): () => void {
  void fassungPruefen('start');
  const takt = setInterval(() => void fassungPruefen('takt'), PRUEFEN_MS);
  document.addEventListener('visibilitychange', sichtbar);
  return () => {
    clearInterval(takt);
    document.removeEventListener('visibilitychange', sichtbar);
  };
}
