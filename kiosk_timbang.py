import io
import random
import time
import cv2
import face_recognition
import mediapipe as mp
import numpy as np
import requests

SERVER_URL = "http://127.0.0.1:5000/timbang/verifikasi-wajah"
URL_TRIGGER = "http://127.0.0.1:5000/api/kamera/status"
URL_BATAL = "http://127.0.0.1:5000/api/kamera/batal"
KAMERA_INDEX = 0
JUMLAH_FRAME_LIVENESS = 12
JEDA_ANTAR_FRAME = 0.20
DURASI_TAMPIL_HASIL = 5
NAMA_JENDELA = "Verifikasi Supir - Timbangan"

# Inisialisasi MediaPipe Face Mesh
mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(
    max_num_faces=1,
    refine_landmarks=True,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5,
)

# Indeks landmark mata
EYE_LEFT = [362, 385, 387, 263, 373, 380]
EYE_RIGHT = [33, 160, 158, 133, 153, 144]

def frame_ke_bytes(frame):
  """Convert frame OpenCV (numpy array) jadi bytes JPEG untuk dikirim via HTTP."""
  ret, buffer = cv2.imencode('.jpg', frame)
  return io.BytesIO(buffer.tobytes())

def kirim_ke_server(frames, tantangan):
  files = []
  for i, frame in enumerate(frames):
    buf = frame_ke_bytes(frame)
    files.append(('frames', (f'frame{i}.jpg', buf, 'image/jpeg')))

  try:
    response = requests.post(
        SERVER_URL, files=files, data={'tantangan': tantangan}, timeout=10
    )
    return response.json()
  except Exception as e:
    return {'error': f'Gagal menghubungi server: {e}'}

def gambar_kotak_wajah(frame, lokasi_wajah):
  for top, right, bottom, left in lokasi_wajah:
    cv2.rectangle(frame, (left, top), (right, bottom), (0, 200, 0), 2)

def hitung_ear(landmarks, indeks_mata, w, h):
  """Menghitung Eye Aspect Ratio (EAR) untuk deteksi kedipan."""
  p = []
  for idx in indeks_mata:
    pt = landmarks[idx]
    p.append(np.array([pt.x * w, pt.y * h]))

  d_v1 = np.linalg.norm(p[1] - p[5])
  d_v2 = np.linalg.norm(p[2] - p[4])
  d_h = np.linalg.norm(p[0] - p[3])

  return (d_v1 + d_v2) / (2.0 * d_h)

def cek_liveness_lokal(frame):
  """Memeriksa apakah wajah menghadap depan dan sedang berkedip."""
  h, w, _ = frame.shape
  rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
  results = face_mesh.process(rgb_frame)

  menghadap_depan = False
  kedip = False

  if results.multi_face_landmarks:
    landmarks = results.multi_face_landmarks[0].landmark

    # Cek wajah lurus ke depan
    hidung = landmarks[1].x * w
    mata_kiri = landmarks[263].x * w
    mata_kanan = landmarks[33].x * w
    jarak_kiri = abs(hidung - mata_kiri)
    jarak_kanan = abs(hidung - mata_kanan)
    rasio = jarak_kiri / (jarak_kanan + 1e-6)

    if 0.65 <= rasio <= 1.35:
      menghadap_depan = True

    # Cek kedipan mata
    ear_kiri = hitung_ear(landmarks, EYE_LEFT, w, h)
    ear_kanan = hitung_ear(landmarks, EYE_RIGHT, w, h)
    avg_ear = (ear_kiri + ear_kanan) / 2.0

    if avg_ear < 0.21:  # Batas kelopak mata berkedip
      kedip = True

  return menghadap_depan, kedip

def cek_arah_wajah(landmarks, w):
  """Return rasio untuk deteksi arah hadap: <1 menoleh kanan, >1 menoleh kiri, ~1 lurus."""
  hidung = landmarks[1].x * w
  mata_kiri = landmarks[263].x * w
  mata_kanan = landmarks[33].x * w
  jarak_kiri = abs(hidung - mata_kiri)
  jarak_kanan = abs(hidung - mata_kanan)
  return jarak_kiri / (jarak_kanan + 1e-6)

def gambar_banner_status(frame, teks_utama, teks_sub='', warna_bg=(0, 0, 0)):
  """Menggambar banner transparan di bagian atas agar teks rapi & proporsional."""
  h, w = frame.shape[:2]

  skala_utama = max(0.45, w / 1100.0)
  skala_sub = max(0.35, w / 1400.0)
  tebal = 1 if w < 640 else 2

  overlay = frame.copy()
  tinggi_banner = int(h * 0.15) if teks_sub else int(h * 0.10)
  cv2.rectangle(overlay, (0, 0), (w, tinggi_banner), warna_bg, -1)
  cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)

  cv2.putText(
      frame,
      teks_utama,
      (20, int(tinggi_banner * 0.5)),
      cv2.FONT_HERSHEY_SIMPLEX,
      skala_utama,
      (255, 255, 255),
      tebal,
      cv2.LINE_AA,
  )

  if teks_sub:
    cv2.putText(
        frame,
        teks_sub,
        (20, int(tinggi_banner * 0.85)),
        cv2.FONT_HERSHEY_SIMPLEX,
        skala_sub,
        (200, 200, 200),
        1,
        cv2.LINE_AA,
    )

def gambar_overlay_hasil(frame, teks_utama, teks_sub, warna):
  """Tampilan penuh saat hasil respons dari server muncul."""
  h, w = frame.shape[:2]
  overlay = frame.copy()
  cv2.rectangle(overlay, (0, 0), (w, h), warna, -1)
  cv2.addWeighted(overlay, 0.75, frame, 0.25, 0, frame)

  skala_utama = max(0.6, w / 800.0)
  skala_sub = max(0.45, w / 1100.0)

  cv2.putText(
      frame,
      teks_utama,
      (30, h // 2 - 10),
      cv2.FONT_HERSHEY_SIMPLEX,
      skala_utama,
      (255, 255, 255),
      2,
      cv2.LINE_AA,
  )
  cv2.putText(
      frame,
      teks_sub,
      (30, h // 2 + 35),
      cv2.FONT_HERSHEY_SIMPLEX,
      skala_sub,
      (255, 255, 255),
      1,
      cv2.LINE_AA,
  )

def jendela_masih_terbuka():
  try:
    return cv2.getWindowProperty(NAMA_JENDELA, cv2.WND_PROP_VISIBLE) >= 1
  except cv2.error:
    return False

def notify_batal_to_server():
    """Memberitahu server Flask bahwa scan dibatalkan agar status camera_trigger_state di-reset."""
    try:
        requests.post(URL_BATAL, timeout=2)
        print("[!] Scan dibatalkan oleh pengguna. Mengirim sinyal reset ke server...")
    except Exception:
        pass

def jalankan_verifikasi_wajah():
    video = cv2.VideoCapture(KAMERA_INDEX)
    if not video.isOpened():
        print("Gagal membuka kamera. Cek KAMERA_INDEX atau koneksi webcam.")
        notify_batal_to_server()
        return

    cv2.namedWindow(NAMA_JENDELA, cv2.WINDOW_NORMAL)

    status = "IDLE"
    waktu_status_berubah = time.time()
    hasil_terakhir = None
    gagal_baca_beruntun = 0
    lokasi_terakhir = []
    terdeteksi_kedip = False
    tantangan_terpilih = None
    dibatalkan_manual = False

    while True:
        # Cek jika pengguna menutup jendela via tombol [X]
        if not jendela_masih_terbuka():
            print("Jendela ditutup oleh pengguna (Tombol X).")
            dibatalkan_manual = True
            break

        ret, frame = video.read()
        if not ret or frame is None:
            gagal_baca_beruntun += 1
            if gagal_baca_beruntun >= 10:
                print("Kamera tidak mengirim gambar valid.")
                dibatalkan_manual = True
                break
            if cv2.waitKey(1) & 0xFF == ord('q'):
                dibatalkan_manual = True
                break
            continue

        gagal_baca_beruntun = 0
        frame = cv2.flip(frame, 1)

        # 1. STATUS IDLE
        if status == "IDLE":
            small_frame = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
            lokasi_wajah = face_recognition.face_locations(small_frame)
            lokasi_wajah_asli = [(t*2, r*2, b*2, l*2) for (t, r, b, l) in lokasi_wajah]
            gambar_kotak_wajah(frame, lokasi_wajah_asli)

            gambar_banner_status(frame, "Arahkan wajah ke kamera...", "Pastikan wajah terlihat jelas (Tekan 'Q' / X untuk batal)", (0, 0, 0))

            if len(lokasi_wajah) > 0:
                lokasi_terakhir = lokasi_wajah_asli
                tantangan_terpilih = random.choice(["KEDIP", "MENOLEH_KANAN", "MENOLEH_KIRI"])
                status = "WAJAH_LURUS"

        # 2. STATUS CEK WAJAH LURUS
        elif status == "WAJAH_LURUS":
            gambar_kotak_wajah(frame, lokasi_terakhir)
            lurus, _ = cek_liveness_lokal(frame)
            
            if lurus:
                gambar_banner_status(frame, "Wajah Sesuai!", "Bersiap untuk verifikasi...", (0, 100, 0))
                status = "TANTANGAN_LIVENESS"
                terdeteksi_kedip = False
            else:
                gambar_banner_status(frame, "Silahkan menghadap ke kamera", "Posisikan wajah lurus ke depan", (0, 50, 150))

        # 3. STATUS CEK KEDIP MATA / TANTANGAN
        elif status == "TANTANGAN_LIVENESS":
            gambar_kotak_wajah(frame, lokasi_terakhir)
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = face_mesh.process(rgb_frame)

            berhasil = False
            if results.multi_face_landmarks:
                landmarks = results.multi_face_landmarks[0].landmark
                h, w, _ = frame.shape

                if tantangan_terpilih == "KEDIP":
                    gambar_banner_status(frame, "Silahkan kedipkan mata", "Kedipkan mata untuk verifikasi", (0, 120, 180))
                    _, kedip = cek_liveness_lokal(frame)
                    if kedip:
                        terdeteksi_kedip = True
                    if terdeteksi_kedip and not kedip:
                        berhasil = True

                elif tantangan_terpilih == "MENOLEH_KANAN":
                    gambar_banner_status(frame, "Silahkan menoleh ke KANAN", "Tahan sebentar lalu kembali", (0, 120, 180))
                    rasio = cek_arah_wajah(landmarks, w)
                    if rasio < 0.6:
                        berhasil = True

                elif tantangan_terpilih == "MENOLEH_KIRI":
                    gambar_banner_status(frame, "Silahkan menoleh ke KIRI", "Tahan sebentar lalu kembali", (0, 120, 180))
                    rasio = cek_arah_wajah(landmarks, w)
                    if rasio > 1.8:
                        berhasil = True

            if berhasil:
                status = "CAPTURING"
                waktu_status_berubah = time.time()

        # 4. STATUS AMBIL FRAME (CAPTURING)
        elif status == "CAPTURING":
            frames_liveness = []
            dibatalkan = False

            for _ in range(JUMLAH_FRAME_LIVENESS):
                ret, f = video.read()
                if ret:
                    f = cv2.flip(f, 1)
                    frames_liveness.append(f)

                    gambar_kotak_wajah(f, lokasi_terakhir)
                    gambar_banner_status(f, "Memverifikasi... Jangan bergerak", "Mengirim data ke server...", (0, 100, 200))
                    cv2.imshow(NAMA_JENDELA, f)

                key = cv2.waitKey(int(JEDA_ANTAR_FRAME * 1000)) & 0xFF
                if key == ord('q') or not jendela_masih_terbuka():
                    dibatalkan = True
                    dibatalkan_manual = True
                    break

            if dibatalkan:
                break

            hasil_terakhir = kirim_ke_server(frames_liveness, tantangan_terpilih)
            status = "HASIL"
            waktu_status_berubah = time.time()

        # 5. STATUS HASIL RESPON SERVER
        elif status == "HASIL":
            if hasil_terakhir and hasil_terakhir.get("message"):
                gambar_overlay_hasil(frame, hasil_terakhir["message"], "Terima kasih! Menutup kamera...", (30, 100, 30))
            else:
                err_msg = hasil_terakhir.get("error", "Gagal Verifikasi") if hasil_terakhir else "Error"
                gambar_overlay_hasil(frame, err_msg, "Silakan coba lagi", (30, 30, 130))

            if time.time() - waktu_status_berubah > DURASI_TAMPIL_HASIL:
                print("[+] Verifikasi selesai. Menutup jendela kamera...")
                break

        cv2.imshow(NAMA_JENDELA, frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            dibatalkan_manual = True
            break

    video.release()
    cv2.destroyAllWindows()
    cv2.waitKey(1)

    # Jika dibatalkan manual (tombol X / Q)
    if dibatalkan_manual:
        notify_batal_to_server()


def main():
  """Main Loop Background Service untuk menunggu trigger dari Pos Security."""
  print("===========================================================")
  print("  KIOSK CAMERA SERVICE STANDBY - MENUNGGU TRIGGER SECURITY ")
  print("===========================================================")

  try:
    while True:
      try:
        # Pengecekan status trigger ke server Flask
        res = requests.get(URL_TRIGGER, timeout=2).json()

        if res.get("is_active") is True:
          print("\n[!] Sinyal diterima dari Security! Membuka kamera...")
          jalankan_verifikasi_wajah()
          print("[+] Kamera ditutup. Kembali ke mode siaga...\n")

      except requests.exceptions.RequestException:
        # Abaikan error jika server app.py belum dinyalakan/berjalan
        pass

      # Jeda 1 detik agar penggunaan CPU tetap ringan
      time.sleep(1)

  except KeyboardInterrupt:
    print("\nProgram dihentikan oleh pengguna. Keluar...")


if __name__ == "__main__":
  main()