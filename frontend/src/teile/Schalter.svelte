<script lang="ts">
  // Kleiner Schalter für einen Dienst: an startet, aus hält an (mit Rückfrage in der Zeile, ohne Browser-Dialog)
  import { api } from '../lib/api';
  import { gb } from '../lib/format';
  import { meldungen } from '../lib/meldung.svelte';
  import { lage } from '../lib/stand.svelte';
  import type { DienstAnsicht } from '../lib/typen.gen';

  let { dienst: d }: { dienst: DienstAnsicht } = $props();
  let arbeitet = $state(false);
  let fragen = $state(false);
  const an = $derived(d.zustand === 'laeuft' || d.zustand === 'startet' || d.zustand === 'stoppt');

  async function schalten() {
    fragen = false;
    arbeitet = true;
    try {
      const e = await (an ? api.anhalten(d.kennung) : api.starten(d.kennung));
      meldungen.zeigen(`${d.name}: ${e.meldung}`, e.erfolg ? 'erfolg' : 'fehler');
    } catch (f) {
      meldungen.fehler(f);
    } finally {
      arbeitet = false;
      await lage.jetzt();
    }
  }
</script>

{#if fragen}
  <span class="frage"><span>Anhalten? Gibt {gb(d.gb_jetzt ?? 0)} frei.</span>
    <button class="knopf klein ohne" onclick={() => (fragen = false)}>Nein</button>
    <button class="knopf klein gefahr-voll" onclick={schalten}>Ja</button></span>
{:else if arbeitet}
  <i class="fa-solid fa-circle-notch fa-spin warten" title="Wird geschaltet"></i>
{:else}
  <button class="schalter" class:an onclick={() => (an ? (fragen = true) : schalten())} aria-label="{d.name} {an ? 'anhalten' : 'starten'}"
          title={an ? 'Anhalten' : 'Starten und warten, bis er antwortet'}></button>
{/if}

<style>
  .frage { display: inline-flex; align-items: center; gap: var(--mr-a2); font-size: var(--mr-gr-klein); }
  .warten { width: 46px; text-align: center; color: var(--mr-text-3); }
</style>
