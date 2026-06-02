"""
Database backup script — creates a timestamped SQL dump.

Usage:
  python scripts/backup_db.py

Saves to: backups/zoiko_YYYY-MM-DD_HHMMSS.sql
Keeps last 30 backups, deletes older ones automatically.

Schedule daily with cron:
  0 2 * * * cd /path/to/zoiko-logistics && python scripts/backup_db.py
"""
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT    = Path(__file__).parent.parent
BACKUP  = ROOT / "backups"
DB_URL  = os.environ.get("DB_URL", "postgresql://postgres:1234@localhost/zoiko")
KEEP    = int(os.environ.get("BACKUP_KEEP_DAYS", "30"))

def main():
    BACKUP.mkdir(exist_ok=True)
    ts       = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out_file = BACKUP / f"zoiko_{ts}.sql"

    # Parse DB_URL for pg_dump
    import urllib.parse
    p = urllib.parse.urlparse(DB_URL)
    env = {
        **os.environ,
        "PGPASSWORD": p.password or "",
    }
    cmd = [
        "pg_dump",
        "-h", p.hostname or "localhost",
        "-p", str(p.port or 5432),
        "-U", p.username or "postgres",
        "-d", p.path.lstrip("/"),
        "-f", str(out_file),
        "--no-password",
        "--verbose",
    ]

    print(f"Backing up to {out_file}...")
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERROR: {result.stderr}", file=sys.stderr)
        sys.exit(1)

    size = out_file.stat().st_size / 1024
    print(f"Backup complete: {out_file} ({size:.1f} KB)")

    # Delete backups older than KEEP days
    cutoff = datetime.now() - timedelta(days=KEEP)
    deleted = 0
    for f in BACKUP.glob("zoiko_*.sql"):
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            if mtime < cutoff:
                f.unlink()
                deleted += 1
        except Exception:
            pass
    if deleted:
        print(f"Deleted {deleted} old backup(s) (older than {KEEP} days)")

if __name__ == "__main__":
    main()
