<script lang="ts">
  // Steuerprogramme des Rechners (etwa das Stellwerk): starten, anhalten, öffnen. Keine KI, die Leitstelle sieht sie nicht.
  // Anhalten fragt erst nach (ohne Browser-Dialog).
  import { api } from '../lib/api';
  import { meldungen } from '../lib/meldung.svelte';
  import { lage } from '../lib/stand.svelte';
  import type { BetriebAnsicht } from '../lib/typen.gen';
  import { ZUSTAND } from '../lib/wort';

  let { programme }: { programme: BetriebAnsicht[] } = $props();
  let arbeitet = $state<string | null>(null);
  let fragen = $state<string | null>(null);

  const laeuft = (p: BetriebAnsicht) => p.zustand === 'laeuft' || p.zustand === 'startet' || p.zustand === 'stoppt';

  async function schalten(p: BetriebAnsicht) {
    fragen = null;
    arbeitet = p.kennung;
    try {
      const e = await api.betrieb(p.kennung, laeuft(p) ? 'anhalten' : 'starten');
      meldungen.zeigen(`${p.name}: ${e.meldung}`, e.erfolg ? 'erfolg' : 'fehler');
    } catch (f) {
      meldungen.fehler(f);
    } finally {
      arbeitet = null;
      await lage.jetzt();
    }
  }
</script>

<section class="karte betrieb">
  <h3><i class="fa-solid fa-power-off"></i> Betrieb</h3>
  {#each programme as p (p.kennung)}
    {@const z = ZUSTAND[p.zustand]}
    <div class="programm">
      <div class="kopfzeile">
        <b>{p.name}</b>
        <span class="zustand {z.klasse}"><i class="fa-solid {arbeitet === p.kennung ? 'fa-circle-notch fa-spin' : z.symbol}"></i>{z.wort}</span>
      </div>
      {#if p.beschreibung}<p class="leise klein">{p.beschreibung}</p>{/if}
      {#if p.meldung}<div class="hinweis klein {p.zustand === 'gestoert' ? 'gefahr' : 'warnung'}"><i class="fa-solid fa-triangle-exclamation"></i><span>{p.meldung}</span></div>{/if}
      {#if fragen === p.kennung}
        <div class="bestaetigen"><i class="fa-solid fa-triangle-exclamation"></i><span>{p.name} anhalten? Was es gestartet hat, läuft weiter, ist aber nicht mehr schaltbar, bis es wieder läuft.</span>
          <div class="rechts"><button class="knopf klein ohne" onclick={() => (fragen = null)}>Abbrechen</button>
            <button class="knopf klein gefahr-voll" onclick={() => schalten(p)}>Ja, anhalten</button></div></div>
      {/if}
      <div class="knoepfe">
        {#if laeuft(p)}
          <button class="knopf klein" disabled={arbeitet !== null} onclick={() => (fragen = p.kennung)}><i class="fa-solid fa-stop"></i> Anhalten</button>
          {#if p.oberflaeche}<a class="knopf klein ohne" href={p.oberflaeche} target="_blank" rel="noopener"><i class="fa-solid fa-arrow-up-right-from-square"></i> Öffnen</a>{/if}
        {:else}
          <button class="knopf klein haupt" disabled={arbeitet !== null} onclick={() => schalten(p)}><i class="fa-solid fa-play"></i> Starten</button>
        {/if}
      </div>
    </div>
  {/each}
</section>

<style>
  .betrieb { display: flex; flex-direction: column; gap: var(--mr-a3); }
  .programm { display: flex; flex-direction: column; gap: var(--mr-a2); }
  .programm + .programm { border-top: 1px solid var(--mr-rand); padding-top: var(--mr-a3); }
  .kopfzeile { display: flex; align-items: center; justify-content: space-between; gap: var(--mr-a3); }
  .knoepfe { display: flex; gap: var(--mr-a2); flex-wrap: wrap; }
</style>
