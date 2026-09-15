from datetime import datetime
import random

_sesi_aktif = {}

DURASI_NAIK_DETIK = 3
DURASI_STABIL_DIBUTUHKAN = 2

def mulai_simulasi():
    global _sesi_aktif
    _sesi_aktif = {
        "mulai": datetime.now(),
        "target": random.randint(8000, 25000)
    }

def baca_status():
    if not _sesi_aktif:
        return {"berat": 0, "stabil": False, "siap_kunci": False}

    elapsed = (datetime.now() - _sesi_aktif["mulai"]).total_seconds()
    target = _sesi_aktif["target"]

    if elapsed < DURASI_NAIK_DETIK:
        berat = round(target * (elapsed / DURASI_NAIK_DETIK) / 10) * 10
        return {"berat": berat, "stabil": False, "siap_kunci": False}

    waktu_stabil = elapsed - DURASI_NAIK_DETIK
    siap_kunci = waktu_stabil >= DURASI_STABIL_DIBUTUHKAN
    return {"berat": target, "stabil": True, "siap_kunci": siap_kunci}

def reset_sesi():
    global _sesi_aktif
    _sesi_aktif = {}