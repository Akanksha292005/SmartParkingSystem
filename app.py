import os
import io
import base64
import secrets
import string
from datetime import datetime, timedelta

import qrcode
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify, send_file
)
from werkzeug.security import generate_password_hash, check_password_hash

from db import get_db, init_db

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "smart-parking-dev-secret-key-2026")

init_db()

DATE_FMT = "%Y-%m-%d %H:%M:%S"


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def current_user():
    if "user_id" not in session:
        return None
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    db.close()
    return user


def login_required(view):
    from functools import wraps

    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    from functools import wraps

    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session or session.get("role") != "admin":
            flash("Admin access required.", "danger")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def generate_booking_code():
    alphabet = string.ascii_uppercase + string.digits
    return "PK-" + "".join(secrets.choice(alphabet) for _ in range(7))


def calc_fare(vehicle_type, hours):
    db = get_db()
    rate = db.execute("SELECT * FROM rates WHERE vehicle_type = ?", (vehicle_type,)).fetchone()
    db.close()
    if hours <= 1:
        return round(rate["base_rate"], 2)
    extra_hours = hours - 1
    import math
    extra_hours = math.ceil(extra_hours)
    return round(rate["base_rate"] + extra_hours * rate["hourly_rate"], 2)


def slot_counts(db):
    rows = db.execute(
        """SELECT vehicle_type,
                  SUM(CASE WHEN status='available' THEN 1 ELSE 0 END) AS available,
                  SUM(CASE WHEN status IN ('booked','occupied') THEN 1 ELSE 0 END) AS occupied,
                  SUM(CASE WHEN status='disabled' THEN 1 ELSE 0 END) AS disabled,
                  COUNT(*) AS total
           FROM slots GROUP BY vehicle_type"""
    ).fetchall()
    return rows


# ----------------------------------------------------------------------
# Public pages
# ----------------------------------------------------------------------

@app.route("/")
def index():
    db = get_db()
    counts = slot_counts(db)
    floors = db.execute("SELECT * FROM floors ORDER BY level_order").fetchall()
    db.close()
    return render_template("index.html", user=current_user(), counts=counts, floors=floors)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")

        if not name or not email or not password:
            flash("Please fill all required fields.", "danger")
            return redirect(url_for("register"))

        db = get_db()
        existing = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            db.close()
            flash("An account with this email already exists.", "danger")
            return redirect(url_for("register"))

        db.execute(
            "INSERT INTO users (name, email, phone, password_hash, role) VALUES (?,?,?,?,?)",
            (name, email, phone, generate_password_hash(password), "user"),
        )
        db.commit()
        db.close()
        flash("Account created successfully. Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html", user=current_user())


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        db = get_db()
        user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        db.close()

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["role"] = user["role"]
            session["name"] = user["name"]
            flash(f"Welcome back, {user['name']}!", "success")
            next_url = request.args.get("next")
            if user["role"] == "admin":
                return redirect(next_url or url_for("admin_dashboard"))
            return redirect(next_url or url_for("user_dashboard"))

        flash("Invalid email or password.", "danger")
        return redirect(url_for("login"))

    return render_template("login.html", user=current_user())


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("index"))


# ----------------------------------------------------------------------
# User area
# ----------------------------------------------------------------------

@app.route("/dashboard")
@login_required
def user_dashboard():
    db = get_db()
    active = db.execute(
        """SELECT b.*, s.slot_number, f.name AS floor_name
           FROM bookings b
           JOIN slots s ON b.slot_id = s.id
           JOIN floors f ON s.floor_id = f.id
           WHERE b.user_id = ? AND b.status IN ('booked','active')
           ORDER BY b.booked_at DESC""",
        (session["user_id"],),
    ).fetchall()

    history = db.execute(
        """SELECT b.*, s.slot_number, f.name AS floor_name
           FROM bookings b
           JOIN slots s ON b.slot_id = s.id
           JOIN floors f ON s.floor_id = f.id
           WHERE b.user_id = ? AND b.status IN ('completed','cancelled')
           ORDER BY b.booked_at DESC LIMIT 10""",
        (session["user_id"],),
    ).fetchall()
    db.close()
    return render_template("user_dashboard.html", user=current_user(), active=active, history=history)


@app.route("/book", methods=["GET", "POST"])
@login_required
def book_slot():
    db = get_db()
    floors = db.execute("SELECT * FROM floors ORDER BY level_order").fetchall()

    if request.method == "POST":
        slot_id = request.form.get("slot_id")
        vehicle_number = request.form.get("vehicle_number", "").strip().upper()
        vehicle_type = request.form.get("vehicle_type")
        expected_hours = float(request.form.get("expected_hours", 1) or 1)

        if not slot_id or not vehicle_number:
            flash("Please select a slot and enter your vehicle number.", "danger")
            return redirect(url_for("book_slot"))

        slot = db.execute("SELECT * FROM slots WHERE id = ?", (slot_id,)).fetchone()
        if not slot or slot["status"] != "available":
            db.close()
            flash("Sorry, that slot is no longer available. Please pick another.", "danger")
            return redirect(url_for("book_slot"))

        code = generate_booking_code()
        estimated_amount = calc_fare(vehicle_type, expected_hours)

        db.execute(
            """INSERT INTO bookings
               (booking_code, user_id, slot_id, vehicle_number, vehicle_type,
                status, expected_hours, amount, payment_status)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (code, session["user_id"], slot_id, vehicle_number, vehicle_type,
             "booked", expected_hours, estimated_amount, "pending"),
        )
        db.execute("UPDATE slots SET status = 'booked' WHERE id = ?", (slot_id,))
        db.commit()
        booking = db.execute("SELECT * FROM bookings WHERE booking_code = ?", (code,)).fetchone()
        db.close()
        flash("Slot booked successfully!", "success")
        return redirect(url_for("ticket", booking_code=booking["booking_code"]))

    db.close()
    return render_template("book_slot.html", user=current_user(), floors=floors)


@app.route("/api/slots/<int:floor_id>")
@login_required
def api_slots(floor_id):
    vehicle_type = request.args.get("vehicle_type", "car")
    db = get_db()
    slots = db.execute(
        "SELECT * FROM slots WHERE floor_id = ? AND vehicle_type = ? ORDER BY slot_number",
        (floor_id, vehicle_type),
    ).fetchall()
    db.close()
    return jsonify([dict(s) for s in slots])


@app.route("/ticket/<booking_code>")
@login_required
def ticket(booking_code):
    db = get_db()
    booking = db.execute(
        """SELECT b.*, s.slot_number, f.name AS floor_name
           FROM bookings b
           JOIN slots s ON b.slot_id = s.id
           JOIN floors f ON s.floor_id = f.id
           WHERE b.booking_code = ?""",
        (booking_code,),
    ).fetchone()
    db.close()
    if not booking:
        flash("Booking not found.", "danger")
        return redirect(url_for("user_dashboard"))
    return render_template("ticket.html", user=current_user(), booking=booking)


@app.route("/qr/<booking_code>.png")
def qr_code(booking_code):
    img = qrcode.make(booking_code)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


@app.route("/cancel/<booking_code>", methods=["POST"])
@login_required
def cancel_booking(booking_code):
    db = get_db()
    booking = db.execute("SELECT * FROM bookings WHERE booking_code = ?", (booking_code,)).fetchone()
    if not booking or booking["user_id"] != session["user_id"]:
        db.close()
        flash("Booking not found.", "danger")
        return redirect(url_for("user_dashboard"))
    if booking["status"] not in ("booked",):
        db.close()
        flash("Only upcoming bookings can be cancelled.", "warning")
        return redirect(url_for("user_dashboard"))

    db.execute("UPDATE bookings SET status = 'cancelled' WHERE id = ?", (booking["id"],))
    db.execute("UPDATE slots SET status = 'available' WHERE id = ?", (booking["slot_id"],))
    db.commit()
    db.close()
    flash("Booking cancelled.", "success")
    return redirect(url_for("user_dashboard"))


@app.route("/pay/<booking_code>", methods=["GET", "POST"])
@login_required
def pay(booking_code):
    db = get_db()
    booking = db.execute("SELECT * FROM bookings WHERE booking_code = ?", (booking_code,)).fetchone()
    if not booking or booking["user_id"] != session["user_id"]:
        db.close()
        flash("Booking not found.", "danger")
        return redirect(url_for("user_dashboard"))

    if request.method == "POST":
        method = request.form.get("method", "UPI")
        db.execute(
            "UPDATE bookings SET payment_status = 'paid', payment_method = ? WHERE id = ?",
            (method, booking["id"]),
        )
        db.commit()
        db.close()
        flash("Payment successful. Thank you!", "success")
        return redirect(url_for("user_dashboard"))

    db.close()
    return render_template("pay.html", user=current_user(), booking=booking)


# ----------------------------------------------------------------------
# Kiosk-style check-in / check-out (used by admin / gate operator)
# ----------------------------------------------------------------------

@app.route("/checkin/<booking_code>", methods=["POST"])
@admin_required
def checkin(booking_code):
    db = get_db()
    booking = db.execute("SELECT * FROM bookings WHERE booking_code = ?", (booking_code,)).fetchone()
    if not booking or booking["status"] != "booked":
        db.close()
        flash("Booking cannot be checked in.", "danger")
        return redirect(url_for("admin_bookings"))

    now = datetime.now().strftime(DATE_FMT)
    db.execute(
        "UPDATE bookings SET status = 'active', entry_time = ? WHERE id = ?",
        (now, booking["id"]),
    )
    db.execute("UPDATE slots SET status = 'occupied' WHERE id = ?", (booking["slot_id"],))
    db.commit()
    db.close()
    flash(f"Vehicle {booking['vehicle_number']} checked in.", "success")
    return redirect(url_for("admin_bookings"))


@app.route("/checkout/<booking_code>", methods=["POST"])
@admin_required
def checkout(booking_code):
    db = get_db()
    booking = db.execute("SELECT * FROM bookings WHERE booking_code = ?", (booking_code,)).fetchone()
    if not booking or booking["status"] != "active":
        db.close()
        flash("Booking cannot be checked out.", "danger")
        return redirect(url_for("admin_bookings"))

    entry = datetime.strptime(booking["entry_time"], DATE_FMT)
    now = datetime.now()
    hours = max((now - entry).total_seconds() / 3600.0, 0.0167)
    amount = calc_fare(booking["vehicle_type"], hours)

    db.execute(
        """UPDATE bookings SET status = 'completed', exit_time = ?, amount = ?
           WHERE id = ?""",
        (now.strftime(DATE_FMT), amount, booking["id"]),
    )
    db.execute("UPDATE slots SET status = 'available' WHERE id = ?", (booking["slot_id"],))
    db.commit()
    db.close()
    flash(f"Vehicle {booking['vehicle_number']} checked out. Amount due: \u20b9{amount}", "success")
    return redirect(url_for("admin_bookings"))


# ----------------------------------------------------------------------
# Admin area
# ----------------------------------------------------------------------

@app.route("/admin")
@admin_required
def admin_dashboard():
    db = get_db()
    counts = slot_counts(db)

    total_slots = db.execute("SELECT COUNT(*) c FROM slots").fetchone()["c"]
    occupied = db.execute(
        "SELECT COUNT(*) c FROM slots WHERE status IN ('booked','occupied')"
    ).fetchone()["c"]

    today_revenue = db.execute(
        """SELECT COALESCE(SUM(amount),0) AS total FROM bookings
           WHERE payment_status='paid' AND date(exit_time) = date('now')"""
    ).fetchone()["total"]

    total_revenue = db.execute(
        "SELECT COALESCE(SUM(amount),0) AS total FROM bookings WHERE payment_status='paid'"
    ).fetchone()["total"]

    active_vehicles = db.execute(
        "SELECT COUNT(*) c FROM bookings WHERE status='active'"
    ).fetchone()["c"]

    # last 7 days revenue
    revenue_trend = db.execute(
        """SELECT date(exit_time) AS day, COALESCE(SUM(amount),0) AS total
           FROM bookings
           WHERE payment_status='paid' AND exit_time IS NOT NULL
             AND date(exit_time) >= date('now', '-6 days')
           GROUP BY date(exit_time)
           ORDER BY day"""
    ).fetchall()

    # occupancy by floor
    floor_occupancy = db.execute(
        """SELECT f.name,
                  SUM(CASE WHEN s.status IN ('booked','occupied') THEN 1 ELSE 0 END) AS occupied,
                  COUNT(s.id) AS total
           FROM floors f JOIN slots s ON s.floor_id = f.id
           GROUP BY f.id ORDER BY f.level_order"""
    ).fetchall()

    recent_bookings = db.execute(
        """SELECT b.*, s.slot_number, f.name AS floor_name, u.name AS user_name
           FROM bookings b
           JOIN slots s ON b.slot_id = s.id
           JOIN floors f ON s.floor_id = f.id
           JOIN users u ON b.user_id = u.id
           ORDER BY b.booked_at DESC LIMIT 8"""
    ).fetchall()

    db.close()
    return render_template(
        "admin_dashboard.html",
        user=current_user(),
        counts=counts,
        total_slots=total_slots,
        occupied=occupied,
        today_revenue=today_revenue,
        total_revenue=total_revenue,
        active_vehicles=active_vehicles,
        revenue_trend=revenue_trend,
        revenue_days=[r["day"] for r in revenue_trend],
        revenue_totals=[r["total"] for r in revenue_trend],
        floor_occupancy=floor_occupancy,
        floor_names=[f["name"] for f in floor_occupancy],
        floor_occupied=[f["occupied"] for f in floor_occupancy],
        floor_totals=[f["total"] for f in floor_occupancy],
        recent_bookings=recent_bookings,
    )


@app.route("/admin/bookings")
@admin_required
def admin_bookings():
    status_filter = request.args.get("status", "all")
    search = request.args.get("q", "").strip()

    query = """SELECT b.*, s.slot_number, f.name AS floor_name, u.name AS user_name
               FROM bookings b
               JOIN slots s ON b.slot_id = s.id
               JOIN floors f ON s.floor_id = f.id
               JOIN users u ON b.user_id = u.id
               WHERE 1=1"""
    params = []
    if status_filter != "all":
        query += " AND b.status = ?"
        params.append(status_filter)
    if search:
        query += " AND (b.vehicle_number LIKE ? OR b.booking_code LIKE ? OR u.name LIKE ?)"
        like = f"%{search}%"
        params.extend([like, like, like])
    query += " ORDER BY b.booked_at DESC"

    db = get_db()
    bookings = db.execute(query, params).fetchall()
    db.close()
    return render_template(
        "admin_bookings.html", user=current_user(), bookings=bookings,
        status_filter=status_filter, search=search
    )


@app.route("/admin/slots")
@admin_required
def admin_slots():
    db = get_db()
    floors = db.execute("SELECT * FROM floors ORDER BY level_order").fetchall()
    slots = db.execute(
        """SELECT s.*, f.name AS floor_name FROM slots s
           JOIN floors f ON s.floor_id = f.id
           ORDER BY f.level_order, s.vehicle_type, s.slot_number"""
    ).fetchall()
    db.close()
    return render_template("admin_slots.html", user=current_user(), floors=floors, slots=slots)


@app.route("/admin/slots/<int:slot_id>/toggle", methods=["POST"])
@admin_required
def toggle_slot(slot_id):
    db = get_db()
    slot = db.execute("SELECT * FROM slots WHERE id = ?", (slot_id,)).fetchone()
    if not slot:
        db.close()
        flash("Slot not found.", "danger")
        return redirect(url_for("admin_slots"))

    if slot["status"] == "disabled":
        new_status = "available"
    elif slot["status"] == "available":
        new_status = "disabled"
    else:
        flash("Cannot toggle a slot that is currently booked/occupied.", "warning")
        db.close()
        return redirect(url_for("admin_slots"))

    db.execute("UPDATE slots SET status = ? WHERE id = ?", (new_status, slot_id))
    db.commit()
    db.close()
    flash(f"Slot {slot['slot_number']} marked {new_status}.", "success")
    return redirect(url_for("admin_slots"))


@app.route("/admin/slots/add", methods=["POST"])
@admin_required
def add_slot():
    floor_id = request.form.get("floor_id")
    vehicle_type = request.form.get("vehicle_type")
    slot_number = request.form.get("slot_number", "").strip().upper()

    if not floor_id or not vehicle_type or not slot_number:
        flash("All fields are required to add a slot.", "danger")
        return redirect(url_for("admin_slots"))

    db = get_db()
    existing = db.execute(
        "SELECT id FROM slots WHERE floor_id=? AND slot_number=?", (floor_id, slot_number)
    ).fetchone()
    if existing:
        db.close()
        flash("A slot with this number already exists on this floor.", "danger")
        return redirect(url_for("admin_slots"))

    db.execute(
        "INSERT INTO slots (floor_id, slot_number, vehicle_type, status) VALUES (?,?,?,?)",
        (floor_id, slot_number, vehicle_type, "available"),
    )
    db.commit()
    db.close()
    flash(f"Slot {slot_number} added.", "success")
    return redirect(url_for("admin_slots"))


@app.route("/admin/users")
@admin_required
def admin_users():
    db = get_db()
    users = db.execute(
        """SELECT u.*,
                  (SELECT COUNT(*) FROM bookings b WHERE b.user_id = u.id) AS booking_count
           FROM users u ORDER BY u.created_at DESC"""
    ).fetchall()
    db.close()
    return render_template("admin_users.html", user=current_user(), users=users)


@app.route("/admin/analytics")
@admin_required
def admin_analytics():
    db = get_db()
    revenue_30d = db.execute(
        """SELECT date(exit_time) AS day, COALESCE(SUM(amount),0) AS total
           FROM bookings
           WHERE payment_status='paid' AND exit_time IS NOT NULL
             AND date(exit_time) >= date('now', '-29 days')
           GROUP BY date(exit_time) ORDER BY day"""
    ).fetchall()

    vehicle_split = db.execute(
        """SELECT vehicle_type, COUNT(*) AS c FROM bookings GROUP BY vehicle_type"""
    ).fetchall()

    peak_hours = db.execute(
        """SELECT strftime('%H', entry_time) AS hr, COUNT(*) AS c
           FROM bookings WHERE entry_time IS NOT NULL
           GROUP BY hr ORDER BY hr"""
    ).fetchall()

    db.close()
    return render_template(
        "admin_analytics.html", user=current_user(),
        revenue_30d=revenue_30d,
        rev30_days=[r["day"] for r in revenue_30d],
        rev30_totals=[r["total"] for r in revenue_30d],
        vehicle_split=vehicle_split,
        vehicle_labels=[v["vehicle_type"].capitalize() for v in vehicle_split],
        vehicle_data=[v["c"] for v in vehicle_split],
        peak_hours=peak_hours,
        peak_labels=[f"{p['hr']}:00" for p in peak_hours],
        peak_data=[p["c"] for p in peak_hours],
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
