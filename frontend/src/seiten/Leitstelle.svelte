<script lang="ts">
  // Verbindung zur Leitstelle und der Weg, über den sie die Dienste erreicht (Durchleitung).
  import type { Stand } from '../lib/typen.gen';
  import LeitstelleFeld from '../teile/LeitstelleFeld.svelte';

  let { stand: s }: { stand: Stand } = $props();
  const d = $derived(s.einstellungen.durchleitung);
</script>

<div class="seiteninhalt seite-leitstelle">
  <div class="rahmen-kopf">
    <div class="seitenkopf"><h1>Leitstelle</h1>
      <p class="unterzeile">Mit einer Leitstelle geht jeder Zugriff auf die Dienste über sie: Anwendungen rufen die Leitstelle, die Leitstelle startet, misst und erreicht die Dienste über diesen Maschinenraum.</p></div>
  </div>
  <div class="rollfeld">
    <div class="spalten-leitstelle">
      <LeitstelleFeld stand={s} />
      <section class="karte">
        <h3><i class="fa-solid fa-route"></i> Durchleitung</h3>
        <dl class="angaben">
          <dt>Port</dt><dd class="zahl">{d.port}</dd>
          <dt>Erreichbar über</dt><dd class="zahl">{d.adresse === '0.0.0.0' ? 'alle Netzadressen dieses Rechners' : d.adresse}</dd>
          <dt>Zugang</dt><dd>nur mit dem Schlüssel dieses Maschinenraums, also nur für die eingetragene Leitstelle</dd>
          <dt>Dienste</dt><dd>lauschen nur auf diesem Rechner; die Durchleitung reicht Anfrage und Antwort unverändert weiter</dd>
        </dl>
        <p class="leise klein">Anwendungen rufen <span class="code">/v1/dienste/&lt;kennung&gt;/&lt;pfad&gt;</span> an der Leitstelle; die Kennung ist der Dateiname der Dienstdatei.</p>
      </section>
    </div>
  </div>
</div>

<style>
  .spalten-leitstelle { display: grid; grid-template-columns: repeat(auto-fit, minmax(360px, 1fr)); gap: var(--mr-a4); align-items: start; max-width: 1200px; }
  .spalten-leitstelle :global(.karte) { margin: 0; }
  .angaben { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: var(--mr-a2) var(--mr-a4); margin: 0 0 var(--mr-a3); font-size: var(--mr-gr-klein); }
  .angaben dt { color: var(--mr-text-3); }
  .angaben dd { margin: 0; }
</style>
