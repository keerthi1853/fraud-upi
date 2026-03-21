# UPI Shield (Streamlit)

## Run locally

```powershell
cd C:\Users\techr\OneDrive\Desktop\UPI\Fraud
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run streamlit_app.py
```

## SMTP (Forgot Password OTP)

Set these before run/deploy:

```powershell
$env:SMTP_HOST="smtp.gmail.com"
$env:SMTP_PORT="587"
$env:SMTP_USER="your-email@gmail.com"
$env:SMTP_PASS="your-16-char-app-password"
$env:SMTP_FROM="your-email@gmail.com"
```

## Deploy on Render

1. Push this `Fraud` folder to GitHub as a repo.
2. Ensure `UPI_Fraud_Detection_Model_Fixed.pkl` exists in repo root (`Fraud/UPI_Fraud_Detection_Model_Fixed.pkl`).
3. In Render: New + > Web Service > connect repo.
4. Render auto-uses `render.yaml`.
5. Set secret env vars in Render dashboard:
   - `SMTP_USER`
   - `SMTP_PASS`
   - `SMTP_FROM`
6. Deploy.

## Notes

- Registered users are exported to `registered_users.xlsx` on each run/registration.
- Do not commit `.streamlit/secrets.toml` or real app passwords.
