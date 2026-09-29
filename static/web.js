/* ═══════════════════════════════════════════════════════════
   web.js — perilaku halaman gaya Miruro (tanpa framework)
   ═══════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  /* ── 1. HERO CAROUSEL: kartu tengah membesar, samping mengecil ── */
  var track = document.getElementById('heroTrack');
  var titik = document.getElementById('heroTitik');
  if (track) {
    var item = Array.prototype.slice.call(track.querySelectorAll('.hero-item'));
    var noktah = titik ? Array.prototype.slice.call(titik.querySelectorAll('span')) : [];
    var sekarang = 0;
    var diam = null;

    function tandai(i) {
      sekarang = (i + item.length) % item.length;
      item.forEach(function (el, k) { el.classList.toggle('aktif', k === sekarang); });
      noktah.forEach(function (el, k) { el.classList.toggle('on', k === sekarang); });
    }

    /* Geser ke kartu ke-i dengan menempatkannya di tengah layar. */
    function ke(i) {
      var k = (i + item.length) % item.length;
      var el = item[k];
      if (!el) return;
      var kiri = el.offsetLeft - (track.clientWidth - el.offsetWidth) / 2;
      track.scrollTo({ left: Math.max(0, kiri), behavior: 'smooth' });
      tandai(k);
      mulaiDiam();
    }

    /* Saat pengguna menggeser sendiri: tandai kartu terdekat ke tengah. */
    function dariGulir() {
      var tengah = track.scrollLeft + track.clientWidth / 2;
      var dekat = 0, jarak = Infinity;
      item.forEach(function (el, k) {
        var p = el.offsetLeft + el.offsetWidth / 2;
        var d = Math.abs(p - tengah);
        if (d < jarak) { jarak = d; dekat = k; }
      });
      if (dekat !== sekarang) tandai(dekat);
    }

    /* Rotasi otomatis tiap 6 dtk, berhenti sebentar setelah disentuh. */
    function mulaiDiam() {
      clearTimeout(diam);
      diam = setTimeout(function () { ke(sekarang + 1); }, 6000);
    }

    track.addEventListener('scroll', function () {
      window.clearTimeout(track._t);
      track._t = setTimeout(dariGulir, 90);
    }, { passive: true });

    ['pointerdown', 'touchstart', 'wheel'].forEach(function (ev) {
      track.addEventListener(ev, function () { clearTimeout(diam); }, { passive: true });
    });
    track.addEventListener('touchend', mulaiDiam, { passive: true });

    noktah.forEach(function (el, k) {
      el.addEventListener('click', function () { ke(k); });
    });

    /* Panah kiri/kanan papan ketik */
    document.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowLeft') ke(sekarang - 1);
      if (e.key === 'ArrowRight') ke(sekarang + 1);
    });

    /* Mulai di kartu pertama (posisi tengah) */
    requestAnimationFrame(function () { ke(0); });
  }

  /* ── 2. TOMBOL PANAH RAK: geser rak ke kiri/kanan ── */
  document.querySelectorAll('[data-geser]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var rak = document.getElementById(btn.getAttribute('data-rak'));
      if (!rak) return;
      var langkah = Math.max(240, rak.clientWidth * 0.8);
      rak.scrollBy({
        left: btn.getAttribute('data-geser') === 'kiri' ? -langkah : langkah,
        behavior: 'smooth'
      });
    });
  });

  /* ── 3. Sembunyikan panah kalau rak tidak bisa digeser ── */
  document.querySelectorAll('.rak').forEach(function (rak) {
    var kotak = rak.closest('.bagian');
    if (!kotak) return;
    var panah = kotak.querySelectorAll('[data-geser]');
    function segarkan() {
      var bisa = rak.scrollWidth > rak.clientWidth + 8;
      var diAwal = rak.scrollLeft <= 4;
      var diAkhir = rak.scrollLeft + rak.clientWidth >= rak.scrollWidth - 4;
      if (panah[0]) panah[0].style.opacity = (bisa && !diAwal) ? '1' : '.35';
      if (panah[1]) panah[1].style.opacity = (bisa && !diAkhir) ? '1' : '.35';
    }
    rak.addEventListener('scroll', segarkan, { passive: true });
    window.addEventListener('resize', segarkan);
    segarkan();
  });
})();
