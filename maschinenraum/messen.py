"""Messwege des Maschinenraums. Nur Bordmittel des Systems; macmon kommt auf dem Mac als Zusatz dazu, wenn vorhanden.

Speicher auf dem Mac: belegt = (anonyme Seiten - löschbare + fest verdrahtete + Kompressor) mal Seitengröße.
"Aktive" Seiten zählen nicht, sie enthalten Dateizwischenspeicher. Das entspricht der Anzeige der
Systemwerkzeuge. Auf Linux: MemTotal - MemAvailable.
Speicher je Dienst misst der Dienstkern (physischer Fußabdruck auf dem Mac, PSS auf Linux). Einheit überall GiB, wie die
Systemanzeigen.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
from pathlib import Path

from dienstkern.messen import GIB, MAC, befehl

from .protokoll import Messwerte

TEMPERATUR_PLAUSIBEL = (15.0, 120.0)            # °C; außerhalb ist es ein Messfehler des Sensors


# ── Rechner ──────────────────────────────────────────────────────────────
def speicher() -> tuple[float, float, float | None, float | None]:
    """(gesamt, belegt, swap belegt, swap gesamt) in GiB."""
    return _speicher_mac() if MAC else _speicher_linux()


def _speicher_mac() -> tuple[float, float, float | None, float | None]:
    gesamt = int(befehl("sysctl", "-n", "hw.memsize"))
    vm = befehl("vm_stat")
    seite = int(re.search(r"page size of (\d+) bytes", vm).group(1))

    def seiten(name: str) -> int:
        m = re.search(rf"^{re.escape(name)}:\s+(\d+)\.", vm, re.M)
        return int(m.group(1)) if m else 0

    belegt = (seiten("Anonymous pages") - seiten("Pages purgeable") + seiten("Pages wired down") + seiten("Pages occupied by compressor")) * seite
    swap, swap_gesamt = swap_mac(befehl("sysctl", "-n", "vm.swapusage"))
    return gesamt / GIB, belegt / GIB, swap, swap_gesamt


def swap_mac(text: str) -> tuple[float | None, float | None]:
    """`total = 18432.00M  used = 17117.56M ...` (auch mit Dezimalkomma) in GiB; unlesbar ergibt None, nie 0."""
    werte = {k: float(v.replace(",", ".")) for k, v in re.findall(r"(total|used) = ([\d.,]+)M", text)}
    if "total" not in werte or "used" not in werte:
        return None, None
    return werte["used"] / 1024, werte["total"] / 1024


def _meminfo() -> dict[str, int]:
    werte = {}
    for zeile in Path("/proc/meminfo").read_text().splitlines():
        name, _, rest = zeile.partition(":")
        werte[name] = int(rest.split()[0]) * 1024
    return werte


def _speicher_linux() -> tuple[float, float, float | None, float | None]:
    m = _meminfo()
    swap_gesamt = m.get("SwapTotal", 0)
    return m["MemTotal"] / GIB, (m["MemTotal"] - m["MemAvailable"]) / GIB, (swap_gesamt - m.get("SwapFree", 0)) / GIB, swap_gesamt / GIB


def platte_frei_gb() -> float:
    wurzel = "/System/Volumes/Data" if MAC and os.path.isdir("/System/Volumes/Data") else "/"
    return shutil.disk_usage(wurzel).free / GIB


def temperatur_linux() -> float | None:
    datei = Path("/sys/class/thermal/thermal_zone0/temp")
    try:
        return int(datei.read_text().strip()) / 1000
    except (OSError, ValueError):
        return None


class CpuLinux:
    """Prozessorlast aus /proc/stat zwischen zwei Messungen."""

    def __init__(self) -> None:
        self._vorher: tuple[int, int] | None = None

    def messen(self) -> float | None:
        try:
            felder = [int(x) for x in Path("/proc/stat").read_text().splitlines()[0].split()[1:]]
        except (OSError, ValueError, IndexError):
            return None
        leer, summe = felder[3] + (felder[4] if len(felder) > 4 else 0), sum(felder)
        vorher, self._vorher = self._vorher, (leer, summe)
        if vorher is None or summe == vorher[1]:
            return None
        return round(100 * (1 - (leer - vorher[0]) / (summe - vorher[1])), 1)


def leistung_w(d: dict) -> float | None:
    """Leistung des ganzen Rechners wie "Total" in macmon: sys_power (alles, was das Gerät zieht). all_power ist nur
    Prozessor, Grafik und Neural Engine und gilt nur, wenn sys_power fehlt (dann zeigt macmon "Power")."""
    wert = d.get("sys_power") or d.get("all_power") or 0
    return round(wert, 1) or None


class Macmon:
    """Liest fortlaufend die Zeilen von `macmon pipe` und hält die letzte; ohne macmon bleibt alles leer."""

    def __init__(self, takt_s: float) -> None:
        self.letzte: dict | None = None
        self._prozess: subprocess.Popen | None = None
        self._takt_ms = int(takt_s * 1000)
        self._kerne = (self._sysctl_int("hw.perflevel1.logicalcpu"), self._sysctl_int("hw.perflevel0.logicalcpu"))

    @staticmethod
    def vorhanden() -> bool:
        return MAC and shutil.which("macmon") is not None

    @staticmethod
    def _sysctl_int(name: str) -> int:
        try:
            return int(befehl("sysctl", "-n", name))
        except (OSError, subprocess.SubprocessError, ValueError):
            return 0

    def starten(self) -> None:
        self._prozess = subprocess.Popen(["macmon", "pipe", "-i", str(self._takt_ms)], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        threading.Thread(target=self._lesen, name="macmon", daemon=True).start()

    def _lesen(self) -> None:
        assert self._prozess and self._prozess.stdout
        for zeile in self._prozess.stdout:
            try:
                self.letzte = json.loads(zeile)
            except json.JSONDecodeError:
                continue

    def beenden(self) -> None:
        if self._prozess and self._prozess.poll() is None:
            self._prozess.terminate()

    def zusatz(self) -> dict[str, float | None]:
        d = self.letzte
        if not d:
            return {}
        e, p = d.get("ecpu_usage", [0, 0])[1], d.get("pcpu_usage", [0, 0])[1]
        ne, np_ = self._kerne
        cpu = (e * ne + p * np_) / (ne + np_) if ne + np_ else max(e, p)
        temperatur = d.get("temp", {}).get("cpu_temp_avg") or 0
        return {"cpu_prozent": round(cpu * 100, 1), "grafik_prozent": round(d.get("gpu_usage", [0, 0])[1] * 100, 1),
                # im Leerlauf meldet der Sensor gelegentlich Unsinn (einstellige Grade); dann lieber nichts zeigen
                "temperatur_c": round(temperatur, 1) if TEMPERATUR_PLAUSIBEL[0] <= temperatur <= TEMPERATUR_PLAUSIBEL[1] else None,
                "leistung_w": leistung_w(d)}


class Messer:
    def __init__(self, takt_s: float, macmon: bool) -> None:
        self.macmon = Macmon(takt_s) if macmon and Macmon.vorhanden() else None
        self.cpu = None if MAC else CpuLinux()
        if self.macmon:
            self.macmon.starten()

    def messwege(self) -> list[str]:
        wege = ["speicher", "swap", "platte", "last"]
        if self.cpu:
            wege += ["cpu", "temperatur"]
        if self.macmon:
            wege += ["cpu", "grafik", "temperatur", "leistung"]
        return wege

    def messen(self) -> Messwerte:
        gesamt, belegt, swap, swap_gesamt = speicher()
        werte = Messwerte(speicher_gesamt_gb=round(gesamt, 2), speicher_belegt_gb=round(belegt, 2),
                          swap_belegt_gb=round(swap, 2) if swap is not None else None,
                          swap_gesamt_gb=round(swap_gesamt, 2) if swap_gesamt is not None else None,
                          last_1m=round(os.getloadavg()[0], 2), platte_frei_gb=round(platte_frei_gb(), 1))
        if self.cpu:
            werte.cpu_prozent, werte.temperatur_c = self.cpu.messen(), temperatur_linux()
        if self.macmon:
            werte = werte.model_copy(update=self.macmon.zusatz())
        return werte

    def beenden(self) -> None:
        if self.macmon:
            self.macmon.beenden()
