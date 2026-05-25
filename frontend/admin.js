const users = document.querySelector("#users");
const newUsername = document.querySelector("#newUsername");
const newPassword = document.querySelector("#newPassword");
const newRole = document.querySelector("#newRole");
const createUser = document.querySelector("#createUser");
const message = document.querySelector("#adminMessage");
let currentUser = null;

async function api(path, options = {}) {
  const response = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "请求失败");
  return payload;
}

async function loadUsers() {
  const [mePayload, usersPayload] = await Promise.all([api("/api/me"), api("/api/admin/users")]);
  currentUser = mePayload.user;
  users.replaceChildren();
  const header = document.createElement("div");
  header.className = "user-row user-row-head";
  header.innerHTML = "<span>用户</span><span>角色</span><span>热点条目</span><span>图片次数</span><span>操作</span>";
  users.appendChild(header);
  for (const user of usersPayload.users || []) {
    const row = document.createElement("div");
    row.className = "user-row";
    const name = document.createElement("strong");
    name.textContent = user.username;
    const role = document.createElement("span");
    role.textContent = user.role;
    const hotspots = document.createElement("span");
    hotspots.textContent = `热点：${user.generated_hotspots}`;
    const images = document.createElement("span");
    images.textContent = `图片：${user.generated_images}`;
    const action = document.createElement("button");
    action.className = "danger small-button";
    action.type = "button";
    action.textContent = user.id === currentUser.id ? "当前用户" : "删除";
    action.disabled = user.id === currentUser.id;
    action.addEventListener("click", () => deleteUser(user));
    const reset = document.createElement("button");
    reset.className = "secondary small-button";
    reset.type = "button";
    reset.textContent = "重置密码";
    reset.addEventListener("click", () => resetPassword(user));
    const actions = document.createElement("div");
    actions.className = "user-actions";
    actions.append(reset, action);
    row.append(name, role, hotspots, images, actions);
    users.appendChild(row);
  }
}

async function resetPassword(user) {
  const nextPassword = window.prompt(`输入用户「${user.username}」的新密码（至少 6 位）`);
  if (!nextPassword) return;
  message.textContent = "";
  try {
    await api(`/api/admin/users/${encodeURIComponent(user.id)}/password`, {
      method: "POST",
      body: JSON.stringify({ new_password: nextPassword }),
    });
    message.textContent = "密码已重置，该用户其他登录会话已失效。";
  } catch (error) {
    message.textContent = error.message;
  }
}

async function addUser() {
  message.textContent = "";
  try {
    await api("/api/admin/users", {
      method: "POST",
      body: JSON.stringify({ username: newUsername.value, password: newPassword.value, role: newRole.value }),
    });
    newUsername.value = "";
    newPassword.value = "";
    await loadUsers();
  } catch (error) {
    message.textContent = error.message;
  }
}

async function deleteUser(user) {
  if (!window.confirm(`确认删除用户「${user.username}」？该用户会被强制退出登录。`)) return;
  message.textContent = "";
  try {
    await api(`/api/admin/users/${encodeURIComponent(user.id)}`, { method: "DELETE" });
    await loadUsers();
  } catch (error) {
    message.textContent = error.message;
  }
}

function escapeHtml(value) {
  return String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
}

createUser.addEventListener("click", addUser);
loadUsers().catch((error) => {
  message.textContent = error.message;
});
