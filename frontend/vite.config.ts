import { svelte } from '@sveltejs/vite-plugin-svelte';
import { defineConfig } from 'vite';

// Entwicklung: Oberfläche auf 5540, Schnittstelle vom laufenden Maschinenraum auf 8540.
// Gebaut wird direkt ins Python-Paket, das die Oberfläche selbst ausliefert.
const dienst = process.env.MASCHINENRAUM ?? 'http://127.0.0.1:8540';

export default defineConfig({
  plugins: [svelte()],
  server: {
    port: 5540,
    strictPort: true,
    proxy: { '/api': { target: dienst, headers: { host: '127.0.0.1:8540' } } },
  },
  build: { outDir: '../maschinenraum/oberflaeche', emptyOutDir: true, chunkSizeWarningLimit: 900 },
});
