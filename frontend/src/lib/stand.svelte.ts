// Stand des Maschinenraums, alle zwei Sekunden neu (nur solange das Fenster sichtbar ist).
// Nach einer Aktion holt `jetzt()` den Stand sofort.
import { api } from './api';
import type { Stand } from './typen.gen';

const TAKT_MS = 2000;

class Lage {
  stand = $state<Stand | null>(null);
  erreichbar = $state(true);
  private zeitgeber: ReturnType<typeof setTimeout> | null = null;

  async jetzt(): Promise<void> {
    try {
      this.stand = await api.stand();
      this.erreichbar = true;
    } catch {
      this.erreichbar = false;
    }
  }

  starten(): void {
    const runde = async () => {
      if (document.visibilityState === 'visible') await this.jetzt();
      this.zeitgeber = setTimeout(runde, TAKT_MS);
    };
    document.addEventListener('visibilitychange', () => document.visibilityState === 'visible' && this.jetzt());
    void runde();
  }
}

export const lage = new Lage();
