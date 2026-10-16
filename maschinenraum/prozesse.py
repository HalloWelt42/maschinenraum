"""Dienstverwaltung des Maschinenraums: starten, anhalten, beobachten, nach Absturz begrenzt neu starten.

Isolation je Dienst: eigene Sitzung und Prozessgruppe (Anhalten trifft genau diese Gruppe), eigener
Arbeitsordner, eigene Umgebung (nur Pfad, Heimordner, Sprache und was die Dienstdatei nennt), eigene
Protokolldatei. Grafikbeschleunigte Dienste laufen auf dem Mac nativ, weil Container dort keinen Zugriff
auf die Grafik haben.

Sollzustand und Prozessgruppe stehen in zustand.json: nach einem Neustart des Maschinenraums oder des Rechners
startet er, was laufen soll, und erkennt eigene Gruppen wieder (nur innerhalb derselben Systemlaufzeit).
Ein Dienst, der schon auf seinem Port antwortet, ohne vom Maschinenraum gestartet zu sein, gilt als fremd
gestartet: er wird übernommen, nicht doppelt gestartet; Anhalten trifft dann den lauschenden Prozess und
seine Nachfahren, nie dessen ganze Gruppe.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request
from collections import deque
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field

from .konfig import DienstVorlage, Einstellungen, Ladefehler, Ordner, Steuerung, erweitern, umgebung_lesen
from .messen import GIB, MAC, Prozesstabelle, lauschender_prozess, prozess_bytes
from .protokoll import Befehl, BefehlErgebnis, Befehlsart, Dienstliste, ProzessBericht, Prozesszustand

log = logging.getLogger("maschinenraum")
PROTOKOLL_GRENZE = 20 * 1024 * 1024
WARTESCHRITT_S = 0.5


class Soll(str, Enum):
    LAEUFT = "laeuft"
    AUS = "aus"


class DienstStand(BaseModel):
    soll: Soll | None = None             # None: hier wurde nie etwas entschieden, der Dienst wird nur übernommen
    spitze_gb: float | None = None
    gruppe: int | None = None


class Gesamtstand(BaseModel):
    systemstart: int | None = None
    dienste: dict[str, DienstStand] = Field(default_factory=dict)


def systemstart() -> int | None:
    """Startzeitpunkt des Rechners in Sekunden; schützt davor, eine alte Prozessgruppe nach Neustart wiederzuerkennen."""
    try:
        if MAC:
            ausgabe = subprocess.run(["sysctl", "-n", "kern.boottime"], capture_output=True, text=True, timeout=5).stdout
            return int(re.search(r"sec = (\d+)", ausgabe).group(1))
        for zeile in Path("/proc/stat").read_text().splitlines():
            if zeile.startswith("btime "):
                return int(zeile.split()[1])
    except (OSError, AttributeError, ValueError, subprocess.SubprocessError):
        pass
    return None


def _lebt(pgid: int, tabelle: Prozesstabelle) -> bool:
    return bool(tabelle.in_gruppe(pgid))


def _signal_gruppe(pgid: int, sig: int) -> None:
    try:
        os.killpg(pgid, sig)
    except (ProcessLookupError, PermissionError):   # macOS: Gruppe nur noch aus Zombies meldet "nicht erlaubt"
        pass


def _signal_prozesse(pids: list[int], sig: int) -> None:
    for pid in pids:
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            pass


class Prozessdienst:
    def __init__(self, vorlage: DienstVorlage, protokolle: Path, stand: DienstStand) -> None:
        self.vorlage = vorlage
        self.protokolle = protokolle
        self.stand = stand
        self.zustand = Prozesszustand.AUS
        self.fremd_pid: int | None = None
        self.prozess: subprocess.Popen | None = None    # nur zum Abholen des Rückgabewerts
        self.meldung = ""
        self.gb: float | None = None
        self.sperre = asyncio.Lock()
        self.abstuerze: deque[float] = deque()
        self.neustart_um: float | None = None
        self.cpu_prozent: float | None = None             # Prozessorlast seit der letzten Prüfung, Prozent eines Kerns
        self._rechenzeit: tuple[float, float] | None = None  # (Uhrzeit, Summe Rechenzeit) der letzten Prüfung

    @property
    def kennung(self) -> str:
        return self.vorlage.kennung

    # ── Beobachten ───────────────────────────────────────────────────────
    def erreichbar(self) -> bool:
        v = self.vorlage
        if v.pruefbefehl:
            try:
                return subprocess.run([erweitern(t, self._umgebung()) for t in v.pruefbefehl], cwd=v.ordner, env=self._umgebung(),
                                      stdin=subprocess.DEVNULL, capture_output=True, timeout=15).returncode == 0
            except (OSError, subprocess.SubprocessError):
                return False
        if v.pruefadresse:
            try:
                with urllib.request.urlopen(v.pruefadresse, timeout=2) as antwort:
                    return antwort.status < 500
            except urllib.error.HTTPError as f:
                return f.code < 500
            except (OSError, ValueError):
                return False
        if v.port:
            for familie, adresse in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
                try:
                    with socket.socket(familie, socket.SOCK_STREAM) as s:
                        s.settimeout(0.5)
                        if s.connect_ex((adresse, v.port)) == 0:
                            return True
                except OSError:
                    continue
            return False
        return self.stand.gruppe is not None

    def pruefen(self, tabelle: Prozesstabelle) -> str | None:
        """Stand aus der Prozesstabelle und der Erreichbarkeit. Rückgabe: Absturzmeldung, wenn eine eigene Gruppe
        unerwartet endete."""
        if self.vorlage.steuerung == Steuerung.BEFEHLE:
            return self._pruefen_befehle(tabelle)
        if self.prozess and self.prozess.poll() is not None:
            code, self.prozess = self.prozess.returncode, None
        else:
            code = None
        g = self.stand.gruppe
        if g is not None and _lebt(g, tabelle):
            self.fremd_pid = None
            if self.zustand == Prozesszustand.AUS or self.zustand == Prozesszustand.GESTOERT:
                self.zustand = Prozesszustand.LAEUFT
            self._messen(tabelle.in_gruppe(g), tabelle)
            return None
        if g is not None:                                   # eigene Gruppe ist weg
            self.stand.gruppe = None
            self._messen([], tabelle)
            if self.zustand in (Prozesszustand.LAEUFT, Prozesszustand.STARTET):
                self.zustand = Prozesszustand.GESTOERT
                self.meldung = f"unerwartet beendet{f' (Code {code})' if code is not None else ''}{self._letzte_zeile()}"
                return self.meldung
            self.zustand = Prozesszustand.AUS
            return None
        if self.zustand == Prozesszustand.GESTOERT:
            return None
        if self.vorlage.port and self.erreichbar():
            self.fremd_pid = lauschender_prozess(self.vorlage.port)
            self.zustand = Prozesszustand.LAEUFT
            self._messen(tabelle.mit_nachfahren(self.fremd_pid) if self.fremd_pid else [], tabelle)
            self.meldung = "von außen gestartet" if self.fremd_pid else "von außen gestartet, Prozess nicht lesbar"
        else:
            self.fremd_pid = None
            self._messen([], tabelle)
            if self.zustand == Prozesszustand.LAEUFT:
                self.meldung = "von außen beendet"
            self.zustand = Prozesszustand.AUS
        return None

    def _pruefen_befehle(self, tabelle: Prozesstabelle) -> None:
        """Befehlsdienst: er läuft, wenn die Prüfung gelingt; gemessen wird, was zum Prozessmuster passt."""
        if self.erreichbar():
            if self.zustand != Prozesszustand.LAEUFT:
                self.zustand, self.meldung = Prozesszustand.LAEUFT, ""
            self._messen(tabelle.passend(self.vorlage.prozessmuster) if self.vorlage.prozessmuster else [], tabelle)
        else:
            if self.zustand == Prozesszustand.LAEUFT:
                self.meldung = "läuft nicht mehr"
            if self.zustand != Prozesszustand.GESTOERT:
                self.zustand = Prozesszustand.AUS
            self._messen([], tabelle)
        return None

    def _befehl_ausfuehren(self, befehl: list[str], grenze_s: float) -> None:
        """Einmaliger Befehl (Start oder Anhalten eines Befehlsdienstes), Ausgabe ins Protokoll des Dienstes, in eigener
        Sitzung, damit nichts davon an der Prozessgruppe des Maschinenraums hängt."""
        env = self._umgebung()
        with self._protokoll_oeffnen() as aus:
            aus.write(f"\n--- {' '.join(befehl)} ({time.strftime('%Y-%m-%d %H:%M:%S')}) ---\n".encode())
            aus.flush()
            subprocess.run([erweitern(t, env) for t in befehl], cwd=self.vorlage.ordner, env=env, stdin=subprocess.DEVNULL, stdout=aus,
                           stderr=subprocess.STDOUT, timeout=grenze_s, check=True, start_new_session=True)

    def _messen(self, pids: list[int], tabelle: Prozesstabelle) -> None:
        """Speicher und Prozessorlast der Prozesse des Dienstes; ohne Prozesse ist beides leer."""
        if not pids:
            self.gb, self.cpu_prozent, self._rechenzeit = None, None, None
            return
        self.gb = sum(prozess_bytes(p) for p in pids) / GIB
        jetzt, summe = time.monotonic(), sum(tabelle.rechenzeit_s.get(p, 0.0) for p in pids)
        if self._rechenzeit and jetzt > self._rechenzeit[0]:
            self.cpu_prozent = round(max(0.0, summe - self._rechenzeit[1]) / (jetzt - self._rechenzeit[0]) * 100, 1)
        self._rechenzeit = (jetzt, summe)

    @property
    def fuer_leitstelle(self) -> bool:
        """Die Leitstelle vermittelt nur Fähigkeiten. Programme ohne Fähigkeit (Oberflächen, Backends von Anwendungen,
        Abholer) verwaltet nur der Maschinenraum; die Leitstelle sieht und schaltet sie nicht."""
        return bool(self.vorlage.faehigkeiten)

    @property
    def aktiv(self) -> bool:
        return self.cpu_prozent is not None and self.cpu_prozent >= self.vorlage.aktiv_ab_prozent

    @property
    def bedarf_gb(self) -> float:
        """Was der Dienst laufend braucht: der höchste je gemessene Wert, mindestens die Schätzung der Dienstdatei.
        Dienste laden ihre Modelle oft erst bei Bedarf; der Wert gleich nach dem Start täuscht."""
        return round(max(self.stand.spitze_gb or 0.0, self.vorlage.speicher_gb, self.gb or 0.0), 2)

    def _protokolldatei(self) -> Path:
        return self.protokolle / f"{self.kennung}.log"

    def _letzte_zeile(self) -> str:
        try:
            zeilen = [z for z in self._protokolldatei().read_text(encoding="utf-8", errors="replace").splitlines() if z.strip()]
            return f"; zuletzt: {zeilen[-1].strip()[:160]}" if zeilen else ""
        except OSError:
            return ""

    # ── Starten ──────────────────────────────────────────────────────────
    def _umgebung(self) -> dict[str, str]:
        v = self.vorlage
        env = {"PATH": v.pfad, "HOME": os.environ.get("HOME", ""), "USER": os.environ.get("USER", ""),
               "LANG": os.environ.get("LANG", "de_DE.UTF-8"), "TMPDIR": os.environ.get("TMPDIR", "/tmp")}
        if v.umgebung_datei:
            env.update(umgebung_lesen(v.umgebung_datei))
        for name, wert in v.umgebung.items():
            env[name] = erweitern(wert, env)
        return env

    def _protokoll_oeffnen(self):
        datei = self._protokolldatei()
        datei.parent.mkdir(parents=True, exist_ok=True)
        if datei.exists() and datei.stat().st_size > PROTOKOLL_GRENZE:
            datei.replace(datei.with_suffix(".log.1"))
        return open(datei, "ab")

    def _vorher(self, env: dict[str, str]) -> None:
        v = self.vorlage
        if not v.vorher:
            return
        befehl = [erweitern(t, env) for t in v.vorher]
        if "/" in befehl[0] and not os.path.isabs(befehl[0]):
            befehl[0] = str(v.ordner / befehl[0])
        with self._protokoll_oeffnen() as aus:
            subprocess.run(befehl, cwd=v.ordner, env=env, stdin=subprocess.DEVNULL, stdout=aus, stderr=subprocess.STDOUT,
                           timeout=v.startzeit_s, check=True)

    def _ausfuehren(self) -> None:
        v = self.vorlage
        env = self._umgebung()
        self._vorher(env)
        with self._protokoll_oeffnen() as aus:
            aus.write(f"\n--- gestartet vom Maschinenraum {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n".encode())
            aus.flush()
            self.prozess = subprocess.Popen(v.programm(env), cwd=v.ordner, env=env, stdin=subprocess.DEVNULL, stdout=aus, stderr=subprocess.STDOUT,
                                            start_new_session=True)
        self.stand.gruppe = self.prozess.pid

    async def starten(self) -> tuple[bool, str]:
        async with self.sperre:
            self.neustart_um = None
            if self.zustand == Prozesszustand.LAEUFT:
                return True, "läuft bereits"
            if self.vorlage.port and await asyncio.to_thread(self.erreichbar):
                return True, "läuft bereits (von außen gestartet)"
            if not self.vorlage.ordner.is_dir():
                return self._gestoert(f"Arbeitsordner fehlt: {self.vorlage.ordner}")
            self.zustand, self.meldung = Prozesszustand.STARTET, ""
            if self.vorlage.steuerung == Steuerung.BEFEHLE:
                return await self._starten_befehle()
            try:
                await asyncio.to_thread(self._ausfuehren)
            except subprocess.CalledProcessError as f:
                return self._gestoert(f"Vorlauf scheiterte mit Code {f.returncode}{self._letzte_zeile()}")
            except (OSError, subprocess.SubprocessError) as f:
                return self._gestoert(f"Start scheiterte: {f}")
            return await self._warten_bis_erreichbar()

    async def _starten_befehle(self) -> tuple[bool, str]:
        v = self.vorlage
        beginn = time.monotonic()
        try:
            await asyncio.to_thread(self._vorher, self._umgebung())
            await asyncio.to_thread(self._befehl_ausfuehren, v.befehl, v.startzeit_s)
        except subprocess.CalledProcessError as f:
            return self._gestoert(f"Startbefehl endete mit Code {f.returncode}{self._letzte_zeile()}")
        except (OSError, subprocess.SubprocessError) as f:
            return self._gestoert(f"Startbefehl scheiterte: {f}")
        while time.monotonic() - beginn < v.startzeit_s:
            if await asyncio.to_thread(self.erreichbar):
                self.zustand, self.meldung = Prozesszustand.LAEUFT, ""
                return True, f"gestartet in {time.monotonic() - beginn:.1f} s"
            await asyncio.sleep(1.0)
        return self._gestoert(f"nach {v.startzeit_s:.0f} s nicht erreichbar{self._letzte_zeile()}")

    async def _warten_bis_erreichbar(self) -> tuple[bool, str]:
        beginn = time.monotonic()
        while time.monotonic() - beginn < self.vorlage.startzeit_s:
            if self.prozess and self.prozess.poll() is not None:
                code = self.prozess.returncode
                self.prozess, self.stand.gruppe = None, None
                return self._gestoert(f"beim Start beendet mit Code {code}{self._letzte_zeile()}")
            if (self.vorlage.port or self.vorlage.pruefadresse) and await asyncio.to_thread(self.erreichbar):
                break
            if not (self.vorlage.port or self.vorlage.pruefadresse) and time.monotonic() - beginn >= 1:
                break
            await asyncio.sleep(WARTESCHRITT_S)
        else:
            await self._gruppe_beenden()
            return self._gestoert(f"nach {self.vorlage.startzeit_s:.0f} s nicht erreichbar; wieder beendet{self._letzte_zeile()}")
        self.zustand, self.meldung = Prozesszustand.LAEUFT, ""
        return True, f"gestartet in {time.monotonic() - beginn:.1f} s"

    def _gestoert(self, meldung: str) -> tuple[bool, str]:
        self.zustand, self.meldung = Prozesszustand.GESTOERT, meldung
        return False, meldung

    # ── Anhalten ─────────────────────────────────────────────────────────
    async def anhalten(self) -> tuple[bool, str]:
        async with self.sperre:
            self.neustart_um = None
            if self.vorlage.anhaltebefehl and (self.vorlage.steuerung == Steuerung.BEFEHLE or self.fremd_pid):
                return await self._anhalten_befehl()
            if self.stand.gruppe is not None:
                self.zustand = Prozesszustand.STOPPT
                hart = await self._gruppe_beenden()
            elif self.fremd_pid:
                self.zustand = Prozesszustand.STOPPT
                hart = await self._fremd_beenden(self.fremd_pid)
            else:
                self.zustand = Prozesszustand.AUS
                return True, "war schon aus"
            self.zustand, self.gb, self.fremd_pid, self.meldung = Prozesszustand.AUS, None, None, ""
            return True, "hart beendet" if hart else "beendet"

    async def _anhalten_befehl(self) -> tuple[bool, str]:
        """Anhalten mit dem eigenen Befehl, nie per Signal: bei Containern träfe ein Signal sonst die Portweiterleitung."""
        if not await asyncio.to_thread(self.erreichbar):
            self.zustand = Prozesszustand.AUS
            return True, "war schon aus"
        self.zustand = Prozesszustand.STOPPT
        try:
            await asyncio.to_thread(self._befehl_ausfuehren, self.vorlage.anhaltebefehl, self.vorlage.anhaltezeit_s)
        except (OSError, subprocess.SubprocessError) as f:
            return self._gestoert(f"Anhaltebefehl scheiterte: {f}{self._letzte_zeile()}")
        beginn = time.monotonic()
        while time.monotonic() - beginn < self.vorlage.anhaltezeit_s:
            if not await asyncio.to_thread(self.erreichbar):
                self.zustand, self.gb, self.fremd_pid, self.meldung = Prozesszustand.AUS, None, None, ""
                return True, "beendet"
            await asyncio.sleep(1.0)
        return self._gestoert(f"läuft nach dem Anhaltebefehl noch ({self.vorlage.anhaltezeit_s:.0f} s gewartet)")

    async def _gruppe_beenden(self) -> bool:
        g = self.stand.gruppe
        if g is None:
            return False
        _signal_gruppe(g, signal.SIGTERM)
        hart = not await self._warten(lambda t: not _lebt(g, t))
        if hart:
            _signal_gruppe(g, signal.SIGKILL)
            await self._warten(lambda t: not _lebt(g, t))
        if self.prozess:
            await asyncio.to_thread(self.prozess.wait)
            self.prozess = None
        self.stand.gruppe = None
        return hart

    async def _fremd_beenden(self, pid: int) -> bool:
        pids = (await asyncio.to_thread(Prozesstabelle)).mit_nachfahren(pid)
        _signal_prozesse(pids, signal.SIGTERM)
        hart = not await self._warten(lambda t: not any(p in t.eltern for p in pids))
        if hart:
            _signal_prozesse(pids, signal.SIGKILL)
            await self._warten(lambda t: not any(p in t.eltern for p in pids))
        return hart

    async def _warten(self, fertig) -> bool:
        beginn = time.monotonic()
        while time.monotonic() - beginn < self.vorlage.anhaltezeit_s:
            if self.prozess:
                self.prozess.poll()                         # eigenes Kind abholen, sonst bleibt es als Zombie in der Tabelle
            if fertig(await asyncio.to_thread(Prozesstabelle)):
                return True
            await asyncio.sleep(WARTESCHRITT_S)
        return False

    # ── Bericht ──────────────────────────────────────────────────────────
    def bericht(self) -> ProzessBericht:
        laeuft = self.zustand in (Prozesszustand.LAEUFT, Prozesszustand.STARTET, Prozesszustand.STOPPT)
        return ProzessBericht(kennung=self.kennung, name=self.vorlage.name, faehigkeiten=set(self.vorlage.faehigkeiten), port=self.vorlage.port,
                              zustand=self.zustand, fremd=self.fremd_pid is not None,
                              gb_jetzt=round(self.gb, 2) if laeuft and self.gb is not None else None, bedarf_gb=self.bedarf_gb,
                              aktiv=laeuft and self.aktiv, anhalten_erlaubt=self.vorlage.leitstelle_anhalten, meldung=self.meldung)


class Verwalter:
    """Alle Dienste des Ordners. Läuft unabhängig von Oberfläche und Leitstelle."""

    def __init__(self, ordner: Ordner, einstellungen: Einstellungen) -> None:
        self.ordner = ordner
        self.einstellungen = einstellungen
        self.dienste: dict[str, Prozessdienst] = {}
        self.ladefehler: list[Ladefehler] = []
        self.stand = self._stand_lesen()
        self.aenderung = asyncio.Event()
        self._aufgaben: set[asyncio.Task] = set()

    def _stand_lesen(self) -> Gesamtstand:
        jetzt = systemstart()
        try:
            stand = Gesamtstand.model_validate_json(self.ordner.zustand_datei.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            stand = Gesamtstand()
        if stand.systemstart != jetzt:                      # Rechner neu gestartet: alte Gruppen gelten nicht mehr
            for d in stand.dienste.values():
                d.gruppe = None
            stand.systemstart = jetzt
        return stand

    def _stand_speichern(self) -> None:
        datei = self.ordner.zustand_datei
        neu = datei.with_suffix(".json.neu")
        neu.write_text(self.stand.model_dump_json(indent=2), encoding="utf-8")
        neu.replace(datei)

    def _dateien_lesen(self) -> bool:
        vorlagen, fehler = self.ordner.dienste()
        geaendert = [f.model_dump() for f in fehler] != [f.model_dump() for f in self.ladefehler]
        for f in fehler:
            if f not in self.ladefehler:
                log.warning("Dienstdatei %s fehlerhaft: %s", f.datei, f.meldung)
        self.ladefehler = fehler
        neu = {v.kennung: v for v in vorlagen}
        for k in list(self.dienste):
            if k not in neu:
                d = self.dienste.pop(k)
                if d.stand.gruppe is not None:
                    self._nebenbei(d.anhalten())
                geaendert = True
        for k, v in neu.items():
            if k in self.dienste:
                if self.dienste[k].vorlage != v:
                    self.dienste[k].vorlage, geaendert = v, True
            else:
                stand = self.stand.dienste.setdefault(k, DienstStand())
                self.dienste[k] = Prozessdienst(v, self.ordner.protokolle, stand)
                geaendert = True
        return geaendert

    def _nebenbei(self, coro) -> None:
        t = asyncio.create_task(coro)
        self._aufgaben.add(t)
        t.add_done_callback(self._aufgaben.discard)

    async def runde(self) -> None:
        """Einmal alles prüfen: Dateien, Prozesse, Abstürze, fällige Neustarts, Höchstwerte."""
        geaendert = self._dateien_lesen()
        tabelle = await asyncio.to_thread(Prozesstabelle)
        jetzt = time.monotonic()
        for d in self.dienste.values():
            if d.sperre.locked():
                continue
            vorher = d.bericht()
            absturz = await asyncio.to_thread(d.pruefen, tabelle)
            if absturz:
                self._absturz(d, jetzt)
            if d.neustart_um is not None and jetzt >= d.neustart_um:
                d.neustart_um = None
                self._nebenbei(self._neustarten(d))
            if d.gb is not None and d.gb > (d.stand.spitze_gb or 0):
                d.stand.spitze_gb = round(d.gb, 2)
            # Messwerte schwanken ständig; gemeldet wird nur, was sich in der Sache ändert (Zustand, Arbeit, Bedarf)
            geaendert = geaendert or d.bericht().model_dump(exclude={"gb_jetzt"}) != vorher.model_dump(exclude={"gb_jetzt"})
        self._stand_speichern()
        if geaendert:
            self.aenderung.set()

    def _absturz(self, d: Prozessdienst, jetzt: float) -> None:
        k = self.einstellungen.neustart
        log.warning("%s: %s", d.vorlage.name, d.meldung)
        if d.stand.soll != Soll.LAEUFT or not d.vorlage.neustart:
            return
        while d.abstuerze and jetzt - d.abstuerze[0] > k.fenster_s:
            d.abstuerze.popleft()
        d.abstuerze.append(jetzt)
        if len(d.abstuerze) > k.im_fenster:
            d.stand.soll = Soll.AUS
            d.meldung += f"; {len(d.abstuerze)} Abstürze in {k.fenster_s:.0f} s, bleibt aus bis zum nächsten Start von Hand"
            return
        pause = k.pausen_s[min(len(d.abstuerze) - 1, len(k.pausen_s) - 1)]
        d.neustart_um = jetzt + pause
        d.meldung += f"; Neustart in {pause:.0f} s"

    async def _mit_abhaengigkeiten(self, d: Prozessdienst, kette: tuple[str, ...] = ()) -> tuple[bool, str]:
        """Erst starten, was der Dienst braucht (der Reihe nach, ohne Kreise), dann ihn selbst."""
        for k in d.vorlage.braucht:
            vor = self.dienste.get(k)
            if vor is None:
                return d._gestoert(f"braucht {k}, den es hier nicht gibt")
            if k in kette or k == d.kennung:
                return d._gestoert(f"Abhängigkeiten im Kreis: {' -> '.join((*kette, d.kennung, k))}")
            if vor.zustand != Prozesszustand.LAEUFT:
                vor.stand.soll = Soll.LAEUFT
                ok, meldung = await self._mit_abhaengigkeiten(vor, (*kette, d.kennung))
                if not ok:
                    return d._gestoert(f"{vor.vorlage.name} startet nicht: {meldung}")
        return await d.starten()

    async def _neustarten(self, d: Prozessdienst) -> None:
        ok, meldung = await self._mit_abhaengigkeiten(d)
        log.info("%s: Neustart %s (%s)", d.vorlage.name, "gelungen" if ok else "gescheitert", meldung)
        self.aenderung.set()

    async def hochfahren(self) -> None:
        """Nach dem Start des Maschinenraums: Dateien lesen, Lage prüfen, starten was laufen soll."""
        await self.runde()
        for d in self.dienste.values():
            if d.stand.soll == Soll.LAEUFT and d.zustand == Prozesszustand.AUS:
                log.info("%s soll laufen: starte", d.vorlage.name)
                self._nebenbei(self._neustarten(d))

    async def schleife(self) -> None:
        await self.hochfahren()
        while True:
            await asyncio.sleep(self.einstellungen.messung.takt_s)
            try:
                await self.runde()
            except Exception:                                   # die Schleife darf nie sterben
                log.exception("Fehler in der Dienstprüfung")

    async def befehl(self, b: Befehl, von_leitstelle: bool = False) -> BefehlErgebnis:
        """Starten oder anhalten. Die Leitstelle darf nur anhalten, was die Dienstdatei ihr erlaubt; von Hand geht immer."""
        d = self.dienste.get(b.ziel)
        if d is None:
            return BefehlErgebnis(befehl=b.befehl, ziel=b.ziel, erfolg=False, meldung=f"unbekannter Dienst {b.ziel}")
        if von_leitstelle and not d.fuer_leitstelle:
            return BefehlErgebnis(befehl=b.befehl, ziel=b.ziel, erfolg=False, meldung="kein Dienst der Leitstelle (ohne Fähigkeit, nur hier verwaltet)")
        if von_leitstelle and b.befehl == Befehlsart.DIENST_ANHALTEN and not d.vorlage.leitstelle_anhalten:
            log.info("Leitstelle wollte %s anhalten; laut Dienstdatei nur von Hand", d.vorlage.name)
            return BefehlErgebnis(befehl=b.befehl, ziel=b.ziel, erfolg=False, meldung="Anhalten nur von Hand (Dienstdatei: leitstelle_anhalten = false)")
        if b.befehl == Befehlsart.DIENST_STARTEN:
            d.stand.soll = Soll.LAEUFT
            d.abstuerze.clear()
            ok, meldung = await self._mit_abhaengigkeiten(d)
        else:
            d.stand.soll = Soll.AUS
            ok, meldung = await d.anhalten()
        self._stand_speichern()
        self.aenderung.set()
        log.info("%s %s: %s", b.befehl.value, d.vorlage.name, meldung)
        return BefehlErgebnis(befehl=b.befehl, ziel=b.ziel, erfolg=ok, meldung=meldung)

    async def neu_starten(self, kennung: str) -> BefehlErgebnis:
        """Anhalten und wieder starten; nur aus der eigenen Oberfläche, nicht Teil des Leitstellen-Protokolls."""
        aus = await self.befehl(Befehl(befehl=Befehlsart.DIENST_ANHALTEN, ziel=kennung))
        if not aus.erfolg:
            return aus
        return await self.befehl(Befehl(befehl=Befehlsart.DIENST_STARTEN, ziel=kennung))

    def liste(self, nur_leitstelle: bool = False) -> Dienstliste:
        """Alle Dienste; für die Leitstelle nur die mit Fähigkeiten (sie vermittelt Fähigkeiten, sonst nichts)."""
        return Dienstliste(dienste=[d.bericht() for d in self.dienste.values() if d.fuer_leitstelle or not nur_leitstelle])

    async def beenden(self) -> None:
        for t in list(self._aufgaben):
            t.cancel()
