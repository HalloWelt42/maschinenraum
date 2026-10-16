<script lang="ts">
  // Fußleiste wie in der Leitstelle: Kurzstand links, Verbindungen und Fassung rechts
  import { prozent } from '../lib/format';
  import { lage } from '../lib/stand.svelte';
  import { VERBINDUNG } from '../lib/wort';

  const s = $derived(lage.stand);
  const laufen = $derived(s?.dienste.filter((d) => d.zustand === 'laeuft' || d.zustand === 'startet').length ?? 0);
  const anteil = $derived(s?.messwerte ? s.messwerte.speicher_belegt_gb / s.messwerte.speicher_gesamt_gb : null);
</script>

<footer class="fuss">
  {#if s}
    <span><i class="fa-solid fa-gears"></i>&nbsp; <span class="zahl">{laufen}</span> von <span class="zahl">{s.dienste.length}</span> Diensten laufen</span>
    {#if anteil != null}<span title="Belegter Speicher des ganzen Rechners (gemessen)"><i class="fa-solid fa-memory"></i>&nbsp; {s.rechner} <span class="zahl">{prozent(anteil)}</span> Speicher</span>{/if}
  {/if}
  <div class="rechts">
    {#if s}<span title={s.leitstelle.meldung || VERBINDUNG[s.leitstelle.zustand].wort}><span class="punkt" class:gefahr={s.leitstelle.zustand !== 'verbunden' && s.leitstelle.zustand !== 'aus'} class:aus={s.leitstelle.zustand === 'aus'}></span>Leitstelle</span>{/if}
    <span title="Verbindung dieser Oberfläche zum Maschinenraum"><span class="punkt" class:lebt={lage.erreichbar} class:gefahr={!lage.erreichbar}></span>{lage.erreichbar ? 'Live' : 'Getrennt'}</span>
    {#if s}<span class="schwach zahl">{s.version}</span>{/if}
  </div>
</footer>
