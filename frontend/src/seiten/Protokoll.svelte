<script lang="ts">
  // Protokolle wie in der Leitstelle mit Reitern: der Maschinenraum selbst und je Dienst seine Ausgabe.
  import type { Stand } from '../lib/typen.gen';
  import { weg } from '../lib/weg.svelte';
  import Protokoll from '../teile/Protokoll.svelte';

  let { stand: s }: { stand: Stand } = $props();
  // Reiter-Pfad: Dienste unter ihrer Kennung, Steuerprogramme unter betrieb:<kennung>
  const gewaehlt = $derived(s.dienste.some((d) => d.kennung === weg.teil) || s.betrieb.some((b) => `betrieb:${b.kennung}` === weg.teil) ? weg.teil : null);
  const istBetrieb = $derived(gewaehlt?.startsWith('betrieb:') ?? false);
</script>

<div class="seiteninhalt seite-protokoll">
  <div class="rahmen-kopf">
    <div class="seitenkopf"><h1>Protokoll</h1></div>
    <div class="reiter">
      <button class:aktiv={gewaehlt === null} onclick={() => weg.gehe('protokoll')}><i class="fa-solid fa-industry"></i> Maschinenraum</button>
      {#each s.betrieb as b (b.kennung)}
        <button class:aktiv={gewaehlt === `betrieb:${b.kennung}`} onclick={() => weg.gehe('protokoll', `betrieb:${b.kennung}`)}><i class="fa-solid fa-power-off"></i> {b.name}</button>
      {/each}
      {#each s.dienste as d (d.kennung)}
        <button class:aktiv={gewaehlt === d.kennung} onclick={() => weg.gehe('protokoll', d.kennung)}><i class="fa-solid fa-gear"></i> {d.name}</button>
      {/each}
    </div>
  </div>
  <div class="rollfeld" style="--hoehe: calc(100vh - 300px)">
    {#key gewaehlt}<Protokoll kennung={istBetrieb ? gewaehlt!.slice(8) : gewaehlt} betrieb={istBetrieb} zeilen={1000} />{/key}
  </div>
</div>
