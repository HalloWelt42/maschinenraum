<script lang="ts">
  // Ende einer Protokolldatei, alle zwei Sekunden neu, solange sichtbar. Ohne Kennung: das eigene Protokoll;
  // mit betrieb: das eines Steuerprogramms (Stellwerk ...).
  import { onDestroy } from 'svelte';
  import { api } from '../lib/api';

  let { kennung = null, betrieb = false, zeilen: anzahl = 300 }: { kennung?: string | null; betrieb?: boolean; zeilen?: number } = $props();

  let zeilen = $state<string[]>([]);
  let datei = $state('');
  let feld = $state<HTMLPreElement | null>(null);
  let laeuft = true;

  async function holen() {
    if (!laeuft) return;
    try {
      const unten = !feld || feld.scrollHeight - feld.scrollTop - feld.clientHeight < 40;
      const p = !kennung ? await api.eigenesProtokoll(anzahl) : betrieb ? await api.betriebProtokoll(kennung, anzahl) : await api.protokoll(kennung, anzahl);
      zeilen = p.zeilen;
      datei = p.datei;
      if (unten) requestAnimationFrame(() => feld && (feld.scrollTop = feld.scrollHeight));
    } catch {
      /* nächster Versuch im nächsten Takt */
    }
    if (laeuft) setTimeout(holen, 2000);
  }

  void holen();
  onDestroy(() => (laeuft = false));
</script>

<div class="protokoll">
  <pre bind:this={feld}>{zeilen.length ? zeilen.join('\n') : 'Noch keine Ausgabe.'}</pre>
  <div class="datei" title="Vollständige Datei">{datei}</div>
</div>

<style>
  .protokoll { margin-top: var(--mr-a3); }
  pre { margin: 0; max-height: var(--hoehe, 360px); overflow: auto; background: var(--mr-mulde); border-radius: var(--mr-ecke); padding: var(--mr-a3);
        font-family: var(--mr-schrift-code); font-size: 14px; line-height: 1.45; white-space: pre-wrap; overflow-wrap: anywhere; color: var(--mr-text-2); }
  .datei { margin-top: 6px; font-family: var(--mr-schrift-code); font-size: var(--mr-gr-marke); color: var(--mr-text-3); overflow-wrap: anywhere; }
</style>
