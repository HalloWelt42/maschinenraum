// Name und Kurzzweck der App: die einzige Quelle für Kopfzeile, Tab-Titel und Manifest der installierten Web-App.
// Der Kurzzweck unterscheidet die Programme des Verbunds, deren Namen ähnlich klingen (ein Begriff, höchstens vier
// Wörter). Das Menüleistensymbol liest den Namen aus dem Manifest, das hier entsteht.
import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import type { Plugin } from 'vite';

export const MARKE = { name: 'Maschinenraum', zweck: 'KI-Dienste' };
export const TITEL = `${MARKE.name} · ${MARKE.zweck}`;

const MANIFEST = 'site.webmanifest';

/** Das Manifest: Vorlage aus public/ (Farben, Symbole) mit Name und Kurzzweck; short_name bleibt der Name. */
function manifest(oeffentlich: string): string {
  const vorlage = JSON.parse(readFileSync(resolve(oeffentlich, MANIFEST), 'utf-8')) as Record<string, unknown>;
  delete vorlage.name;                   // Name und Kurzzweck kommen nur von hier
  delete vorlage.short_name;
  return JSON.stringify({ name: TITEL, short_name: MARKE.name, ...vorlage }, null, 2) + '\n';
}

/** Setzt %TITEL% und %NAME% in index.html und liefert das Manifest mit Name und Kurzzweck aus (Entwicklung) oder
 *  schreibt es über die Vorlage im gebauten Ordner. */
export function marke(): Plugin {
  let oeffentlich = '';
  let ziel = '';
  return {
    name: 'marke',
    configResolved(c) {
      oeffentlich = c.publicDir;
      ziel = resolve(c.root, c.build.outDir);
    },
    transformIndexHtml: (html) => html.replaceAll('%TITEL%', TITEL).replaceAll('%NAME%', MARKE.name),
    configureServer(server) {
      server.middlewares.use(`/${MANIFEST}`, (_anfrage, antwort) => {
        antwort.setHeader('Content-Type', 'application/manifest+json');
        antwort.end(manifest(oeffentlich));
      });
    },
    closeBundle() {
      writeFileSync(resolve(ziel, MANIFEST), manifest(oeffentlich));
    },
  };
}
