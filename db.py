import sqlite3
import os
from werkzeug.security import generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "instance", "parking.db")
SCHEMA_PATH = os.path.join(BASE_DIR, "schema.sql")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(force=False):
    os.makedirs(os.path.join(BASE_DIR, "instance"), exist_ok=True)
    fresh = force or not os.path.exists(DB_PATH)
    if not fresh:
        return

    conn = get_db()
    with open(SCHEMA_PATH, "r") as f:
        conn.executescript(f.read())

    # --- Seed rates ---
    conn.execute(
        "INSERT INTO rates (vehicle_type, base_rate, hourly_rate) VALUES (?,?,?)",
        ("car", 30, 20),
    )
    conn.execute(
        "INSERT INTO rates (vehicle_type, base_rate, hourly_rate) VALUES (?,?,?)",
        ("bike", 15, 10),
    )

    # --- Seed floors ---
    floors = [("Ground Floor", 0), ("First Floor", 1), ("Second Floor", 2)]
    floor_ids = []
    for name, order in floors:
        cur = conn.execute(
            "INSERT INTO floors (name, level_order) VALUES (?,?)", (name, order)
        )
        floor_ids.append(cur.lastrowid)

    # --- Seed slots: each floor gets 12 car slots + 6 bike slots ---
    for fid in floor_ids:
        for i in range(1, 13):
            conn.execute(
                "INSERT INTO slots (floor_id, slot_number, vehicle_type, status) VALUES (?,?,?,?)",
                (fid, f"C{i:02d}", "car", "available"),
            )
        for i in range(1, 7):
            conn.execute(
                "INSERT INTO slots (floor_id, slot_number, vehicle_type, status) VALUES (?,?,?,?)",
                (fid, f"B{i:02d}", "bike", "available"),
            )

    # --- Seed admin user ---
    conn.execute(
        "INSERT INTO users (name, email, phone, password_hash, role) VALUES (?,?,?,?,?)",
        ("Admin", "admin@parking.com", "9999999999",
         generate_password_hash("admin123"), "admin"),
    )

    # --- Seed a demo user ---
    conn.execute(
        "INSERT INTO users (name, email, phone, password_hash, role) VALUES (?,?,?,?,?)",
        ("Demo User", "user@parking.com", "9876543210",
         generate_password_hash("user123"), "user"),
    )

    conn.commit()
    conn.close()
