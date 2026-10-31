<script lang="ts">
  // Ein Dienst: Zustand, Speicher, Schalter und Protokoll. Anhalten fragt erst nach (ohne Browser-Dialog).
  import { api } from '../lib/api';
  import { gb } from '../lib/format';
  import { lage } from '../lib/stand.svelte';
  import { meldungen } from '../lib/meldung.svelte';
  import type { BefehlErgebnis, DienstAnsicht, Ergebnis } from '../lib/typen.gen';
  import { FAEHIGKEIT, ZUSTAND } from '../lib/wort';
  import Protokoll from './Protokoll.svelte';

  let { dienst: d }: { dienst: DienstAnsicht } = $props();

  let arbeitet = $state<'' | 'starten' | 'anhalten' | 'neustarten' | 'entsperren' | 'sperren' | 'verwerfen'>('');
  let fragen = $state<'' | 'anhalten' | 'neustarten' | 'entsperren' | 'sperren' | 'verwerfen'>('');
  let sperrgrund = $state('');
  let protokollOffen = $state(false);

  const z = $derived(ZUSTAND[d.zustand]);
  const laeuft = $derived(d.zustand === 'laeuft' || d.zustand === 'startet' || d.zustand === 'stoppt');
  // Gemessene Spitze deutlich über der Anmeldung: fällt sofort auf (die Grenze leitet sich aus der Anmeldung ab)
  const abweichung = $derived(d.spitze_gb != null && d.spitze_gb > d.schaetzung_gb * 1.2 + 0.5);

  async function entsperren() {
    await handeln('entsperren', () => api.entsperren(d.kennung));
  }

  async function handeln(art: 'entsperren' | 'sperren' | 'verwerfen', aufruf: () => Promise<Ergebnis>) {
    fragen = '';
    arbeitet = art;
    try {
      const e: Ergebnis = await aufruf();
      meldungen.zeigen(`${d.name}: ${e.meldung}`, e.erfolg ? 'erfolg' : 'fehler');
    } catch (f) {
      meldungen.fehler(f);
    } finally {
      arbeitet = '';
      await lage.jetzt();
    }
  }

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
    <div class="speicherzahl" title="Bedarf: der Wert, mit dem 80 Prozent der jüngsten Arbeitsphasen auskamen, mindestens die Anmeldung der Dienstdatei ({gb(d.schaetzung_gb)}). Mit diesem Wert plant die Leitstelle.">
      <b class="zahl">{gb(d.bedarf_gb)}</b><span>Bedarf{d.spitze_gb ? '' : ', geschätzt'}</span>
      {#if d.gb_jetzt != null}<span class="jetzt" title="Gerade gemessen; Dienste laden ihre Modelle oft erst bei Bedarf">jetzt <b class="zahl">{gb(d.gb_jetzt)}</b></span>{/if}</div>
  </header>

  <div class="unter">
    {#each d.faehigkeiten as f (f)}<span class="faehigkeit {FAEHIGKEIT[f].klasse}"><i class="fa-solid {FAEHIGKEIT[f].symbol}"></i>{FAEHIGKEIT[f].wort}</span>{/each}
    {#if d.port}<span class="zahl" title="Port, auf dem der Dienst antwortet">Port {d.port}</span>{/if}
    {#if d.soll === 'laeuft'}<span title="Läuft nach einem Neustart des Rechners wieder an"><i class="fa-solid fa-rotate"></i> startet mit dem Rechner</span>{/if}
    {#if d.aktiv}<span class="arbeitet" title="Prozessorlast {d.cpu_prozent} Prozent eines Kerns: der Dienst arbeitet gerade"><i class="fa-solid fa-gear fa-spin"></i> arbeitet</span>{/if}
    <span title={d.anhalten_erlaubt ? 'Die Leitstelle darf ihn anhalten, wenn ein Modell den Speicher braucht und er nicht arbeitet' : 'Die Leitstelle darf ihn nicht anhalten; nur von Hand (Dienstdatei: leitstelle_anhalten = false)'}>
      <i class="fa-solid {d.anhalten_erlaubt ? 'fa-tower-broadcast' : 'fa-lock'}"></i> {d.anhalten_erlaubt ? 'Leitstelle darf anhalten' : 'nur von Hand anhalten'}</span>
  </div>
  {#if d.beschreibung}<p class="beschreibung">{d.beschreibung}</p>{/if}

  {#if d.fremd}
    <div class="hinweis klein"><i class="fa-solid fa-circle-info"></i><span>Von außen gestartet. Der Maschinenraum misst ihn und kann ihn anhalten; der nächste Start geschieht von hier.</span></div>
  {/if}
  <div class="speicherreihe">
    <span title="Angemeldet in der Dienstdatei (speicher_gb); daraus leitet sich die Grenze ab"><i class="fa-solid fa-file-lines"></i> angemeldet <b class="zahl">{gb(d.schaetzung_gb)}</b></span>
    <span class:abweichung title={abweichung ? 'Die gemessene Spitze liegt deutlich über der Anmeldung: speicher_gb in der Dienstdatei anheben oder den Dienst prüfen' : 'Höchste gemessene Arbeitsspitze (physischer Fußabdruck aller Prozesse, samt Grafikspeicher)'}>
      <i class="fa-solid {abweichung ? 'fa-triangle-exclamation' : 'fa-chart-line'}"></i> Spitze gemessen <b class="zahl">{d.spitze_gb != null ? gb(d.spitze_gb) : '-'}</b></span>
    {#if d.spitze_gb != null}<button class="knopf klein ohne" disabled={!!arbeitet} onclick={() => (fragen = 'verwerfen')} title="Gemessene Spitzen verwerfen (nach einem Umbau)"><i class="fa-solid fa-eraser"></i> verwerfen</button>{/if}
    {#if d.grenze_gb != null}<span title="Harte Grenze: darüber beendet die Speicherwache den Dienst sofort und sperrt ihn; der Dienst kennt sie auch selbst (MASCHINENRAUM_SPEICHER_GRENZE_GB, für torch als Marken)"><i class="fa-solid fa-shield-halved"></i> Grenze <b class="zahl">{gb(d.grenze_gb)}</b></span>{/if}
  </div>

  {#if d.sperre}
    <div class="hinweis klein gefahr sperre"><i class="fa-solid fa-ban"></i>
      <span><b>Gesperrt</b>{d.sperre_seit ? ` seit ${new Date(d.sperre_seit).toLocaleString('de-DE', { dateStyle: 'short', timeStyle: 'short' })}` : ''}: {d.sperre}. Er startet nicht wieder, weder mit dem Rechner noch auf Wunsch der Leitstelle, bis die Sperre hier aufgehoben ist.</span></div>
  {:else if d.meldung && !d.fremd}
    <div class="hinweis klein {d.zustand === 'gestoert' ? 'gefahr' : 'warnung'}"><i class="fa-solid fa-triangle-exclamation"></i><span>{d.meldung}</span></div>
  {/if}

  {#if fragen}
    <div class="bestaetigen"><i class="fa-solid fa-triangle-exclamation"></i>
      {#if fragen === 'sperren'}
        <span>{d.name} sperren? Er hält an und startet nicht wieder, auch nicht auf Wunsch der Leitstelle, bis die Sperre hier
          aufgehoben ist.</span>
        <input class="eingabe grund" bind:value={sperrgrund} maxlength="300" placeholder="Grund, etwa: neu eingerichtet, Kurzmessung steht aus" />
        <div class="rechts"><button class="knopf klein ohne" onclick={() => (fragen = '')}>Abbrechen</button>
          <button class="knopf klein gefahr-voll" disabled={!sperrgrund.trim()} onclick={() => handeln('sperren', () => api.sperren(d.kennung, sperrgrund.trim()))}>Ja, sperren</button></div>
      {:else if fragen === 'verwerfen'}
        <span>Gemessene Spitzen von {d.name} verwerfen? Sinnvoll nach einem Umbau, wenn die alten Werte nicht mehr gelten; der Bedarf
          beginnt wieder bei der Anmeldung ({gb(d.schaetzung_gb)}).</span>
        <div class="rechts"><button class="knopf klein ohne" onclick={() => (fragen = '')}>Abbrechen</button>
          <button class="knopf klein gefahr-voll" onclick={() => handeln('verwerfen', () => api.spitzenVerwerfen(d.kennung))}>Ja, verwerfen</button></div>
      {:else if fragen === 'entsperren'}
        <span>Sperre von {d.name} aufheben? Erst, wenn die Ursache behoben ist (etwa speicher_gb oder der Dienst selbst); gestartet wird damit noch nichts.</span>
        <div class="rechts"><button class="knopf klein ohne" onclick={() => (fragen = '')}>Abbrechen</button>
          <button class="knopf klein gefahr-voll" onclick={entsperren}>Ja, Sperre aufheben</button></div>
      {:else}
        <span>{d.name} {fragen === 'anhalten' ? 'anhalten' : 'neu starten'}? Wer ihn gerade nutzt, verliert die Verbindung{fragen === 'anhalten' && d.gb_jetzt != null ? '; er gibt etwa ' + gb(d.gb_jetzt) + ' frei' : ''}.</span>
        <div class="rechts"><button class="knopf klein ohne" onclick={() => (fragen = '')}>Abbrechen</button>
          <button class="knopf klein gefahr-voll" onclick={() => tun(fragen as 'anhalten' | 'neustarten')}>{fragen === 'anhalten' ? 'Ja, anhalten' : 'Ja, neu starten'}</button></div>
      {/if}</div>
  {/if}

  <footer>
    {#if d.sperre}
      <button class="knopf haupt" disabled={!!arbeitet} onclick={() => (fragen = 'entsperren')} title="Sperre aufheben (startet nichts)"><i class="fa-solid fa-lock-open"></i> Sperre aufheben</button>
    {:else if !laeuft}
      <button class="knopf haupt" disabled={!!arbeitet} onclick={() => tun('starten')} title="Starten und warten, bis er antwortet"><i class="fa-solid fa-play"></i> Starten</button>
    {:else}
      <button class="knopf" disabled={!!arbeitet} onclick={() => (fragen = 'anhalten')} title="Erst freundlich beenden, nach der Anhaltezeit hart"><i class="fa-solid fa-stop"></i> Anhalten</button>
      <button class="knopf ohne" disabled={!!arbeitet} onclick={() => (fragen = 'neustarten')} title="Anhalten und wieder starten"><i class="fa-solid fa-rotate-right"></i> Neu starten</button>
    {/if}
    {#if !d.sperre}<button class="knopf ohne" disabled={!!arbeitet} onclick={() => (fragen = 'sperren')} title="Sperren: hält an und startet nicht, bis die Sperre von Hand aufgehoben ist"><i class="fa-solid fa-lock"></i> Sperren</button>{/if}
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
  .speicherzahl span { display: block; font-size: var(--mr-gr-marke); color: var(--mr-text-3); }
  .speicherzahl .jetzt b { display: inline; font-size: var(--mr-gr-marke); color: var(--mr-text-2); }
  .arbeitet { color: var(--mr-akzent-schrift); }
  .speicherreihe { display: flex; align-items: center; gap: var(--mr-a2) var(--mr-a4); flex-wrap: wrap; font-size: var(--mr-gr-klein); color: var(--mr-text-2); }
  .speicherreihe b { color: var(--mr-text); font-weight: 600; }
  .speicherreihe .abweichung, .speicherreihe .abweichung b { color: var(--mr-warnung); }
  .unter { display: flex; align-items: center; gap: var(--mr-a2) var(--mr-a4); flex-wrap: wrap; font-size: var(--mr-gr-klein); color: var(--mr-text-2); }
  .beschreibung { color: var(--mr-text-2); font-size: var(--mr-gr-klein); }
  footer { display: flex; align-items: center; gap: var(--mr-a2); flex-wrap: wrap; }
  .grund { flex: 1 1 16rem; min-width: 0; }
  .datei { margin-left: auto; font-family: var(--mr-schrift-code); font-size: var(--mr-gr-marke); color: var(--mr-text-3); overflow-wrap: anywhere; }
</style>
