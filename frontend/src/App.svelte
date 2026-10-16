<script lang="ts">
  // Maschinenraum: alle Dienste dieses Rechners an einem Ort. Links die Dienste, rechts Speicher, Modell-Läufer,
  // Leitstelle und der Ordner, in dem die Dienstdateien liegen.
  import { ansicht } from './lib/ansicht.svelte';
  import { gb } from './lib/format';
  import { lage } from './lib/stand.svelte';
  import { VERBINDUNG } from './lib/wort';
  import DienstKarte from './teile/DienstKarte.svelte';
  import LeitstelleFeld from './teile/LeitstelleFeld.svelte';
  import Protokoll from './teile/Protokoll.svelte';
  import Rueckmeldungen from './teile/Rueckmeldungen.svelte';
  import Speicher from './teile/Speicher.svelte';

  lage.starten();
  let eigenesProtokoll = $state(false);

  const s = $derived(lage.stand);
  const laufen = $derived(s ? s.dienste.filter((d) => d.zustand === 'laeuft' || d.zustand === 'startet').length : 0);
  const gestoert = $derived(s ? s.dienste.filter((d) => d.zustand === 'gestoert').length : 0);
  const dienste_gb = $derived(s ? s.dienste.reduce((x, d) => x + (d.gb_jetzt ?? 0), 0) : 0);

  $effect(() => {
    document.title = s ? `Maschinenraum ${s.rechner}` : 'Maschinenraum';
  });
</script>

<div class="mr-schale">
  <header class="mr-kopf">
    <div class="marke"><img class="marke-bild" src="/symbol.svg" alt="" />Maschinenraum{#if s}<span class="zahl">{s.version}</span>{/if}</div>
    {#if s}<span class="rechner"><i class="fa-solid fa-desktop"></i> {s.rechner}</span>{/if}
    <div class="kopf-aktionen">
      {#if s}<a class="zustand {VERBINDUNG[s.leitstelle.zustand].klasse}" href="#leitstelle" title={s.leitstelle.meldung || VERBINDUNG[s.leitstelle.zustand].wort}>
        <i class="fa-solid fa-tower-broadcast"></i>{VERBINDUNG[s.leitstelle.zustand].wort}</a>{/if}
      <button class="knopf ohne" class:aktiv={eigenesProtokoll} onclick={() => (eigenesProtokoll = !eigenesProtokoll)} title="Protokoll des Maschinenraums selbst"><i class="fa-solid fa-scroll"></i> Protokoll</button>
      <button class="knopf ohne symbol" onclick={() => ansicht.setzeThema(ansicht.thema === 'dunkel' ? 'hell' : 'dunkel')} title="Hell oder dunkel"><i class="fa-solid {ansicht.thema === 'dunkel' ? 'fa-sun' : 'fa-moon'}"></i></button>
    </div>
  </header>

  <main class="mr-rollfeld">
    {#if !lage.erreichbar}
      <div class="hinweis gefahr"><i class="fa-solid fa-plug-circle-xmark"></i><span>Der Maschinenraum antwortet nicht. Läuft er noch? Neuer Versuch alle zwei Sekunden.</span></div>
    {/if}
    {#if eigenesProtokoll}<section class="karte"><h3><i class="fa-solid fa-scroll"></i> Protokoll des Maschinenraums</h3><Protokoll /></section>{/if}

    {#if s}
      <div class="mr-raster">
        <section class="mr-dienste">
          <div class="seitenkopf"><h1>Dienste</h1><span class="zahl">{s.dienste.length}</span></div>
          <div class="kennzahlen">
            <div class="kennzahl erfolg"><b>{laufen}</b><span>Laufen</span></div>
            <div class="kennzahl"><b>{s.dienste.length - laufen - gestoert}</b><span>Aus</span></div>
            {#if gestoert}<div class="kennzahl fehler"><b>{gestoert}</b><span>Gestört</span></div>{/if}
            <div class="kennzahl"><b>{gb(dienste_gb)}</b><span>Speicher der Dienste</span></div>
          </div>
          {#each s.ladefehler as f (f.datei)}
            <div class="hinweis gefahr klein"><i class="fa-solid fa-file-circle-exclamation"></i><span>Dienstdatei <b>{f.datei}</b> wird übergangen: {f.meldung}</span></div>
          {/each}
          {#each s.dienste as d (d.kennung)}
            <DienstKarte dienst={d} />
          {:else}
            <div class="leer"><i class="fa-solid fa-gears"></i><h2>Noch keine Dienste</h2>
              <p>Je Dienst eine Datei im Ordner <span class="code">{s.ordner}/dienste</span> anlegen: Name, Arbeitsordner, Befehl, Port. Der Maschinenraum liest sie im nächsten Takt.</p></div>
          {/each}
        </section>

        <aside class="mr-seite">
          <Speicher stand={s} />
          {#if s.nachbar.adresse}
            <section class="karte">
              <h3><i class="fa-solid fa-microchip"></i> Modell-Läufer <span class="rechts">{s.nachbar.erreichbar ? `${s.nachbar.modelle.length} geladen` : 'nicht erreichbar'}</span></h3>
              {#if s.nachbar.erreichbar}
                {#if s.nachbar.modelle.length}
                  <ul class="liste">{#each s.nachbar.modelle as m (m.name)}<li><span>{m.name}</span><b class="zahl">{gb(m.gb)}</b></li>{/each}</ul>
                {:else}<p class="leise klein">Kein Modell geladen.</p>{/if}
                <p class="schwach klein">Laden und Entladen verwaltet der Modell-Läufer selbst; hier steht er nur, damit der Speicher vollständig ist.</p>
              {:else}<p class="leise klein">Unter <span class="zahl">{s.nachbar.adresse}</span> antwortet keiner.</p>{/if}
            </section>
          {/if}
          <LeitstelleFeld stand={s} />
          <section class="karte">
            <h3><i class="fa-solid fa-folder-open"></i> Ordner</h3>
            <p class="klein"><span class="code">{s.ordner}</span></p>
            <p class="leise klein">Dienste stehen unter <span class="code">dienste/</span>, je Dienst eine Datei. Ausgaben unter <span class="code">protokolle/</span>.</p>
          </section>
        </aside>
      </div>
    {:else if lage.erreichbar}
      <p class="leise">Lade.</p>
    {/if}
  </main>
  <Rueckmeldungen />
</div>
