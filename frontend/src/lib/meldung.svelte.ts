// Kurze Rückmeldungen unten rechts (statt Browser-Dialogen). Fehler bleiben länger stehen.
import { ApiFehler } from './api';

export interface Rueckmeldung { nummer: number; text: string; art: 'erfolg' | 'fehler' | 'hinweis' }

class Meldungen {
  liste = $state<Rueckmeldung[]>([]);
  private zaehler = 0;

  zeigen(text: string, art: Rueckmeldung['art'] = 'erfolg'): void {
    const nummer = ++this.zaehler;
    this.liste = [...this.liste, { nummer, text, art }].slice(-4);
    setTimeout(() => this.weg(nummer), art === 'fehler' ? 9000 : 4000);
  }

  fehler(f: unknown): void {
    this.zeigen(f instanceof ApiFehler ? f.begruendung : f instanceof Error ? f.message : String(f), 'fehler');
  }

  weg(nummer: number): void {
    this.liste = this.liste.filter((m) => m.nummer !== nummer);
  }
}

export const meldungen = new Meldungen();

/** Führt eine Aktion aus und meldet Erfolg oder Fehler; gibt das Ergebnis oder undefined zurück. */
export async function tun<T>(aktion: () => Promise<T>, erfolg?: string): Promise<T | undefined> {
  try {
    const ergebnis = await aktion();
    if (erfolg) meldungen.zeigen(erfolg);
    return ergebnis;
  } catch (f) {
    meldungen.fehler(f);
    return undefined;
  }
}
