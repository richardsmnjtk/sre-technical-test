# Junior DevOps / Site Reliability Engineer Technical Test

## 1. Project Overview

### Objective

This project implements a containerized PHP application stack with automated
deployment, CI/CD, security hardening, and a database performance analysis. It
covers every area of the assignment:

- Docker (image build + push to a private registry)
- Docker Compose (Nginx, PHP-FPM, PostgreSQL)
- PostgreSQL configuration and access control
- Security hardening (Nginx + PHP)
- Ansible deployment over SSH
- GitLab CI/CD (build + deploy jobs)
- GitLab CI quiz fix
- Database performance analysis
- Log rotation scripting (Bash + Python)

### Technology Stack

| Component     | Technology        |
| ------------- | ----------------- |
| Web Server    | OpenResty / Nginx |
| Application   | PHP 8.2 FPM       |
| Database      | PostgreSQL 16     |
| Container     | Docker            |
| Orchestration | Docker Compose    |
| Automation    | Ansible           |
| CI/CD         | GitLab CI         |
| Registry      | Docker Hub        |
| OS            | Ubuntu 24.04      |

---

## 2. Architecture

```text
Developer
    |
    v
GitLab Repository
    |
    v
GitLab CI/CD
    |
    +--> Build Image
    |       |
    |       v
    |   Docker Hub
    |
    v
Ansible Deploy
    |
    v
Ubuntu VPS
    |
    +--> Nginx (8080)
    +--> PHP-FPM (9000)
    +--> PostgreSQL (5432)
```

The pipeline builds images on a Dockerfile change, pushes them to Docker Hub, and
deploys to the VPS via Ansible. Deployment also runs on a Docker Compose change
(without rebuilding).

---

## 3. Docker Implementation

### Base Images

The application image is built on the official PHP 8.2 FPM Alpine image, and the
web server image on an Alpine-based OpenResty/Nginx image, as required:

```dockerfile
# php/Dockerfile
FROM php:8.2-fpm-alpine

# nginx/Dockerfile
FROM openresty/openresty:alpine
```

### Image Repository (Docker Hub, private)

```text
richardsmnjtk/sre-test-app
richardsmnjtk/sre-test-nginx
```

Both images run as a non-root user (see Security Hardening).

---

## 4. Docker Compose

### Services

| Service      | Purpose                        |
| ------------ | ------------------------------ |
| nginx        | Web server / reverse proxy     |
| php-app      | PHP 8.2 FPM application         |
| postgres-db  | PostgreSQL 16 database         |

A simple PHP file echoes "hello world" to verify the stack end to end.

### Port Mapping

| Service    | Container | Host |
| ---------- | --------- | ---- |
| Nginx      | 80        | 8080 |
| PostgreSQL | 5432      | 5432 |

The Nginx container port 80 is mapped to host port 8080 as required.

---

## 5. PostgreSQL Configuration

### Database

A database named `sre` is created and owned by the full-access user.

### Users

| User       | Access                                            |
| ---------- | ------------------------------------------------- |
| fullaccess | Full access (owns and manages the `sre` database) |
| readonly   | Read-only (`SELECT` only)                         |

The read-only user is not just granted `SELECT` on existing tables. **Default
privileges** are also configured so that any table created in the future is
automatically read-only for this user. Without this step a "read-only" user would
silently gain access to new tables, so handling default privileges is what makes
the restriction actually hold:

```sql
GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO readonly;
```

### Max Connections

`max_connections` was raised to 200 in the PostgreSQL configuration and verified
from a query:

```sql
SHOW max_connections;   -- returns 200
```

---

## 6. Security Hardening

### Nginx

| Goal                          | Implementation         |
| ----------------------------- | ---------------------- |
| No directory listing          | `autoindex off;`       |
| Block access to `.git`        | `location ~ /\.git { deny all; }` |
| Hide server header            | `server_tokens off;` (plus header rewrite so the response `Server` header is not `nginx`) |
| Not running as root           | Worker processes run as a non-root user |

Verified results:

- A directory without an index file returns `403` instead of a file listing.
- `/.git/config` returns `403`.
- The response no longer exposes a `Server: nginx` header.

### PHP

| Goal                          | Implementation         |
| ----------------------------- | ---------------------- |
| Cannot run `exec()`           | `disable_functions=exec,shell_exec,system,passthru` |
| PHP-FPM not running as root   | FPM pool runs as a non-root user |

Verified results:

- Before: `exec("id")` worked.
- After: `Call to undefined function exec()` — the function is disabled.

---

## 7. Ansible Deployment

### Inventory

The target VPS is defined in `ansible/inventory.ini`, connecting over SSH using an
SSH key (no password):

```ini
[production]
139.59.246.122 ansible_user=vibe-bt
```

### Playbook

`ansible/deploy.yml` performs a force update of the Docker Compose stack:

```text
Pull the latest image(s)
docker compose up -d (force recreate)
Verify running containers
```

---

## 8. CI/CD Pipeline

### Jobs

The pipeline has two jobs across two stages: `build` and `deploy`.

### Scenario 1 — Dockerfile changed

```text
Commit (Dockerfile)
        |
        v
   Build image  -->  Push to Docker Hub
        |
        v
     Deploy
```

### Scenario 2 — docker-compose.yml changed

```text
Commit (docker-compose.yml)
        |
        v
     Deploy   (build is skipped)
```

This is implemented with GitLab `rules: changes:`. The `build` job only matches a
Dockerfile change; the `deploy` job matches either a Dockerfile or a
docker-compose change. Stage ordering guarantees build completes before deploy
when both run.

### Image Versioning

Each image is tagged twice and both tags are pushed:

```text
:latest
:<commit SHA>   (CI_COMMIT_SHORT_SHA)
```

Justification: the commit SHA tag provides traceability (which image came from
which commit) and rollback capability, while `:latest` is convenient for the
deploy path.

### Design note: compose image tags

The Docker Compose file references the images so the deploy path can pull the
latest build. This is a deliberate trade-off: using `:latest` for the deployed
stack keeps deployment simple, at the cost of explicit version pinning in compose.
In a production setup the CI deploy job would inject the specific commit-SHA tag to
keep full traceability end to end.

---

## 9. GitLab CI Quiz

### Problem

```yaml
stages:
  - unittest
  -security-scan
```

### Root Cause

Line 3 (`-security-scan`) is missing the space after the list marker `-`. In YAML a
list item requires a space after the dash, so `-security-scan` is not parsed as a
list item and the `security-scan` stage is never registered. The job that
references `stage: security-scan` then fails because the stage does not exist.

A secondary issue: the `unittest` stage is declared but no job uses it (a dead
stage).

### Solution

```yaml
stages:
  - unittest
  - security-scan
```

---

## 10. Database Performance Analysis

### Scenario

```sql
SELECT count(affiliates) FROM client WHERE client_id = 'client_500';
```

Symptoms: slow query, database CPU spike, while application/dashboard resources
stay normal.

### Investigation

**Step 1 — Review schema.** The `client` table only has a Primary Key index on
`id`. There is no index on `client_id`, the column the query filters on.

**Step 2 — `EXPLAIN ANALYZE` (before).**

```text
Seq Scan on client
Filter: ((client_id)::text = 'client_500'::text)
Rows Removed by Filter: 99903
Execution Time: 9.467 ms
```

Because `client_id` is not indexed, PostgreSQL reads the entire table (Sequential
Scan) and discards 99,903 of 100,000 rows to find the matches. This full-table
read is the source of the CPU spike. The application is normal because the
bottleneck is entirely on the database side.

### Solution

```sql
CREATE INDEX idx_client_client_id ON client (client_id);
ANALYZE client;
```

### Validation (after)

```text
Bitmap Index Scan on idx_client_client_id
Execution Time: 0.478 ms
```

### Benchmark

| Metric         | Before   | After             |
| -------------- | -------- | ----------------- |
| Scan Type      | Seq Scan | Bitmap Index Scan |
| Execution Time | 9.467 ms | 0.478 ms          |
| Improvement    | -        | ~20x              |

### Deeper observation

Beyond the missing index, the data model is questionable: `affiliates` is a
`varchar(250)` column, so `count(affiliates)` counts matching rows with a non-null
value, not the actual number of affiliates. A correct model would store affiliates
in a separate table with a foreign key to `client` and an index on that key. The
index is the immediate fix; the model change is the proper long-term fix.

Full analysis with reproduction is in `DB_ANALYSIS.md`.

---

## 11. Bash Script

### `set -e`

`set -e` makes the script stop immediately if any command fails, instead of
continuing on a broken state. It makes the script "fail fast".

### Logrotate Script

Features:

- Scans every `.log` file in a directory.
- Archives any file larger than 5 MB with gzip, then truncates the original to 0
  bytes.
- Logs every action (ARCHIVED / SKIPPED) with a timestamp.
- Skips its own action log so it never rotates the file it is writing to.

Validation:

```text
ARCHIVED ./logs/big.log (6291456 byte)
SKIPPED ./logs/small.log (6 byte)
```

After the run, `big.log` is 0 bytes and a timestamped `.gz` archive exists. Full
script and verified terminal output are in `SCRIPTING.md`.

---

## 12. Python Implementation

A Python rewrite of the Bash logrotate script with identical behaviour, using the
standard library only.

Validation:

```text
ARCHIVED ./logs/big.log (6291456 byte) -> ./logs/archive/big.log.<timestamp>.gz
SKIPPED ./logs/small.log (6 byte)
```

The output matches the Bash version exactly. Full script and verified terminal
output are in `SCRIPTING.md`.

---

## 13. Repository Structure

```text
.
├── ansible/
│   ├── deploy.yml
│   └── inventory.ini
├── app/
│   ├── index.php
│   └── testdir/
├── nginx/
│   ├── Dockerfile
│   └── default.conf
├── php/
│   ├── Dockerfile
│   └── security.ini
├── postgres/
│   ├── init.sql
│   └── postgresql.conf
├── scripts/
│   ├── logrotate.sh
│   └── logrotate.py
├── docker-compose.yml
├── .gitlab-ci.yml
├── .gitignore
├── .env.example
├── QUIZ.md
├── DB_ANALYSIS.md
├── SCRIPTING.md
└── README.md
```

---

## 14. Conclusion

Achieved in this project:

- Containerized application stack (Nginx + PHP 8.2 FPM + PostgreSQL 16).
- PostgreSQL configuration and access control, including correct read-only
  default privileges.
- Security hardening for Nginx and PHP, with verified before/after results.
- Automated deployment using Ansible over SSH.
- GitLab CI/CD with conditional build/deploy based on which files changed.
- Database performance optimization (Sequential Scan to Index Scan, ~20x faster),
  with a note on the underlying data-model issue.
- Log rotation automation in both Bash and Python, reproduced and verified.
