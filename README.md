# SmartPark — Advanced Smart Parking Management System

A full-featured, production-style smart parking system built with **Flask, SQLite, and vanilla JS**. Real-time slot tracking, QR-coded tickets, automatic fare calculation, and a complete admin console with analytics.

## Features

### For Users
- Account registration & secure login (hashed passwords)
- **Live interactive slot map** — color-coded by floor and vehicle type (car/bike), auto-refreshes every 6 seconds
- One-click booking with instant **QR-coded ticket** and unique booking code
- Auto fare estimate at booking time, **final fare auto-calculated from actual parked duration** at checkout
- Booking history, cancellation, and simulated online payment (UPI/Card/Wallet/Cash)
- Personal dashboard with active & past bookings

### For Admins
- **Overview dashboard**: live KPIs (total slots, occupancy %, active vehicles, today's & lifetime revenue)
- **Charts** (Chart.js): 7-day revenue trend, floor-wise occupancy, 30-day revenue, vehicle type split, peak entry hours
- **Booking management**: search/filter by status, vehicle number, or user; one-click **Check-In** / **Check-Out** (gate operator workflow)
- **Slot inventory management**: add new slots, enable/disable slots for maintenance
- **User directory** with booking counts

### System Design
- Multi-floor parking (Ground / 1st / 2nd by default), separate inventories for cars and bikes
- Slot states: `available → booked → occupied(active) → available` (auto-released on checkout/cancel)
- Fare engine: base rate for first hour + hourly rate for every additional (rounded-up) hour, configurable per vehicle type
- Booking codes are unique, scannable QR identifiers generated server-side (`qrcode` + `Pillow`)
- Session-based auth with role separation (`user` / `admin`)

## Tech Stack
- **Backend**: Python, Flask
- **Database**: SQLite (file-based, zero config)
- **Frontend**: HTML, CSS (custom design system, no framework), vanilla JavaScript
- **Charts**: Chart.js (via CDN)
- **QR Codes**: `qrcode` + `Pillow`

## Project Structure
```
smart_parking/
├── app.py                 # All routes & business logic
├── db.py                  # DB connection + seed data
├── schema.sql             # Database schema
├── requirements.txt
├── instance/
│   └── parking.db         # SQLite database (auto-created)
├── static/
│   ├── css/style.css      # Design system
│   └── js/
│       ├── script.js      # Nav + flash messages
│       └── booking.js     # Live slot map logic
└── templates/
    ├── base.html
    ├── index.html, login.html, register.html
    ├── user_dashboard.html, book_slot.html, ticket.html, pay.html
    └── admin_dashboard.html, admin_bookings.html,
        admin_slots.html, admin_users.html, admin_analytics.html
```

## Setup & Run

```bash
cd smart_parking
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python3 app.py
```

Open **http://localhost:5000** in your browser.

The database is created automatically on first run with demo data.

## Demo Logins

| Role  | Email              | Password   |
|-------|---------------------|------------|
| Admin | admin@parking.com   | admin123   |
| User  | user@parking.com    | user123    |

## Default Pricing
| Vehicle | First Hour | Each Additional Hour |
|---------|-----------|------------------------|
| Car     | ₹30       | ₹20                    |
| Bike    | ₹15       | ₹10                    |

Edit the `rates` table (via `db.py` seed or directly in SQLite) to change pricing.

## Typical Flow
1. **User** registers/logs in → goes to **Book a Slot** → picks vehicle type, floor, and an available slot → confirms → gets a **QR ticket**.
2. **Admin/gate operator** checks the vehicle in (`Check In`) when it physically arrives — this starts the timer.
3. When the vehicle leaves, admin clicks **Check Out** — the system calculates the final amount from actual duration.
4. **User** pays via the simulated payment page; receipt status updates instantly.

## Possible Extensions
- Real hardware integration (IMU/ultrasonic sensors, ANPR cameras) feeding the `/api/slots` endpoint
- Razorpay/Stripe integration to replace simulated payments
- Email/SMS notifications on booking and checkout
- Reserved/monthly-pass parking plans
