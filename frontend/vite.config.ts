import { readFileSync } from 'node:fs';
import { svelte } from '@sveltejs/vite-plugin-svelte';
import { defineConfig } from 'vite';
import { MARKE, marke } from './marke';

// Entwicklung: Oberfläche auf 5540, Schnittstelle vom laufenden Maschinenraum auf 8540.
// Gebaut wird direkt ins Python-Paket, das die Oberfläche selbst ausliefert.
const dienst = process.env.MASCHINENRAUM ?? 'http://127.0.0.1:8540';

// Fassung der gebauten Oberfläche aus der einzigen Quelle; weicht die des Dienstes ab, lädt die Oberfläche neu (lib/fassung.svelte.ts)
const FASSUNG = (JSON.parse(readFileSync(new URL('../version.json', import.meta.url), 'utf-8')) as { version: string }).version;

export default defineConfig({
  plugins: [svelte(), marke()],
  define: { __FASSUNG__: JSON.stringify(FASSUNG), __MARKE__: JSON.stringify(MARKE) },
  server: {
    port: 5540,
    strictPort: true,
    proxy: { '/api': { target: dienst, headers: { host: '127.0.0.1:8540' } } },
  },
  build: { outDir: '../maschinenraum/oberflaeche', emptyOutDir: true, chunkSizeWarningLimit: 900 },
});
