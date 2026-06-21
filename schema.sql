-- Smart Parking System Database Schema

DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS floors;
DROP TABLE IF EXISTS slots;
DROP TABLE IF EXISTS bookings;
DROP TABLE IF EXISTS rates;

CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    phone TEXT,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',   -- 'user' or 'admin'
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE floors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    level_order INTEGER NOT NULL
);

CREATE TABLE slots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    floor_id INTEGER NOT NULL,
    slot_number TEXT NOT NULL,
    vehicle_type TEXT NOT NULL DEFAULT 'car',  -- 'car' or 'bike'
    status TEXT NOT NULL DEFAULT 'available',  -- 'available','booked','occupied','disabled'
    FOREIGN KEY (floor_id) REFERENCES floors(id)
);

CREATE TABLE bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_code TEXT UNIQUE NOT NULL,
    user_id INTEGER NOT NULL,
    slot_id INTEGER NOT NULL,
    vehicle_number TEXT NOT NULL,
    vehicle_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'booked',  -- 'booked','active','completed','cancelled'
    booked_at TEXT NOT NULL DEFAULT (datetime('now')),
    entry_time TEXT,
    exit_time TEXT,
    expected_hours REAL DEFAULT 1,
    amount REAL DEFAULT 0,
    payment_status TEXT NOT NULL DEFAULT 'pending',  -- 'pending','paid'
    payment_method TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (slot_id) REFERENCES slots(id)
);

CREATE TABLE rates (
    vehicle_type TEXT PRIMARY KEY,
    base_rate REAL NOT NULL,       -- amount for first hour
    hourly_rate REAL NOT NULL      -- amount per additional hour
);
