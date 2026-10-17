<script lang="ts">
  // Band für eine neue Fassung des Maschinenraums (lib/fassung.svelte.ts): sagt, wann sie von selbst lädt, und lädt auf Wunsch sofort.
  import { fassung, ruhig } from '../lib/fassung.svelte';

  const wann = $derived(ruhig() ? 'Beim nächsten Seitenwechsel lädt der Maschinenraum sie von selbst.'
    : 'Sie lädt von selbst, sobald die laufende Arbeit abgeschlossen ist.');
</script>

{#if fassung.neu}
  <div class="hinweis neue-fassung" role="status">
    <i class="fa-solid fa-rotate"></i>
    <span><b>Neue Fassung <span class="zahl">{fassung.neu}</span> ist da.</b> {wann}</span>
    <div class="rechts"><button class="knopf klein haupt" onclick={() => location.reload()}><i class="fa-solid fa-rotate"></i> Jetzt neu laden</button></div>
  </div>
{/if}

<style>
  .neue-fassung { flex: none; align-items: center; margin: var(--mr-a3) var(--mr-a6) 0; }
  .neue-fassung > i { margin-top: 0; }
</style>
