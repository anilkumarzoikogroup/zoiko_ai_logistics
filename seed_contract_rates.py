"""Seed contract rates for all major carriers."""
import os, psycopg2, uuid, hashlib
from datetime import date

DB_URL = os.getenv("DB_URL", "postgresql://postgres:1234@localhost/zoiko")

RATES = [
    ("BlueDart",    "Mumbai",    "Delhi",      "AIR",      8000, "INR", "FUEL_CHARGE"),
    ("BlueDart",    "Mumbai",    "Delhi",      "AIR",       800, "INR", "ACCESSORIAL"),
    ("BlueDart",    "Bangalore", "Mumbai",     "AIR",      6500, "INR", "FUEL_CHARGE"),
    ("BlueDart",    "Chennai",   "Delhi",      "AIR",      9000, "INR", "FUEL_CHARGE"),
    ("Delhivery",   "Kochi",     "Delhi",      "SURFACE",  7500, "INR", "FUEL_CHARGE"),
    ("Delhivery",   "Kochi",     "Delhi",      "SURFACE",   500, "INR", "ACCESSORIAL"),
    ("Delhivery",   "Mumbai",    "Bangalore",  "SURFACE",  5500, "INR", "FUEL_CHARGE"),
    ("Delhivery",   "Delhi",     "Chennai",    "SURFACE",  8200, "INR", "FUEL_CHARGE"),
    ("FedEx India", "Bangalore", "Mumbai",     "AIR",      9200, "INR", "FUEL_CHARGE"),
    ("FedEx India", "Bangalore", "Mumbai",     "AIR",      1000, "INR", "ACCESSORIAL"),
    ("FedEx India", "Mumbai",    "Delhi",      "AIR",     10500, "INR", "FUEL_CHARGE"),
    ("Ekart",       "Chennai",   "Delhi",      "SURFACE",  7000, "INR", "FUEL_CHARGE"),
    ("Ekart",       "Chennai",   "Delhi",      "SURFACE",   600, "INR", "ACCESSORIAL"),
    ("Ekart",       "Bangalore", "Kolkata",    "SURFACE",  8500, "INR", "FUEL_CHARGE"),
    ("DTDC",        "Mumbai",    "Hyderabad",  "SURFACE",  4500, "INR", "FUEL_CHARGE"),
    ("DTDC",        "Delhi",     "Bangalore",  "SURFACE",  7800, "INR", "FUEL_CHARGE"),
    ("DTDC",        "Kolkata",   "Mumbai",     "SURFACE",  6200, "INR", "FUEL_CHARGE"),
    ("Delhivery",   "Dallas",    "Atlanta",    "TRUCKLOAD",1500, "USD", "FUEL_CHARGE"),
    ("Delhivery",   "Dallas",    "Atlanta",    "TRUCKLOAD", 100, "USD", "ACCESSORIAL"),
]

def lane_hash(origin, dest, mode):
    return hashlib.sha256(f"{origin}|{dest}|{mode}".encode()).hexdigest()

conn = psycopg2.connect(DB_URL)
cur = conn.cursor()
cur.execute("SELECT id, slug FROM tenants WHERE status=%s LIMIT 1", ("ACTIVE",))
tenant = cur.fetchone()
if not tenant:
    print("ERROR: No active tenant."); conn.close(); exit(1)

tenant_id, tenant_slug = tenant
print(f"Tenant: {tenant_slug}")
added = 0
for carrier, origin, dest, mode, rate, currency, rate_type in RATES:
    lh = lane_hash(origin, dest, mode)
    cur.execute("SELECT id FROM contract_rates WHERE tenant_id=%s AND carrier_id=%s AND lane_hash=%s AND rate_type=%s",
                (tenant_id, carrier, lh, rate_type))
    if cur.fetchone():
        print(f"  SKIP: {carrier} {rate_type}")
        continue
    cur.execute("INSERT INTO contract_rates (id,tenant_id,carrier_id,rate_type,rate_value,currency,effective_on,lane_hash,base_rate,effective_from) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (str(uuid.uuid4()), tenant_id, carrier, rate_type, rate, currency, date(2025,1,1), lh, rate, date(2025,1,1)))
    print(f"  ADDED: {carrier} {origin}-{dest} {rate_type} = {currency} {rate}")
    added += 1
conn.commit(); conn.close()
print(f"Done. {added} rates added.")
