document.getElementById('formTambahUser').addEventListener('submit', async function (e) {
    e.preventDefault();
    const formData = new FormData(this);
    const res = await fetch('/admin/users/tambah', { method: 'POST', body: formData });
    const data = await res.json();
    alert(data.message || data.error);
    if (data.message) location.reload();
});

let userIdReset = null;
function bukaResetPassword(id) {
    userIdReset = id;
    openModal('modalResetPassword');
}

document.getElementById('formResetPassword').addEventListener('submit', async function (e) {
    e.preventDefault();
    const formData = new FormData(this);
    const res = await fetch(`/admin/users/reset-password/${userIdReset}`, { method: 'POST', body: formData });
    const data = await res.json();
    alert(data.message || data.error);
    if (data.message) closeModal('modalResetPassword');
});

async function toggleStatus(id, statusBaru) {
    const aksi = statusBaru === 1 ? "aktifkan kembali" : "nonaktifkan";
    if (!confirm(`Yakin ${aksi} user ini?`)) return;
    const formData = new FormData();
    formData.append('status', statusBaru);
    const res = await fetch(`/admin/users/toggle/${id}`, { method: 'POST', body: formData });
    const data = await res.json();
    alert(data.message || data.error);
    if (data.message) location.reload();
}