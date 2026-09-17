from datetime import datetime

_verifikasi_terakhir = None

def set_terverifikasi(supir_id, nama, nik=None):
    global _verifikasi_terakhir
    _verifikasi_terakhir = {"supir_id": supir_id, "nama": nama, "nik": nik, "waktu": datetime.now()}

def get_verifikasi():
    return _verifikasi_terakhir

def reset_verifikasi():
    global _verifikasi_terakhir
    _verifikasi_terakhir = None