let fotoBlobDaftar = null;
let streamDaftar = null;

function pilihModeFoto(mode) {
    const btnUpload = document.getElementById('btnModeUpload');
    const btnKamera = document.getElementById('btnModeKamera');
    const areaUpload = document.getElementById('areaUpload');
    const areaKamera = document.getElementById('areaKamera');
    const inputFile = document.getElementById('inputFotoFile');

    if (mode === 'upload') {
        btnUpload.className = "text-xs px-3 py-1.5 rounded-lg bg-emerald-600 text-white";
        btnKamera.className = "text-xs px-3 py-1.5 rounded-lg bg-slate-700 text-slate-300";
        areaUpload.classList.remove('hidden');
        areaKamera.classList.add('hidden');
        inputFile.required = true;
        if (streamDaftar) { streamDaftar.getTracks().forEach(t => t.stop()); streamDaftar = null; }
    } else {
        btnKamera.className = "text-xs px-3 py-1.5 rounded-lg bg-emerald-600 text-white";
        btnUpload.className = "text-xs px-3 py-1.5 rounded-lg bg-slate-700 text-slate-300";
        areaUpload.classList.add('hidden');
        areaKamera.classList.remove('hidden');
        inputFile.required = false;
        navigator.mediaDevices.getUserMedia({ video: true }).then(stream => {
            streamDaftar = stream;
            document.getElementById('videoDaftar').srcObject = stream;
        }).catch(err => alert("Gagal akses kamera: " + err.message));
    }
}

function ambilFotoDaftar() {
    const video = document.getElementById('videoDaftar');
    const canvas = document.getElementById('canvasDaftar');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext('2d').drawImage(video, 0, 0);
    canvas.toBlob(blob => {
        fotoBlobDaftar = blob;
        document.getElementById('previewStatus').classList.remove('hidden');
    }, 'image/jpeg');
}

document.getElementById("form-register").addEventListener("submit", async function (e) {
    e.preventDefault();
    const formData = new FormData(this);
    const modeKamera = !document.getElementById('areaKamera').classList.contains('hidden');
    if (modeKamera) {
        if (!fotoBlobDaftar) { alert("Ambil foto dulu"); return; }
        formData.delete('foto');
        formData.append('foto', fotoBlobDaftar, 'capture.jpg');
    }
    try {
        const response = await fetch("/supir/register", { method: "POST", body: formData });
        const data = await response.json();
        alert(data.message || data.error || "Terjadi kesalahan");
        if (data.message) { closeModal('modalDaftar'); location.reload(); }
    } catch (err) { alert("Gagal menghubungi server: " + err); }
});

function openEditModal(id, nama, nik, sim, simBerlaku) {
    document.getElementById('edit-nama').value = nama;
    document.getElementById('edit-nik').value = nik;
    document.getElementById('edit-sim').value = sim;
    document.getElementById('edit-sim-berlaku').value = simBerlaku;
    document.getElementById('form-edit').action = `/supir/edit/${id}`;
    openModal('modalEdit');
}

document.getElementById("form-edit").addEventListener("submit", async function (e) {
    e.preventDefault();
    const formData = new FormData(this);
    try {
        const response = await fetch(this.action, { method: "POST", body: formData });
        const data = await response.json();
        alert(data.message || data.error || "Terjadi kesalahan");
        if (data.message) { closeModal('modalEdit'); location.reload(); }
    } catch (err) { alert("Gagal menghubungi server: " + err); }
});

async function hapusSupir(id) {
    if (!confirm("Nonaktifkan supir ini? Data riwayat timbang tetap tersimpan.")) return;
    const res = await fetch(`/supir/hapus/${id}`, { method: 'POST' });
    const data = await res.json();
    alert(data.message || data.error);
    if (data.message) location.reload();
}