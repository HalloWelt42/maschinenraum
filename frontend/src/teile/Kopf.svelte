<script lang="ts">
  // Kopf wie in der Leitstelle: Marke links, rechts der Zustand der Verbindung zur Leitstelle (statt der Lage)
  import { lage } from '../lib/stand.svelte';
  import { VERBINDUNG } from '../lib/wort';
  import { weg } from '../lib/weg.svelte';

  const s = $derived(lage.stand);
  const verbindung = $derived(s ? VERBINDUNG[s.leitstelle.zustand] : null);
</script>

<header class="kopf">
  <div class="marke">
    <img class="marke-bild" src="/symbol.svg" alt="" />
    <span class="marke-name">{__MARKE__.name}</span>
    <span class="marke-zweck" title="Startet, misst und hält die KI-Dienste dieses Rechners"><span aria-hidden="true">·</span> {__MARKE__.zweck}</span>
    {#if s}<span class="zahl">{s.version}</span>{/if}
  </div>
  {#if s}<span class="rechner" title="Dieser Rechner"><i class="fa-solid fa-desktop"></i>{s.rechner}</span>{/if}

  <div class="kopf-aktionen">
    {#if !lage.erreichbar}
      <span class="lage engpass" title="Die Oberfläche bekommt keine Antwort vom Maschinenraum"><span class="punkt gefahr"></span>Keine Antwort</span>
    {:else if s && verbindung}
      <a class="lage {verbindung.lage}" href={weg.pfad('leitstelle')} onclick={(e) => weg.klick(e, 'leitstelle')}
         title={s.leitstelle.meldung || verbindung.wort}><span class="punkt" class:lebt={s.leitstelle.zustand === 'verbunden'} class:aus={s.leitstelle.zustand === 'aus'}></span>{verbindung.wort}</a>
    {/if}
  </div>
</header>

<style>
  .rechner { display: inline-flex; align-items: center; gap: var(--mr-a2); color: var(--mr-text-2); white-space: nowrap; }
  .rechner i { color: var(--mr-text-3); }
  a.lage { text-decoration: none; }
</style>
