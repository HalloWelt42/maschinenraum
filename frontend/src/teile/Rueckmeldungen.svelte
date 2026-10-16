<script lang="ts">
  import { meldungen } from '../lib/meldung.svelte';
</script>

<div class="rueckmeldungen" aria-live="polite">
  {#each meldungen.liste as m (m.nummer)}
    <div class="meldung {m.art}">
      <i class="fa-solid {m.art === 'fehler' ? 'fa-triangle-exclamation' : m.art === 'hinweis' ? 'fa-circle-info' : 'fa-check'}"></i>
      <span>{m.text}</span>
      <button class="knopf ohne symbol klein" onclick={() => meldungen.weg(m.nummer)} aria-label="Schließen"><i class="fa-solid fa-xmark"></i></button>
    </div>
  {/each}
</div>
