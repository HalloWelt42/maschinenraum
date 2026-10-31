<script lang="ts">
  // Name eines Dienstes: das Modell vorn, die Aufgabe klein dahinter ("Whisper Large V3 · Spracherkennung"); ein Dienst
  // ohne Modell heißt nach seiner Aufgabe, dann bleibt sie leer (kommt fertig vom Maschinenraum)
  let { name, aufgabe = '' }: { name: string; aufgabe?: string } = $props();
  // Trenner als Ausdruck: Svelte kürzt das Leerzeichen am Anfang eines Elements weg ("Name· Aufgabe")
</script>

{name}{#if aufgabe}<span class="aufgabe">{` · ${aufgabe}`}</span>{/if}
