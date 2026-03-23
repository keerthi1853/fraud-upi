import os
import random
import smtplib
import sqlite3
import string
from datetime import datetime, timedelta
from email.message import EmailMessage
from pathlib import Path

import pandas as pd
import pickle
import streamlit as st
from werkzeug.security import check_password_hash, generate_password_hash
try:
    import psycopg
    from psycopg.rows import dict_row
except Exception:
    psycopg = None

st.set_page_config(page_title='UPI Shield', page_icon=':shield:', layout='wide')

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / 'fraud_app.db'
USERS_EXCEL_PATH = BASE_DIR / 'registered_users.xlsx'
DATABASE_URL = os.environ.get('DATABASE_URL')
MODEL_CANDIDATES = [
    BASE_DIR / 'UPI_Fraud_Detection_Model_Fixed.pkl',
    BASE_DIR.parent / 'trans' / 'UPI_Fraud_Detection_Model_Fixed.pkl',
]
SECURITY_QUESTIONS = [
    "What is your favorite teacher name?",
    "What is your first school name?",
    "What is your childhood best friend name?",
]
OTP_EXPIRY_MINUTES = 5
OTP_MAX_ATTEMPTS = 3
OTP_RESEND_COOLDOWN_SECONDS = 60
OTP_LOCK_MINUTES = 10


def apply_custom_theme():
    st.markdown(
        """
        <style>
            .stApp {
                background: radial-gradient(circle at 10% 10%, #ffe7d6 0%, #f0f7ff 35%, #ecfff5 100%);
            }
            .block-container {
                padding-top: 1.2rem;
                padding-bottom: 2rem;
            }
            .hero-card {
                background: linear-gradient(120deg, #0f6cbd 0%, #14b8a6 55%, #22c55e 100%);
                color: white;
                border-radius: 16px;
                padding: 18px 20px;
                box-shadow: 0 10px 24px rgba(0, 0, 0, 0.14);
                margin-bottom: 12px;
            }
            .soft-card {
                background: #ffffff;
                border: 1px solid #dbeafe;
                border-radius: 14px;
                padding: 14px 16px;
                box-shadow: 0 6px 18px rgba(14, 116, 144, 0.10);
                margin-bottom: 10px;
            }
            .risk-low {
                border-left: 6px solid #16a34a;
            }
            .risk-medium {
                border-left: 6px solid #f59e0b;
            }
            .risk-high {
                border-left: 6px solid #dc2626;
            }
            .stButton > button {
                border-radius: 10px;
                border: none;
                padding: 0.52rem 0.9rem;
                font-weight: 600;
                background: linear-gradient(90deg, #0f6cbd 0%, #14b8a6 100%);
                color: white;
            }
            .stButton > button:hover {
                filter: brightness(1.05);
            }
            .back-note {
                color: #334155;
                font-weight: 600;
                margin-bottom: 6px;
            }
            [data-testid="stSidebar"] {
                background: linear-gradient(180deg, #082f49 0%, #0f766e 100%);
            }
            [data-testid="stSidebar"] * {
                color: #e5f6ff !important;
            }
            .landing-panel {
                background: rgba(255, 255, 255, 0.82);
                border: 1px solid #dbeafe;
                border-radius: 16px;
                padding: 26px 20px 22px 20px;
                box-shadow: 0 10px 24px rgba(14, 116, 144, 0.12);
                text-align: center;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def get_db():
    if DATABASE_URL:
        if psycopg is None:
            raise RuntimeError('Postgres driver not available. Install psycopg[binary].')
        conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
    return conn


def _sql(query: str) -> str:
    return query.replace('?', '%s') if DATABASE_URL else query


def fetch_one(query: str, params=()):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(_sql(query), params)
    row = cur.fetchone()
    cur.close()
    conn.close()
    if row is None:
        return None
    return dict(row) if not isinstance(row, dict) else row


def fetch_all(query: str, params=()):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(_sql(query), params)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) if not isinstance(r, dict) else r for r in rows]


def run_write(query: str, params=()):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(_sql(query), params)
    conn.commit()
    cur.close()
    conn.close()


def init_db():
    conn = get_db()
    cur = conn.cursor()

    if DATABASE_URL:
        cur.execute(
            '''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                phone TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                security_question TEXT,
                security_answer_hash TEXT,
                created_at TEXT NOT NULL
            )
            '''
        )
        cur.execute(
            '''
            CREATE TABLE IF NOT EXISTS feedback (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            '''
        )
        cur.execute(
            '''
            CREATE TABLE IF NOT EXISTS reset_messages (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                code TEXT NOT NULL,
                created_at TEXT NOT NULL,
                destination TEXT,
                purpose TEXT DEFAULT 'password_reset',
                expires_at TEXT,
                attempts INTEGER DEFAULT 0,
                locked_until TEXT
            )
            '''
        )
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS security_question TEXT")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS security_answer_hash TEXT")
        cur.execute("ALTER TABLE reset_messages ADD COLUMN IF NOT EXISTS purpose TEXT DEFAULT 'password_reset'")
        cur.execute("ALTER TABLE reset_messages ADD COLUMN IF NOT EXISTS expires_at TEXT")
        cur.execute("ALTER TABLE reset_messages ADD COLUMN IF NOT EXISTS attempts INTEGER DEFAULT 0")
        cur.execute("ALTER TABLE reset_messages ADD COLUMN IF NOT EXISTS locked_until TEXT")
    else:
        cur.execute(
            '''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                phone TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                security_question TEXT,
                security_answer_hash TEXT,
                created_at TEXT NOT NULL
            )
            '''
        )
        cur.execute(
            '''
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            '''
        )
        cur.execute(
            '''
            CREATE TABLE IF NOT EXISTS reset_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                code TEXT NOT NULL,
                created_at TEXT NOT NULL,
                destination TEXT,
                purpose TEXT DEFAULT 'password_reset',
                expires_at TEXT,
                attempts INTEGER DEFAULT 0,
                locked_until TEXT,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
            '''
        )

        users_cols = [row['name'] for row in cur.execute("PRAGMA table_info(users)").fetchall()]
        if 'security_question' not in users_cols:
            cur.execute("ALTER TABLE users ADD COLUMN security_question TEXT")
        if 'security_answer_hash' not in users_cols:
            cur.execute("ALTER TABLE users ADD COLUMN security_answer_hash TEXT")

        cols = [row['name'] for row in cur.execute("PRAGMA table_info(reset_messages)").fetchall()]
        if 'destination' not in cols:
            cur.execute("ALTER TABLE reset_messages ADD COLUMN destination TEXT")
        if 'purpose' not in cols:
            cur.execute("ALTER TABLE reset_messages ADD COLUMN purpose TEXT DEFAULT 'password_reset'")
        if 'expires_at' not in cols:
            cur.execute("ALTER TABLE reset_messages ADD COLUMN expires_at TEXT")
        if 'attempts' not in cols:
            cur.execute("ALTER TABLE reset_messages ADD COLUMN attempts INTEGER DEFAULT 0")
        if 'locked_until' not in cols:
            cur.execute("ALTER TABLE reset_messages ADD COLUMN locked_until TEXT")

    conn.commit()
    cur.close()
    conn.close()


def export_users_to_excel():
    rows = fetch_all(
        'SELECT id, name, email, phone, security_question, security_answer_hash, created_at FROM users ORDER BY id DESC'
    )
    users_df = pd.DataFrame(
        rows,
        columns=['id', 'name', 'email', 'phone', 'security_question', 'security_answer_hash', 'created_at']
    )
    users_df.to_excel(USERS_EXCEL_PATH, index=False)


@st.cache_resource(show_spinner=False)
def load_model_bundle():
    for model_path in MODEL_CANDIDATES:
        if model_path.exists():
            with open(model_path, 'rb') as f:
                bundle = pickle.load(f)

            if isinstance(bundle, dict):
                if bundle.get('model') is not None and bundle.get('feature_columns'):
                    return {
                        'model': bundle.get('model'),
                        'feature_columns': bundle.get('feature_columns'),
                        'scaler': bundle.get('scaler'),
                        'format': 'model_scaler',
                    }
                if bundle.get('pipeline') is not None and bundle.get('features'):
                    return {
                        'model': bundle.get('pipeline'),
                        'feature_columns': bundle.get('features'),
                        'scaler': None,
                        'format': 'pipeline_features',
                    }
    return None


def init_session():
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
    if 'user' not in st.session_state:
        st.session_state.user = None
    if 'page' not in st.session_state:
        st.session_state.page = 'Home'
    if 'pending_medium_txn' not in st.session_state:
        st.session_state.pending_medium_txn = None
    if 'pending_txn_otp' not in st.session_state:
        st.session_state.pending_txn_otp = None
    if 'pending_txn_otp_created_at' not in st.session_state:
        st.session_state.pending_txn_otp_created_at = None
    if 'pending_txn_otp_attempts' not in st.session_state:
        st.session_state.pending_txn_otp_attempts = 0
    if 'pending_txn_otp_resend_after' not in st.session_state:
        st.session_state.pending_txn_otp_resend_after = None
    if 'auth_view' not in st.session_state:
        st.session_state.auth_view = 'landing'


def get_time_period():
    hour = datetime.now().hour
    if 5 <= hour < 12:
        return 'Morning'
    if 12 <= hour < 17:
        return 'Afternoon'
    if 17 <= hour < 22:
        return 'Evening'
    return 'Night'


def generate_otp():
    return ''.join(random.choices(string.digits, k=6))


def mask_email(email: str):
    try:
        local, domain = email.split('@')
        if len(local) <= 2:
            return f"{local[0]}*@{domain}"
        return f"{local[:2]}{'*' * (len(local) - 2)}@{domain}"
    except ValueError:
        return email


def mask_phone(phone: str):
    if not phone:
        return '***'
    if len(phone) <= 4:
        return '*' * len(phone)
    return ('*' * (len(phone) - 2)) + phone[-2:]


def send_otp_email(recipient_email: str, name: str, otp_code: str, subject: str = 'FraudShield OTP'):
    smtp_host = os.environ.get('SMTP_HOST', 'smtp.gmail.com')
    smtp_port = int(os.environ.get('SMTP_PORT', '587'))
    smtp_user = os.environ.get('SMTP_USER')
    smtp_pass = os.environ.get('SMTP_PASS')
    sender = os.environ.get('SMTP_FROM', smtp_user)

    if not smtp_user or not smtp_pass or not sender:
        return False, 'SMTP_USER / SMTP_PASS / SMTP_FROM env vars are missing'

    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = sender
    msg['To'] = recipient_email
    msg.set_content(
        f'Hello {name},\n\nYour 6-digit OTP is: {otp_code}\n\nDo not share this code.'
    )

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        return True, None
    except Exception as exc:
        return False, str(exc)


def build_pipeline_input(data):
    return {
        'Transaction_Amount': float(data['transaction_amount']),
        'Transaction_Type': data['transaction_type'],
        'Time_of_Transaction': float(data['time_of_transaction']),
        'Device_Used': data['device_used'],
        'Location': data['location'],
        'Previous_Fraudulent_Transactions': int(data.get('previous_fraudulent_transactions', 0)),
        'Account_Age': float(data['account_age']),
        'Number_of_Transactions_Last_24H': int(data['number_of_transactions_last_24h']),
        'Payment_Method': data['payment_method'],
    }


def build_model_scaler_input(data, feature_columns):
    row = {col: 0 for col in feature_columns}
    if 'amount' in row:
        row['amount'] = float(data.get('transaction_amount', 0))
    if 'Transaction_Frequency' in row:
        row['Transaction_Frequency'] = float(data.get('number_of_transactions_last_24h', 0))
    if 'Year' in row:
        row['Year'] = datetime.now().year

    mapping = {
        'Transaction_Type': data.get('transaction_type', ''),
        'Payment_Gateway': data.get('payment_gateway', ''),
        'Merchant_Category': data.get('merchant_category', ''),
        'Device_OS': data.get('device_used', ''),
        'Month': datetime.now().strftime('%B'),
    }

    for base, value in mapping.items():
        key = f'{base}_{value}'
        if key in row:
            row[key] = 1
    return row


def get_fraud_probability(bundle, input_data):
    model = bundle['model']

    if bundle['format'] == 'pipeline_features':
        row = build_pipeline_input(input_data)
        X = pd.DataFrame([row], columns=bundle['feature_columns'])
    else:
        row = build_model_scaler_input(input_data, bundle['feature_columns'])
        base_df = pd.DataFrame([row], columns=bundle['feature_columns'])
        scaler = bundle.get('scaler')
        X = scaler.transform(base_df) if scaler is not None else base_df

    if hasattr(model, 'predict_proba'):
        return float(model.predict_proba(X)[0][1])
    return float(model.predict(X)[0])


def risk_band(prob):
    if prob < 0.35:
        return 'Low Risk', 'Approved instantly with no interruption.'
    if prob < 0.70:
        return 'Medium Risk', 'Suspicious transaction: alert + user confirmation required.'
    return 'High Risk', 'Transaction blocked and advanced verification required.'


def amount_risk_band(amount: float):
    if amount <= 15000:
        return 'Low Risk', 'Transaction is possible and approved instantly.'
    if amount <= 50000:
        return 'Medium Risk', 'OTP verification is required to complete this transaction.'
    if amount <= 99999:
        return 'High Risk', 'Be alert and think again before transferring this amount to the person.'
    return 'Very High Risk', 'Amount is extremely high. Transaction is blocked and sent for manual review.'


def parse_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except Exception:
        return None


def get_demo_testcases():
    return [
        {
            'Testcase ID': 'TC_001',
            'Scenario': 'High-risk amount transaction',
            'transaction_amount': 100000,
            'transaction_type': 'P2P',
            'location': 'Utilities',
            'number_of_transactions_last_24h': 631,
            'payment_gateway': 'GooglePay',
            'device_used': 'Android',
            'payment_method': 'UPI',
            'account_age': 12,
            'time_of_transaction': 12,
        },
        {
            'Testcase ID': 'TC_002',
            'Scenario': 'Low-risk transaction',
            'transaction_amount': 4000,
            'transaction_type': 'P2P',
            'location': 'Food',
            'number_of_transactions_last_24h': 10,
            'payment_gateway': 'PhonePe',
            'device_used': 'Android',
            'payment_method': 'UPI',
            'account_age': 12,
            'time_of_transaction': 12,
        },
        {
            'Testcase ID': 'TC_003',
            'Scenario': 'High frequency with low amount',
            'transaction_amount': 4000,
            'transaction_type': 'P2P',
            'location': 'Food',
            'number_of_transactions_last_24h': 780,
            'payment_gateway': 'Paytm',
            'device_used': 'iOS',
            'payment_method': 'UPI',
            'account_age': 12,
            'time_of_transaction': 12,
        },
        {
            'Testcase ID': 'TC_004',
            'Scenario': 'Medium-risk amount rule',
            'transaction_amount': 25000,
            'transaction_type': 'P2P',
            'location': 'Utilities',
            'number_of_transactions_last_24h': 100,
            'payment_gateway': 'PhonePe',
            'device_used': 'Android',
            'payment_method': 'UPI',
            'account_age': 12,
            'time_of_transaction': 12,
        },
        {
            'Testcase ID': 'TC_005',
            'Scenario': 'Very high amount transaction',
            'transaction_amount': 200000,
            'transaction_type': 'P2P',
            'location': 'Utilities',
            'number_of_transactions_last_24h': 50,
            'payment_gateway': 'GooglePay',
            'device_used': 'Android',
            'payment_method': 'UPI',
            'account_age': 12,
            'time_of_transaction': 12,
        },
        {
            'Testcase ID': 'TC_006',
            'Scenario': 'Gateway anomaly style case',
            'transaction_amount': 12000,
            'transaction_type': 'P2P',
            'location': 'Utilities',
            'number_of_transactions_last_24h': 250,
            'payment_gateway': 'Unknown',
            'device_used': 'Android',
            'payment_method': 'UPI',
            'account_age': 12,
            'time_of_transaction': 12,
        },
    ]


def build_testcase_output_table(model_bundle):
    rows = []
    for case in get_demo_testcases():
        payload = {
            'transaction_amount': case['transaction_amount'],
            'transaction_type': case['transaction_type'],
            'time_of_transaction': case['time_of_transaction'],
            'device_used': case['device_used'],
            'location': case['location'],
            'previous_fraudulent_transactions': 0,
            'number_of_transactions_last_24h': case['number_of_transactions_last_24h'],
            'payment_method': case['payment_method'],
            'account_age': case['account_age'],
            'payment_gateway': case['payment_gateway'],
            'merchant_category': case['location'],
        }

        model_score_text = 'N/A'
        if model_bundle is not None:
            try:
                model_score = get_fraud_probability(model_bundle, payload)
                model_score = max(0.0, min(1.0, model_score))
                model_score_text = f"{model_score * 100:.2f}%"
            except Exception:
                model_score_text = 'Unavailable'

        level, action = amount_risk_band(case['transaction_amount'])
        rows.append({
            'Testcase ID': case['Testcase ID'],
            'Scenario': case['Scenario'],
            'Input': f"Amt={case['transaction_amount']}, Type={case['transaction_type']}, Loc={case['location']}, Freq={case['number_of_transactions_last_24h']}, Gateway={case['payment_gateway']}, Device={case['device_used']}",
            'Model Risk Score': model_score_text,
            'Rule Decision': level,
            'System Action': action,
        })
    return pd.DataFrame(rows)


def auth_ui():
    view = st.session_state.auth_view

    if view == 'landing':
        st.markdown("<div style='height:20vh;'></div>", unsafe_allow_html=True)
        c1, c2, c3 = st.columns([1.2, 2.6, 1.2])
        with c2:
            st.markdown(
                """
                <div class="landing-panel">
                    <h1 style="margin:0;">UPI Shield</h1>
                    <p style="margin:10px 0 8px 0;color:#516b85;">Secure and simple transaction risk awareness platform</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            left, right = st.columns(2)
            with left:
                if st.button('Login', use_container_width=True):
                    st.session_state.auth_view = 'login'
                    st.rerun()
            with right:
                if st.button('Register', use_container_width=True):
                    st.session_state.auth_view = 'register'
                    st.rerun()
        return

    if view == 'login':
        _, center_col, _ = st.columns([1.1, 2.2, 1.1])
        with center_col:
            st.markdown('<div class="back-note">Navigation</div>', unsafe_allow_html=True)
            if st.button('Back to Welcome', use_container_width=True):
                st.session_state.auth_view = 'landing'
                st.rerun()

            st.markdown('<div class="soft-card">', unsafe_allow_html=True)
            st.subheader('Login')
            with st.form('login_form'):
                email = st.text_input('Email')
                password = st.text_input('Password', type='password')
                submitted = st.form_submit_button('Login')
            st.markdown('</div>', unsafe_allow_html=True)

            if submitted:
                user = fetch_one('SELECT * FROM users WHERE email = ?', (email.strip().lower(),))
                if user and check_password_hash(user['password_hash'], password):
                    st.session_state.authenticated = True
                    st.session_state.user = dict(user)
                    st.success('Login successful')
                    st.rerun()
                st.error('Invalid email or password')

            with st.expander('Forgot Password'):
                c1, c2 = st.columns(2)

                with c1:
                    with st.form('send_otp_form'):
                        email_send = st.text_input('Registered Email')
                        send = st.form_submit_button('Send 6-digit OTP')

                    if send:
                        user = fetch_one('SELECT id, name, email FROM users WHERE email = ?', (email_send.strip().lower(),))
                        if user:
                            latest = fetch_one(
                                "SELECT id, created_at, locked_until FROM reset_messages WHERE user_id = ? AND purpose = 'password_reset' ORDER BY id DESC LIMIT 1",
                                (user['id'],)
                            )
                            now = datetime.now()
                            if latest:
                                locked_until = parse_dt(latest.get('locked_until'))
                                created_at = parse_dt(latest.get('created_at'))
                                if locked_until and now < locked_until:
                                    st.error('Too many wrong attempts. Try again later.')
                                elif created_at and (now - created_at).total_seconds() < OTP_RESEND_COOLDOWN_SECONDS:
                                    wait_sec = int(OTP_RESEND_COOLDOWN_SECONDS - (now - created_at).total_seconds())
                                    st.warning(f'Please wait {wait_sec}s before requesting another OTP.')
                                else:
                                    otp = generate_otp()
                                    expires_at = (now + timedelta(minutes=OTP_EXPIRY_MINUTES)).isoformat()
                                    run_write(
                                        'INSERT INTO reset_messages (user_id, code, created_at, destination, purpose, expires_at, attempts, locked_until) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                                        (user['id'], otp, now.isoformat(), user['email'], 'password_reset', expires_at, 0, None),
                                    )
                                    ok, err = send_otp_email(user['email'], user['name'], otp)
                                    if ok:
                                        st.success(f'OTP sent to {mask_email(user["email"])}. Valid for {OTP_EXPIRY_MINUTES} minutes.')
                                    else:
                                        st.error(f'OTP email failed: {err}')
                            else:
                                otp = generate_otp()
                                expires_at = (now + timedelta(minutes=OTP_EXPIRY_MINUTES)).isoformat()
                                run_write(
                                    'INSERT INTO reset_messages (user_id, code, created_at, destination, purpose, expires_at, attempts, locked_until) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                                    (user['id'], otp, now.isoformat(), user['email'], 'password_reset', expires_at, 0, None),
                                )
                                ok, err = send_otp_email(user['email'], user['name'], otp)
                                if ok:
                                    st.success(f'OTP sent to {mask_email(user["email"])}. Valid for {OTP_EXPIRY_MINUTES} minutes.')
                                else:
                                    st.error(f'OTP email failed: {err}')
                        else:
                            st.success('If email exists, OTP has been sent.')

                with c2:
                    with st.form('reset_form'):
                        email_r = st.text_input('Email for Reset')
                        question_r = st.selectbox('Security Question', SECURITY_QUESTIONS)
                        answer_r = st.text_input('Security Answer')
                        otp_r = st.text_input('Enter 6-digit OTP')
                        new_password = st.text_input('New Password', type='password')
                        confirm_new = st.text_input('Confirm New Password', type='password')
                        reset = st.form_submit_button('Verify & Reset Password')

                    if reset:
                        if new_password != confirm_new:
                            st.error('Passwords do not match')
                        elif len(otp_r.strip()) != 6 or not otp_r.strip().isdigit():
                            st.error('OTP must contain exactly 6 numbers')
                        elif len(new_password) < 6:
                            st.error('Password must be at least 6 characters')
                        else:
                            user = fetch_one(
                                'SELECT id, security_question, security_answer_hash FROM users WHERE email = ?',
                                (email_r.strip().lower(),)
                            )
                            if not user:
                                st.error('Invalid recovery details')
                            elif user.get('security_question') != question_r:
                                st.error('Security question does not match')
                            elif not user.get('security_answer_hash') or not check_password_hash(
                                user['security_answer_hash'],
                                answer_r.strip().lower()
                            ):
                                st.error('Security answer is incorrect')
                            else:
                                otp_row = fetch_one(
                                    "SELECT id, code, expires_at, attempts, locked_until FROM reset_messages WHERE user_id = ? AND purpose = 'password_reset' ORDER BY id DESC LIMIT 1",
                                    (user['id'],),
                                )
                                now = datetime.now()
                                if not otp_row:
                                    st.error('OTP not found. Please request a new OTP.')
                                else:
                                    locked_until = parse_dt(otp_row.get('locked_until'))
                                    expires_at = parse_dt(otp_row.get('expires_at'))
                                    attempts = int(otp_row.get('attempts') or 0)

                                    if locked_until and now < locked_until:
                                        st.error('Too many wrong attempts. Try again later.')
                                    elif expires_at and now > expires_at:
                                        st.error('OTP expired. Please request a new OTP.')
                                    elif otp_r.strip() != str(otp_row.get('code', '')).strip():
                                        attempts += 1
                                        if attempts >= OTP_MAX_ATTEMPTS:
                                            run_write(
                                                'UPDATE reset_messages SET attempts = ?, locked_until = ? WHERE id = ?',
                                                (attempts, (now + timedelta(minutes=OTP_LOCK_MINUTES)).isoformat(), otp_row['id'])
                                            )
                                            st.error('Too many wrong OTP attempts. Recovery temporarily locked.')
                                        else:
                                            run_write(
                                                'UPDATE reset_messages SET attempts = ? WHERE id = ?',
                                                (attempts, otp_row['id'])
                                            )
                                            st.error(f'Invalid OTP. Attempts left: {OTP_MAX_ATTEMPTS - attempts}')
                                    else:
                                        run_write(
                                            'UPDATE users SET password_hash = ? WHERE id = ?',
                                            (generate_password_hash(new_password), user['id']),
                                        )
                                        run_write("DELETE FROM reset_messages WHERE user_id = ? AND purpose = 'password_reset'", (user['id'],))
                                        st.success('Password reset successful. Please login now.')
        return

    _, center_col, _ = st.columns([1.1, 2.2, 1.1])
    with center_col:
        st.markdown('<div class="back-note">Navigation</div>', unsafe_allow_html=True)
        if st.button('Back to Welcome', use_container_width=True):
            st.session_state.auth_view = 'landing'
            st.rerun()

        st.markdown('<div class="soft-card">', unsafe_allow_html=True)
        st.subheader('Register')
        with st.form('register_form'):
            name = st.text_input('Name')
            email = st.text_input('Email')
            phone = st.text_input('Registered Number')
            security_question = st.selectbox('Choose Security Question', SECURITY_QUESTIONS)
            security_answer = st.text_input('Security Answer')
            password = st.text_input('Password', type='password')
            confirm = st.text_input('Confirm Password', type='password')
            submitted = st.form_submit_button('Register')
        st.markdown('</div>', unsafe_allow_html=True)

        if submitted:
            if not all([name, email, phone, security_question, security_answer, password, confirm]):
                st.error('Please fill all fields')
            elif password != confirm:
                st.error('Passwords do not match')
            elif len(password) < 6:
                st.error('Password must be at least 6 characters')
            else:
                try:
                    run_write(
                        'INSERT INTO users (name, email, phone, password_hash, security_question, security_answer_hash, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)',
                        (
                            name.strip(),
                            email.strip().lower(),
                            phone.strip(),
                            generate_password_hash(password),
                            security_question,
                            generate_password_hash(security_answer.strip().lower()),
                            datetime.now().isoformat(),
                        ),
                    )
                    export_users_to_excel()
                    st.success('Registration successful. Please login.')
                    st.session_state.auth_view = 'login'
                except Exception as exc:
                    if 'UNIQUE' in str(exc).upper() or 'DUPLICATE' in str(exc).upper():
                        st.error('Email already exists')
                    else:
                        st.error(f'Registration failed: {exc}')


def home_page():
    st.markdown(
        """
        <div class="hero-card">
            <h2 style="margin:0;">UPI Fraud Detection Using Machine Learning</h2>
            <p style="margin:8px 0 0 0;">Real-time protection with smart risk checks and secure payment flow.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button('Go to Transaction Page'):
        st.session_state.page = 'Transaction'
        st.rerun()

    st.markdown('### Our Mission & Vision')
    st.markdown(
        """
        <div class="soft-card">
            <p><b>Our Mission:</b> To develop a reliable and intelligent web-based system that detects fraudulent UPI transactions in real time using machine learning, ensuring secure digital payments while providing a smooth and trustworthy experience for users.</p>
            <p style="margin-bottom:0;"><b>Our Vision:</b> To be the leading global platform for technological insights, driving progress and creating a future where technology serves humanity's greatest needs.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('### Risk Levels')
    st.markdown(
        """
        <div class="soft-card risk-low"><b>Low Risk:</b> Safe UPI transactions are approved instantly using intelligent machine learning checks, ensuring fast and smooth payments without any user interruption.</div>
        <div class="soft-card risk-medium"><b>Medium Risk:</b> Suspicious transactions trigger instant alerts and user confirmation to verify authenticity while minimizing inconvenience.</div>
        <div class="soft-card risk-high"><b>High Risk:</b> High-risk transactions are immediately blocked and secured using advanced verification methods to prevent fraud and protect user funds.</div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('### Feedback')
    with st.form('feedback_form'):
        name = st.text_input('Your Name')
        email = st.text_input('Your Email')
        message = st.text_area('Your Feedback')
        submit = st.form_submit_button('Submit Feedback')

    if submit:
        if not all([name, email, message]):
            st.error('Please complete all feedback fields.')
        else:
            run_write(
                'INSERT INTO feedback (name, email, message, created_at) VALUES (?, ?, ?, ?)',
                (name.strip(), email.strip(), message.strip(), datetime.now().isoformat()),
            )
            st.success('Thanks for your feedback!')


def transaction_page():
    st.markdown(
        """
        <div class="hero-card">
            <h2 style="margin:0;">Transaction Risk Check</h2>
            <p style="margin:8px 0 0 0;">Amount-based risk policy with OTP confirmation for medium-risk transactions.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption('Risk logic: Low <= 15,000 | Medium 15,001-50,000 | High 50,001-99,999')
    model_bundle = load_model_bundle()

    current_hour = datetime.now().hour
    with st.form('risk_form'):
        c1, c2 = st.columns(2)
        with c1:
            transaction_amount = st.number_input('Transaction Amount', min_value=0.0, value=1000.0, step=100.0)
            beneficiary_name = st.text_input('Beneficiary Name', value='')
            transaction_type = st.selectbox('Transaction Type', ['P2P', 'P2M', 'Bill Payment', 'Recharge', 'Merchant'])
            device_used = st.selectbox('Device Used', ['Android', 'iOS', 'Web'])
            number_of_transactions_last_24h = st.number_input('Transactions in Last 24H', min_value=0, value=3, step=1)

        with c2:
            time_of_transaction = st.number_input('Time of Transaction (Hour 0-23)', min_value=0, max_value=23, value=current_hour, step=1)
            location = st.text_input('Location', value='Chennai')
            payment_method = st.selectbox('Payment Method', ['UPI', 'Card', 'Wallet', 'NetBanking'])
            account_age = st.number_input('Account Age (months)', min_value=0.0, value=12.0, step=1.0)
            payment_gateway = st.selectbox('Payment Gateway', ['GooglePay', 'PhonePe', 'Paytm', 'BHIM', 'Unknown'])
            merchant_category = st.selectbox('Merchant Category', ['Grocery', 'Food', 'Travel', 'Utilities', 'Shopping', 'Other'])

        check = st.form_submit_button('Check Risk')

    if check:
        input_data = {
            'transaction_amount': transaction_amount,
            'transaction_type': transaction_type,
            'time_of_transaction': time_of_transaction,
            'device_used': device_used,
            'location': location,
            'previous_fraudulent_transactions': 0,
            'number_of_transactions_last_24h': number_of_transactions_last_24h,
            'payment_method': payment_method,
            'account_age': account_age,
            'payment_gateway': payment_gateway,
            'merchant_category': merchant_category,
        }

        if model_bundle is not None:
            try:
                model_score = get_fraud_probability(model_bundle, input_data)
                model_score = max(0.0, min(1.0, model_score))
                st.write(f'Model Risk Score: **{model_score * 100:.2f}%**')
            except Exception as exc:
                st.warning(f'Model score unavailable ({exc}). Rule-based decision still applied.')

        level, action = amount_risk_band(transaction_amount)
        st.subheader(f'Risk Level: {level}')
        st.write(f'System Action: **{action}**')

        if level == 'Low Risk':
            st.success('Transaction is possible. Amount is below 15,000 and approved instantly.')
            st.info('Tip: Verify beneficiary name once before final transfer.')

        elif level == 'Medium Risk':
            otp_code = generate_otp()
            user = st.session_state.user

            sent_ok, err = send_otp_email(
                user['email'],
                user['name'],
                otp_code,
                subject='FraudShield Transaction OTP'
            )
            if sent_ok:
                st.success(f'Transaction OTP sent to {mask_email(user["email"])}')
            else:
                st.error(f'Could not send OTP email: {err}')

            if sent_ok:
                st.session_state.pending_medium_txn = {
                    'amount': transaction_amount,
                    'beneficiary_name': beneficiary_name.strip() or 'Beneficiary',
                    'created_at': datetime.now().isoformat()
                }
                st.session_state.pending_txn_otp = otp_code
                st.session_state.pending_txn_otp_created_at = datetime.now().isoformat()
                st.session_state.pending_txn_otp_attempts = 0
                st.session_state.pending_txn_otp_resend_after = (
                    datetime.now() + timedelta(seconds=OTP_RESEND_COOLDOWN_SECONDS)
                ).isoformat()
                st.info(f'Enter OTP below to confirm this medium-risk transaction. OTP valid for {OTP_EXPIRY_MINUTES} minutes.')

        elif level == 'High Risk':
            person_name = beneficiary_name.strip() or 'this person'
            st.warning(
                f'Notification Alert: Be alert and think again before transferring this amount to {person_name}.'
            )
            st.warning('Recommended: Verify via call, check recent payment history, and retry after a short pause.')
        else:
            st.error('Very High Risk: Transaction is blocked temporarily and requires manual review.')
            st.error('Additional safety idea: split payment after verification and use a trusted contact method.')

    if st.session_state.pending_medium_txn:
        st.markdown('---')
        st.subheader('Medium Risk Confirmation')
        pending = st.session_state.pending_medium_txn
        st.write(
            f"Pending transfer: **{pending['amount']:.2f}** to **{pending['beneficiary_name']}** "
            f"via **Email OTP**"
        )

        otp_created = parse_dt(st.session_state.get('pending_txn_otp_created_at'))
        if otp_created:
            remaining = int((otp_created + timedelta(minutes=OTP_EXPIRY_MINUTES) - datetime.now()).total_seconds())
            if remaining > 0:
                st.caption(f'OTP expires in {remaining} seconds')
            else:
                st.warning('OTP expired. Please resend OTP.')

        resend_allowed_at = parse_dt(st.session_state.get('pending_txn_otp_resend_after'))
        if resend_allowed_at and datetime.now() >= resend_allowed_at:
            if st.button('Resend OTP', key='resend_txn_otp'):
                user = st.session_state.user
                new_otp = generate_otp()
                sent_ok, err = send_otp_email(user['email'], user['name'], new_otp, subject='FraudShield Transaction OTP')
                if sent_ok:
                    st.session_state.pending_txn_otp = new_otp
                    st.session_state.pending_txn_otp_created_at = datetime.now().isoformat()
                    st.session_state.pending_txn_otp_attempts = 0
                    st.session_state.pending_txn_otp_resend_after = (
                        datetime.now() + timedelta(seconds=OTP_RESEND_COOLDOWN_SECONDS)
                    ).isoformat()
                    st.success('New OTP sent to your registered email.')
                else:
                    st.error(f'Could not resend OTP: {err}')
        elif resend_allowed_at:
            wait_sec = int((resend_allowed_at - datetime.now()).total_seconds())
            if wait_sec > 0:
                st.caption(f'Resend available in {wait_sec} seconds')

        with st.form('verify_txn_otp_form'):
            entered_otp = st.text_input('Enter 6-digit OTP', max_chars=6)
            verify = st.form_submit_button('Verify OTP and Proceed')

        if verify:
            otp_created_at = parse_dt(st.session_state.get('pending_txn_otp_created_at'))
            if otp_created_at and datetime.now() > (otp_created_at + timedelta(minutes=OTP_EXPIRY_MINUTES)):
                st.error('OTP expired. Please resend OTP and try again.')
            elif st.session_state.get('pending_txn_otp_attempts', 0) >= OTP_MAX_ATTEMPTS:
                st.error('Maximum OTP attempts reached. Start verification again.')
            elif entered_otp.strip() == st.session_state.pending_txn_otp:
                st.success('OTP verified. Transaction is possible and confirmed.')
                st.session_state.pending_medium_txn = None
                st.session_state.pending_txn_otp = None
                st.session_state.pending_txn_otp_created_at = None
                st.session_state.pending_txn_otp_attempts = 0
                st.session_state.pending_txn_otp_resend_after = None
            else:
                st.session_state.pending_txn_otp_attempts = st.session_state.get('pending_txn_otp_attempts', 0) + 1
                attempts_left = OTP_MAX_ATTEMPTS - st.session_state.pending_txn_otp_attempts
                if attempts_left <= 0:
                    st.error('Invalid OTP. Maximum attempts reached. Please restart medium-risk verification.')
                    st.session_state.pending_medium_txn = None
                    st.session_state.pending_txn_otp = None
                    st.session_state.pending_txn_otp_created_at = None
                    st.session_state.pending_txn_otp_attempts = 0
                    st.session_state.pending_txn_otp_resend_after = None
                else:
                    st.error(f'Invalid OTP. Attempts left: {attempts_left}')


def testcases_page():
    st.markdown(
        """
        <div class="hero-card">
            <h2 style="margin:0;">Test Cases and Outputs</h2>
            <p style="margin:8px 0 0 0;">Presentation-ready model metrics and testcase execution outputs.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    model_bundle = load_model_bundle()
    if model_bundle is None:
        st.error('Model bundle not found. Test outputs require the model file.')
        return

    metrics = None
    if model_bundle['format'] == 'pipeline_features':
        model_path = next((p for p in MODEL_CANDIDATES if p.exists()), None)
        if model_path:
            try:
                with open(model_path, 'rb') as f:
                    raw = pickle.load(f)
                metrics = raw.get('performance_metrics')
            except Exception:
                metrics = None

    if metrics:
        st.subheader('Model Performance Metrics')
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric('Accuracy', f"{metrics.get('Accuracy', 0)*100:.2f}%")
        c2.metric('Precision', f"{metrics.get('Precision', 0)*100:.2f}%")
        c3.metric('Recall', f"{metrics.get('Recall', 0)*100:.2f}%")
        c4.metric('F1 Score', f"{metrics.get('F1_Score', 0)*100:.2f}%")
        c5.metric('ROC-AUC', f"{metrics.get('ROC_AUC', 0)*100:.2f}%")

    st.subheader('Testcase Execution Output')
    table = build_testcase_output_table(model_bundle)
    st.dataframe(table, use_container_width=True)


def main_app():
    st.sidebar.title('FraudShield')
    st.sidebar.write(f"Logged in as: {st.session_state.user['name']}")

    pages = ['Home', 'Transaction', 'Test Cases']
    selected = st.sidebar.radio('Navigate', pages, index=pages.index(st.session_state.page))
    st.session_state.page = selected

    if st.sidebar.button('Logout'):
        st.session_state.authenticated = False
        st.session_state.user = None
        st.session_state.page = 'Home'
        st.rerun()

    if selected == 'Home':
        home_page()
    elif selected == 'Transaction':
        transaction_page()
    else:
        testcases_page()


def run():
    apply_custom_theme()
    init_db()
    export_users_to_excel()
    init_session()

    if not st.session_state.authenticated:
        auth_ui()
        return

    main_app()


if __name__ == '__main__':
    run()

