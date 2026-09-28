#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
web/main.py — WEB NAVER (SSR) untuk arsip novel sendiri.

Arsitektur:
  · FastAPI + Jinja2 (HTML dirender SERVER → ramah SEO)
  · Database: naver.db (SQLite, dibaca LANGSUNG -- tidak lewat HTTP API,
    supaya waktu muat cepat & tidak dobel rate-limit)
  · Tampilan: meniru UX novelpia (hero, kartu grid, rak geser),
    WARNA & SECTION mengikuti APK Naver:
        Bg #071018 · Header #0E1B26 · Aksen Cyan #049DFD
  · Tailwind dibaca dari file LOKAL (assets/tw.css) — kalau tidak ada,
    jatuh ke CDN. JS dari assets/web.js (bukan inline, biar CSP aman).

Jalankan:
    uvicorn main:app --host 127.0.0.1 --port 8100
"""
import json
import os
import re
import sqlite3
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse,
                               PlainTextResponse, Response)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent
DB = ROOT / "naver.db"

app = FastAPI(title="Naver Web", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")
tpl = Jinja2Templates(directory=str(BASE / "templates"))


@app.middleware("http")
async def atur_cache(request, call_next):
    """Berkas /static: cache 1 jam + wajib revalidate.

    Cloudflare sebelumnya menyimpan CSS 4 jam (`max-age=14400`) → tampilan
    lama bertahan lama. Sekarang 1 jam dan `must-revalidate` supaya berkas
    yang berubah cepat terpakai. HTML tidak di-cache (selalu segar).
    """
    jawab = await call_next(request)
    if request.url.path.startswith("/static/"):
        jawab.headers["Cache-Control"] = "public, max-age=3600, must-revalidate"
    elif jawab.headers.get("content-type", "").startswith("text/html"):
        jawab.headers["Cache-Control"] = "no-cache"
    return jawab


def _versi_aset() -> str:
    """Versi aset ikut waktu-ubah berkas CSS/JS.

    Dipakai di base.html sebagai `?v=` supaya browser & Cloudflare TIDAK
    menyajikan CSS basi (pelajaran 28 Sep: CF cache `max-age=14400` bikin
    tampilan lama bertahan sampai 4 jam walau berkas sudah diperbarui).
    """
    try:
        t = max((BASE / "static" / n).stat().st_mtime
                for n in ("web.css", "web.js")
                if (BASE / "static" / n).exists())
        return str(int(t))
    except Exception:
        return "1"


tpl.env.globals["versi_aset"] = _versi_aset

# ── konfigurasi situs (dipakai di <head> utk SEO) ──
SITUS = os.environ.get("NAVER_SITUS", "https://navernovel.my.id")
NAMA = "Naver Novel"
DESK = ("Baca novel terjemahan Indonesia gratis: web novel & light novel "
        "lengkap dengan ilustrasi, update tiap hari.")


def db():
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=25)
    con.row_factory = sqlite3.Row
    return con


def kartu(r, dasar="") -> dict:
    """Bentuk 1 novel jadi kartu tampilan."""
    return {
        "id": r["id"], "slug": r["slug"], "judul": r["judul"],
        "cover": f"/cover/{r['id']}.webp" if r["cover_webp"] else None,
        "jumlah_bab": r["jumlah_bab"], "rating": r["rating"],
        "status": r["status"], "tipe": r["tipe"], "country": r["country"],
        "url": f"/novel/{r['slug']}",
    }


def ambil(q, par=(), satu=False):
    con = db()
    try:
        cur = con.execute(q, par)
        r = cur.fetchone() if satu else cur.fetchall()
        return r
    finally:
        con.close()


# ═════════════════════════════════════════════════════════════
#  HALAMAN: BERANDA
# ═════════════════════════════════════════════════════════════
@app.get("/", response_class=HTMLResponse)
def beranda(request: Request):
    n = ambil("SELECT COUNT(*) c FROM novel", satu=True)["c"]
    b = ambil("SELECT COUNT(*) c FROM bab", satu=True)["c"]
    # HERO: novel rating tertinggi (rating 0 dilewati — 148 novel ratingnya 0)
    hero = [kartu(r) for r in ambil(
        "SELECT * FROM novel WHERE cover_webp IS NOT NULL AND judul != '' "
        "AND COALESCE(rating,0) >= 1 "
        "ORDER BY rating DESC, bookmark DESC LIMIT 3")]
    # TRENDING: paling banyak di-bookmark
    trending = [kartu(r) for r in ambil(
        "SELECT * FROM novel WHERE cover_webp IS NOT NULL AND judul != '' "
        "ORDER BY COALESCE(bookmark,0) DESC LIMIT 10")]
    # RANDOM: tetap sama tiap hari (seed tanggal) supaya tidak berkedip saat reload
    seed = int(time.strftime("%Y%m%d"))
    acak = [kartu(r) for r in ambil(
        "SELECT * FROM novel WHERE cover_webp IS NOT NULL AND judul != '' "
        "ORDER BY (id * ?) % 10007 LIMIT 10", (seed,))]
    # BARU DI TAMBAH: created_at terbaru (TERISI SEMUA, tidak seperti waktu_update)
    baru = [kartu(r) for r in ambil(
        "SELECT * FROM novel WHERE cover_webp IS NOT NULL AND judul != '' "
        "ORDER BY created_at DESC LIMIT 10")]
    # LATEST UPDATE: pakai MAX(bab.tanggal) — waktu_update KOSONG di 478/495 novel.
    # ⚠️ JANGAN pakai "GROUP BY n.id + MAX()" → 12 detik (pindai 111.680 bab).
    #    Cara cepat: ambil 60 bab terbaru (kena index idx_bab_tanggal, 0,01 dtk),
    #    baru ambil novel uniknya. Lihat tambah-index-tanggal.py.
    update, sudah = [], set()
    for r in ambil("""
        SELECT b.tanggal AS tg, n.*
        FROM bab b JOIN novel n ON n.id = b.novel_id
        WHERE b.tanggal IS NOT NULL AND b.tanggal != ''
          AND n.cover_webp IS NOT NULL AND n.judul != ''
        ORDER BY b.tanggal DESC LIMIT 60"""):
        if r["id"] in sudah:
            continue
        sudah.add(r["id"])
        k = kartu(r)
        k["tanggal"] = (r["tg"] or "")[:10]
        k["c_bab"] = r["jumlah_bab"]
        update.append(k)
        if len(update) >= 10:
            break
    # TAMAT: status Completed
    tamat = [kartu(r) for r in ambil(
        "SELECT * FROM novel WHERE cover_webp IS NOT NULL AND judul != '' "
        "AND LOWER(COALESCE(status,'')) LIKE '%complete%' "
        "ORDER BY COALESCE(rating,0) DESC, COALESCE(bookmark,0) DESC LIMIT 10")]
    ongoing = [kartu(r) for r in ambil(
        "SELECT * FROM novel WHERE cover_webp IS NOT NULL AND judul != '' "
        "AND LOWER(COALESCE(status,'')) LIKE '%ongoing%' "
        "ORDER BY COALESCE(bookmark,0) DESC LIMIT 10")]
    genre = [dict(r) for r in ambil("""
        SELECT g.slug, g.nama, COUNT(ng.novel_id) jumlah FROM genre g
        JOIN novel_genre ng ON ng.genre_id = g.id
        GROUP BY g.id ORDER BY jumlah DESC LIMIT 18""")]
    tag = [dict(r) for r in ambil(
        "SELECT slug, nama, jumlah_novel FROM tag ORDER BY jumlah_novel DESC LIMIT 24")]
    return tpl.TemplateResponse(request, "beranda.html", {
        "situs": SITUS, "nama": NAMA, "desk": DESK,
        "kanon": str(request.url), "total_novel": n, "total_bab": b,
        "hero": hero, "trending": trending, "acak": acak, "baru": baru,
        "update": update, "tamat": tamat, "ongoing": ongoing,
        "genre": genre, "tag": tag,
    })


# ═════════════════════════════════════════════════════════════
#  HALAMAN: DETAIL NOVEL
# ═════════════════════════════════════════════════════════════
@app.get("/novel/{slug}", response_class=HTMLResponse)
def novel(request: Request, slug: str):
    r = ambil("SELECT * FROM novel WHERE slug=?", (slug,), satu=True)
    if not r:
        raise HTTPException(404)
    genre = [dict(x) for x in ambil("""
        SELECT g.slug, g.nama FROM genre g
        JOIN novel_genre ng ON ng.genre_id=g.id WHERE ng.novel_id=?""", (r["id"],))]
    tag = [dict(x) for x in ambil("""
        SELECT t.slug, t.nama FROM tag t
        JOIN novel_tag nt ON nt.tag_id=t.id WHERE nt.novel_id=?""", (r["id"],))]
    bab = [dict(x) for x in ambil(
        "SELECT urutan, nomor, judul, tanggal, ada_gambar FROM bab "
        "WHERE novel_id=? ORDER BY urutan", (r["id"],))]
    serupa = [kartu(x) for x in ambil("""
        SELECT DISTINCT n.* FROM novel n
        JOIN novel_genre ng ON ng.novel_id=n.id
        WHERE ng.genre_id IN (SELECT genre_id FROM novel_genre WHERE novel_id=?)
          AND n.id<>? AND n.cover_webp IS NOT NULL
        ORDER BY n.jumlah_bab DESC LIMIT 12""", (r["id"], r["id"]))]
    return tpl.TemplateResponse(request, "novel.html", {
        "situs": SITUS, "nama": NAMA,
        "judul": f"{r['judul']}: {NAMA}",
        "desk": (r["sinopsis"] or DESK)[:160],
        "kanon": f"{SITUS}/novel/{slug}",
        "gambar_og": f"{SITUS}/cover/{r['id']}.webp" if r["cover_webp"] else None,
        "n": dict(r), "cover": f"/cover/{r['id']}.webp" if r["cover_webp"] else None,
        "genre": genre, "tag": tag, "bab": bab, "serupa": serupa,
        "jlh_bab": len(bab),
    })


# ═════════════════════════════════════════════════════════════
#  HALAMAN: BACA BAB
# ═════════════════════════════════════════════════════════════
@app.get("/novel/{slug}/bab/{urutan}", response_class=HTMLResponse)
def bab(request: Request, slug: str, urutan: int):
    n = ambil("SELECT * FROM novel WHERE slug=?", (slug,), satu=True)
    if not n:
        raise HTTPException(404)
    b = ambil("SELECT * FROM bab WHERE novel_id=? AND urutan=?", (n["id"], urutan), satu=True)
    if not b:
        raise HTTPException(404)
    gmb = [dict(x) for x in ambil(
        "SELECT urutan, file_lokal, url_asli, caption FROM bab_gambar WHERE bab_id=? ORDER BY urutan",
        (b["id"],))]
    for g in gmb:
        # gambar lokal → lewat API kita (di-cache CF 7 hari)
        # belum diunduh  → pakai URL asli langsung (biar tetap tampil)
        g["sumber"] = (f"/api/gambar/{b['id']}/{g['urutan']}"
                       if g["file_lokal"] else g["url_asli"])
    sebelum = ambil("SELECT MAX(urutan) u FROM bab WHERE novel_id=? AND urutan<?",
                    (n["id"], urutan), satu=True)["u"]
    sesudah = ambil("SELECT MIN(urutan) u FROM bab WHERE novel_id=? AND urutan>?",
                    (n["id"], urutan), satu=True)["u"]
    # paragraf: pisah baris → HTML aman (autoescape Jinja)
    teks = (b["teks"] or "").split("\n")
    ada_teks = bool((b["teks"] or "").strip())
    return tpl.TemplateResponse(request, "bab.html", {
        "situs": SITUS, "nama": NAMA,
        "judul": f"{b['judul']}: {n['judul']} | {NAMA}",
        "desk": (b["teks"] or "")[:150],
        "kanon": f"{SITUS}/novel/{slug}/bab/{urutan}",
        "n": dict(n), "b": dict(b), "paragraf": teks, "gambar": gmb,
        "sebelum": sebelum, "sesudah": sesudah,
    })


# ═════════════════════════════════════════════════════════════
#  HALAMAN: JELAJAH / GENRE / TAG / CARI
# ═════════════════════════════════════════════════════════════
@app.get("/jelajah", response_class=HTMLResponse)
def jelajah(request: Request,
            q: str = "", status: str = "", tipe: str = "",
            genre: str = "", tag: str = "", order: str = "populer",
            page: int = 1, per: int = 24):
    where, par = ["n.cover_webp IS NOT NULL"], []
    if q:
        where.append("(n.judul LIKE ? OR COALESCE(n.penulis, n.author) LIKE ?)")
        par += [f"%{q}%", f"%{q}%"]
    if status:
        where.append("LOWER(COALESCE(n.status,''))=?"); par.append(status.lower())
    if tipe:
        where.append("LOWER(COALESCE(n.tipe,'')) LIKE ?"); par.append(f"%{tipe.lower()}%")
    if genre:
        where.append("n.id IN (SELECT ng.novel_id FROM novel_genre ng "
                     "JOIN genre g ON g.id=ng.genre_id WHERE g.slug=?)")
        par.append(genre)
    if tag:
        where.append("n.id IN (SELECT nt.novel_id FROM novel_tag nt "
                     "JOIN tag t ON t.id=nt.tag_id WHERE t.slug=?)")
        par.append(tag)
    urut = {"populer": "n.jumlah_bab DESC", "baru": "COALESCE(n.waktu_update,n.created_at) DESC",
            "judul": "n.judul COLLATE NOCASE ASC", "rating": "n.rating DESC"}\
        .get(order, "n.jumlah_bab DESC")
    W = " WHERE " + " AND ".join(where)
    total = ambil(f"SELECT COUNT(*) c FROM novel n{W}", tuple(par), satu=True)["c"]
    baris = ambil(f"SELECT n.* FROM novel n{W} ORDER BY {urut} LIMIT ? OFFSET ?",
                  tuple(par) + (per, (page - 1) * per))
    g_list = [dict(x) for x in ambil("""
        SELECT g.slug, g.nama, COUNT(ng.novel_id) j FROM genre g
        JOIN novel_genre ng ON ng.genre_id=g.id GROUP BY g.id
        ORDER BY j DESC""")]
    t_list = [dict(x) for x in ambil(
        "SELECT slug, nama, jumlah_novel FROM tag ORDER BY jumlah_novel DESC LIMIT 60")]
    return tpl.TemplateResponse(request, "jelajah.html", {
        "situs": SITUS, "nama": NAMA,
        "judul": f"Jelajah Novel: {NAMA}", "desk": DESK,
        "kanon": f"{SITUS}/jelajah",
        "hasil": [kartu(x) for x in baris], "total": total,
        "q": q, "status": status, "tipe": tipe, "genre": genre, "tag": tag,
        "order": order, "page": page, "per": per,
        "total_hal": (total + per - 1) // per,
        "genre_list": g_list, "tag_list": t_list,
    })


@app.get("/genre/{slug}", response_class=HTMLResponse)
def genre(request: Request, slug: str, page: int = 1, per: int = 24):
    g = ambil("SELECT * FROM genre WHERE slug=?", (slug,), satu=True)
    if not g:
        raise HTTPException(404)
    total = ambil("SELECT COUNT(*) c FROM novel_genre WHERE genre_id=?", (g["id"],),
                  satu=True)["c"]
    baris = ambil("""SELECT n.* FROM novel n JOIN novel_genre ng ON ng.novel_id=n.id
        WHERE ng.genre_id=? AND n.cover_webp IS NOT NULL
        ORDER BY n.jumlah_bab DESC LIMIT ? OFFSET ?""",
                  (g["id"], per, (page - 1) * per))
    return tpl.TemplateResponse(request, "daftar.html", {
        "situs": SITUS, "nama": NAMA,
        "judul": f"Genre {g['nama']}: {NAMA}", "desk": f"Novel genre {g['nama']}.",
        "kanon": f"{SITUS}/genre/{slug}",
        "kepala": f"Genre: {g['nama']}", "hasil": [kartu(x) for x in baris],
        "total": total, "page": page, "per": per,
        "total_hal": (total + per - 1) // per, "dasar_url": f"/genre/{slug}",
    })


@app.get("/tag/{slug}", response_class=HTMLResponse)
def tag(request: Request, slug: str, page: int = 1, per: int = 24):
    t = ambil("SELECT * FROM tag WHERE slug=?", (slug,), satu=True)
    if not t:
        raise HTTPException(404)
    total = ambil("SELECT COUNT(*) c FROM novel_tag WHERE tag_id=?", (t["id"],),
                  satu=True)["c"]
    baris = ambil("""SELECT n.* FROM novel n JOIN novel_tag nt ON nt.novel_id=n.id
        WHERE nt.tag_id=? AND n.cover_webp IS NOT NULL
        ORDER BY n.jumlah_bab DESC LIMIT ? OFFSET ?""",
                  (t["id"], per, (page - 1) * per))
    return tpl.TemplateResponse(request, "daftar.html", {
        "situs": SITUS, "nama": NAMA,
        "judul": f"Tag {t['nama']}: {NAMA}", "desk": f"Novel dengan tag {t['nama']}.",
        "kanon": f"{SITUS}/tag/{slug}",
        "kepala": f"Tag: {t['nama']}", "hasil": [kartu(x) for x in baris],
        "total": total, "page": page, "per": per,
        "total_hal": (total + per - 1) // per, "dasar_url": f"/tag/{slug}",
    })


@app.get("/cari", response_class=HTMLResponse)
def cari(request: Request, q: str = "", page: int = 1, per: int = 24):
    hasil, total, bab_hits = [], 0, []
    if q:
        total = ambil("SELECT COUNT(*) c FROM novel WHERE judul LIKE ? OR "
                      "COALESCE(penulis,author) LIKE ?",
                      (f"%{q}%", f"%{q}%"), satu=True)["c"]
        hasil = [kartu(x) for x in ambil(
            "SELECT * FROM novel WHERE judul LIKE ? OR COALESCE(penulis,author) LIKE ? "
            "ORDER BY jumlah_bab DESC LIMIT ? OFFSET ?",
            (f"%{q}%", f"%{q}%", per, (page - 1) * per))]
        try:
            bab_hits = [dict(x) for x in ambil("""
                SELECT b.judul, b.urutan, n.slug, n.judul AS novel_judul
                FROM bab_fts f JOIN bab b ON b.id=f.rowid
                JOIN novel n ON n.id=b.novel_id
                WHERE bab_fts MATCH ? LIMIT 10""", (q,))]
        except sqlite3.Error:
            bab_hits = []
    return tpl.TemplateResponse(request, "cari.html", {
        "situs": SITUS, "nama": NAMA,
        "judul": f"Cari {q}: {NAMA}", "desk": DESK,
        "kanon": f"{SITUS}/cari?q={q}",
        "q": q, "hasil": hasil, "total": total, "bab_hits": bab_hits,
        "page": page, "per": per, "total_hal": (total + per - 1) // per,
    })


# ═════════════════════════════════════════════════════════════
#  SEO: sitemap.xml + robots.txt
# ═════════════════════════════════════════════════════════════
_POTONG = 45000          # di bawah batas Google 50.000 URL per berkas


@app.get("/sitemap.xml")
def sitemap_index():
    """INDEX sitemap — karena Google batas 50.000 URL per berkas.

    Kita punya 495 novel + 111.680 bab → WAJIB dipecah.
    Berkas anak:
      /sitemap-halaman.xml   → beranda, jelajah, genre, tag
      /sitemap-novel-N.xml   → novel (potong 45.000)
      /sitemap-bab-N.xml     → bab   (potong 45.000)
    """
    jml_novel = ambil("SELECT COUNT(*) c FROM novel", satu=True)["c"]
    jml_bab = ambil("""SELECT COUNT(*) c FROM bab b
        WHERE b.teks IS NOT NULL""", satu=True)["c"]
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for nama in ["halaman"]:
        out.append(f"<sitemap><loc>{SITUS}/sitemap-{nama}.xml</loc></sitemap>")
    for i in range(1, (jml_novel // _POTONG) + 2):
        out.append(f"<sitemap><loc>{SITUS}/sitemap-novel-{i}.xml</loc></sitemap>")
    for i in range(1, (jml_bab // _POTONG) + 2):
        out.append(f"<sitemap><loc>{SITUS}/sitemap-bab-{i}.xml</loc></sitemap>")
    out.append("</sitemapindex>")
    return Response("\n".join(out), media_type="application/xml",
                    headers={"Cache-Control": "public, max-age=3600"})


_POTONG = 45000          # di bawah batas Google 50.000


@app.get("/sitemap-halaman.xml")
def sitemap_halaman():
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    out.append(f"<url><loc>{SITUS}/</loc><changefreq>hourly</changefreq>"
               "<priority>1.0</priority></url>")
    out.append(f"<url><loc>{SITUS}/jelajah</loc><changefreq>daily</changefreq>"
               "<priority>0.9</priority></url>")
    for r in ambil("SELECT slug FROM genre ORDER BY id"):
        out.append(f"<url><loc>{SITUS}/genre/{r['slug']}</loc>"
                   "<changefreq>weekly</changefreq><priority>0.7</priority></url>")
    for r in ambil("SELECT slug FROM tag ORDER BY jumlah_novel DESC LIMIT 3000"):
        out.append(f"<url><loc>{SITUS}/tag/{r['slug']}</loc>"
                   "<changefreq>weekly</changefreq><priority>0.5</priority></url>")
    out.append("</urlset>")
    return Response("\n".join(out), media_type="application/xml",
                    headers={"Cache-Control": "public, max-age=3600"})


@app.get("/sitemap-novel-{bagian}.xml")
def sitemap_novel(bagian: int):
    if bagian < 1:
        raise HTTPException(404)
    geser = (bagian - 1) * _POTONG
    baris = ambil("SELECT slug FROM novel ORDER BY id LIMIT ? OFFSET ?",
                  (_POTONG, geser))
    if not baris:
        raise HTTPException(404)
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for r in baris:
        out.append(f"<url><loc>{SITUS}/novel/{r['slug']}</loc>"
                   "<changefreq>daily</changefreq><priority>0.8</priority></url>")
    out.append("</urlset>")
    return Response("\n".join(out), media_type="application/xml",
                    headers={"Cache-Control": "public, max-age=3600"})


@app.get("/sitemap-bab-{bagian}.xml")
def sitemap_bab(bagian: int):
    if bagian < 1:
        raise HTTPException(404)
    geser = (bagian - 1) * _POTONG
    baris = ambil("""SELECT n.slug, b.urutan FROM bab b
        JOIN novel n ON n.id = b.novel_id
        WHERE b.teks IS NOT NULL AND b.teks <> ''
        ORDER BY b.id LIMIT ? OFFSET ?""", (_POTONG, geser))
    if not baris:
        raise HTTPException(404)
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for r in baris:
        out.append(f"<url><loc>{SITUS}/novel/{r['slug']}/bab/{r['urutan']}</loc>"
                   "<changefreq>weekly</changefreq><priority>0.6</priority></url>")
    out.append("</urlset>")
    return Response("\n".join(out), media_type="application/xml",
                    headers={"Cache-Control": "public, max-age=3600"})


@app.get("/robots.txt")
def robots():
    return PlainTextResponse(
        f"User-agent: *\nAllow: /\nDisallow: /api/\n"
        f"Sitemap: {SITUS}/sitemap.xml\n")


@app.get("/status")
def status():
    n = ambil("SELECT COUNT(*) c FROM novel", satu=True)["c"]
    b = ambil("SELECT COUNT(*) c FROM bab", satu=True)["c"]
    g = ambil("SELECT COUNT(*) c FROM bab_gambar", satu=True)["c"]
    return {"aplikasi": "Naver Web", "novel": n, "bab": b, "gambar": g}


@app.get("/apk", response_class=HTMLResponse)
def apk(request: Request):
    """Halaman unduh APK (file ditaruh di web/static/naver.apk kalau ada)."""
    apk = BASE / "static" / "naver.apk"
    n = ambil("SELECT COUNT(*) c FROM novel", satu=True)["c"]
    b = ambil("SELECT COUNT(*) c FROM bab", satu=True)["c"]
    return tpl.TemplateResponse(request, "apk.html", {
        "situs": SITUS, "nama": NAMA,
        "judul": f"Unduh APK: {NAMA}",
        "desk": "Unduh aplikasi Android Naver Novel untuk baca offline.",
        "kanon": f"{SITUS}/apk",
        "apk_url": "/static/naver.apk" if apk.exists() else None,
        "total_novel": n, "total_bab": b,
    })


# ═════════════════════════════════════════════════════════════
#  HALAMAN GALAT (antislop A-05 · R-27: state error harus ada)
#  Tanpa ini, galat keluar jadi JSON {"detail":"Not Found"} di situs HTML.
#  Pesan menyebut SEBAB + LANGKAH berikutnya, bukan sekadar "error".
# ═════════════════════════════════════════════════════════════
def _hal_galat(request: Request, kode: int, pesan: str, rinci: str):
    q = request.query_params.get("q", "")
    return tpl.TemplateResponse(request, "galat.html", {
        "situs": SITUS, "nama": NAMA, "kanon": str(request.url),
        "judul": f"{kode}: {pesan} | {NAMA}",
        "desk": rinci,
        "kode": kode, "pesan": pesan, "rinci": rinci, "q": q,
    }, status_code=kode)


@app.exception_handler(404)
async def galat_404(request: Request, exc):
    return _hal_galat(
        request, 404, "Halaman tidak ditemukan",
        "Alamat yang kamu buka tidak ada di arsip ini. "
        "Mungkin tautannya salah ketik, atau novelnya sudah berganti judul.")


@app.exception_handler(500)
async def galat_500(request: Request, exc):
    return _hal_galat(
        request, 500, "Ada gangguan di server",
        "Server sedang bermasalah saat memuat halaman ini. "
        "Coba muat ulang sebentar lagi; kalau tetap gagal, kembali ke beranda.")
