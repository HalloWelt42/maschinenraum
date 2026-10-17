// Was gerade läuft und durch ein Neuladen der Seite verloren ginge: schreibende Aufrufe, deren Antwort noch aussteht
// (Starten und Anhalten warten, bis der Dienst antwortet), und offene Bearbeitungen (Eintrag der Leitstelle). Die
// Fassungsprüfung fragt das ab, bevor sie die Seite von selbst neu lädt (lib/fassung.svelte.ts).
import { SvelteSet } from 'svelte/reactivity';

class Arbeit {
  /** schreibende Aufrufe, deren Antwort noch aussteht (lib/api.ts) */
  schreibend = $state(0);
  private offen = new SvelteSet<() => boolean>();

  /** Rahmt einen schreibenden Aufruf: zählt mit, solange er läuft. */
  async rahmen<T>(aufruf: () => Promise<T>): Promise<T> {
    this.schreibend += 1;
    try {
      return await aufruf();
    } finally {
      this.schreibend -= 1;
    }
  }

  /** Beim Aufbau einer Komponente aufrufen: solange `offen()` wahr ist, wartet ein Neuladen; mit der Komponente endet es. */
  bearbeitung(offen: () => boolean): void {
    $effect(() => {
      this.offen.add(offen);
      return () => this.offen.delete(offen);
    });
  }

  /** Nichts in Arbeit, das ein Neuladen abbräche. */
  ruhig(): boolean {
    return this.schreibend === 0 && ![...this.offen].some((o) => o());
  }
}

export const arbeit = new Arbeit();
