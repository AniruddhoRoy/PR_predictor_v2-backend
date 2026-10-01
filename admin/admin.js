const state = { token: localStorage.getItem("pr_admin_token") };
const $ = (id) => document.getElementById(id);

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[character]));
}
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
  $("users").innerHTML = users.map(user => `<tr><td>${escapeHtml(user.username)}</td><td>${escapeHtml(user.fullName)}</td><td>${escapeHtml(user.email)}</td><td><select data-id="${escapeHtml(user.userId)}" class="role"><option ${user.role === "USER" ? "selected" : ""}>USER</option><option ${user.role === "ADMIN" ? "selected" : ""}>ADMIN</option></select></td><td><button class="small save-role" data-id="${escapeHtml(user.userId)}" type="button">Save</button></td></tr>`).join("");
  document.querySelectorAll(".save-role").forEach(button => button.onclick = async () => { try { const role = document.querySelector(`.role[data-id="${button.dataset.id}"]`).value; await api(`users/${button.dataset.id}/role`, { method: "PATCH", body: JSON.stringify({ role }) }); await load(); } catch (error) { alert(error.message); } });
}
function renderPredictions(items) {
  $("predictions").innerHTML = items.map(item => `<tr><td>${escapeHtml(item.username || "-")}</td><td>${escapeHtml(item.predictionType)}</td><td>${escapeHtml(item.status)}</td><td>${item.createdAt ? escapeHtml(new Date(item.createdAt).toLocaleString()) : "-"}</td></tr>`).join("");
}
function renderModels(items) {
  $("models").innerHTML = items.map(model => `<tr><td>${escapeHtml(model.code)}</td><td>${escapeHtml(model.name)}</td><td>${escapeHtml(model.taskType)}</td><td>${escapeHtml(model.version)}</td><td>${escapeHtml(model.provider || "-")}</td><td><span class="status ${model.active ? "active" : "inactive"}">${model.active ? "Active" : "Inactive"}</span></td><td><button class="small edit-model" data-id="${escapeHtml(model.modelId)}" type="button">Edit</button> <button class="small ${model.active ? "danger" : "secondary"} toggle-model" data-id="${escapeHtml(model.modelId)}" data-active="${model.active}" type="button">${model.active ? "Delete" : "Activate"}</button></td></tr>`).join("");
  document.querySelectorAll(".edit-model").forEach(button => button.onclick = () => { const model = items.find(item => item.modelId === button.dataset.id); if (model) openModelForm(model); });
  document.querySelectorAll(".toggle-model").forEach(button => button.onclick = async () => { const active = button.dataset.active === "true"; try { if (active) { if (!confirm("Deactivate this model? Existing prediction history will remain available.")) return; await api(`models/${button.dataset.id}`, { method: "DELETE" }); } else { await api(`models/${button.dataset.id}`, { method: "PATCH", body: JSON.stringify({ active: true }) }); } await load(); } catch (error) { alert(error.message); } });
}
async function load() {
  try {
    const [stats, users, predictions, models] = await Promise.all([api("stats"), api("users"), api("predictions"), api("models")]);
    renderStats(stats); renderUsers(users); renderPredictions(predictions); renderModels(models);
  } catch (error) {
    if (error.message.toLowerCase().includes("token") || error.message.includes("Admin")) { state.token = null; localStorage.removeItem("pr_admin_token"); show(false); }
    else alert(error.message);
  }
}
function resetModelForm() {
  $("model-form").reset(); $("model-id").value = ""; $("model-active").checked = true; $("model-error").textContent = ""; $("model-form").classList.add("hidden");
}
function openModelForm(model = null) {
  $("model-form").classList.remove("hidden"); $("model-error").textContent = "";
  $("model-id").value = model ? model.modelId : ""; $("model-code").value = model ? model.code : ""; $("model-name").value = model ? model.name : ""; $("model-task").value = model ? model.taskType : "BOTH"; $("model-version").value = model ? model.version : ""; $("model-provider").value = model ? (model.provider || "") : ""; $("model-description").value = model ? (model.description || "") : ""; $("model-active").checked = model ? model.active : true;
  $("model-code").focus();
}
$("model-form").onsubmit = async (event) => {
  event.preventDefault(); $("model-error").textContent = "";
  const id = $("model-id").value;
  const payload = { code: $("model-code").value, name: $("model-name").value, taskType: $("model-task").value, version: $("model-version").value, provider: $("model-provider").value || null, description: $("model-description").value || null, active: $("model-active").checked };
  try { await api(id ? `models/${id}` : "models", { method: id ? "PATCH" : "POST", body: JSON.stringify(payload) }); resetModelForm(); await load(); } catch (error) { $("model-error").textContent = error.message; }
};
$("new-model").onclick = () => openModelForm();
$("cancel-model").onclick = resetModelForm;
$("login-form").onsubmit = async (event) => { event.preventDefault(); $("login-error").textContent = ""; try { const response = await fetch("/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: $("username").value, password: $("password").value }) }); const data = await response.json(); if (!response.ok) throw new Error(data.detail || "Login failed"); if (data.user.role !== "ADMIN") throw new Error("This account is not an admin"); state.token = data.accessToken; localStorage.setItem("pr_admin_token", state.token); show(true); await load(); } catch (error) { $("login-error").textContent = error.message; } };
$("logout").onclick = () => { state.token = null; localStorage.removeItem("pr_admin_token"); show(false); };
$("refresh").onclick = load;
show(Boolean(state.token));
if (state.token) load();
