import os
import json
import uuid
from flask import Flask, request, jsonify, render_template, redirect
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from utils.auth import User
from utils.timbang_state import mulai_simulasi, baca_status, reset_sesi
from utils.verifikasi_state import set_terverifikasi, get_verifikasi, reset_verifikasi
from utils.face_utils import (
    extract_embedding, embedding_to_binary, binary_to_embedding, 
    compare_faces, verifikasi_liveness
)
from utils.db_utils import (
    get_connection, insert_supir, get_all_supir, get_daftar_supir, get_supir_by_id,
    get_or_create_kendaraan, catat_timbang_masuk, catat_timbang_keluar, get_riwayat_transaksi, 
    get_user_by_username, update_last_login, cek_nik_supir_ada, cari_wajah_mirip_supir, 
    get_dashboard_summary_timbang, buat_tiket_security, cari_transaksi_by_qr, nonaktifkan_supir, 
    get_supir_lengkap_by_id, update_supir, batalkan_transaksi
)

app = Flask(__name__)
app.secret_key = "ganti-dengan-random-string-rahasia"

# Cek folder upload
UPLOAD_FOLDER = os.path.join("static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

camera_trigger_state = {
    "is_active": False,
    "last_scanned_driver": None
}

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)

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
            return render_template("login.html", error="Username atau password salah")

        user = User(row.Id, row.Username, row.NamaLengkap, row.Role)
        login_user(user)
        update_last_login(row.Id)
        return redirect("/dashboard")

    return render_template("login.html", error=None)

@app.route("/dashboard")
@login_required
def dashboard():
    summary = get_dashboard_summary_timbang()
    return render_template("dashboard.html", summary=summary, active_page="dashboard")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect("/login")

# 1. POS SECURITY CHECK-IN & TRIGGER KAMERA
@app.route("/security")
@login_required
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
  return jsonify(
      {"status": "SUCCESS", "message": "Trigger kamera dibatalkan"}
  ), 200

@app.route("/api/security/cetak-tiket", methods=["POST"])
@login_required
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

    return jsonify({
        "status": "SUCCESS",
        "qr_token": qr_token,
        "plat_nomor": plat_nomor,
        "nama_supir": nama_supir
    }), 200

# 2. POS JEMBATAN TIMBANG (BRUTO & TARA)
@app.route("/timbang")
@login_required
def timbang():
    return render_template("timbang.html", active_page="timbang")

@app.route("/api/timbang/scan-qr", methods=["POST"])
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
        "status": row.Status
    }

    # Set state terverifikasi
    set_terverifikasi(row.SupirId, row.NamaSupir)

    return jsonify({
        "status": "SUCCESS",
        "tiket": tiket
    }), 200

@app.route("/timbang/mulai", methods=["POST"])
def timbang_mulai():
    mulai_simulasi()
    return jsonify({"message": "Simulasi dimulai"})

@app.route("/timbang/status")
def timbang_status():
    return jsonify(baca_status())

@app.route("/timbang/kunci", methods=["POST"])
@login_required
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
        catat_timbang_masuk(row.SupirId, row.KendaraanId, berat, row.PlatNomor, qr_token)
        return jsonify({"message": f"Timbang MASUK berhasil. Tiket: {qr_token}. Berat: {berat} kg"}), 200

    if row.Status == 'Selesai' or row.Status == 'Perlu Cek Manual':
        return jsonify({"error": "Tiket ini sudah selesai ditimbang"}), 400

    netto, status_final = catat_timbang_keluar(row.Id, berat)
    if status_final == 'Perlu Cek Manual':
        return jsonify({"message": f"Timbang KELUAR tercatat, TAPI netto tidak valid ({netto} kg) — perlu Manual Check", "perlu_manual_check": True}), 200
    return jsonify({"message": f"Timbang KELUAR berhasil. Berat: {berat} kg, Netto: {netto} kg"}), 200

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
            is_match, _ = compare_faces(embedding_tersimpan, embedding_baru, threshold=0.55)
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
        camera_trigger_state["last_scanned_driver"] = {"supir_id": supir_id, "nama": nama}

        return jsonify({"message": f"Terverifikasi: {nama}", "nik": nik_asli, "nama": nama}), 200

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
        "nik": v.get("nik")
    })

# 4. RIWAYAT & MANAGEMENT SUPIR
@app.route("/riwayat")
@login_required
def riwayat():
    data = get_riwayat_transaksi()
    return render_template("riwayat.html", data=data, active_page="riwayat")

@app.route("/supir")
@login_required
def supir():
    data = get_daftar_supir()
    return render_template("supir.html", data=data, active_page="supir")

@app.route("/supir/register", methods=["POST"])
@login_required
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
        return jsonify({"error": f"Wajah ini sudah terdaftar sebagai '{nama_terdaftar}'"}), 400

    binary_data = embedding_to_binary(embedding)
    insert_supir(nama, binary_data, nik=nik, nomor_sim=nomor_sim, sim_berlaku=sim_berlaku, foto_path=f"uploads/{unique_filename}")

    return jsonify({"message": f"Supir '{nama}' berhasil didaftarkan"}), 200

@app.route("/supir/hapus/<int:supir_id>", methods=["POST"])
@login_required
def supir_hapus(supir_id):
    nonaktifkan_supir(supir_id)
    return jsonify({"message": "Supir berhasil dinonaktifkan"}), 200

@app.route("/supir/edit/<int:supir_id>", methods=["POST"])
@login_required
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
            return jsonify({"error": f"Wajah ini sudah terdaftar sebagai '{nama_terdaftar}'"}), 400

        embedding_binary = embedding_to_binary(embedding_baru)
        foto_path = f"uploads/{unique_filename}"

    update_supir(supir_id, nama, nik if nik else None, nomor_sim, sim_berlaku, embedding_binary, foto_path)
    return jsonify({"message": f"Data '{nama}' berhasil diperbarui"}), 200

@app.route("/riwayat/batalkan/<int:transaksi_id>", methods=["POST"])
@login_required
def riwayat_batalkan(transaksi_id):
    alasan = request.form.get("alasan", "").strip()
    if not alasan:
        return jsonify({"error": "Alasan pembatalan wajib diisi"}), 400
    batalkan_transaksi(transaksi_id, alasan, current_user.nama_lengkap)
    return jsonify({"message": "Transaksi ditandai batal"}), 200

if __name__ == "__main__":
    app.run(debug=True, port=5000)