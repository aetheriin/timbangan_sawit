import os
import hashlib
import pyodbc
from dotenv import load_dotenv
from datetime import date, datetime
from config import get_connection_string

load_dotenv()

def get_connection():
  return pyodbc.connect(get_connection_string())

# SUPIR
def insert_supir(
    nama,
    embedding_binary,
    nik=None,
    nomor_sim=None,
    sim_berlaku=None,
    foto_path=None,
):
  conn = get_connection()
  cursor = conn.cursor()
  cursor.execute(
      "INSERT INTO Supir (Nama, NIK, NomorSIM, SIMBerlakuSampai, FaceEmbedding,"
      " FotoPath) VALUES (?, ?, ?, ?, ?, ?)",
      nama,
      nik,
      nomor_sim,
      sim_berlaku,
      embedding_binary,
      foto_path,
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
    cursor.execute("""
        SELECT Id, NIK, Nama, NomorSIM, SIMBerlakuSampai, FotoPath, CreatedAt
        FROM Supir WHERE IsActive = 1 ORDER BY CreatedAt DESC
    """)
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

def nonaktifkan_supir(supir_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE Supir SET IsActive = 0 WHERE Id = ?", supir_id)
    conn.commit()
    conn.close()

def get_supir_lengkap_by_id(supir_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT Id, Nama, NIK, NomorSIM, SIMBerlakuSampai FROM Supir WHERE Id = ?", supir_id)
    row = cursor.fetchone()
    conn.close()
    return row

def update_supir(supir_id, nama, nik, nomor_sim, sim_berlaku, embedding_binary=None, foto_path=None):
    conn = get_connection()
    cursor = conn.cursor()
    if embedding_binary is not None:
        cursor.execute(
            "UPDATE Supir SET Nama=?, NIK=?, NomorSIM=?, SIMBerlakuSampai=?, FaceEmbedding=?, FotoPath=? WHERE Id=?",
            nama, nik, nomor_sim, sim_berlaku, embedding_binary, foto_path, supir_id
        )
    else:
        cursor.execute(
            "UPDATE Supir SET Nama=?, NIK=?, NomorSIM=?, SIMBerlakuSampai=? WHERE Id=?",
            nama, nik, nomor_sim, sim_berlaku, supir_id
        )
    conn.commit()
    conn.close()

# KENDARAAN
def get_or_create_kendaraan(plat_nomor, jenis_truk=None):
  conn = get_connection()
  cursor = conn.cursor()
  cursor.execute("SELECT Id FROM Kendaraan WHERE PlatNomor = ?", plat_nomor)
  row = cursor.fetchone()
  if row:
    conn.close()
    return row.Id

  cursor.execute(
      "INSERT INTO Kendaraan (PlatNomor, JenisTruk) VALUES (?, ?)",
      plat_nomor,
      jenis_truk,
  )
  conn.commit()
  cursor.execute("SELECT Id FROM Kendaraan WHERE PlatNomor = ?", plat_nomor)
  kendaraan_id = cursor.fetchone().Id
  conn.close()
  return kendaraan_id

# TRANSAKSI TIMBANG & SECURITY (TOKENIZATION & HASH)
def hitung_hash(
    nomor_tiket,
    supir_id,
    plat_nomor,
    berat_bruto,
    berat_tara=0,
    secret_key=None,
):
  """Menghitung Hash Keamanan SHA-256 """
  if secret_key is None:
      secret_key = os.getenv("HASH_SECRET_KEY")
  data = (
      f"{nomor_tiket}{supir_id}{plat_nomor}{berat_bruto}{berat_tara}{secret_key}"
  )
  return hashlib.sha256(data.encode()).hexdigest()

def buat_tiket_security(supir_id, plat_nomor, qr_token):
  """Mencatat registrasi awal di Pos Security sebelum truk masuk timbangan."""
  kendaraan_id = get_or_create_kendaraan(plat_nomor)
  conn = get_connection()
  cursor = conn.cursor()
  cursor.execute(
      """
        INSERT INTO TransaksiTimbang (SupirId, KendaraanId, NomorTiket, Status)
        VALUES (?, ?, ?, 'Menunggu Timbang')
    """,
      supir_id,
      kendaraan_id,
      qr_token,
  )
  conn.commit()
  conn.close()
  return qr_token

def cari_transaksi_by_qr(qr_token):
  """Mencari data tiket aktif berdasarkan QR Token untuk di-scan di Pos Timbangan."""
  conn = get_connection()
  cursor = conn.cursor()
  cursor.execute(
      """
        SELECT t.Id, t.NomorTiket, t.SupirId, s.Nama AS NamaSupir, s.NIK,
               t.KendaraanId, k.PlatNomor, t.BeratBruto, t.Status
        FROM TransaksiTimbang t
        JOIN Supir s ON t.SupirId = s.Id
        JOIN Kendaraan k ON t.KendaraanId = k.Id
        WHERE t.NomorTiket = ?
    """,
      qr_token,
  )
  row = cursor.fetchone()
  conn.close()
  return row

def catat_timbang_masuk(supir_id, kendaraan_id, berat, plat_nomor, qr_token):
  """Mengunci Berat Bruto (Masuk) & membuat Hash Keamanan Pertama."""
  hash_val = hitung_hash(qr_token, supir_id, plat_nomor, berat)

  conn = get_connection()
  cursor = conn.cursor()

  # Pengecekan apakah transaksi sudah dibuat dari Pos Security
  cursor.execute(
      "SELECT Id FROM TransaksiTimbang WHERE NomorTiket = ?", qr_token
  )
  row = cursor.fetchone()

  if row:
    cursor.execute(
        """
            UPDATE TransaksiTimbang 
            SET WaktuMasuk = GETDATE(), BeratBruto = ?, HashKeamanan = ?, Status = 'Menunggu Keluar'
            WHERE NomorTiket = ?
        """,
        berat,
        hash_val,
        qr_token,
    )
  else:
    cursor.execute(
        """
            INSERT INTO TransaksiTimbang (SupirId, KendaraanId, NomorTiket, WaktuMasuk, BeratBruto, HashKeamanan, Status) 
            VALUES (?, ?, ?, GETDATE(), ?, ?, 'Menunggu Keluar')
        """,
        supir_id,
        kendaraan_id,
        qr_token,
        berat,
        hash_val,
    )

  conn.commit()
  conn.close()
  return qr_token

def catat_timbang_keluar(transaksi_id, berat_tara):
    """Mengunci Berat Tara (Keluar), menghitung Netto, dan memperbarui Hash Keamanan Akhir."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT t.NomorTiket, t.SupirId, t.BeratBruto, k.PlatNomor
        FROM TransaksiTimbang t
        JOIN Kendaraan k ON t.KendaraanId = k.Id
        WHERE t.Id = ?
    """, transaksi_id)
    row = cursor.fetchone()

    if row:
        nomor_tiket, supir_id, berat_bruto, plat_nomor = row
        berat_netto = berat_bruto - berat_tara
        status_final = 'Selesai' if berat_netto > 0 else 'Perlu Cek Manual'
        hash_baru = hitung_hash(nomor_tiket, supir_id, plat_nomor, berat_bruto, berat_tara)

        cursor.execute("""
            UPDATE TransaksiTimbang
            SET WaktuKeluar = GETDATE(), BeratTara = ?, BeratNetto = ?, HashKeamanan = ?, Status = ?
            WHERE Id = ?
        """, berat_tara, berat_netto, hash_baru, status_final, transaksi_id)

        conn.commit()
        conn.close()
        return berat_netto, status_final

    conn.close()
    return None, None

# USER MANAGEMENT & DASHBOARD SUMMARY
def get_riwayat_transaksi():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT t.Id, t.NomorTiket, s.Nama AS NamaSupir, k.PlatNomor, t.WaktuMasuk, t.BeratBruto,
               t.WaktuKeluar, t.BeratTara, t.BeratNetto, t.Status, t.HashKeamanan, t.AlasanBatal,
               t.CatatanManual, t.FotoBuktiManual, t.DiperiksaOleh
        FROM TransaksiTimbang t
        JOIN Supir s ON t.SupirId = s.Id
        JOIN Kendaraan k ON t.KendaraanId = k.Id
        ORDER BY t.CreatedAt DESC
    """)
    columns = [c[0] for c in cursor.description]
    data = [dict(zip(columns, row)) for row in cursor.fetchall()]
    conn.close()
    return data

def batalkan_transaksi(transaksi_id, alasan, dibatalkan_oleh):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE TransaksiTimbang SET Status = 'Dibatalkan', AlasanBatal = ? WHERE Id = ?",
        f"{alasan} (oleh: {dibatalkan_oleh})", transaksi_id
    )
    conn.commit()
    conn.close()

def get_user_by_username(username):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT Id, Username, PasswordHash, NamaLengkap, Role FROM Users WHERE Username = ? AND IsActive = 1", username)
    row = cursor.fetchone()
    conn.close()
    return row

def get_user_by_id(user_id):
  conn = get_connection()
  cursor = conn.cursor()
  cursor.execute(
      "SELECT Id, Username, NamaLengkap, Role FROM Users WHERE Id = ?", user_id
  )
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

  cursor.execute(
      "SELECT COUNT(*) FROM TransaksiTimbang WHERE CAST(CreatedAt AS DATE) ="
      " CAST(GETDATE() AS DATE)"
  )
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
      "sim_expired": sim_expired,
  }

def insert_user(username, password_hash, nama_lengkap, role="admin"):
  conn = get_connection()
  cursor = conn.cursor()
  cursor.execute(
      "INSERT INTO Users (Username, PasswordHash, NamaLengkap, Role) VALUES"
      " (?, ?, ?, ?)",
      username,
      password_hash,
      nama_lengkap,
      role,
  )
  conn.commit()
  conn.close()

def cek_nik_supir_ada(nik, exclude_id=None):
  if not nik:
    return False
  conn = get_connection()
  cursor = conn.cursor()
  if exclude_id:
    cursor.execute(
        "SELECT Id FROM Supir WHERE NIK = ? AND Id != ?", nik, exclude_id
    )
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
    is_match, distance = compare_faces(
        embedding_tersimpan, embedding_baru, threshold
    )
    if is_match:
      return (supir_id, nama)
  return None

def tambah_bukti_manual(transaksi_id, catatan, foto_path=None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE TransaksiTimbang SET CatatanManual = ?, FotoBuktiManual = ? WHERE Id = ?",
        catatan, foto_path, transaksi_id
    )
    conn.commit()
    conn.close()

def setujui_manual_check(transaksi_id, admin_nama):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE TransaksiTimbang SET Status = 'Selesai', DiperiksaOleh = ? WHERE Id = ?",
        admin_nama, transaksi_id
    )
    conn.commit()
    conn.close()

def tolak_manual_check(transaksi_id, admin_nama, alasan):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE TransaksiTimbang SET Status = 'Ditolak', DiperiksaOleh = ?, AlasanBatal = ? WHERE Id = ?",
        admin_nama, alasan, transaksi_id
    )
    conn.commit()
    conn.close()

def get_all_users():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT Id, Username, NamaLengkap, Role, IsActive, LastLogin, CreatedAt FROM Users ORDER BY CreatedAt DESC")
    columns = [c[0] for c in cursor.description]
    data = [dict(zip(columns, row)) for row in cursor.fetchall()]
    conn.close()
    return data

def cek_username_ada(username):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT Id FROM Users WHERE Username = ?", username)
    row = cursor.fetchone()
    conn.close()
    return row is not None

def reset_password_user(user_id, password_hash_baru):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE Users SET PasswordHash = ? WHERE Id = ?", password_hash_baru, user_id)
    conn.commit()
    conn.close()

def toggle_status_user(user_id, status_baru):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE Users SET IsActive = ? WHERE Id = ?", status_baru, user_id)
    conn.commit()
    conn.close()