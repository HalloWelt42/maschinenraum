<script lang="ts">
  // Wer belegt was: Dienste des Maschinenraums (Ist und Bedarf), Modelle des Modell-Läufers, der Rest.
  import { gb } from '../lib/format';
  import type { Stand } from '../lib/typen.gen';
  import { ZUSTAND, dienstfarbe } from '../lib/wort';
  import SpeicherKarte from '../teile/SpeicherKarte.svelte';

  let { stand: s }: { stand: Stand } = $props();
  const mw = $derived(s.messwerte);
  const dienste_jetzt = $derived(s.dienste.reduce((x, d) => x + (d.gb_jetzt ?? 0), 0));
  const laeufer = $derived(s.nachbar.erreichbar ? s.nachbar.geladen_gb : 0);
  const rest = $derived(mw ? Math.max(0, mw.speicher_belegt_gb - dienste_jetzt - laeufer) : 0);
</script>

<div class="seiteninhalt seite-speicher">
  <div class="rahmen-kopf">
    <div class="seitenkopf"><h1>Speicher</h1>
      <p class="unterzeile">Gemessen, nicht geschätzt. Jetzt ist, was ein Dienst gerade belegt; Bedarf ist sein höchster gemessener Wert, mindestens die Schätzung. Mit dem Bedarf plant die Leitstelle.</p></div>
  </div>
  <div class="rollfeld">
    <div class="spalten-speicher">
      <table class="tabelle">
        <thead><tr><th>Wer</th><th>Herkunft</th><th>Zustand</th><th class="r">Jetzt</th><th class="r">Bedarf</th><th>Leitstelle</th></tr></thead>
        <tbody>
          {#each s.dienste as d (d.kennung)}
            <tr><td><span class="farbe" style="background:{dienstfarbe(d.faehigkeiten)}"></span>{d.name}</td><td class="leise">Maschinenraum</td>
              <td><span class="zustand {ZUSTAND[d.zustand].klasse}">{ZUSTAND[d.zustand].wort}</span>{#if d.aktiv}<span class="arbeitet"> arbeitet</span>{/if}</td>
              <td class="r zahl">{d.gb_jetzt != null ? gb(d.gb_jetzt) : '-'}</td><td class="r zahl">{gb(d.bedarf_gb)}</td>
              <td class="leise">{d.anhalten_erlaubt ? 'darf anhalten' : 'nur von Hand'}</td></tr>
          {/each}
          {#each s.nachbar.modelle as m (m.name)}
            <tr><td><span class="farbe laeufer"></span>{m.name}</td><td class="leise">Modell-Läufer</td><td><span class="zustand fertig">Geladen</span></td>
              <td class="r zahl">{gb(m.gb)}</td><td class="r zahl">{gb(m.gb)}</td><td class="leise">verwaltet der Modell-Läufer</td></tr>
          {/each}
          {#if mw}
            <tr class="rest"><td><span class="farbe system"></span>System und Programme</td><td class="leise">Rechner</td><td></td>
              <td class="r zahl">{gb(rest)}</td><td></td><td></td></tr>
          {/if}
        </tbody>
      </table>
      <SpeicherKarte stand={s} />
    </div>
  </div>
</div>

<style>
  .spalten-speicher { display: grid; grid-template-columns: minmax(0, 1fr) 420px; gap: var(--mr-a5); align-items: start; }
  .tabelle { width: 100%; }
  .r { text-align: right; white-space: nowrap; }
  .farbe { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: var(--mr-a2); }
  .farbe.laeufer { background: var(--mr-himmel); }
  .farbe.system { background: var(--mr-stahl); }
  .arbeitet { color: var(--mr-akzent-schrift); font-size: var(--mr-gr-klein); }
  .rest td { color: var(--mr-text-2); }
  @media (max-width: 1100px) { .spalten-speicher { grid-template-columns: minmax(0, 1fr); } }
</style>
