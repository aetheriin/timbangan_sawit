import pyodbc
import hashlib
from datetime import datetime, date
from config import get_connection_string

def get_connection():
    return pyodbc.connect(get_connection_string())

# ===== SUPIR =====

def insert_supir(nama, embedding_binary, nik=None, nomor_sim=None, sim_berlaku=None, foto_path=None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO Supir (Nama, NIK, NomorSIM, SIMBerlakuSampai, FaceEmbedding, FotoPath) VALUES (?, ?, ?, ?, ?, ?)",
        nama, nik, nomor_sim, sim_berlaku, embedding_binary, foto_path
    )
    conn.commit()
    conn.close()

def get_all_supir():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT Id, Nama, FaceEmbedding FROM Supir")
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_daftar_supir():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT Id, NIK, Nama, NomorSIM, SIMBerlakuSampai, FotoPath, CreatedAt FROM Supir ORDER BY CreatedAt DESC")
    columns = [c[0] for c in cursor.description]
    data = [dict(zip(columns, row)) for row in cursor.fetchall()]
    conn.close()
    return data

def get_supir_by_id(supir_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT Id, Nama, NIK FROM Supir WHERE Id = ?", supir_id)
    row = cursor.fetchone()
    conn.close()
    return row

# ===== KENDARAAN =====

def get_or_create_kendaraan(plat_nomor, jenis_truk=None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT Id FROM Kendaraan WHERE PlatNomor = ?", plat_nomor)
    row = cursor.fetchone()
    if row:
        conn.close()
        return row.Id

    cursor.execute("INSERT INTO Kendaraan (PlatNomor, JenisTruk) VALUES (?, ?)", plat_nomor, jenis_truk)
    conn.commit()
    cursor.execute("SELECT Id FROM Kendaraan WHERE PlatNomor = ?", plat_nomor)
    kendaraan_id = cursor.fetchone().Id
    conn.close()
    return kendaraan_id

# ===== TRANSAKSI TIMBANG =====

def buat_nomor_tiket():
    return f"TKT-{datetime.now().strftime('%Y%m%d%H%M%S')}"

def hitung_hash(nomor_tiket, supir_id, plat_nomor, berat, secret_key="ganti-secret-key-rahasia"):
    data = f"{nomor_tiket}{supir_id}{plat_nomor}{berat}{secret_key}"
    return hashlib.sha256(data.encode()).hexdigest()

def cari_transaksi_terbuka(supir_id, kendaraan_id):
    """Cari transaksi hari ini yang sudah timbang masuk tapi belum timbang keluar."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT Id, NomorTiket, BeratBruto FROM TransaksiTimbang
        WHERE SupirId = ? AND KendaraanId = ? AND WaktuKeluar IS NULL
        AND CAST(WaktuMasuk AS DATE) = CAST(GETDATE() AS DATE)
    """, supir_id, kendaraan_id)
    row = cursor.fetchone()
    conn.close()
    return row

def catat_timbang_masuk(supir_id, kendaraan_id, berat, plat_nomor):
    nomor_tiket = buat_nomor_tiket()
    hash_val = hitung_hash(nomor_tiket, supir_id, plat_nomor, berat)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO TransaksiTimbang (SupirId, KendaraanId, NomorTiket, WaktuMasuk, BeratBruto, HashKeamanan, Status) VALUES (?, ?, ?, GETDATE(), ?, ?, 'Menunggu Keluar')",
        supir_id, kendaraan_id, nomor_tiket, berat, hash_val
    )
    conn.commit()
    conn.close()
    return nomor_tiket

def catat_timbang_keluar(transaksi_id, berat):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE TransaksiTimbang SET WaktuKeluar = GETDATE(), BeratTara = ?, Status = 'Selesai' WHERE Id = ?",
        berat, transaksi_id
    )
    conn.commit()
    conn.close()

def get_riwayat_transaksi():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT t.NomorTiket, s.Nama AS NamaSupir, k.PlatNomor, t.WaktuMasuk, t.BeratBruto,
               t.WaktuKeluar, t.BeratTara, t.BeratNetto, t.Status, t.HashKeamanan
        FROM TransaksiTimbang t
        JOIN Supir s ON t.SupirId = s.Id
        JOIN Kendaraan k ON t.KendaraanId = k.Id
        ORDER BY t.CreatedAt DESC
    """)
    columns = [c[0] for c in cursor.description]
    data = [dict(zip(columns, row)) for row in cursor.fetchall()]
    conn.close()
    return data

def get_user_by_username(username):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT Id, Username, PasswordHash, NamaLengkap, Role FROM Users WHERE Username = ?", username)
    row = cursor.fetchone()
    conn.close()
    return row

def get_user_by_id(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT Id, Username, NamaLengkap, Role FROM Users WHERE Id = ?", user_id)
    row = cursor.fetchone()
    conn.close()
    return row

def update_last_login(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE Users SET LastLogin = GETDATE() WHERE Id = ?", user_id)
    conn.commit()
    conn.close()

def get_dashboard_summary_timbang():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM TransaksiTimbang WHERE CAST(CreatedAt AS DATE) = CAST(GETDATE() AS DATE)")
    total_hari_ini = cursor.fetchone()[0]

    cursor.execute("""
        SELECT ISNULL(SUM(BeratNetto), 0) FROM TransaksiTimbang
        WHERE Status = 'Selesai' AND CAST(CreatedAt AS DATE) = CAST(GETDATE() AS DATE)
    """)
    total_netto = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM Supir")
    total_supir = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*) FROM Supir
        WHERE SIMBerlakuSampai IS NOT NULL AND SIMBerlakuSampai < GETDATE()
    """)
    sim_expired = cursor.fetchone()[0]

    conn.close()
    return {
        "total_hari_ini": total_hari_ini,
        "total_netto": total_netto,
        "total_supir": total_supir,
        "sim_expired": sim_expired
    }

def insert_user(username, password_hash, nama_lengkap, role="admin"):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO Users (Username, PasswordHash, NamaLengkap, Role) VALUES (?, ?, ?, ?)",
        username, password_hash, nama_lengkap, role
    )
    conn.commit()
    conn.close()

def cek_nik_supir_ada(nik, exclude_id=None):
    if not nik:
        return False
    conn = get_connection()
    cursor = conn.cursor()
    if exclude_id:
        cursor.execute("SELECT Id FROM Supir WHERE NIK = ? AND Id != ?", nik, exclude_id)
    else:
        cursor.execute("SELECT Id FROM Supir WHERE NIK = ?", nik)
    row = cursor.fetchone()
    conn.close()
    return row is not None

def cari_wajah_mirip_supir(embedding_baru, threshold=0.55, exclude_id=None):
    from utils.face_utils import binary_to_embedding, compare_faces
    supir_list = get_all_supir()
    for row in supir_list:
        supir_id, nama, embedding_binary = row
        if exclude_id and supir_id == exclude_id:
            continue
        embedding_tersimpan = binary_to_embedding(embedding_binary)
        is_match, distance = compare_faces(embedding_tersimpan, embedding_baru, threshold)
        if is_match:
            return (supir_id, nama)
    return None
