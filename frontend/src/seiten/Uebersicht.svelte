<script lang="ts">
  // Übersicht wie in der Leitstelle: Kennzahlen, links was läuft und was nicht, rechts Speicher, Leitstelle, Protokoll.
  import { gb, prozent } from '../lib/format';
  import type { Stand } from '../lib/typen.gen';
  import { VERBINDUNG, ZUSTAND, dienstfarbe } from '../lib/wort';
  import { weg } from '../lib/weg.svelte';
  import Protokoll from '../teile/Protokoll.svelte';
  import Schalter from '../teile/Schalter.svelte';
  import SpeicherKarte from '../teile/SpeicherKarte.svelte';

  let { stand: s }: { stand: Stand } = $props();

  const laufen = $derived(s.dienste.filter((d) => d.zustand === 'laeuft' || d.zustand === 'startet'));
  const gestoert = $derived(s.dienste.filter((d) => d.zustand === 'gestoert'));
  const arbeiten = $derived(s.dienste.filter((d) => d.aktiv));
  const jetzt_gb = $derived(s.dienste.reduce((x, d) => x + (d.gb_jetzt ?? 0), 0));
  const bedarf_gb = $derived(laufen.reduce((x, d) => x + d.bedarf_gb, 0));
  const satz = $derived(gestoert.length ? `${gestoert.length === 1 ? 'Ein Dienst ist' : `${gestoert.length} Dienste sind`} gestört`
    : laufen.length ? `${laufen.length === 1 ? 'ein Dienst läuft' : `${laufen.length} Dienste laufen`}${arbeiten.length ? `, ${arbeiten.length} arbeiten gerade` : ''}`
    : 'alles aus, kein Dienst belegt Speicher');
</script>

<div class="seiteninhalt seite-uebersicht">
  <div class="rahmen-kopf">
    <div class="seitenkopf"><h1>Übersicht</h1><span class="lagesatz" class:gefahr={gestoert.length > 0}>{satz}</span></div>
    <div class="kennzahlen">
      <div class="kennzahl erfolg"><b>{laufen.length}</b><span>Laufen</span>{#if arbeiten.length}<small>{arbeiten.length} arbeiten gerade</small>{/if}</div>
      <div class="kennzahl"><b>{s.dienste.length - laufen.length - gestoert.length}</b><span>Aus</span></div>
      {#if gestoert.length}<div class="kennzahl fehler"><b>{gestoert.length}</b><span>Gestört</span></div>{/if}
      <div class="kennzahl" title="Was die laufenden Dienste gerade belegen"><b>{gb(jetzt_gb)}</b><span>Dienste jetzt</span><small>Bedarf {gb(bedarf_gb)}</small></div>
      {#if s.messwerte}<div class="kennzahl" title="Belegter Speicher des ganzen Rechners"><b>{prozent(s.messwerte.speicher_belegt_gb / s.messwerte.speicher_gesamt_gb)}</b><span>Speicher belegt</span><small>{gb(s.messwerte.speicher_belegt_gb)} von {gb(s.messwerte.speicher_gesamt_gb)}</small></div>{/if}
    </div>
  </div>

  <div class="rollfeld">
    <div class="spalten-uebersicht">
      <div class="links">
        <section class="abschnitt">
          <div class="abschnitt-kopf"><h2>Dienste</h2><a class="mehr" href={weg.pfad('dienste')} onclick={(e) => weg.klick(e, 'dienste')}>Alle Dienste</a></div>
          {#each s.dienste as d (d.kennung)}
            {@const z = ZUSTAND[d.zustand]}
            <div class="dienstzeile" style="--f:{dienstfarbe(d.faehigkeiten)}">
              <span class="farbe"></span>
              <div class="name"><a href={weg.pfad('dienste')} onclick={(e) => weg.klick(e, 'dienste')}>{d.name}</a>
                <span class="zustand {z.klasse}"><i class="fa-solid {z.symbol}"></i>{z.wort}</span>
                {#if d.aktiv}<span class="arbeitet"><i class="fa-solid fa-gear fa-spin"></i> arbeitet</span>{/if}</div>
              <div class="werte" title="Jetzt belegt / Bedarf, mit dem die Leitstelle plant">
                <b class="zahl">{d.gb_jetzt != null ? gb(d.gb_jetzt) : '-'}</b><span>Bedarf {gb(d.bedarf_gb)}</span></div>
              <Schalter dienst={d} />
            </div>
          {:else}
            <p class="leise">Noch keine Dienste. Je Dienst eine Datei im Ordner <span class="code">{s.ordner}/dienste</span>.</p>
          {/each}
        </section>
        <section class="abschnitt">
          <div class="abschnitt-kopf"><h2>Protokoll</h2><a class="mehr" href={weg.pfad('protokoll')} onclick={(e) => weg.klick(e, 'protokoll')}>Ganzes Protokoll</a></div>
          <Protokoll zeilen={12} />
        </section>
      </div>
      <div class="rechts">
        <SpeicherKarte stand={s} />
        <section class="karte">
          <h3><i class="fa-solid fa-tower-broadcast"></i> Leitstelle <span class="rechts"><span class="zustand {VERBINDUNG[s.leitstelle.zustand].klasse}">{VERBINDUNG[s.leitstelle.zustand].wort}</span></span></h3>
          {#if s.leitstelle.adresse}
            <p class="leise klein">Anwendungen erreichen die Dienste nur über die Leitstelle unter <span class="zahl">{s.leitstelle.adresse}</span>.</p>
          {:else}
            <p class="leise klein">Der Maschinenraum arbeitet für sich. Mit einer Leitstelle geht jeder Zugriff auf die Dienste über sie.</p>
          {/if}
          <a class="knopf klein" href={weg.pfad('leitstelle')} onclick={(e) => weg.klick(e, 'leitstelle')}><i class="fa-solid fa-arrow-right"></i> Verbindung</a>
        </section>
      </div>
    </div>
  </div>
</div>

<style>
  .lagesatz { color: var(--mr-erfolg); font-weight: 600; padding-bottom: 4px; }
  .lagesatz.gefahr { color: var(--mr-gefahr); }
  .spalten-uebersicht { display: grid; grid-template-columns: minmax(0, 1fr) 420px; gap: var(--mr-a5); align-items: start; }
  .links, .rechts { display: flex; flex-direction: column; gap: var(--mr-a4); min-width: 0; }
  .abschnitt-kopf { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: var(--mr-a2); }
  .abschnitt-kopf .mehr { font-size: var(--mr-gr-klein); }
  .dienstzeile { display: grid; grid-template-columns: 6px minmax(0, 1fr) auto auto; align-items: center; gap: var(--mr-a3);
                 padding: var(--mr-a3) var(--mr-a4) var(--mr-a3) 0; background: var(--mr-karte); border-radius: var(--mr-ecke); }
  .dienstzeile + .dienstzeile { margin-top: var(--mr-a2); }
  .farbe { align-self: stretch; background: var(--f); border-radius: var(--mr-ecke) 0 0 var(--mr-ecke); }
  .name { display: flex; align-items: center; gap: var(--mr-a3); flex-wrap: wrap; min-width: 0; }
  .name a { color: var(--mr-text); font-weight: 600; }
  .arbeitet { color: var(--mr-akzent-schrift); font-size: var(--mr-gr-klein); }
  .werte { text-align: right; line-height: 1.2; }
  .werte b { display: block; font-weight: 600; }
  .werte span { font-size: var(--mr-gr-marke); color: var(--mr-text-3); }
  @media (max-width: 1100px) { .spalten-uebersicht { grid-template-columns: minmax(0, 1fr); } }
</style>
