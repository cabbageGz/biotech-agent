const username = document.querySelector("#username");
const password = document.querySelector("#password");
const login = document.querySelector("#login");
const message = document.querySelector("#loginMessage");

async function doLogin() {
  message.textContent = "";
  const response = await fetch("/api/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: username.value, password: password.value }),
  });
  const payload = await response.json();
  if (!response.ok) {
    message.textContent = payload.error || "登录失败";
    return;
  }
  window.location.href = "/";
}

login.addEventListener("click", doLogin);
password.addEventListener("keydown", (event) => {
  if (event.key === "Enter") doLogin();
});
