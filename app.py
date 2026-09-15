import os
import json
import uuid
from flask import Flask, request, jsonify, render_template, redirect
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from utils.face_utils import extract_embedding, embedding_to_binary, binary_to_embedding, compare_faces, verifikasi_liveness
from utils.auth import User
from utils.db_utils import (
    get_connection, insert_supir, get_all_supir, get_daftar_supir, get_supir_by_id,
    get_or_create_kendaraan, cari_transaksi_terbuka, catat_timbang_masuk,
    catat_timbang_keluar, get_riwayat_transaksi, get_user_by_username, update_last_login, 
    get_daftar_supir, cek_nik_supir_ada, cari_wajah_mirip_supir, get_dashboard_summary_timbang
)
from utils.timbang_state import mulai_simulasi, baca_status, reset_sesi
from utils.verifikasi_state import set_terverifikasi, get_verifikasi, reset_verifikasi

app = Flask(__name__)
app.secret_key = "ganti-dengan-random-string-rahasia"
UPLOAD_FOLDER = "static/uploads"

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

@app.route("/timbang")
def timbang():
    return render_template("timbang.html", active_page="timbang")

@app.route("/timbang/mulai", methods=["POST"])
def timbang_mulai():
    mulai_simulasi()
    return jsonify({"message": "Simulasi dimulai"})

@app.route("/timbang/status")
def timbang_status():
    return jsonify(baca_status())

@app.route("/timbang/kunci", methods=["POST"])
def timbang_kunci():
    status = baca_status()
    if not status["siap_kunci"]:
        return jsonify({"error": "Berat belum stabil"}), 400

    v = get_verifikasi()
    if v is None:
        return jsonify({"error": "Belum ada verifikasi wajah supir"}), 400

    plat_nomor = request.form.get("plat_nomor", "").strip().upper()
    if not plat_nomor:
        return jsonify({"error": "Plat nomor wajib diisi"}), 400

    supir_id, nama = v["supir_id"], v["nama"]
    berat = status["berat"]
    kendaraan_id = get_or_create_kendaraan(plat_nomor)
    transaksi_terbuka = cari_transaksi_terbuka(supir_id, kendaraan_id)

    reset_verifikasi()

    if transaksi_terbuka is None:
        nomor_tiket = catat_timbang_masuk(supir_id, kendaraan_id, berat, plat_nomor)
        reset_sesi()
        return jsonify({"message": f"Timbang MASUK berhasil. Tiket: {nomor_tiket}. Berat: {berat} kg", "supir": nama}), 200
    else:
        catat_timbang_keluar(transaksi_terbuka.Id, berat)
        reset_sesi()
        netto = transaksi_terbuka.BeratBruto - berat
        return jsonify({"message": f"Timbang KELUAR berhasil. Berat: {berat} kg, Netto: {netto} kg", "supir": nama}), 200

@app.route("/timbang/verifikasi-wajah", methods=["POST"])
def verifikasi_wajah_timbang():
    files = request.files.getlist("frames")
    tantangan = request.form.get("tantangan", "KEDIP")

    if not files or len(files) < 3:
        return jsonify({"error": "Frame tidak cukup"}), 400

    filepaths = []
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
    set_terverifikasi(supir_id, nama)
    return jsonify({"message": f"Terverifikasi: {nama}"}), 200

@app.route("/timbang/status-verifikasi")
def status_verifikasi():
    v = get_verifikasi()
    if v is None:
        return jsonify({"terverifikasi": False})
    return jsonify({"terverifikasi": True, "supir_id": v["supir_id"], "nama": v["nama"]})

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
        return jsonify({"error": "Wajah tidak terdeteksi di foto"}), 400

    wajah_mirip = cari_wajah_mirip_supir(embedding)
    if wajah_mirip:
        _, nama_terdaftar = wajah_mirip
        return jsonify({"error": f"Wajah ini sudah terdaftar sebagai '{nama_terdaftar}'"}), 400

    binary_data = embedding_to_binary(embedding)
    insert_supir(nama, binary_data, nik=nik, nomor_sim=nomor_sim, sim_berlaku=sim_berlaku, foto_path=f"uploads/{unique_filename}")

    return jsonify({"message": f"Supir '{nama}' berhasil didaftarkan"}), 200

if __name__ == "__main__":
    app.run(debug=True)

