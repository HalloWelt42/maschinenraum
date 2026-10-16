<script lang="ts">
  // Ein Dienst: Zustand, Speicher, Schalter und Protokoll. Anhalten fragt erst nach (ohne Browser-Dialog).
  import { api } from '../lib/api';
  import { gb } from '../lib/format';
  import { lage } from '../lib/stand.svelte';
  import { meldungen } from '../lib/meldung.svelte';
  import type { BefehlErgebnis, DienstAnsicht } from '../lib/typen.gen';
  import { FAEHIGKEIT, ZUSTAND } from '../lib/wort';
  import Protokoll from './Protokoll.svelte';

  let { dienst: d }: { dienst: DienstAnsicht } = $props();

  let arbeitet = $state<'' | 'starten' | 'anhalten' | 'neustarten'>('');
  let fragen = $state<'' | 'anhalten' | 'neustarten'>('');
  let protokollOffen = $state(false);

  const z = $derived(ZUSTAND[d.zustand]);
  const laeuft = $derived(d.zustand === 'laeuft' || d.zustand === 'startet' || d.zustand === 'stoppt');

  async function tun(art: 'starten' | 'anhalten' | 'neustarten') {
    fragen = '';
    arbeitet = art;
    try {
      const e: BefehlErgebnis = await api[art](d.kennung);
      meldungen.zeigen(`${d.name}: ${e.meldung}`, e.erfolg ? 'erfolg' : 'fehler');
      if (!e.erfolg) protokollOffen = true;
    } catch (f) {
      meldungen.fehler(f);
    } finally {
      arbeitet = '';
      await lage.jetzt();
    }
  }
</script>

<article class="karte dienst" class:an={laeuft}>
  <header>
    <span class="zustand {z.klasse}"><i class="fa-solid {arbeitet ? 'fa-circle-notch fa-spin' : z.symbol}"></i>{arbeitet === 'starten' ? 'Startet' : arbeitet === 'anhalten' ? 'Hält an' : arbeitet === 'neustarten' ? 'Startet neu' : z.wort}</span>
    <h2>{d.name}</h2>
    <div class="speicherzahl" title={d.gemessen ? 'Gemessener Speicher aller Prozesse des Dienstes' : d.spitze_gb ? 'Höchster gemessener Wert; so viel braucht er etwa beim nächsten Start' : 'Schätzung aus der Dienstdatei, bis er einmal gemessen wurde'}>
      <b class="zahl">{gb(d.gb)}</b><span>{d.gemessen ? 'gemessen' : d.spitze_gb ? 'zuletzt höchstens' : 'geschätzt'}</span></div>
  </header>

  <div class="unter">
    {#each d.faehigkeiten as f (f)}<span class="faehigkeit {FAEHIGKEIT[f].klasse}"><i class="fa-solid {FAEHIGKEIT[f].symbol}"></i>{FAEHIGKEIT[f].wort}</span>{/each}
    {#if d.port}<span class="zahl" title="Port, auf dem der Dienst antwortet">Port {d.port}</span>{/if}
    {#if d.soll === 'laeuft'}<span title="Läuft nach einem Neustart des Rechners wieder an"><i class="fa-solid fa-rotate"></i> startet mit dem Rechner</span>{/if}
  </div>
  {#if d.beschreibung}<p class="beschreibung">{d.beschreibung}</p>{/if}

  {#if d.fremd}
    <div class="hinweis klein"><i class="fa-solid fa-circle-info"></i><span>Von außen gestartet. Der Maschinenraum misst ihn und kann ihn anhalten; der nächste Start geschieht von hier.</span></div>
  {/if}
  {#if d.meldung && !d.fremd}
    <div class="hinweis klein {d.zustand === 'gestoert' ? 'gefahr' : 'warnung'}"><i class="fa-solid fa-triangle-exclamation"></i><span>{d.meldung}</span></div>
  {/if}

  {#if fragen}
    <div class="bestaetigen"><i class="fa-solid fa-triangle-exclamation"></i>
      <span>{d.name} {fragen === 'anhalten' ? 'anhalten' : 'neu starten'}? Wer ihn gerade nutzt, verliert die Verbindung{fragen === 'anhalten' ? '; er gibt etwa ' + gb(d.gb) + ' frei' : ''}.</span>
      <div class="rechts"><button class="knopf klein ohne" onclick={() => (fragen = '')}>Abbrechen</button>
        <button class="knopf klein gefahr-voll" onclick={() => tun(fragen as 'anhalten' | 'neustarten')}>{fragen === 'anhalten' ? 'Ja, anhalten' : 'Ja, neu starten'}</button></div></div>
  {/if}

  <footer>
    {#if !laeuft}
      <button class="knopf haupt" disabled={!!arbeitet} onclick={() => tun('starten')} title="Starten und warten, bis er antwortet"><i class="fa-solid fa-play"></i> Starten</button>
    {:else}
      <button class="knopf" disabled={!!arbeitet} onclick={() => (fragen = 'anhalten')} title="Erst freundlich beenden, nach der Anhaltezeit hart"><i class="fa-solid fa-stop"></i> Anhalten</button>
      <button class="knopf ohne" disabled={!!arbeitet} onclick={() => (fragen = 'neustarten')} title="Anhalten und wieder starten"><i class="fa-solid fa-rotate-right"></i> Neu starten</button>
    {/if}
    <button class="knopf ohne" class:aktiv={protokollOffen} onclick={() => (protokollOffen = !protokollOffen)} title="Ausgabe des Dienstes"><i class="fa-solid fa-scroll"></i> Protokoll</button>
    {#if d.oberflaeche && laeuft}<a class="knopf ohne" href={d.oberflaeche} target="_blank" rel="noopener" title="Eigene Oberfläche des Dienstes öffnen"><i class="fa-solid fa-arrow-up-right-from-square"></i> Öffnen</a>{/if}
    <span class="datei" title="Dienstdatei: Befehl, Ordner, Port, Umgebung">{d.datei}</span>
  </footer>
  {#if protokollOffen}<Protokoll kennung={d.kennung} />{/if}
</article>

<style>
  .dienst { display: flex; flex-direction: column; gap: var(--mr-a3); }
  .dienst + :global(.dienst) { margin-top: var(--mr-a3); }
  header { display: flex; align-items: center; gap: var(--mr-a3); flex-wrap: wrap; }
  header h2 { font-size: var(--mr-gr-titel); }
  .speicherzahl { margin-left: auto; text-align: right; line-height: 1.2; }
  .speicherzahl b { display: block; font-size: var(--mr-gr-titel); font-weight: 600; }
  .speicherzahl span { font-size: var(--mr-gr-marke); color: var(--mr-text-3); }
  .unter { display: flex; align-items: center; gap: var(--mr-a2) var(--mr-a4); flex-wrap: wrap; font-size: var(--mr-gr-klein); color: var(--mr-text-2); }
  .beschreibung { color: var(--mr-text-2); font-size: var(--mr-gr-klein); }
  footer { display: flex; align-items: center; gap: var(--mr-a2); flex-wrap: wrap; }
  .datei { margin-left: auto; font-family: var(--mr-schrift-code); font-size: var(--mr-gr-marke); color: var(--mr-text-3); overflow-wrap: anywhere; }
</style>
