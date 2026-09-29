/* web.js — interaksi ringan (tanpa framework) */
document.addEventListener('DOMContentLoaded', function () {

  // geser rak dgn tombol roda (desktop)
  document.querySelectorAll('[data-geser]').forEach(function (rak) {
    rak.addEventListener('wheel', function (e) {
      if (Math.abs(e.deltaY) > Math.abs(e.deltaX)) {
        rak.scrollLeft += e.deltaY;
        e.preventDefault();
      }
    }, { passive: false });
  });

  // tombol "selengkapnya" sinopsis
  var btn = document.getElementById('btn-sinopsis');
  var box = document.getElementById('sinopsis');
  if (btn && box) {
    btn.addEventListener('click', function () {
      box.classList.toggle('buka');
      btn.textContent = box.classList.contains('buka') ? 'Ringkas ▴' : 'Selengkapnya ▾';
    });
  }

  // pintasan keyboard saat membaca bab
  var navL = document.querySelector('.baca-nav a:not(.kembali):not(.mati)');
  document.addEventListener('keydown', function (e) {
    if (e.target.tagName === 'INPUT') return;
    if (e.key === 'ArrowRight' && navL) {
      var n = document.querySelectorAll('.baca-nav a');
      if (n[2] && !n[2].classList.contains('mati')) location.href = n[2].href;
    }
    if (e.key === 'ArrowLeft' && navL && !navL.classList.contains('mati')) {
      location.href = navL.href;
    }
  });

  // simpan posisi baca terakhir (biar bisa lanjut)
  var isi = document.querySelector('.baca-isi');
  if (isi) {
    try {
      localStorage.setItem('naver_terakhir', location.pathname);
    } catch (e) {}
  }
});
