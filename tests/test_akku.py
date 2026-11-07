"""Akku messen (HELF-187): Einträge von `ioreg -rn AppleSmartBattery -a` wie auf den Macs am 07.11.2026 gemessen."""

from __future__ import annotations

from maschinenraum.akku import Akkumesser, akku_aus_eintrag
from maschinenraum.messen import Messer
from maschinenraum.protokoll import Akku

# MacBook M4 Max, macOS 15: am Netzteil, lädt nicht (Akku-Schonung), Zustand bekannt
NETZTEIL_SCHONUNG = {"BatteryInstalled": True, "CurrentCapacity": 79, "MaxCapacity": 100, "ExternalConnected": True,
                     "IsCharging": False, "AvgTimeToFull": 65535, "AvgTimeToEmpty": 1933, "AppleRawMaxCapacity": 8131,
                     "DesignCapacity": 8579, "CycleCount": 67}
# MacBook 32 GB, macOS 27: lädt, ohne Rohwerte der Kapazität
LAEDT_MACOS27 = {"BatteryInstalled": True, "CurrentCapacity": 52, "MaxCapacity": 100, "ExternalConnected": True,
                 "IsCharging": True, "AvgTimeToFull": 141, "AvgTimeToEmpty": 65535, "CycleCount": 227}


def test_am_netzteil_ohne_laden_hat_keine_restzeit_und_den_zustand():
    assert akku_aus_eintrag(NETZTEIL_SCHONUNG) == Akku(prozent=79, netzteil=True, laedt=False, rest_min=None,
                                                       kapazitaet_prozent=94.8, zyklen=67)


def test_beim_laden_die_zeit_bis_voll_ohne_zustand_unter_macos_27():
    assert akku_aus_eintrag(LAEDT_MACOS27) == Akku(prozent=52, netzteil=True, laedt=True, rest_min=141, zyklen=227)


def test_ohne_netzteil_die_zeit_bis_leer_und_65535_heisst_unbekannt():
    leer = {**NETZTEIL_SCHONUNG, "CurrentCapacity": 17, "ExternalConnected": False, "AvgTimeToEmpty": 41}
    assert akku_aus_eintrag(leer).rest_min == 41
    assert akku_aus_eintrag({**leer, "AvgTimeToEmpty": 65535}).rest_min is None


def test_aeltere_macs_melden_mah_statt_prozent():
    assert akku_aus_eintrag({"CurrentCapacity": 3100, "MaxCapacity": 6200, "ExternalConnected": False}).prozent == 50


def test_ohne_akku_oder_ohne_ladestand_nichts():
    assert akku_aus_eintrag({"BatteryInstalled": False, "CurrentCapacity": 50, "MaxCapacity": 100}) is None
    assert akku_aus_eintrag({"ExternalConnected": True}) is None


def test_messer_fragt_hoechstens_im_abstand_und_nur_auf_dem_mac():
    zeit, aufrufe = [0.0], []

    def lesen():
        aufrufe.append(zeit[0])
        return [NETZTEIL_SCHONUNG]
    m = Akkumesser(lesen=lesen, abstand_s=30, system="darwin", uhr=lambda: zeit[0])
    assert m.vorhanden and m.messen().prozent == 79
    zeit[0] = 29
    m.messen()
    zeit[0] = 31
    m.messen()
    assert aufrufe == [0.0, 31]
    anderswo = Akkumesser(lesen=lesen, system="linux")
    assert not anderswo.vorhanden and anderswo.messen() is None


def test_messwerte_tragen_akku_und_platte():
    ohne = Messer(5, macmon=False, akku=Akkumesser(lesen=lambda: [], system="darwin"))
    w = ohne.messen()
    assert w.akku is None and "akku" not in ohne.messwege()
    assert w.platte_gesamt_gb is not None and 0 < w.platte_frei_gb <= w.platte_gesamt_gb
    mit = Messer(5, macmon=False, akku=Akkumesser(lesen=lambda: [LAEDT_MACOS27], system="darwin"))
    assert mit.messen().akku.prozent == 52 and "akku" in mit.messwege()
