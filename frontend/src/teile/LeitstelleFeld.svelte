<script lang="ts">
  // Verbindung zur Leitstelle: optional. Adresse und Schlüssel eintragen, trennen. Der Schlüssel wird nie angezeigt,
  // nur ersetzt; er liegt in der Datei schluessel im Ordner des Maschinenraums.
  import { api } from '../lib/api';
  import { vor } from '../lib/format';
  import { tun } from '../lib/meldung.svelte';
  import { lage } from '../lib/stand.svelte';
  import type { Stand } from '../lib/typen.gen';
  import { VERBINDUNG } from '../lib/wort';

  let { stand }: { stand: Stand } = $props();

  const l = $derived(stand.leitstelle);
  let bearbeiten = $state(false);
  let adresse = $state('');
  let schluessel = $state('');
  let sichtbar = $state(false);

  function oeffnen() {
    adresse = l.adresse ?? '';
    schluessel = '';
    bearbeiten = true;
  }

  async function speichern() {
    const r = await tun(() => api.leitstelle({ adresse, schluessel: schluessel || null }), 'Leitstelle eingetragen');
    if (r) { bearbeiten = false; schluessel = ''; await lage.jetzt(); }
  }

  async function trennen() {
    const r = await tun(() => api.leitstelle({ adresse: null, schluessel: '' }), 'Ohne Leitstelle');
    if (r) { bearbeiten = false; await lage.jetzt(); }
  }
</script>

<section class="karte" id="leitstelle">
  <h3><i class="fa-solid fa-tower-broadcast"></i> Leitstelle <span class="rechts"><span class="zustand {VERBINDUNG[l.zustand].klasse}">{VERBINDUNG[l.zustand].wort}</span></span></h3>
  {#if l.adresse}
    <p class="leise klein">Adresse <span class="zahl">{l.adresse}</span>{#if l.name}, geführt als <b>{l.name}</b>{/if}{#if l.seit}, seit {vor(l.seit, stand.zeit)}{/if}</p>
    {#if l.meldung}<p class="klein akzent">{l.meldung}</p>{/if}
  {:else}
    <p class="leise klein">Der Maschinenraum arbeitet für sich. Mit einer Leitstelle kann sie seine Dienste mit einplanen, starten und anhalten.</p>
  {/if}

  {#if bearbeiten}
    <div class="felder">
      <label class="feld-l"><span>Adresse <small>zum Beispiel http://leitstelle:8530</small></span>
        <input class="eingabe" bind:value={adresse} placeholder="http://" /></label>
      <label class="feld-l"><span>Schlüssel <small>aus der Leitstelle, Seite Knoten; leer lassen: unverändert</small></span>
        <span class="mit-auge"><input class="eingabe zahl" type={sichtbar ? 'text' : 'password'} bind:value={schluessel} autocomplete="off" />
          <button class="knopf symbol ohne" onclick={() => (sichtbar = !sichtbar)} aria-label="Schlüssel zeigen"><i class="fa-solid {sichtbar ? 'fa-eye-slash' : 'fa-eye'}"></i></button></span></label>
    </div>
    <div class="knoepfe">
      <button class="knopf haupt" onclick={speichern}><i class="fa-solid fa-plug"></i> Verbinden</button>
      <button class="knopf ohne" onclick={() => (bearbeiten = false)}>Abbrechen</button>
      {#if l.adresse}<button class="knopf ohne gefahr" onclick={trennen} title="Adresse und Schlüssel entfernen">Ohne Leitstelle</button>{/if}
    </div>
  {:else}
    <div class="knoepfe"><button class="knopf klein" onclick={oeffnen}><i class="fa-solid fa-pen"></i> {l.adresse ? 'Ändern' : 'Leitstelle eintragen'}</button></div>
  {/if}
</section>

<style>
  .felder { display: grid; gap: var(--mr-a3); margin-top: var(--mr-a3); }
  .mit-auge { display: flex; gap: var(--mr-a1); }
  .mit-auge input { flex: 1; min-width: 0; }
  .knoepfe { display: flex; gap: var(--mr-a2); flex-wrap: wrap; margin-top: var(--mr-a3); }
</style>
