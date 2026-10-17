// Weg durch die Seiten: echte Pfade (/dienste, /speicher ...); der Maschinenraum liefert für jeden Pfad index.html.
// Ein Seitenwechsel ist der ruhige Moment für eine neue Fassung (die Adresse steht schon, das Neuladen landet dort).
import { nachOrtswechsel } from './fassung.svelte';

export type Seite = 'uebersicht' | 'dienste' | 'speicher' | 'leitstelle' | 'protokoll' | 'ordner';

const PFADE: Record<Seite, string> = {
  uebersicht: '/', dienste: '/dienste', speicher: '/speicher', leitstelle: '/leitstelle', protokoll: '/protokoll', ordner: '/ordner',
};

function lesen(): { seite: Seite; teil: string | null } {
  const [, erster, zweiter] = location.pathname.split('/');
  const seite = (Object.entries(PFADE).find(([, p]) => p === `/${erster ?? ''}`)?.[0] ?? 'uebersicht') as Seite;
  return { seite, teil: zweiter ? decodeURIComponent(zweiter) : null };
}

class Weg {
  seite = $state<Seite>(lesen().seite);
  /** zweiter Pfadteil, zum Beispiel der Dienst, dessen Protokoll offen ist */
  teil = $state<string | null>(lesen().teil);

  constructor() {
    window.addEventListener('popstate', () => {
      const w = lesen();
      this.seite = w.seite;
      this.teil = w.teil;
      nachOrtswechsel();
    });
  }

  pfad(seite: Seite, teil?: string | null): string {
    return PFADE[seite] + (teil ? `/${encodeURIComponent(teil)}` : '');
  }

  gehe(seite: Seite, teil: string | null = null, ersetzen = false): void {
    const ziel = this.pfad(seite, teil);
    const wechsel = ziel !== location.pathname;
    if (wechsel) (ersetzen ? history.replaceState : history.pushState).call(history, null, '', ziel);
    this.seite = seite;
    this.teil = teil;
    if (wechsel) nachOrtswechsel();
  }

  /** Für <a href>: normale Klicks bleiben in der Oberfläche, Mittelklick öffnet einen neuen Reiter */
  klick(e: MouseEvent, seite: Seite, teil: string | null = null): void {
    if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey) return;
    e.preventDefault();
    this.gehe(seite, teil);
  }
}

export const weg = new Weg();
