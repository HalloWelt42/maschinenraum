<script lang="ts">
  // Auslastungs-Ring: Anteil in Prozent, Farbe nach Stufe (ab 75 Warnung, ab 90 Gefahr)
  let { wert, name, titel = '' }: { wert: number; name: string; titel?: string } = $props();
  const rund = $derived(Math.max(0, Math.min(100, Math.round(wert))));
  const stufe = $derived(rund >= 90 ? 'gefahr' : rund >= 75 ? 'warnung' : '');
</script>

<div><div class="ring {stufe}" style="--wert:{rund}" title={titel || `${name}: ${rund} Prozent`}><b class="zahl">{rund}%</b></div>{name}</div>
