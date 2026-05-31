#!/bin/bash
# logrotate-simple.sh
# Cek semua file .log di sebuah folder.
# Kalau ukurannya lebih dari 5 MB: arsipkan (gzip) lalu kosongkan filenya.
# Setiap aksi dicatat ke file log.

set -e   # berhenti kalau ada command yang gagal

# --- Pengaturan ---
LOG_DIR="./logs"                              # folder yang dicek
MAX_SIZE=$((5 * 1024 * 1024))                 # 5 MB dalam byte
ACTION_LOG="$LOG_DIR/logrotate-actions.log"   # catatan aksi script

# Buat folder arsip kalau belum ada
mkdir -p "$LOG_DIR/archive"

# --- Proses tiap file .log ---
for file in "$LOG_DIR"/*.log; do

       # Lewati file action log milik script ini sendiri
    if [ "$file" = "$ACTION_LOG" ]; then
        continue
    fi
	# Ambil ukuran file dalam byte
    size=$(stat -c %s "$file")

    if [ "$size" -gt "$MAX_SIZE" ]; then
        # Nama arsip pakai tanggal+jam biar unik
        waktu=$(date +%Y%m%d-%H%M%S)
        arsip="$LOG_DIR/archive/$(basename "$file").$waktu.gz"

        # 1. Arsipkan: kompres isi file ke folder archive
        gzip -c "$file" > "$arsip"

        # 2. Kosongkan file aslinya (truncate jadi 0 byte)
        > "$file"

        # 3. Catat aksinya
        echo "$(date '+%Y-%m-%d %H:%M:%S') | ARCHIVED $file -> $arsip" >> "$ACTION_LOG"
        echo "ARCHIVED $file ($size byte)"
    else
        echo "$(date '+%Y-%m-%d %H:%M:%S') | SKIPPED $file ($size byte)" >> "$ACTION_LOG"
        echo "SKIPPED $file ($size byte)"
    fi

done
