let pollingInterval = null;

async function mulaiScanWajah() {
    const btnScan = document.getElementById('btnScanWajah');
    const statusKamera = document.getElementById('statusKamera');

    btnScan.disabled = true;
    btnScan.className = "w-full bg-slate-700 text-slate-400 font-semibold py-3 px-4 rounded-xl flex items-center justify-center gap-2 cursor-not-allowed";
    statusKamera.classList.remove('hidden');

    try {
        await fetch('/api/kamera/start', { method: 'POST' });
        if (pollingInterval) clearInterval(pollingInterval);

        pollingInterval = setInterval(async () => {
            const resVerifikasi = await fetch('/timbang/status-verifikasi');
            const dataVerifikasi = await resVerifikasi.json();

            if (dataVerifikasi.terverifikasi) {
                clearInterval(pollingInterval);
                statusKamera.classList.add('hidden');
                isiFormDariVerifikasi(dataVerifikasi);
                resetTombolScan(btnScan);
                return;
            }

            const resKamera = await fetch('/api/kamera/status');
            const dataKamera = await resKamera.json();

            if (dataKamera.is_active === false) {
                const resUlang = await fetch('/timbang/status-verifikasi');
                const dataUlang = await resUlang.json();

                if (dataUlang.terverifikasi) {
                    clearInterval(pollingInterval);
                    statusKamera.classList.add('hidden');
                    isiFormDariVerifikasi(dataUlang);
                    resetTombolScan(btnScan);
                    return;
                }

                clearInterval(pollingInterval);
                statusKamera.classList.add('hidden');
                resetTombolScan(btnScan);
            }
        }, 1000);

    } catch (err) {
        alert("Gagal menghubungi server backend.");
        statusKamera.classList.add('hidden');
        resetTombolScan(btnScan);
    }
}

function isiFormDariVerifikasi(data) {
    document.getElementById('secNik').value = data.nik || '-';
    document.getElementById('secSupirId').value = data.supir_id;
    document.getElementById('secNama').value = data.nama;
    document.getElementById('btnCetak').disabled = false;
    document.getElementById('secPlat').focus();
}

function resetTombolScan(btn) {
    btn.disabled = false;
    btn.className = "w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold py-3 px-4 rounded-xl flex items-center justify-center gap-2 transition cursor-pointer";
}

async function handleCetakTiket(e) {
    e.preventDefault();
    const plat = document.getElementById('secPlat').value.trim();
    const supirId = document.getElementById('secSupirId').value.trim();
    const nama = document.getElementById('secNama').value.trim();

    if (!plat || !supirId) {
        alert("Plat nomor dan data supir wajib terisi!");
        return;
    }

    try {
        const res = await fetch('/api/security/cetak-tiket', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ plat_nomor: plat, supir_id: supirId, nama: nama })
        });
        const result = await res.json();

        if (res.ok && result.status === 'SUCCESS') {
            generateTiketBarcode(result.qr_token, result.plat_nomor, result.nama_supir);
        } else {
            alert(result.error || "Gagal mencetak tiket!");
        }
    } catch (err) {
        alert("Gagal memproses tiket barcode.");
    }
}

function generateTiketBarcode(qrToken, platNomor, namaSupir) {
    document.getElementById('barcodeTokenText').innerText = qrToken;
    document.getElementById('detailTiketText').innerText = `${platNomor} - ${namaSupir}`;

    const container = document.getElementById('qrcodeCanvas');
    container.innerHTML = "";

    new QRCode(container, {
        text: qrToken,
        width: 160,
        height: 160,
        colorDark: "#000000",
        colorLight: "#ffffff",
        correctLevel: QRCode.CorrectLevel.H
    });

    openModal('modalCetakTiket');
}

function tutupModal() {
    closeModal('modalCetakTiket');
    document.getElementById('formCheckin').reset();
    document.getElementById('secNik').value = '';
    document.getElementById('secSupirId').value = '';
    document.getElementById('secNama').value = '';
    document.getElementById('btnCetak').disabled = true;
}