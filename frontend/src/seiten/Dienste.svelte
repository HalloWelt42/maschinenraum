<script lang="ts">
  // Alle Dienste mit Schaltern, Speicher und Protokoll; fehlerhafte Dienstdateien oben als Hinweis.
  import { gb } from '../lib/format';
  import type { Stand } from '../lib/typen.gen';
  import DienstKarte from '../teile/DienstKarte.svelte';

  let { stand: s }: { stand: Stand } = $props();
  const laufen = $derived(s.dienste.filter((d) => d.zustand === 'laeuft' || d.zustand === 'startet').length);
  const gestoert = $derived(s.dienste.filter((d) => d.zustand === 'gestoert').length);
  const bedarf = $derived(s.dienste.reduce((x, d) => x + d.bedarf_gb, 0));
</script>

<div class="seiteninhalt seite-dienste">
  <div class="rahmen-kopf">
    <div class="seitenkopf"><h1>Dienste</h1><span class="zahl">{s.dienste.length}</span>
      <p class="unterzeile">Alles, was der Modell-Läufer nicht verwaltet. Jeder Dienst läuft in eigener Prozessgruppe mit eigener Umgebung und eigenem Protokoll.</p></div>
    <div class="kennzahlen">
      <div class="kennzahl erfolg"><b>{laufen}</b><span>Laufen</span></div>
      <div class="kennzahl"><b>{s.dienste.length - laufen - gestoert}</b><span>Aus</span></div>
      {#if gestoert}<div class="kennzahl fehler"><b>{gestoert}</b><span>Gestört</span></div>{/if}
      <div class="kennzahl" title="Summe der Bedarfe aller Dienste, wenn alle liefen"><b>{gb(bedarf)}</b><span>Bedarf aller</span></div>
    </div>
  </div>
  <div class="rollfeld liste-dienste">
    {#each s.ladefehler as f (f.datei)}
      <div class="hinweis gefahr klein"><i class="fa-solid fa-file-circle-exclamation"></i><span>Dienstdatei <b>{f.datei}</b> wird übergangen: {f.meldung}</span></div>
    {/each}
    {#each s.dienste as d (d.kennung)}
      <DienstKarte dienst={d} />
    {:else}
      <div class="leer"><i class="fa-solid fa-gears"></i><h2>Noch keine Dienste</h2>
        <p>Je Dienst eine Datei im Ordner <span class="code">{s.ordner}/dienste</span> anlegen: Name, Arbeitsordner, Befehl, Port. Der Maschinenraum liest sie im nächsten Takt.</p></div>
    {/each}
  </div>
</div>

<style>
  .liste-dienste { display: flex; flex-direction: column; gap: var(--mr-a3); }
  .liste-dienste :global(.dienst) { margin: 0; max-width: 1100px; }
</style>
