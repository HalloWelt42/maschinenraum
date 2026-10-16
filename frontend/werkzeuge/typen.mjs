// Erzeugt src/lib/typen.gen.ts aus den Pydantic-Modellen des Maschinenraums (eine Wahrheit für beide Seiten).
// Aufruf: npm run typen (braucht .venv im Wurzelordner).
import { execFileSync } from 'node:child_process';
import { writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { compile } from 'json-schema-to-typescript';

const hier = dirname(fileURLToPath(import.meta.url));
const wurzel = resolve(hier, '../..');
const roh = execFileSync(resolve(wurzel, '.venv/bin/python'), ['-m', 'maschinenraum.schema'], { cwd: wurzel, encoding: 'utf8' });
const schema = JSON.parse(roh);

// Feldtitel entfernen, damit Felder inline typisiert werden statt je Feld einen eigenen Typnamen zu bekommen
function ohneFeldtitel(knoten, istModell) {
  if (Array.isArray(knoten)) return knoten.forEach((k) => ohneFeldtitel(k, false));
  if (!knoten || typeof knoten !== 'object') return;
  if (!istModell) delete knoten.title;
  for (const [k, v] of Object.entries(knoten)) {
    if (k === '$defs') for (const d of Object.values(v)) ohneFeldtitel(d, true);
    else if (k === 'properties') for (const p of Object.values(v)) ohneFeldtitel(p, false);
    else ohneFeldtitel(v, false);
  }
}
ohneFeldtitel(schema, true);

const ts = await compile(schema, 'Maschinenraum', {
  bannerComment: '// Erzeugt aus den Pydantic-Modellen des Maschinenraums (npm run typen). Nicht von Hand ändern.',
  additionalProperties: false, unreachableDefinitions: true, style: { singleQuote: true, printWidth: 140 },
});
writeFileSync(resolve(hier, '../src/lib/typen.gen.ts'), ts);
console.log('typen.gen.ts geschrieben');
