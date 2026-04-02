const riskForm = document.getElementById("risk-form");
const resultBox = document.getElementById("risk-result");
const otpForm = document.getElementById("otp-form");
const otpInput = document.getElementById("otp-input");
const otpAlert = document.getElementById("otp-alert");
const stepButtons = document.querySelectorAll(".step-btn");
let pendingAmount = null;

function classForLevel(level) {
  if (level === "Low") return "risk-low";
  if (level === "Medium") return "risk-medium";
  if (level === "High") return "risk-high";
  return "risk-blocked";
}

function showAlert(message, type) {
  otpAlert.textContent = message;
  otpAlert.className = `alert-block ${type}`;
  otpAlert.classList.remove("hidden");
}

function hideOtpFlow() {
  otpForm.classList.add("hidden");
  otpInput.value = "";
}

stepButtons.forEach((button) => {
  button.addEventListener("click", () => {
    const targetId = button.dataset.target;
    const step = Number(button.dataset.step || 1);
    const input = document.getElementById(targetId);
    if (!input) return;

    const current = Number(input.value || 0);
    const min = input.min !== "" ? Number(input.min) : Number.NEGATIVE_INFINITY;
    const max = input.max !== "" ? Number(input.max) : Number.POSITIVE_INFINITY;
    const next = Math.min(max, Math.max(min, current + step));
    input.value = String(next);
  });
});

riskForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const amount = Number(document.getElementById("amount").value);
  pendingAmount = amount;
  hideOtpFlow();
  otpAlert.classList.add("hidden");

  const response = await fetch("/api/risk-level", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ amount }),
  });
  const data = await response.json();

  if (!response.ok || !data.ok) {
    resultBox.className = "result";
    resultBox.innerHTML = `<strong>Error:</strong> ${data.message || "Unable to evaluate amount."}`;
    resultBox.classList.remove("hidden");
    showAlert(data.message || "Risk check failed.", "alert-error");
    return;
  }

  resultBox.className = `result ${classForLevel(data.level)}`;
  resultBox.innerHTML = `
    <p><strong>Entered Amount:</strong> INR ${amount.toLocaleString("en-IN")}</p>
    <p><strong>Risk Level:</strong> ${data.level}</p>
    <p><strong>Decision:</strong> ${data.message}</p>
    <p><strong>Transfer Allowed:</strong> ${data.allowed ? "Yes" : "No"}</p>
  `;
  resultBox.classList.remove("hidden");

  if (data.otp_required) {
    otpForm.classList.remove("hidden");
    const deliveryNote = data.delivery_note ? ` ${data.delivery_note}` : "";
    showAlert(
      `${data.notification} OTP sent to ${data.email_hint}.${deliveryNote}`,
      data.level === "High" ? "alert-high" : "alert-medium"
    );
    return;
  }

  if (data.level === "Low") {
    showAlert("Low risk transaction. OTP verification is not required.", "alert-success");
    return;
  }

  showAlert("Transaction is blocked as per risk policy.", "alert-error");
});

otpForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const otp = otpInput.value.trim();

  const response = await fetch("/api/verify-otp", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ otp, amount: pendingAmount }),
  });
  const data = await response.json();

  if (!response.ok || !data.ok) {
    showAlert(data.message || "OTP verification failed.", "alert-error");
    return;
  }

  hideOtpFlow();
  resultBox.className = `result ${classForLevel(data.verified.level)}`;
  resultBox.innerHTML = `
    <p><strong>Entered Amount:</strong> INR ${Number(data.verified.amount).toLocaleString("en-IN")}</p>
    <p><strong>Risk Level:</strong> ${data.verified.level}</p>
    <p><strong>Transfer Allowed:</strong> Yes</p>
    <p><strong>Verified At:</strong> ${data.verified.verified_at}</p>
  `;
  showAlert("OTP verified. Transaction is approved.", "alert-success");
});
