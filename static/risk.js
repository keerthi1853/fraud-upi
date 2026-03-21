const riskForm = document.getElementById("risk-form");
const resultBox = document.getElementById("risk-result");

function classForLevel(level) {
  if (level === "Low") return "risk-low";
  if (level === "Medium") return "risk-medium";
  if (level === "High") return "risk-high";
  return "risk-blocked";
}

riskForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const amount = Number(document.getElementById("amount").value);

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
});
