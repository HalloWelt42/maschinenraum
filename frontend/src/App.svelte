<script lang="ts">
  // Schale wie in der Leitstelle: Kopf, Seitenleiste mit Menü und Ansicht, Hauptbereich, Fußleiste.
  import { onMount } from 'svelte';
  import { fassungVerfolgen } from './lib/fassung.svelte';
  import { lage } from './lib/stand.svelte';
  import { weg } from './lib/weg.svelte';
  import Dienste from './seiten/Dienste.svelte';
  import Leitstelle from './seiten/Leitstelle.svelte';
  import Ordner from './seiten/Ordner.svelte';
  import Protokoll from './seiten/Protokoll.svelte';
  import Speicher from './seiten/Speicher.svelte';
  import Uebersicht from './seiten/Uebersicht.svelte';
  import Fuss from './teile/Fuss.svelte';
  import Kopf from './teile/Kopf.svelte';
  import NeueFassung from './teile/NeueFassung.svelte';
  import Rueckmeldungen from './teile/Rueckmeldungen.svelte';
  import Seitenleiste from './teile/Seitenleiste.svelte';

  lage.starten();
  // Neue Fassung des Maschinenraums: von selbst neu laden, sobald es nichts unterbricht
  onMount(fassungVerfolgen);
  const s = $derived(lage.stand);

  $effect(() => {
    document.title = s ? `Maschinenraum ${s.rechner}` : 'Maschinenraum';
  });
</script>

<div class="schale">
  <Kopf />
  <Seitenleiste />
  <main class="haupt rahmen" id="haupt">
    <NeueFassung />
    {#if !s}
      <div class="verbinden"><div class="leer"><i class="fa-solid fa-industry"></i>
        <h2>{lage.erreichbar ? 'Lade den Stand' : 'Der Maschinenraum antwortet nicht'}</h2>
        <p>{lage.erreichbar ? 'Einen Augenblick.' : 'Läuft er noch? Neuer Versuch alle zwei Sekunden.'}</p></div></div>
    {:else if weg.seite === 'uebersicht'}<Uebersicht stand={s} />
    {:else if weg.seite === 'dienste'}<Dienste stand={s} />
    {:else if weg.seite === 'speicher'}<Speicher stand={s} />
    {:else if weg.seite === 'leitstelle'}<Leitstelle stand={s} />
    {:else if weg.seite === 'protokoll'}<Protokoll stand={s} />
    {:else if weg.seite === 'ordner'}<Ordner stand={s} />
    {/if}
  </main>
  <Fuss />
</div>
<Rueckmeldungen />
