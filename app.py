import json
import os
import uuid
from functools import wraps

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, url_for
from flask_login import (
    LoginManager,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from utils.auth import User
from utils.db_utils import (
    batalkan_transaksi,
    buat_tiket_security,
    cari_transaksi_by_qr,
    cari_wajah_mirip_supir,
    catat_timbang_keluar,
    catat_timbang_masuk,
    cek_nik_supir_ada,
    get_all_supir,
    get_connection,
    get_daftar_supir,
    get_dashboard_summary_timbang,
    get_or_create_kendaraan,
    get_riwayat_transaksi,
    get_supir_by_id,
    get_supir_lengkap_by_id,
    get_user_by_username,
    insert_supir,
    insert_user,
    nonaktifkan_supir,
    setujui_manual_check,
    tambah_bukti_manual,
    tolak_manual_check,
    update_last_login,
    update_supir,
    get_all_users, 
    cek_username_ada, 
    reset_password_user, 
    toggle_status_user
)
from utils.face_utils import (
    binary_to_embedding,
    compare_faces,
    embedding_to_binary,
    extract_embedding,
    verifikasi_liveness,
)
from utils.timbang_state import baca_status, mulai_simulasi, reset_sesi
from utils.verifikasi_state import (
    get_verifikasi,
    reset_verifikasi,
    set_terverifikasi,
)
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")

# Cek folder upload
UPLOAD_FOLDER = os.path.join("static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

camera_trigger_state = {"is_active": False, "last_scanned_driver": None}

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


@login_manager.user_loader
def load_user(user_id):
  return User.get(user_id)


def role_required(*roles):
  def decorator(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
      if not current_user.is_authenticated:
        return jsonify({"error": "Pengguna belum terautentikasi"}), 401
      if current_user.role not in roles:
        return jsonify({"error": "Akses ditolak untuk role Anda"}), 403
      return f(*args, **kwargs)

    return wrapped

  return decorator


@app.route("/")
def index():
  return redirect("/login")


@app.route("/login", methods=["GET", "POST"])
def login():
  if request.method == "POST":
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")

    row = get_user_by_username(username)
    if row is None or not check_password_hash(row.PasswordHash, password):
      return render_template(
          "login.html", error="Username atau password salah"
      )

    user = User(row.Id, row.Username, row.NamaLengkap, row.Role)
    login_user(user)
    update_last_login(row.Id)

    # PERBAIKAN: Redirect dinamis sesuai role pengguna untuk mencegah HTTP 403
    if user.role == "admin":
      return redirect(url_for("dashboard"))
    elif user.role == "security":
      return redirect(url_for("security_page"))
    elif user.role == "operator_timbang":
      return redirect(url_for("timbang"))
    else:
      return redirect(url_for("riwayat"))

  return render_template("login.html", error=None)


@app.route("/dashboard")
@login_required
@role_required("admin")
def dashboard():
  summary = get_dashboard_summary_timbang()
  return render_template(
      "dashboard.html", summary=summary, active_page="dashboard"
  )


@app.route("/logout")
@login_required
def logout():
  logout_user()
  return redirect("/login")


# 1. POS SECURITY CHECK-IN & TRIGGER KAMERA
@app.route("/security")
@login_required
@role_required("security", "admin")
def security_page():
  return render_template("security.html", active_page="security")


@app.route("/api/kamera/start", methods=["POST"])
def api_kamera_start():
  """Trigger dari Web Security untuk menyalakan kamera kiosk_timbang.py."""
  camera_trigger_state["is_active"] = True
  camera_trigger_state["last_scanned_driver"] = None
  reset_verifikasi()
  return jsonify({"status": "SUCCESS", "message": "Kamera Kiosk diaktifkan"}), 200


@app.route("/api/kamera/status", methods=["GET"])
def api_kamera_status():
  """Endpoint polling yang dipanggil kiosk_timbang.py setiap 1 detik."""
  return jsonify({"is_active": camera_trigger_state["is_active"]}), 200


@app.route("/api/kamera/batal", methods=["POST"])
def api_kamera_batal():
  """Dipanggil oleh kiosk_timbang.py jika kamera ditutup manual oleh user (Tombol X / Q)."""
  camera_trigger_state["is_active"] = False
  camera_trigger_state["last_scanned_driver"] = None
  reset_verifikasi()
  return (
      jsonify({"status": "SUCCESS", "message": "Trigger kamera dibatalkan"}),
      200,
  )


@app.route("/api/security/cetak-tiket", methods=["POST"])
@login_required
@role_required("security", "admin")
def api_cetak_tiket():
  """Security menginput plat nomor & generate UUID acak untuk QR Code Struk yang tersimpan di DB."""
  data = request.json or {}
  plat_nomor = data.get("plat_nomor", "").strip().upper()
  supir_id = data.get("supir_id", "").strip()
  nama_supir = data.get("nama", "").strip()

  if not plat_nomor or not supir_id:
    return jsonify({"error": "Plat nomor dan data supir wajib diisi"}), 400

  qr_token = f"TKT-{uuid.uuid4().hex[:8].upper()}"
  buat_tiket_security(supir_id, plat_nomor, qr_token)

  return (
      jsonify({
          "status": "SUCCESS",
          "qr_token": qr_token,
          "plat_nomor": plat_nomor,
          "nama_supir": nama_supir,
      }),
      200,
  )

@app.route("/admin/users")
@login_required
@role_required('admin')
def admin_users():
    data = get_all_users()
    return render_template("admin_users.html", data=data, active_page="admin_users")

@app.route("/admin/users/tambah", methods=["POST"])
@login_required
@role_required('admin')
def admin_users_tambah():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()
    nama = request.form.get("nama", "").strip()
    role = request.form.get("role", "").strip()

    if not all([username, password, nama, role]):
        return jsonify({"error": "Semua field wajib diisi"}), 400
    if role not in ['security', 'operator_timbang', 'admin']:
        return jsonify({"error": "Role tidak valid"}), 400
    if cek_username_ada(username):
        return jsonify({"error": f"Username '{username}' sudah dipakai"}), 400

    password_hash = generate_password_hash(password)
    insert_user(username, password_hash, nama, role)
    return jsonify({"message": f"User '{username}' berhasil dibuat"}), 200

@app.route("/admin/users/reset-password/<int:user_id>", methods=["POST"])
@login_required
@role_required('admin')
def admin_users_reset(user_id):
    password_baru = request.form.get("password_baru", "").strip()
    if not password_baru or len(password_baru) < 6:
        return jsonify({"error": "Password minimal 6 karakter"}), 400
    reset_password_user(user_id, generate_password_hash(password_baru))
    return jsonify({"message": "Password berhasil direset"}), 200

@app.route("/admin/users/toggle/<int:user_id>", methods=["POST"])
@login_required
@role_required('admin')
def admin_users_toggle(user_id):
    status_baru = request.form.get("status") == "1"
    if user_id == current_user.id and not status_baru:
        return jsonify({"error": "Tidak bisa menonaktifkan akun sendiri"}), 400
    toggle_status_user(user_id, status_baru)
    return jsonify({"message": "Status user berhasil diperbarui"}), 200

# 2. POS JEMBATAN TIMBANG (BRUTO & TARA)
@app.route("/timbang")
@login_required
@role_required("operator_timbang", "admin")
def timbang():
  return render_template("timbang.html", active_page="timbang")


@app.route("/api/timbang/scan-qr", methods=["POST"])
@login_required
@role_required("operator_timbang", "admin")
def api_scan_qr():
  """Lookup data supir & plat langsung dari Database SQL berdasarkan Token QR yang di-scan."""
  data = request.json or {}
  token = data.get("qr_token", "").strip().upper()

  # Query ke Database via db_utils
  row = cari_transaksi_by_qr(token)
  if not row:
    return jsonify({"error": "Tiket QR tidak ditemukan / tidak valid!"}), 404

  tiket = {
      "id": row.Id,
      "qr_token": row.NomorTiket,
      "supir_id": row.SupirId,
      "nama": row.NamaSupir,
      "nik": row.NIK,
      "kendaraan_id": row.KendaraanId,
      "plat_nomor": row.PlatNomor,
      "berat_bruto": row.BeratBruto,
      "status": row.Status,
  }

  # Set state terverifikasi
  set_terverifikasi(row.SupirId, row.NamaSupir)

  return jsonify({"status": "SUCCESS", "tiket": tiket}), 200


@app.route("/timbang/mulai", methods=["POST"])
@login_required
def timbang_mulai():
  mulai_simulasi()
  return jsonify({"message": "Simulasi dimulai"})


@app.route("/timbang/status")
@login_required
def timbang_status():
  return jsonify(baca_status())


@app.route("/timbang/kunci", methods=["POST"])
@login_required
@role_required("operator_timbang", "admin")
def timbang_kunci():
  status = baca_status()
  if not status["siap_kunci"]:
    return jsonify({"error": "Berat belum stabil"}), 400

  qr_token = request.form.get("qr_token", "").strip().upper()
  if not qr_token:
    return jsonify({"error": "Tiket QR belum di-scan"}), 400

  row = cari_transaksi_by_qr(qr_token)
  if not row:
    return jsonify({"error": "Tiket tidak ditemukan"}), 404

  berat = status["berat"]
  reset_verifikasi()
  reset_sesi()

  if row.BeratBruto is None:
    catat_timbang_masuk(
        row.SupirId, row.KendaraanId, berat, row.PlatNomor, qr_token
    )
    return (
        jsonify({
            "message": (
                f"Timbang MASUK berhasil. Tiket: {qr_token}. Berat: {berat} kg"
            )
        }),
        200,
    )

  if row.Status == "Selesai" or row.Status == "Perlu Cek Manual":
    return jsonify({"error": "Tiket ini sudah selesai ditimbang"}), 400

  netto, status_final = catat_timbang_keluar(row.Id, berat)
  if status_final == "Perlu Cek Manual":
    return (
        jsonify({
            "message": (
                f"Timbang KELUAR tercatat, TAPI netto tidak valid ({netto} kg)"
                " perlu Manual Check"
            ),
            "perlu_manual_check": True,
        }),
        200,
    )
  return (
      jsonify({
          "message": (
              f"Timbang KELUAR berhasil. Berat: {berat} kg, Netto: {netto} kg"
          )
      }),
      200,
  )


# 3. VERIFIKASI WAJAH & LIVENESS (DARI KIOSK_TIMBANG.PY)
@app.route("/timbang/verifikasi-wajah", methods=["POST"])
def verifikasi_wajah_timbang():
  files = request.files.getlist("frames")
  tantangan = request.form.get("tantangan", "KEDIP")

  if not files or len(files) < 3:
    return jsonify({"error": "Frame tidak cukup"}), 400

  filepaths = []
  try:
    for f in files:
      filepath = os.path.join(UPLOAD_FOLDER, f"tmp_{uuid.uuid4().hex}.jpg")
      f.save(filepath)
      filepaths.append(filepath)

    if not verifikasi_liveness(filepaths, tantangan):
      return jsonify({"error": "Liveness tidak terverifikasi"}), 400

    embedding_baru = extract_embedding(filepaths[len(filepaths) // 2])
    if embedding_baru is None:
      return jsonify({"error": "Wajah tidak terdeteksi"}), 400

    supir_list = get_all_supir()
    match_found = None
    for row in supir_list:
      supir_id, nama, embedding_binary = row
      embedding_tersimpan = binary_to_embedding(embedding_binary)
      is_match, _ = compare_faces(
          embedding_tersimpan, embedding_baru, threshold=0.55
      )
      if is_match:
        match_found = (supir_id, nama)
        break

    if not match_found:
      return jsonify({"error": "Supir tidak dikenali"}), 404

    supir_id, nama = match_found
    detail = get_supir_by_id(supir_id)
    nik_asli = detail.NIK if detail else None
    set_terverifikasi(supir_id, nama, nik_asli)

    camera_trigger_state["is_active"] = False
    camera_trigger_state["last_scanned_driver"] = {
        "supir_id": supir_id,
        "nama": nama,
    }

    return (
        jsonify({
            "message": f"Terverifikasi: {nama}",
            "nik": nik_asli,
            "nama": nama,
        }),
        200,
    )

  finally:
    # OPTIMASI: Hapus file temporer frame JPEG
    for path in filepaths:
      if os.path.exists(path):
        try:
          os.remove(path)
        except Exception:
          pass


@app.route("/timbang/status-verifikasi")
def status_verifikasi():
  v = get_verifikasi()
  if v is None:
    return jsonify({"terverifikasi": False})
  return jsonify({
      "terverifikasi": True,
      "supir_id": v["supir_id"],
      "nama": v["nama"],
      "nik": v.get("nik"),
  })


# 4. RIWAYAT & MANAGEMENT SUPIR
@app.route("/riwayat")
@login_required
def riwayat():
  data = get_riwayat_transaksi()
  return render_template("riwayat.html", data=data, active_page="riwayat")


@app.route("/supir")
@login_required
@role_required("admin")
def supir():
  data = get_daftar_supir()
  return render_template("supir.html", data=data, active_page="supir")


@app.route("/supir/register", methods=["POST"])
@login_required
@role_required("admin")
def supir_register():
  nama = request.form.get("nama", "").strip()
  nik = request.form.get("nik", "").strip()
  nomor_sim = request.form.get("nomor_sim", "").strip() or None
  sim_berlaku = request.form.get("sim_berlaku", "").strip() or None
  file = request.files.get("foto")

  if not nama or not file:
    return jsonify({"error": "Nama dan foto wajib diisi"}), 400
  if not nik.isdigit():
    return jsonify({"error": "NIK harus berupa angka"}), 400
  if cek_nik_supir_ada(nik):
    return jsonify({"error": f"NIK '{nik}' sudah terdaftar"}), 400

  ext = os.path.splitext(file.filename)[1]
  unique_filename = f"{uuid.uuid4().hex}{ext}"
  filepath = os.path.join(UPLOAD_FOLDER, unique_filename)
  file.save(filepath)

  embedding = extract_embedding(filepath)
  if embedding is None:
    if os.path.exists(filepath):
      os.remove(filepath)
    return jsonify({"error": "Wajah tidak terdeteksi di foto"}), 400

  wajah_mirip = cari_wajah_mirip_supir(embedding)
  if wajah_mirip:
    if os.path.exists(filepath):
      os.remove(filepath)
    _, nama_terdaftar = wajah_mirip
    return (
        jsonify(
            {"error": f"Wajah ini sudah terdaftar sebagai '{nama_terdaftar}'"}
        ),
        400,
    )

  binary_data = embedding_to_binary(embedding)
  insert_supir(
      nama,
      binary_data,
      nik=nik,
      nomor_sim=nomor_sim,
      sim_berlaku=sim_berlaku,
      foto_path=f"uploads/{unique_filename}",
  )

  return jsonify({"message": f"Supir '{nama}' berhasil didaftarkan"}), 200


@app.route("/supir/hapus/<int:supir_id>", methods=["POST"])
@login_required
@role_required("admin")
def supir_hapus(supir_id):
  nonaktifkan_supir(supir_id)
  return jsonify({"message": "Supir berhasil dinonaktifkan"}), 200


@app.route("/supir/edit/<int:supir_id>", methods=["POST"])
@login_required
@role_required("admin")
def supir_edit(supir_id):
  nama = request.form.get("nama", "").strip()
  nik = request.form.get("nik", "").strip()
  nomor_sim = request.form.get("nomor_sim", "").strip() or None
  sim_berlaku = request.form.get("sim_berlaku", "").strip() or None
  file = request.files.get("foto")

  if not nama:
    return jsonify({"error": "Nama tidak boleh kosong"}), 400
  if nik and not nik.isdigit():
    return jsonify({"error": "NIK harus berupa angka"}), 400
  if nik and cek_nik_supir_ada(nik, exclude_id=supir_id):
    return jsonify({"error": f"NIK '{nik}' sudah dipakai supir lain"}), 400

  embedding_binary = None
  foto_path = None
  if file and file.filename != "":
    ext = os.path.splitext(file.filename)[1]
    unique_filename = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(UPLOAD_FOLDER, unique_filename)
    file.save(filepath)

    embedding_baru = extract_embedding(filepath)
    if embedding_baru is None:
      os.remove(filepath)
      return jsonify({"error": "Wajah tidak terdeteksi di foto baru"}), 400

    wajah_mirip = cari_wajah_mirip_supir(embedding_baru, exclude_id=supir_id)
    if wajah_mirip:
      os.remove(filepath)
      _, nama_terdaftar = wajah_mirip
      return (
          jsonify(
              {"error": f"Wajah ini sudah terdaftar sebagai '{nama_terdaftar}'"}
          ),
          400,
      )

    embedding_binary = embedding_to_binary(embedding_baru)
    foto_path = f"uploads/{unique_filename}"

  update_supir(
      supir_id,
      nama,
      nik if nik else None,
      nomor_sim,
      sim_berlaku,
      embedding_binary,
      foto_path,
  )
  return jsonify({"message": f"Data '{nama}' berhasil diperbarui"}), 200


@app.route("/riwayat/batalkan/<int:transaksi_id>", methods=["POST"])
@login_required
@role_required("admin")
def riwayat_batalkan(transaksi_id):
  alasan = request.form.get("alasan", "").strip()
  if not alasan:
    return jsonify({"error": "Alasan pembatalan wajib diisi"}), 400
  batalkan_transaksi(transaksi_id, alasan, current_user.nama_lengkap)
  return jsonify({"message": "Transaksi ditandai batal"}), 200


@app.route("/riwayat/tambah-bukti/<int:transaksi_id>", methods=["POST"])
@login_required
@role_required("security", "operator_timbang", "admin")
def riwayat_tambah_bukti(transaksi_id):
  catatan = request.form.get("catatan", "").strip()
  file = request.files.get("foto")
  if not catatan:
    return jsonify({"error": "Catatan wajib diisi"}), 400

  foto_path = None
  if file and file.filename != "":
    ext = os.path.splitext(file.filename)[1]
    unique_filename = f"bukti_{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(UPLOAD_FOLDER, unique_filename)
    file.save(filepath)
    foto_path = f"uploads/{unique_filename}"

  tambah_bukti_manual(transaksi_id, catatan, foto_path)
  return (
      jsonify({
          "message": (
              "Catatan/bukti berhasil ditambahkan, menunggu keputusan Admin"
          )
      }),
      200,
  )


@app.route("/riwayat/setujui/<int:transaksi_id>", methods=["POST"])
@login_required
@role_required("admin")
def riwayat_setujui(transaksi_id):
  setujui_manual_check(transaksi_id, current_user.nama_lengkap)
  return jsonify({"message": "Transaksi disetujui dan ditandai Selesai"}), 200


@app.route("/riwayat/tolak/<int:transaksi_id>", methods=["POST"])
@login_required
@role_required("admin")
def riwayat_tolak(transaksi_id):
  alasan = request.form.get("alasan", "").strip()
  if not alasan:
    return jsonify({"error": "Alasan penolakan wajib diisi"}), 400
  tolak_manual_check(transaksi_id, current_user.nama_lengkap, alasan)
  return jsonify({"message": "Transaksi ditolak"}), 200


if __name__ == "__main__":
  app.run(debug=True, port=5000)