import hashlib
import json
import re
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, session, url_for


app = Flask(__name__)
app.secret_key = "upi_demo_secret_key_change_me"

USER_STORE_PATH = Path("users.json")


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

    if amount > 100000:
        return jsonify(
            {
                "ok": True,
                "allowed": False,
                "level": "Blocked",
                "message": "More than 1L is not possible to transfer.",
            }
        )
    if amount > 50000:
        return jsonify(
            {
                "ok": True,
                "allowed": True,
                "level": "High",
                "message": "Amount from above 50k to 1L is High Risk.",
            }
        )
    if amount > 10000:
        return jsonify(
            {
                "ok": True,
                "allowed": True,
                "level": "Medium",
                "message": "Amount more than 10k to 50k is Medium Risk.",
            }
        )
    return jsonify(
        {
            "ok": True,
            "allowed": True,
            "level": "Low",
            "message": "Amount up to 10k is Low Risk.",
        }
    )


if __name__ == "__main__":
    app.run(debug=True)
