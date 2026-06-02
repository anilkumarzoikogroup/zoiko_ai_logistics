"""
Helper called by launch.bat — writes .env vars as a temporary bat file.
Usage: python _load_env.py  ->  writes .env_tmp.bat
"""
import os, sys

try:
    from dotenv import dotenv_values
    vals = dotenv_values(".env")
except Exception:
    # Fallback: simple line parser
    vals = {}
    with open(".env", encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, _, v = line.partition("=")
                vals[k.strip()] = v.strip()

with open(".env_tmp.bat", "w", encoding="ascii", errors="replace") as out:
    for k, v in vals.items():
        if v is not None:
            # Quote value to prevent & in URLs being treated as command separator
            out.write(f'set "{k}={v}"\r\n')

print("OK")
