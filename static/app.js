const riskForm = document.getElementById("risk-form");
const resultBox = document.getElementById("risk-result");
const logoutBtn = document.getElementById("logout-btn");

function classForLevel(level) {
  if (level === "Low") return "risk-low";
  if (level === "Medium") return "risk-medium";
  return "risk-high";
}

riskForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const payload = {
    amount: Number(document.getElementById("amount").value),
    transaction_frequency: Number(document.getElementById("transaction-frequency").value),
    transaction_type: document.getElementById("transaction-type").value,
    payment_gateway: document.getElementById("payment-gateway").value,
    merchant_category: document.getElementById("merchant-category").value,
    device_os: document.getElementById("device-os").value,
  };

  const res = await fetch("/api/risk-score", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();

  if (!res.ok || !data.ok) {
    resultBox.className = "result";
    resultBox.innerHTML = `<strong>Error:</strong> ${data.message || "Could not calculate risk."}`;
    resultBox.classList.remove("hidden");
    return;
  }

  const pct = (data.score * 100).toFixed(2);
  resultBox.className = `result ${classForLevel(data.level)}`;
  resultBox.innerHTML = `
    <p><strong>Risk Score:</strong> ${pct}%</p>
    <p><strong>Risk Level:</strong> ${data.level}</p>
    <p><strong>Recommended Action:</strong> ${data.recommended_action}</p>
    <p><strong>Scoring Mode:</strong> ${data.used_model ? "ML Model" : "Fallback Rule"}</p>
  `;
  resultBox.classList.remove("hidden");
});

logoutBtn.addEventListener("click", async () => {
  await fetch("/api/logout", { method: "POST" });
  window.location.href = "/login";
});
