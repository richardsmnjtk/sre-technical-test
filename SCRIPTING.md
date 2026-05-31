# Scripting A — Bash

## 1. What does `set -e` do?

`set -e` tells the script to stop right away if any command fails, instead of
just continuing to the next line.

Normally Bash doesn't care if a command fails — it keeps going no matter what.
That can cause problems. For example, if a `cd` into a folder fails but the script
keeps running, the next commands might run in the wrong place. With `set -e`, the
script stops at the first error so the rest doesn't run on a broken state.

In short: it makes the script "fail fast" instead of silently doing the wrong
thing.

## 2. Logrotate bash script

Requirements:

- Check every `.log` file in a specific directory.
- If a file is larger than 5 MB: archive it (gzip), then truncate the original.
- Log every action the script takes.

### Script

```bash
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
```

### Design justification

- **`stat -c %s "$file"`** returns the file size in bytes, which is then compared
  against the 5 MB threshold (`5 * 1024 * 1024`). Using bytes avoids the rounding
  problems of human-readable sizes.

- **Archive with `gzip -c "$file" > "$arsip"`** compresses a copy into the
  `archive/` folder. The archive filename includes a timestamp
  (`$(date +%Y%m%d-%H%M%S)`) so repeated runs never overwrite previous archives.

- **Truncate with `> "$file"`** empties the original file in place instead of
  deleting it. This keeps the same inode and permissions, so any process still
  writing to that log (e.g. nginx) continues writing to the same file with no
  restart needed. Deleting and recreating the file (`rm` + `touch`) would break
  this: a process holding the old file open would keep writing to the now-unlinked
  file, and new logs would not appear until the process restarts.

- **Skipping the action log** (`if [ "$file" = "$ACTION_LOG" ]; then continue`)
  prevents the script from rotating the very file it is writing to. Without this
  guard, once the action log itself exceeds 5 MB the script would try to archive
  and truncate it mid-write.

- **Logging every action** to `$ACTION_LOG` (ARCHIVED / SKIPPED with a timestamp)
  gives an audit trail of what the script did and when.

### Reproduction (verified)

The script was tested on the target Ubuntu server. A clean `logs/` directory was
prepared with one 6 MB file (expected to rotate) and one tiny file (expected to be
skipped), then the script was run and the resulting state inspected:

```console
vibe-bt@sre-assignment:~/logrotate-test$ rm -rf logs && mkdir logs
vibe-bt@sre-assignment:~/logrotate-test$ head -c 6M /dev/urandom > logs/big.log
vibe-bt@sre-assignment:~/logrotate-test$ echo "kecil" > logs/small.log
vibe-bt@sre-assignment:~/logrotate-test$ ls -lh logs/
total 6.1M
-rw-rw-r-- 1 vibe-bt vibe-bt 6.0M May 31 14:59 big.log
-rw-rw-r-- 1 vibe-bt vibe-bt    6 May 31 14:59 small.log
vibe-bt@sre-assignment:~/logrotate-test$ bash logrotate.sh
ARCHIVED ./logs/big.log (6291456 byte)
SKIPPED ./logs/small.log (6 byte)
vibe-bt@sre-assignment:~/logrotate-test$ cat logs/logrotate-actions.log
2026-05-31 14:59:38 | ARCHIVED ./logs/big.log -> ./logs/archive/big.log.20260531-145938.gz
2026-05-31 14:59:38 | SKIPPED ./logs/small.log (6 byte)
vibe-bt@sre-assignment:~/logrotate-test$ ls -lh logs/ logs/archive/
logs/:
total 12K
drwxrwxr-x 2 vibe-bt vibe-bt 4.0K May 31 14:59 archive
-rw-rw-r-- 1 vibe-bt vibe-bt    0 May 31 14:59 big.log
-rw-rw-r-- 1 vibe-bt vibe-bt  147 May 31 14:59 logrotate-actions.log
-rw-rw-r-- 1 vibe-bt vibe-bt    6 May 31 14:59 small.log

logs/archive/:
total 6.1M
-rw-rw-r-- 1 vibe-bt vibe-bt 6.1M May 31 14:59 big.log.20260531-145938.gz
```

The run confirms all requirements: `.log` files are scanned, the 6 MB file is
gzip-archived into `archive/` and then truncated to 0 bytes, the small file is left
untouched, and every action is recorded in the action log. Note that `big.log` is
now 0 bytes while a timestamped `.gz` archive exists, and the script's own action
log is correctly excluded from rotation.

### Note on archive size with random data

When testing with `/dev/urandom`, the resulting `.gz` archive is marginally
**larger** than the source (e.g. 6.0M -> 6.1M). This is expected, not a bug: random
data is incompressible, so gzip cannot shrink it and adds a small header overhead.
With real text logs (lots of repeated patterns) gzip typically compresses by
80–90%.

## Notes

A more defensive "production" variant of this script also exists, adding: a
configurable target directory via argument, a portable size check
(GNU/BSD `stat` fallback), `shopt -s nullglob` to handle an empty directory, and
helper functions. The simple version above keeps the core logic readable and is
sufficient for this task.

---

# Scripting B — Program (Python)

The same logrotate logic, rewritten in Python. The behaviour is exactly the same
as the bash version: scan `.log` files, archive anything over 5 MB with gzip, then
empty the original, and log every action.

### Script

```python
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
```

### How it maps to the bash version

Each piece does the same thing as in the bash script, just using Python:

- `os.path.getsize(file)` gets the file size in bytes — same as `stat -c %s`.
- Looping over `os.listdir()` and checking `.endswith(".log")` is the same as
  `for file in *.log` — only `.log` files are processed.
- `gzip.open` writes the compressed copy into the `archive/` folder. The file is
  read first (`f.read()`) and then written into the gzip file (`f.write(isi)`) —
  the same end result as `gzip -c file > arsip` in bash.
- `f.truncate(0)` empties the file to 0 bytes without deleting it. This is the same
  idea as `> "$file"` in bash: the file is truncated but not removed, so anything
  still writing to it keeps working.
- The action log is skipped so the script doesn't rotate its own log file, and
  `catat()` writes each action with a timestamp.

### Reproduction (verified)

The Python version was tested the same way as the bash script, on the same server,
to confirm identical behaviour:

```console
vibe-bt@sre-assignment:~/logrotate-test$ rm -rf logs && mkdir logs
vibe-bt@sre-assignment:~/logrotate-test$ head -c 6M /dev/urandom > logs/big.log
vibe-bt@sre-assignment:~/logrotate-test$ echo "kecil" > logs/small.log
vibe-bt@sre-assignment:~/logrotate-test$ ls -lh logs
total 6.1M
-rw-rw-r-- 1 vibe-bt vibe-bt 6.0M May 31 15:22 big.log
-rw-rw-r-- 1 vibe-bt vibe-bt    6 May 31 15:22 small.log
vibe-bt@sre-assignment:~/logrotate-test$ python3 logrotate.py
ARCHIVED ./logs/big.log (6291456 byte) -> ./logs/archive/big.log.20260531-152251.gz
SKIPPED ./logs/small.log (6 byte)
vibe-bt@sre-assignment:~/logrotate-test$ cat logs/logrotate-actions.log
2026-05-31 15:22:51 | ARCHIVED ./logs/big.log (6291456 byte) -> ./logs/archive/big.log.20260531-152251.gz
2026-05-31 15:22:51 | SKIPPED ./logs/small.log (6 byte)
vibe-bt@sre-assignment:~/logrotate-test$ ls -lh logs logs/archive/
logs:
total 12K
drwxrwxr-x 2 vibe-bt vibe-bt 4.0K May 31 15:22 archive
-rw-rw-r-- 1 vibe-bt vibe-bt    0 May 31 15:22 big.log
-rw-rw-r-- 1 vibe-bt vibe-bt  162 May 31 15:22 logrotate-actions.log
-rw-rw-r-- 1 vibe-bt vibe-bt    6 May 31 15:22 small.log

logs/archive/:
total 6.1M
-rw-rw-r-- 1 vibe-bt vibe-bt 6.1M May 31 15:22 big.log.20260531-152251.gz
```

The output matches the bash version exactly: the 6 MB file is archived and
truncated to 0 bytes, the small file is skipped, and each action is logged. This
confirms the rewrite preserves the same behaviour as the original script.
