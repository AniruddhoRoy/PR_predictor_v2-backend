const state = { token: localStorage.getItem("pr_admin_token") };
const $ = (id) => document.getElementById(id);

function show(authed) {
  $("login-card").classList.toggle("hidden", authed);
  $("dashboard").classList.toggle("hidden", !authed);
  $("logout").classList.toggle("hidden", !authed);
}
async function api(path, options = {}) {
  const response = await fetch(`/admin/api/${path}`, { ...options, headers: { "Content-Type": "application/json", Authorization: `Bearer ${state.token}`, ...(options.headers || {}) } });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || "Request failed");
  return data;
}
function renderStats(stats) {
  $("stats").innerHTML = Object.entries({ Users: stats.users, Predictions: stats.predictions, Models: stats.models, Plans: stats.plans }).map(([name, value]) => `<div class="stat"><span>${name}</span><strong>${value}</strong></div>`).join("");
}
function renderUsers(users) {
  $("users").innerHTML = users.map(user => `<tr><td>${user.username}</td><td>${user.fullName}</td><td>${user.email}</td><td><select data-id="${user.userId}" class="role"><option ${user.role === "USER" ? "selected" : ""}>USER</option><option ${user.role === "ADMIN" ? "selected" : ""}>ADMIN</option></select></td><td><button class="small save-role" data-id="${user.userId}">Save</button></td></tr>`).join("");
  document.querySelectorAll(".save-role").forEach(button => button.onclick = async () => { const role = document.querySelector(`.role[data-id="${button.dataset.id}"]`).value; await api(`users/${button.dataset.id}/role`, { method: "PATCH", body: JSON.stringify({ role }) }); await load(); });
}
function renderPredictions(items) { $("predictions").innerHTML = items.map(item => `<tr><td>${item.username || "-"}</td><td>${item.predictionType}</td><td>${item.status}</td><td>${new Date(item.createdAt).toLocaleString()}</td></tr>`).join(""); }
async function load() { try { const [stats, users, predictions] = await Promise.all([api("stats"), api("users"), api("predictions")]); renderStats(stats); renderUsers(users); renderPredictions(predictions); } catch (error) { if (error.message.includes("token") || error.message.includes("Admin")) { state.token = null; localStorage.removeItem("pr_admin_token"); show(false); } else alert(error.message); } }
$("login-form").onsubmit = async (event) => { event.preventDefault(); $("login-error").textContent = ""; try { const response = await fetch("/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: $("username").value, password: $("password").value }) }); const data = await response.json(); if (!response.ok) throw new Error(data.detail || "Login failed"); if (data.user.role !== "ADMIN") throw new Error("This account is not an admin"); state.token = data.accessToken; localStorage.setItem("pr_admin_token", state.token); show(true); await load(); } catch (error) { $("login-error").textContent = error.message; } };
$("logout").onclick = () => { state.token = null; localStorage.removeItem("pr_admin_token"); show(false); };
$("refresh").onclick = load;
show(Boolean(state.token));
if (state.token) load();
