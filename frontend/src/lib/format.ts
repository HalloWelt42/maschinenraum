// Deutsche Zahlen- und Zeitformate. Keine Abkürzungen außer Maßeinheiten (s, GB).

const ganz = new Intl.NumberFormat('de-DE');
const eins = new Intl.NumberFormat('de-DE', { minimumFractionDigits: 1, maximumFractionDigits: 1 });

export const zahl = (n: number | null | undefined): string => (n == null ? '-' : ganz.format(n));
/** Speicher: ab 1 GB mit einer Nachkommastelle, darunter in ganzen MB (sonst stünde 0,0 GB da) */
export const gb = (n: number | null | undefined): string => (n == null ? '-' : n < 1 ? `${ganz.format(Math.round(n * 1024))} MB` : `${eins.format(n)} GB`);
export const prozent = (anteil: number): string => `${ganz.format(Math.round(anteil * 100))} %`;
/** Zahl mit fester Zahl an Nachkommastellen, deutsches Komma */
export const komma = (n: number, stellen = 1): string => n.toLocaleString('de-DE', { minimumFractionDigits: stellen, maximumFractionDigits: stellen });

/** Dauer in Worten: 4 s, 2 Minuten 10 s, 3 Stunden 5 Minuten */
export function dauer(s: number | null | undefined): string {
  if (s == null || !isFinite(s)) return '-';
  if (s < 10) return `${eins.format(Math.max(0, s))} s`;
  if (s < 90) return `${Math.round(s)} s`;
  const min = Math.floor(s / 60);
  if (min < 60) return `${min} ${min === 1 ? 'Minute' : 'Minuten'}${s % 60 >= 1 && min < 10 ? ` ${Math.round(s % 60)} s` : ''}`;
  const std = Math.floor(min / 60);
  return `${std} ${std === 1 ? 'Stunde' : 'Stunden'}${min % 60 ? ` ${min % 60} ${min % 60 === 1 ? 'Minute' : 'Minuten'}` : ''}`;
}

/** Uhrzeit zu Sekunden seit 1970; älter als heute mit Tag */
export function uhrzeit(zeit_s: number | null | undefined, mitSekunden = false): string {
  if (zeit_s == null) return '-';
  const d = new Date(zeit_s * 1000);
  const heute = new Date();
  const zeit = d.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit', ...(mitSekunden ? { second: '2-digit' } : {}) });
  if (d.toDateString() === heute.toDateString()) return zeit;
  return `${d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' })} ${zeit}`;
}

/** vor 3 Minuten, vor 2 Stunden */
export function vor(zeit_s: number | null | undefined, jetzt_s: number): string {
  if (zeit_s == null) return 'nie';
  const s = Math.max(0, jetzt_s - zeit_s);
  return s < 5 ? 'gerade eben' : `vor ${dauer(s)}`;
}
