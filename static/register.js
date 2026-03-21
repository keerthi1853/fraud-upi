const registerForm = document.getElementById("register-form");
const messageBox = document.getElementById("message");

function showMessage(text, type) {
  messageBox.textContent = text;
  messageBox.className = `message ${type}`;
}

registerForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  const name = document.getElementById("name").value.trim();
  const email = document.getElementById("email").value.trim();
  const password = document.getElementById("password").value;
  const confirmPassword = document.getElementById("confirm-password").value;

  const response = await fetch("/api/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name,
      email,
      password,
      confirm_password: confirmPassword,
    }),
  });

  const data = await response.json();
  if (response.ok && data.ok) {
    showMessage("Registration successful. Redirecting...", "success");
    setTimeout(() => {
      window.location.href = data.redirect || "/home";
    }, 700);
    return;
  }

  showMessage(data.message || "Registration failed", "error");
});
