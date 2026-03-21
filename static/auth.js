const messageBox = document.getElementById("message");

function showMessage(text, type) {
  messageBox.textContent = text;
  messageBox.className = `message ${type}`;
}

document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById(btn.dataset.tab).classList.add("active");
    showMessage("", "");
  });
});

document.getElementById("login-tab").addEventListener("submit", async (e) => {
  e.preventDefault();
  const username = document.getElementById("login-username").value.trim();
  const password = document.getElementById("login-password").value;

  const res = await fetch("/api/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  const data = await res.json();

  if (res.ok && data.ok) {
    window.location.href = "/dashboard";
  } else {
    showMessage(data.message || "Login failed", "error");
  }
});

document.getElementById("register-tab").addEventListener("submit", async (e) => {
  e.preventDefault();
  const username = document.getElementById("register-username").value.trim();
  const password = document.getElementById("register-password").value;
  const confirmPassword = document.getElementById("register-confirm-password").value;

  if (password !== confirmPassword) {
    showMessage("Passwords do not match", "error");
    return;
  }

  const res = await fetch("/api/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  const data = await res.json();
  showMessage(data.message || (res.ok ? "Success" : "Registration failed"), res.ok ? "success" : "error");
});

document.getElementById("forgot-tab").addEventListener("submit", async (e) => {
  e.preventDefault();
  const username = document.getElementById("forgot-username").value.trim();
  const newPassword = document.getElementById("forgot-password").value;
  const confirmPassword = document.getElementById("forgot-confirm-password").value;

  if (newPassword !== confirmPassword) {
    showMessage("Passwords do not match", "error");
    return;
  }

  const res = await fetch("/api/forgot-password", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, new_password: newPassword }),
  });
  const data = await res.json();
  showMessage(data.message || (res.ok ? "Success" : "Reset failed"), res.ok ? "success" : "error");
});
