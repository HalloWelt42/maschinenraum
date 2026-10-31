// Zugriff auf die lokale Schnittstelle /api/*. Schreibende Aufrufe tragen den Kopf X-Maschinenraum,
// den fremde Webseiten nicht setzen dürfen, und zählen als laufende Arbeit, solange ihre Antwort aussteht.
import { arbeit } from './arbeit.svelte';
import type { BefehlErgebnis, Ergebnis, Fassung, LeitstellenDaten, LeitstellenStand, Protokollauszug, Stand } from './typen.gen';

export class ApiFehler extends Error {
  constructor(public grund: string, public begruendung: string, public status: number) {
    super(begruendung);
  }
}

function rufen<T>(pfad: string, methode = 'GET', daten?: unknown): Promise<T> {
  return methode === 'GET' ? senden<T>(pfad, methode, daten) : arbeit.rahmen(() => senden<T>(pfad, methode, daten));
}

async function senden<T>(pfad: string, methode: string, daten?: unknown): Promise<T> {
  const kopf: Record<string, string> = methode === 'GET' ? {} : { 'X-Maschinenraum': '1' };
  if (daten !== undefined) kopf['Content-Type'] = 'application/json';
  const antwort = await fetch(`/api${pfad}`, { method: methode, headers: kopf, body: daten === undefined ? undefined : JSON.stringify(daten) });
  const text = await antwort.text();
  const inhalt = text ? JSON.parse(text) : null;
  if (!antwort.ok) {
    const satz = inhalt?.meldung ?? (typeof inhalt?.detail === 'string' ? inhalt.detail : `Der Maschinenraum antwortet mit ${antwort.status}.`);
    throw new ApiFehler(inhalt?.grund ?? 'fehler', satz, antwort.status);
  }
  return inhalt as T;
}

export const api = {
  version: () => rufen<Fassung>('/version'),
  stand: () => rufen<Stand>('/stand'),
  starten: (k: string) => rufen<BefehlErgebnis>(`/dienste/${k}/starten`, 'POST'),
  anhalten: (k: string) => rufen<BefehlErgebnis>(`/dienste/${k}/anhalten`, 'POST'),
  neustarten: (k: string) => rufen<BefehlErgebnis>(`/dienste/${k}/neustarten`, 'POST'),
  entsperren: (k: string) => rufen<Ergebnis>(`/dienste/${k}/entsperren`, 'POST'),
  sperren: (k: string, grund: string) => rufen<Ergebnis>(`/dienste/${k}/sperren`, 'POST', { grund }),
  spitzenVerwerfen: (k: string) => rufen<Ergebnis>(`/dienste/${k}/spitzen_verwerfen`, 'POST'),
  protokoll: (k: string, zeilen = 300) => rufen<Protokollauszug>(`/dienste/${k}/protokoll?zeilen=${zeilen}`),
  eigenesProtokoll: (zeilen = 300) => rufen<Protokollauszug>(`/protokoll?zeilen=${zeilen}`),
  leitstelle: (d: LeitstellenDaten) => rufen<LeitstellenStand>('/leitstelle', 'PUT', d),
  betrieb: (k: string, s: 'starten' | 'anhalten' | 'neustarten') => rufen<Ergebnis>(`/betrieb/${k}/${s}`, 'POST'),
  betriebProtokoll: (k: string, zeilen = 300) => rufen<Protokollauszug>(`/betrieb/${k}/protokoll?zeilen=${zeilen}`),
};
