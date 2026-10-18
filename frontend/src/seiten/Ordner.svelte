<script lang="ts">
  // Wo alles liegt und was eingestellt ist. Geändert wird in den Dateien; neue Dienstdateien liest der Maschinenraum
  // im nächsten Takt, geänderte Einstellungen nach einem Neustart (die Leitstelle stellt man auf ihrer Seite ein).
  import type { Stand } from '../lib/typen.gen';

  let { stand: s }: { stand: Stand } = $props();
  const e = $derived(s.einstellungen);
  const pfade = $derived([
    ['Ordner', s.ordner, 'alles an einem Ort'],
    ['Einstellungen', `${s.ordner}/einstellungen.toml`, 'Oberfläche, Durchleitung, Messung, Neustartregeln, Schlaf, Leitstelle'],
    ['Dienste', `${s.ordner}/dienste/`, 'je KI-Dienst eine Datei; der Dateiname ist die Kennung'],
    ['Betrieb', `${s.ordner}/betrieb/`, 'Steuerprogramme wie das Stellwerk; tragen sich bei ihrer Installation ein'],
    ['Protokolle', `${s.ordner}/protokolle/`, 'Ausgabe des Maschinenraums und je Dienst eine Datei'],
    ['Zustand', `${s.ordner}/zustand.json`, 'Sollzustand je Dienst und gemessene Höchstwerte'],
  ]);
</script>

<div class="seiteninhalt seite-ordner">
  <div class="rahmen-kopf">
    <div class="seitenkopf"><h1>Ordner</h1>
      <p class="unterzeile">Neue oder geänderte Dienstdateien liest der Maschinenraum im nächsten Takt. Geänderte Einstellungen gelten nach einem Neustart des Maschinenraums.</p></div>
  </div>
  <div class="rollfeld">
    {#each s.ladefehler as f (f.datei)}
      <div class="hinweis gefahr klein"><i class="fa-solid fa-file-circle-exclamation"></i><span>Dienstdatei <b>{f.datei}</b> wird übergangen: {f.meldung}</span></div>
    {/each}
    <div class="spalten-ordner">
      <section class="karte">
        <h3><i class="fa-solid fa-folder-open"></i> Pfade</h3>
        <dl class="angaben">{#each pfade as [name, pfad, satz] (name)}<dt>{name}</dt><dd><span class="code">{pfad}</span><small>{satz}</small></dd>{/each}</dl>
      </section>
      <section class="karte">
        <h3><i class="fa-solid fa-sliders"></i> Einstellungen</h3>
        <dl class="angaben">
          <dt>Name</dt><dd>{e.name ?? s.rechner}</dd>
          <dt>Oberfläche</dt><dd class="zahl">{e.oberflaeche.adresse}:{e.oberflaeche.port}</dd>
          <dt>Durchleitung</dt><dd class="zahl">{e.durchleitung.adresse}:{e.durchleitung.port}</dd>
          <dt>Messtakt</dt><dd><span class="zahl">{e.messung.takt_s}</span> s{e.messung.macmon ? ', mit Zusatzmessungen, wenn vorhanden' : ''}</dd>
          <dt>Neustart nach Absturz</dt><dd>Pausen <span class="zahl">{e.neustart.pausen_s.join(', ')}</span> s, höchstens <span class="zahl">{e.neustart.im_fenster}</span> in <span class="zahl">{e.neustart.fenster_s}</span> s</dd>
          <dt>Modell-Läufer</dt><dd class="zahl">{e.nachbar.modell_laeufer ?? 'keiner'}</dd>
          <dt>Schlaf</dt><dd>{e.schlaf.melden ? 'der Leitstelle melden; Aufträge warten, bis der Rechner wach ist' : 'nicht melden'}
            <small>{e.schlaf.leerlauf_aufschieben ? 'Kein Leerlaufschlaf, solange die Leitstelle hier rechnen lässt; Deckel, Menü und Ein-Taste wirken weiter' : 'Leerlaufschlaf wie eingestellt, auch mitten in einem Auftrag'}</small></dd>
        </dl>
      </section>
    </div>
  </div>
</div>

<style>
  .spalten-ordner { display: grid; grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); gap: var(--mr-a4); align-items: start; }
  .spalten-ordner :global(.karte) { margin: 0; }
  .angaben { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: var(--mr-a3) var(--mr-a4); margin: 0; font-size: var(--mr-gr-klein); }
  .angaben dt { color: var(--mr-text-3); }
  .angaben dd { margin: 0; min-width: 0; overflow-wrap: anywhere; }
  .angaben small { display: block; color: var(--mr-text-3); font-size: var(--mr-gr-marke); margin-top: 2px; }
</style>
