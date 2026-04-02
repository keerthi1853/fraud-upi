import hashlib
import json
import os
import random
import re
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from urllib import error, request as urllib_request

from flask import Flask, jsonify, redirect, render_template, request, session, url_for


app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "upi_demo_secret_key_change_me")

USER_STORE_PATH = Path("users.json")
OTP_EXPIRY_MINUTES = 5
IST = timezone(timedelta(hours=5, minutes=30))
APP_DIR = Path(__file__).resolve().parent
ENV_PATH = APP_DIR / ".env"


def load_env_file() -> None:
    if not ENV_PATH.exists():
        return
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, value = text.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ[key] = value


load_env_file()


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def seed_users() -> dict:
    return {
        "admin@upi.com": {
            "name": "Admin User",
            "email": "admin@upi.com",
            "password_hash": hash_password("admin123"),
        }
    }


def save_users(users: dict) -> None:
    USER_STORE_PATH.write_text(json.dumps(users, indent=2), encoding="utf-8")


def load_users() -> dict:
    if not USER_STORE_PATH.exists():
        users = seed_users()
        save_users(users)
        return users

    try:
        raw_text = USER_STORE_PATH.read_text(encoding="utf-8")
        data = json.loads(raw_text) if raw_text.strip() else {}
        if not isinstance(data, dict):
            raise ValueError("Invalid store")

        normalized: dict = {}
        for key, value in data.items():
            if isinstance(value, str):
                email = key.strip().lower()
                normalized[email] = {
                    "name": key.strip(),
                    "email": email,
                    "password_hash": value,
                }
            elif isinstance(value, dict):
                email = str(value.get("email", key)).strip().lower()
                password_hash = str(value.get("password_hash", ""))
                normalized[email] = {
                    "name": str(value.get("name", email)).strip(),
                    "email": email,
                    "password_hash": password_hash,
                }
        if not normalized:
            normalized = seed_users()
        save_users(normalized)
        return normalized
    except Exception:
        users = seed_users()
        save_users(users)
        return users


def is_valid_email(email: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email))


def mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    if len(local) < 3:
        return f"{local[0]}***@{domain}" if local else f"***@{domain}"
    return f"{local[:2]}***@{domain}"


def generate_otp() -> str:
    return f"{random.randint(0, 999999):06d}"


def send_otp_brevo_api(recipient: str, otp: str, risk_level: str, amount: float) -> tuple[bool, str]:
    api_key = os.getenv("BREVO_API_KEY", "").strip()
    sender_email = os.getenv("SMTP_SENDER_EMAIL", "").strip()
    sender_name = os.getenv("SMTP_SENDER_NAME", "UPI Shield Security").strip()

    if not api_key:
        return False, "BREVO_API_KEY is missing."
    if not sender_email:
        return False, "SMTP_SENDER_EMAIL is missing."

    payload = {
        "sender": {"name": sender_name, "email": sender_email},
        "to": [{"email": recipient}],
        "subject": f"UPI Shield OTP Verification - {risk_level} Risk",
        "textContent": (
            f"Dear User,\n\n"
            f"We detected a {risk_level} risk transaction attempt of INR {amount:,.2f}.\n"
            f"Your OTP is: {otp}\n"
            f"This OTP is valid for {OTP_EXPIRY_MINUTES} minutes.\n\n"
            f"If this was not initiated by you, please stop immediately.\n\n"
            f"Regards,\nUPI Shield"
        ),
    }

    req = urllib_request.Request(
        "https://api.brevo.com/v3/smtp/email",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "accept": "application/json",
            "content-type": "application/json",
            "api-key": api_key,
        },
    )

    try:
        with urllib_request.urlopen(req, timeout=15) as response:
            if 200 <= response.status < 300:
                return True, "OTP sent successfully via Brevo API."
            return False, f"Brevo API returned status {response.status}."
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        return False, f"Brevo API error {exc.code}: {body}"
    except Exception as exc:
        return False, f"Brevo API request failed: {exc}"


def send_otp_email(recipient: str, otp: str, risk_level: str, amount: float) -> tuple[bool, str]:
    if not is_valid_email(recipient):
        return False, "Registered email is invalid. Please update your email and retry."

    email_provider = os.getenv("EMAIL_PROVIDER", "").strip().lower()
    if email_provider == "brevo":
        return send_otp_brevo_api(recipient, otp, risk_level, amount)

    smtp_server = os.getenv("SMTP_SERVER", "").strip()
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_username = os.getenv("SMTP_USERNAME", "").strip()
    smtp_password = os.getenv("SMTP_PASSWORD", "").strip().replace(" ", "")
    sender_email = os.getenv("SMTP_SENDER_EMAIL", smtp_username).strip()
    sender_name = os.getenv("SMTP_SENDER_NAME", "UPI Shield Security").strip()

    if not smtp_server or not smtp_username or not smtp_password or not sender_email:
        # Development fallback: we log OTP to server console if SMTP is not configured.
        print(
            f"[OTP-DEV] SMTP not configured. OTP for {recipient} is {otp} "
            f"for INR {amount:,.2f} ({risk_level})"
        )
        return True, "SMTP is not configured. OTP logged to server console for development."

    message = EmailMessage()
    message["Subject"] = f"UPI Shield OTP Verification - {risk_level} Risk"
    message["From"] = f"{sender_name} <{sender_email}>"
    message["To"] = recipient
    message.set_content(
        f"Dear User,\n\n"
        f"We detected a {risk_level} risk transaction attempt of INR {amount:,.2f}.\n"
        f"Your OTP is: {otp}\n"
        f"This OTP is valid for {OTP_EXPIRY_MINUTES} minutes.\n\n"
        f"If this was not initiated by you, please stop immediately.\n\n"
        f"Regards,\nUPI Shield"
    )

    with smtplib.SMTP(smtp_server, smtp_port, timeout=15) as server:
        server.starttls()
        server.login(smtp_username, smtp_password)
        server.send_message(message)

    return True, "OTP sent successfully."


@app.route("/")
def root():
    if session.get("authenticated"):
        return redirect(url_for("home_page"))
    return render_template("index.html")


@app.route("/login")
def login_page():
    return render_template("login.html")


@app.route("/register")
def register_page():
    return render_template("register.html")


@app.route("/home")
def home_page():
    if not session.get("authenticated"):
        return redirect(url_for("root"))
    return render_template("home.html", username=session.get("name", "User"))


@app.route("/dashboard")
def dashboard_page():
    if not session.get("authenticated"):
        return redirect(url_for("root"))
    return render_template("risk_dashboard.html", username=session.get("name", "User"))


@app.post("/api/login")
def api_login():
    payload = request.get_json(silent=True) or {}
    email = str(payload.get("email", "")).strip().lower()
    password = str(payload.get("password", ""))

    users = load_users()
    user = users.get(email)
    if user and user.get("password_hash") == hash_password(password):
        session["authenticated"] = True
        session["email"] = email
        session["name"] = user.get("name", "User")
        return jsonify({"ok": True})

    return jsonify({"ok": False, "message": "Invalid email or password"}), 401


@app.post("/api/register")
def api_register():
    payload = request.get_json(silent=True) or {}
    name = str(payload.get("name", "")).strip()
    email = str(payload.get("email", "")).strip().lower()
    password = str(payload.get("password", ""))
    confirm_password = str(payload.get("confirm_password", ""))

    if len(name) < 2:
        return jsonify({"ok": False, "message": "Name must be at least 2 characters"}), 400
    if not is_valid_email(email):
        return jsonify({"ok": False, "message": "Please enter a valid email"}), 400
    if len(password) < 6:
        return jsonify({"ok": False, "message": "Password must be at least 6 characters"}), 400
    if password != confirm_password:
        return jsonify({"ok": False, "message": "Passwords do not match"}), 400

    users = load_users()
    if email in users:
        return jsonify({"ok": False, "message": "Email is already registered"}), 400

    users[email] = {
        "name": name,
        "email": email,
        "password_hash": hash_password(password),
    }
    save_users(users)
    session["authenticated"] = True
    session["email"] = email
    session["name"] = name
    return jsonify({"ok": True, "redirect": url_for("home_page")})


@app.post("/api/logout")
def api_logout():
    session.clear()
    return jsonify({"ok": True})


@app.post("/api/risk-level")
def api_risk_level():
    if not session.get("authenticated"):
        return jsonify({"ok": False, "message": "Unauthorized"}), 401

    payload = request.get_json(silent=True) or {}
    try:
        amount = float(payload.get("amount", 0))
    except Exception:
        return jsonify({"ok": False, "message": "Invalid amount"}), 400

    if amount < 0:
        return jsonify({"ok": False, "message": "Amount cannot be negative"}), 400

    user_email = session.get("email", "")
    if amount > 100000:
        return jsonify(
            {
                "ok": True,
                "allowed": False,
                "level": "Blocked",
                "message": "More than 1L is not possible to transfer.",
                "otp_required": False,
            }
        )
    if amount > 50000:
        level = "High"
        otp = generate_otp()
        session["pending_otp"] = {
            "otp_hash": hash_password(otp),
            "level": level,
            "amount": amount,
            "email": user_email,
            "expires_at": (datetime.now(tz=IST) + timedelta(minutes=OTP_EXPIRY_MINUTES)).isoformat(),
            "attempts_left": 3,
        }
        try:
            sent, delivery_note = send_otp_email(user_email, otp, level, amount)
            if not sent:
                session.pop("pending_otp", None)
                return jsonify({"ok": False, "message": delivery_note}), 400
        except Exception as exc:
            print(f"[OTP-ERROR] Failed to send high-risk OTP to {user_email}: {exc}")
            session.pop("pending_otp", None)
            return jsonify({"ok": False, "message": f"Failed to send OTP email. {exc}"}), 500
        return jsonify(
            {
                "ok": True,
                "allowed": False,
                "level": level,
                "message": "Amount from above 50k to 1L is High Risk.",
                "otp_required": True,
                "email_hint": mask_email(user_email),
                "notification": (
                    "High Risk Alert: OTP sent to your registered email. "
                    "Security notification was triggered."
                ),
                "delivery_note": delivery_note,
            }
        )
    if amount > 10000:
        level = "Medium"
        otp = generate_otp()
        session["pending_otp"] = {
            "otp_hash": hash_password(otp),
            "level": level,
            "amount": amount,
            "email": user_email,
            "expires_at": (datetime.now(tz=IST) + timedelta(minutes=OTP_EXPIRY_MINUTES)).isoformat(),
            "attempts_left": 3,
        }
        try:
            sent, delivery_note = send_otp_email(user_email, otp, level, amount)
            if not sent:
                session.pop("pending_otp", None)
                return jsonify({"ok": False, "message": delivery_note}), 400
        except Exception as exc:
            print(f"[OTP-ERROR] Failed to send medium-risk OTP to {user_email}: {exc}")
            session.pop("pending_otp", None)
            return jsonify({"ok": False, "message": f"Failed to send OTP email. {exc}"}), 500
        return jsonify(
            {
                "ok": True,
                "allowed": False,
                "level": level,
                "message": "Amount more than 10k to 50k is Medium Risk.",
                "otp_required": True,
                "email_hint": mask_email(user_email),
                "notification": "Medium Risk: OTP sent to your registered email for verification.",
                "delivery_note": delivery_note,
            }
        )
    return jsonify(
        {
            "ok": True,
            "allowed": True,
            "level": "Low",
            "message": "Amount up to 10k is Low Risk.",
            "otp_required": False,
        }
    )


@app.post("/api/verify-otp")
def api_verify_otp():
    if not session.get("authenticated"):
        return jsonify({"ok": False, "message": "Unauthorized"}), 401

    payload = request.get_json(silent=True) or {}
    otp = str(payload.get("otp", "")).strip()
    pending = session.get("pending_otp")

    if not pending:
        return jsonify({"ok": False, "message": "No pending verification found."}), 400

    if not re.fullmatch(r"\d{6}", otp):
        return jsonify({"ok": False, "message": "OTP must be 6 digits."}), 400

    expires_at = datetime.fromisoformat(str(pending.get("expires_at")))
    if datetime.now(tz=IST) > expires_at:
        session.pop("pending_otp", None)
        return jsonify({"ok": False, "message": "OTP expired. Please retry transaction."}), 400

    if pending.get("otp_hash") != hash_password(otp):
        attempts_left = int(pending.get("attempts_left", 0)) - 1
        pending["attempts_left"] = attempts_left
        session["pending_otp"] = pending
        if attempts_left <= 0:
            session.pop("pending_otp", None)
            return jsonify({"ok": False, "message": "Maximum OTP attempts reached."}), 400
        return jsonify({"ok": False, "message": f"Invalid OTP. Attempts left: {attempts_left}"}), 400

    approved = {
        "level": pending.get("level", "Unknown"),
        "amount": pending.get("amount", 0),
        "verified_at": datetime.now(tz=IST).strftime("%Y-%m-%d %H:%M:%S IST"),
    }
    session.pop("pending_otp", None)
    return jsonify(
        {
            "ok": True,
            "allowed": True,
            "message": "OTP verified successfully. Transaction can proceed.",
            "verified": approved,
        }
    )


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    debug_mode = os.getenv("FLASK_DEBUG", "false").strip().lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug_mode)
