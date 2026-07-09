const API = "/api";
let rolesCache = null;
let expandedUserId = null;

async function api(path, options = {}) {
  const res = await fetch(API + path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch (err) {
      // response had no JSON body; keep statusText
    }
    throw new Error(`${res.status}: ${detail}`);
  }
  if (res.status === 204) return null;
  return res.json();
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str ?? "";
  return div.innerHTML;
}

function showToast(message, isError = false) {
  const toast = document.getElementById("toast");
  toast.textContent = message;
  toast.style.background = isError ? "#b91c1c" : "#1a1d23";
  toast.classList.add("visible");
  clearTimeout(showToast._timer);
  showToast._timer = setTimeout(() => toast.classList.remove("visible"), 3000);
}

async function loadRoles() {
  if (!rolesCache) {
    rolesCache = await api("/roles");
  }
  return rolesCache;
}

async function loadUsers() {
  const tbody = document.getElementById("users-tbody");
  try {
    const users = await api("/users");
    if (users.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" class="empty-state">No users yet. Ingest a profile to get started.</td></tr>`;
      return;
    }
    await loadRoles();
    tbody.innerHTML = users.map(renderUserRow).join("");
    attachRowHandlers();
    if (expandedUserId) {
      const row = document.getElementById(`detail-${expandedUserId}`);
      if (row) {
        row.hidden = false;
        renderDetail(expandedUserId);
      }
    }
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="6" class="empty-state">Failed to load users: ${escapeHtml(err.message)}</td></tr>`;
  }
}

function bandBadge(band) {
  if (!band) return "";
  return `<span class="badge band-${band}">${band.replace("_", " ")}</span>`;
}

function renderUserRow(user) {
  const role = user.effective_role;
  const roleLabel = role.role_name ? escapeHtml(role.role_name) : `<span class="muted">unassigned</span>`;
  const confidence = role.confidence != null ? role.confidence.toFixed(2) : "—";
  const sourceBadge =
    `<span class="badge source-${role.source}">${role.source}</span>` +
    (user.override_pinned ? `<span class="badge pinned">pinned</span>` : "");
  const userId = escapeHtml(user.user_id);
  return `
    <tr class="user-row" data-user-id="${userId}">
      <td><strong>${userId}</strong><br/><span class="muted">${escapeHtml(user.display_name || "")}</span></td>
      <td>${escapeHtml(user.title || "—")}<br/><span class="muted">${escapeHtml(user.department || "—")}</span></td>
      <td>${roleLabel}<br/>${sourceBadge}</td>
      <td>${confidence} ${bandBadge(role.band)}</td>
      <td><button class="details-btn" data-user-id="${userId}">Details</button></td>
      <td class="actions-cell">
        <button class="override-btn" data-user-id="${userId}">Override</button>
        <button class="reset-btn" data-user-id="${userId}" ${user.override_active ? "" : "disabled"}>Reset</button>
        <button class="reinfer-btn" data-user-id="${userId}">Re-infer</button>
      </td>
    </tr>
    <tr class="detail-row" id="detail-${userId}" hidden>
      <td colspan="6"><div class="detail-content" id="detail-content-${userId}">Loading&hellip;</div></td>
    </tr>
  `;
}

function attachRowHandlers() {
  document.querySelectorAll(".details-btn").forEach((btn) => btn.addEventListener("click", onToggleDetails));
  document.querySelectorAll(".override-btn").forEach((btn) => btn.addEventListener("click", onOpenOverrideForm));
  document.querySelectorAll(".reset-btn").forEach((btn) => btn.addEventListener("click", onReset));
  document.querySelectorAll(".reinfer-btn").forEach((btn) => btn.addEventListener("click", onReinfer));
}

async function onToggleDetails(e) {
  const userId = e.target.dataset.userId;
  const row = document.getElementById(`detail-${userId}`);
  if (!row.hidden) {
    row.hidden = true;
    if (expandedUserId === userId) expandedUserId = null;
    return;
  }
  document.querySelectorAll(".detail-row").forEach((r) => (r.hidden = true));
  row.hidden = false;
  expandedUserId = userId;
  await renderDetail(userId);
}

async function renderDetail(userId) {
  const container = document.getElementById(`detail-content-${userId}`);
  if (!container) return;
  container.innerHTML = "Loading&hellip;";
  try {
    const inference = await api(`/users/${encodeURIComponent(userId)}/inference`);
    const signalsHtml = inference.signals.map((s) => `<li>${escapeHtml(s)}</li>`).join("") || `<li class="muted">none</li>`;
    const altsHtml =
      inference.alternative_roles
        .map((a) => `<li><strong>${escapeHtml(a.role)}</strong> (${a.confidence.toFixed(2)}) — ${escapeHtml(a.why_lost || "")}</li>`)
        .join("") || `<li class="muted">none</li>`;
    const negHtml = inference.negative_evidence.map((s) => `<li>${escapeHtml(s)}</li>`).join("") || `<li class="muted">none</li>`;
    const missingHtml = inference.missing_information.map((s) => `<li>${escapeHtml(s)}</li>`).join("") || `<li class="muted">none</li>`;

    container.innerHTML = `
      <div class="human-readable">${escapeHtml(inference.explanation)}</div>
      <div>
        <h4>Signals used</h4>
        <ul>${signalsHtml}</ul>
      </div>
      <div>
        <h4>Alternatives considered</h4>
        <ul>${altsHtml}</ul>
      </div>
      <div>
        <h4>Negative evidence</h4>
        <ul>${negHtml}</ul>
      </div>
      <div>
        <h4>Missing information</h4>
        <ul>${missingHtml}</ul>
      </div>
      <div class="muted" style="grid-column:1/-1; font-size:12px;">
        run #${inference.run_id} &middot; engine ${escapeHtml(inference.engine_version)} &middot;
        catalog v${inference.catalog_version} &middot;
        llm_used=${inference.llm_used} &middot; llm_degraded=${inference.llm_degraded}
      </div>
    `;
  } catch (err) {
    container.innerHTML = `<span class="muted">No inference yet (${escapeHtml(err.message)}).</span>`;
  }
}

async function onOpenOverrideForm(e) {
  const userId = e.target.dataset.userId;
  const row = document.getElementById(`detail-${userId}`);
  document.querySelectorAll(".detail-row").forEach((r) => {
    if (r.id !== `detail-${userId}`) r.hidden = true;
  });
  row.hidden = false;
  expandedUserId = userId;
  const container = document.getElementById(`detail-content-${userId}`);
  const roles = await loadRoles();
  const options = roles.map((r) => `<option value="${escapeHtml(r.role_id)}">${escapeHtml(r.role_name)}</option>`).join("");
  container.innerHTML = `
    <form class="override-form" data-user-id="${escapeHtml(userId)}">
      <h4>Set override</h4>
      <div class="field-row">
        <div class="field">
          <label>Role</label>
          <select name="role_id">${options}</select>
        </div>
        <div class="field">
          <label>Reason</label>
          <input type="text" name="reason" placeholder="Why is this being overridden?" />
        </div>
      </div>
      <div class="field">
        <label><input type="checkbox" name="pinned" checked /> Pinned (survives bulk reprocess)</label>
      </div>
      <button type="submit" class="primary">Save override</button>
      <button type="button" class="cancel-override-btn">Cancel</button>
    </form>
  `;
  container.querySelector("form").addEventListener("submit", onSubmitOverride);
  container.querySelector(".cancel-override-btn").addEventListener("click", () => renderDetail(userId));
}

async function onSubmitOverride(e) {
  e.preventDefault();
  const form = e.target;
  const userId = form.dataset.userId;
  const roleId = form.role_id.value;
  const reason = form.reason.value;
  const pinned = form.pinned.checked;
  try {
    await api(`/users/${encodeURIComponent(userId)}/override`, {
      method: "PATCH",
      body: JSON.stringify({ role_id: roleId, reason: reason || null, pinned, created_by: "admin" }),
    });
    showToast(`Override set for ${userId}`);
    await loadUsers();
  } catch (err) {
    showToast(err.message, true);
  }
}

async function onReset(e) {
  const userId = e.target.dataset.userId;
  try {
    await api(`/users/${encodeURIComponent(userId)}/override`, { method: "DELETE" });
    showToast(`Override reset for ${userId}`);
    await loadUsers();
  } catch (err) {
    showToast(err.message, true);
  }
}

async function onReinfer(e) {
  const userId = e.target.dataset.userId;
  try {
    await api("/infer", { method: "POST", body: JSON.stringify({ user_id: userId }) });
    showToast(`Re-inferred ${userId}`);
    await loadUsers();
  } catch (err) {
    showToast(err.message, true);
  }
}

async function onSubmitIngest(e) {
  e.preventDefault();
  const splitList = (value) =>
    value
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
  const payload = {
    user_id: document.getElementById("ingest-user-id").value.trim(),
    display_name: document.getElementById("ingest-display-name").value.trim() || null,
    title: document.getElementById("ingest-title").value.trim() || null,
    department: document.getElementById("ingest-department").value.trim() || null,
    manager_title: document.getElementById("ingest-manager-title").value.trim() || null,
    location: document.getElementById("ingest-location").value.trim() || null,
    notes: document.getElementById("ingest-notes").value.trim() || null,
    skills: splitList(document.getElementById("ingest-skills").value),
    groups: splitList(document.getElementById("ingest-groups").value),
  };
  if (!payload.user_id) {
    showToast("user_id is required", true);
    return;
  }
  try {
    await api("/profiles", { method: "POST", body: JSON.stringify(payload) });
    showToast(`Ingested ${payload.user_id}`);
    document.getElementById("ingest-form").reset();
    await loadUsers();
  } catch (err) {
    showToast(err.message, true);
  }
}

async function onReprocessAll() {
  try {
    const result = await api("/reprocess", {
      method: "POST",
      body: JSON.stringify({ scope: "all", respect_pins: true }),
    });
    showToast(`Reprocessed ${result.processed_count}, skipped ${result.skipped_pinned_count} pinned`);
    await loadUsers();
  } catch (err) {
    showToast(err.message, true);
  }
}

document.getElementById("toggle-ingest-btn").addEventListener("click", () => {
  const panel = document.getElementById("ingest-panel");
  panel.hidden = !panel.hidden;
});
document.getElementById("ingest-form").addEventListener("submit", onSubmitIngest);
document.getElementById("reprocess-btn").addEventListener("click", onReprocessAll);

loadUsers();
