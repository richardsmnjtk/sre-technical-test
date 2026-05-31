#!/usr/bin/env python3
# logrotate-simple.py
# Versi Python dari logrotate.sh
# Cek semua file .log di sebuah folder.
# Kalau ukurannya lebih dari 5 MB: arsipkan (gzip) lalu kosongkan filenya.
# Setiap aksi dicatat ke file log.

import os
import gzip
from datetime import datetime

# --- Pengaturan ---
LOG_DIR = "./logs"                                  # folder yang dicek
MAX_SIZE = 5 * 1024 * 1024                          # 5 MB dalam byte
ACTION_LOG = os.path.join(LOG_DIR, "logrotate-actions.log")  # catatan aksi

# Buat folder arsip kalau belum ada
os.makedirs(os.path.join(LOG_DIR, "archive"), exist_ok=True)


# Fungsi kecil buat nyatat aksi ke file log + tampil di layar
def catat(pesan):
    waktu = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    baris = waktu + " | " + pesan
    print(pesan)
    with open(ACTION_LOG, "a") as f:
        f.write(baris + "\n")


# --- Proses tiap file .log ---
for nama in os.listdir(LOG_DIR):

    # Cuma proses file yang berakhiran .log
    if not nama.endswith(".log"):
        continue

    file = os.path.join(LOG_DIR, nama)

    # Lewati file action log milik script ini sendiri
    if file == ACTION_LOG:
        continue

    # Ambil ukuran file dalam byte
    size = os.path.getsize(file)

    if size > MAX_SIZE:
        # Nama arsip pakai tanggal+jam biar unik
        waktu = datetime.now().strftime("%Y%m%d-%H%M%S")
        arsip = os.path.join(LOG_DIR, "archive", nama + "." + waktu + ".gz")

        # 1. Arsipkan: baca isi file, lalu tulis versi terkompres ke folder archive
        with open(file, "rb") as f:
            isi = f.read()
        with gzip.open(arsip, "wb") as f:
            f.write(isi)

        # 2. Kosongkan file aslinya (truncate jadi 0 byte)
        with open(file, "w") as f:
            f.truncate(0)

        catat("ARCHIVED " + file + " (" + str(size) + " byte) -> " + arsip)
    else:
        catat("SKIPPED " + file + " (" + str(size) + " byte)")
