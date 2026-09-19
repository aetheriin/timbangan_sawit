let transaksiIdAktif = null;

function tambahBukti(id) {
    transaksiIdAktif = id;
    openModal('modalBukti');
}

document.getElementById('formBukti').addEventListener('submit', async function (e) {
    e.preventDefault();
    const formData = new FormData(this);
    const res = await fetch(`/riwayat/tambah-bukti/${transaksiIdAktif}`, { method: 'POST', body: formData });
    const data = await res.json();
    alert(data.message || data.error);
    if (data.message) location.reload();
});

document.querySelectorAll('.lihat-bukti-btn').forEach(btn => {
    btn.addEventListener('click', function () {
        const catatan = this.dataset.catatan;
        const foto = this.dataset.foto;

        document.getElementById('lihatBuktiCatatan').textContent = catatan;

        const fotoWrapper = document.getElementById('lihatBuktiFotoWrapper');
        const tanpaFoto = document.getElementById('lihatBuktiTanpaFoto');
        const fotoImg = document.getElementById('lihatBuktiFoto');

        if (foto) {
            fotoImg.src = foto;
            fotoWrapper.classList.remove('hidden');
            tanpaFoto.classList.add('hidden');
        } else {
            fotoWrapper.classList.add('hidden');
            tanpaFoto.classList.remove('hidden');
        }

        openModal('modalLihatBukti');
    });
});

async function setujuiTransaksi(id) {
    if (!confirm("Setujui transaksi ini jadi Selesai?")) return;
    const res = await fetch(`/riwayat/setujui/${id}`, { method: 'POST' });
    const data = await res.json();
    alert(data.message || data.error);
    if (data.message) location.reload();
}

async function tolakTransaksi(id) {
    const alasan = prompt("Alasan penolakan:");
    if (!alasan) return;
    const formData = new FormData();
    formData.append('alasan', alasan);
    const res = await fetch(`/riwayat/tolak/${id}`, { method: 'POST', body: formData });
    const data = await res.json();
    alert(data.message || data.error);
    if (data.message) location.reload();
}

async function batalkanTransaksi(id) {
    const alasan = prompt("Alasan pembatalan transaksi ini:");
    if (!alasan) return;
    const formData = new FormData();
    formData.append('alasan', alasan);
    const res = await fetch(`/riwayat/batalkan/${id}`, { method: 'POST', body: formData });
    const data = await res.json();
    alert(data.message || data.error);
    if (data.message) location.reload();
}