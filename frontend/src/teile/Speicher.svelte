<script lang="ts">
  // Speicher des Rechners, aufgeteilt: Dienste des Maschinenraums, Modell-Läufer, alles andere, frei.
  // Alle Werte gemessen; der Modell-Läufer meldet die Größe seiner geladenen Modelle.
  import { gb, komma } from '../lib/format';
  import type { Stand } from '../lib/typen.gen';
  import { dienstfarbe } from '../lib/wort';
  import Ring from './Ring.svelte';

  let { stand }: { stand: Stand } = $props();

  const mw = $derived(stand.messwerte);
  const laufend = $derived(stand.dienste.filter((d) => d.gemessen && d.gb > 0));
  const dienste_gb = $derived(laufend.reduce((s, d) => s + d.gb, 0));
  const laeufer_gb = $derived(stand.nachbar.erreichbar ? stand.nachbar.geladen_gb : 0);
  const uebrig_gb = $derived(mw ? Math.max(0, mw.speicher_belegt_gb - dienste_gb - laeufer_gb) : 0);
  const frei_gb = $derived(mw ? Math.max(0, mw.speicher_gesamt_gb - mw.speicher_belegt_gb) : 0);
  const anteil = (wert: number) => (mw && mw.speicher_gesamt_gb ? `${(100 * wert) / mw.speicher_gesamt_gb}%` : '0%');
  const swapAnteil = $derived(mw?.swap_gesamt_gb ? (mw.swap_belegt_gb ?? 0) / mw.swap_gesamt_gb : 0);
</script>

<section class="karte speicherkarte">
  <h3><i class="fa-solid fa-memory"></i> Speicher
    {#if mw}<span class="rechts"><b class="zahl">{gb(mw.speicher_belegt_gb)}</b> von <span class="zahl">{gb(mw.speicher_gesamt_gb)}</span> belegt</span>{/if}</h3>
  {#if mw}
    <div class="speicher gross" title="Belegter Speicher nach Herkunft">
      {#each laufend as d (d.kennung)}<span style="width:{anteil(d.gb)};background:{dienstfarbe(d.faehigkeiten)}" title="{d.name}: {gb(d.gb)}"></span>{/each}
      {#if laeufer_gb}<span class="laeufer" style="width:{anteil(laeufer_gb)}" title="Modell-Läufer: {gb(laeufer_gb)}"></span>{/if}
      <span class="system" style="width:{anteil(uebrig_gb)}" title="System und andere Programme: {gb(uebrig_gb)}"></span>
    </div>
    <ul class="legende">
      {#each laufend as d (d.kennung)}<li><i class="fa-solid fa-square" style="color:{dienstfarbe(d.faehigkeiten)}"></i>{d.name}<b class="zahl">{gb(d.gb)}</b></li>{/each}
      {#if stand.nachbar.erreichbar}<li title="Geladene Modelle des Modell-Läufers; die verwaltet er selbst"><i class="fa-solid fa-square laeufer-farbe"></i>Modell-Läufer<b class="zahl">{gb(laeufer_gb)}</b></li>{/if}
      <li title="Betriebssystem und alle Programme, die der Maschinenraum nicht verwaltet"><i class="fa-solid fa-square system-farbe"></i>System und Programme<b class="zahl">{gb(uebrig_gb)}</b></li>
      <li><i class="fa-regular fa-square"></i>Frei<b class="zahl">{gb(frei_gb)}</b></li>
    </ul>
    {#if mw.swap_gesamt_gb}
      <div class="swap" title="Auslagerung auf die Platte. Viel davon heißt: der Speicher reicht nicht, alles wird langsamer.">
        <span>Auslagerung</span><div class="balken" class:fehler={swapAnteil > 0.6}><b style="width:{swapAnteil * 100}%"></b></div>
        <b class="zahl">{gb(mw.swap_belegt_gb)} von {gb(mw.swap_gesamt_gb)}</b>
      </div>
    {/if}
    <div class="mess">
      <div class="ringe">
        {#if mw.cpu_prozent != null}<Ring wert={mw.cpu_prozent} name="Prozessor" />{/if}
        {#if mw.grafik_prozent != null}<Ring wert={mw.grafik_prozent} name="Grafik" />{/if}
      </div>
      <div class="werte">
        {#if mw.temperatur_c != null}<span title="Temperatur des Prozessors"><i class="fa-solid fa-temperature-half"></i><b class="zahl">{komma(mw.temperatur_c, 0)} °C</b></span>{/if}
        {#if mw.leistung_w != null}<span title="Leistungsaufnahme des ganzen Rechners"><i class="fa-solid fa-bolt"></i><b class="zahl">{komma(mw.leistung_w, 0)}</b> Watt</span>{/if}
        {#if mw.last_1m != null}<span title="Durchschnittliche Last der letzten Minute"><i class="fa-solid fa-gauge"></i><b class="zahl">{komma(mw.last_1m, 1)}</b> Last</span>{/if}
        {#if mw.platte_frei_gb != null}<span title="Freier Platz auf der Platte"><i class="fa-solid fa-hard-drive"></i><b class="zahl">{gb(mw.platte_frei_gb)}</b> frei</span>{/if}
      </div>
    </div>
  {:else}
    <p class="leise">Erste Messung läuft.</p>
  {/if}
</section>

<style>
  .speicher.gross { height: 22px; }
  .laeufer, .laeufer-farbe { background: var(--mr-himmel); color: var(--mr-himmel); }
  .system, .system-farbe { background: var(--mr-stahl); color: var(--mr-stahl); }
  .laeufer-farbe, .system-farbe { background: none; }
  .legende { list-style: none; margin: var(--mr-a3) 0 0; padding: 0; display: grid; gap: 6px; font-size: var(--mr-gr-klein); color: var(--mr-text-2); }
  .legende li { display: grid; grid-template-columns: 22px minmax(0, 1fr) auto; align-items: center; }
  .legende i { font-size: 12px; }
  .legende b { color: var(--mr-text); font-weight: 600; }
  .swap { display: grid; grid-template-columns: auto minmax(60px, 1fr) auto; gap: var(--mr-a3); align-items: center; margin-top: var(--mr-a4);
          font-size: var(--mr-gr-klein); color: var(--mr-text-2); }
  .swap b.zahl { color: var(--mr-text); font-weight: 600; }
  .mess { display: flex; gap: var(--mr-a4); align-items: center; flex-wrap: wrap; margin-top: var(--mr-a4); }
  .werte { display: grid; gap: 6px; font-size: var(--mr-gr-klein); color: var(--mr-text-2); }
  .werte i { width: 22px; color: var(--mr-text-3); }
  .werte b { color: var(--mr-text); font-weight: 600; }
</style>
