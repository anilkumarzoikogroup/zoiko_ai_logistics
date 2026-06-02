"""Start Phase 2 with all .env variables properly loaded."""
import os, sys, subprocess
from pathlib import Path

ROOT = Path(__file__).parent

# Load .env
env_file = ROOT / ".env"
for line in env_file.read_text().splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, _, val = line.partition("=")
    os.environ[key.strip()] = val.strip()   # always override, even if already set

os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["ZOIKO_DEV_MODE"]   = os.environ.get("ZOIKO_DEV_MODE", "true")

groq = os.environ.get("GROQ_API_KEY", "")
print(f"GROQ_API_KEY: {'SET (' + groq[:8] + '...)' if groq else 'NOT SET — will use template'}")
print(f"DB_URL: {os.environ.get('DB_URL','')}")
print(f"TOKEN_TTL_MINUTES: {os.environ.get('TOKEN_TTL_MINUTES','15')}")
print()

os.chdir(ROOT / "phase-2")
subprocess.run([
    sys.executable, "-m", "uvicorn",
    "services.api_gateway.app:app",
    "--host", "0.0.0.0", "--port", "8000"
])
