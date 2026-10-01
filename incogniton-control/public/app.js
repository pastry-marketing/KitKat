import { cloudApi, getCloudSession, isCloudMode, signIn, signOut, signUp } from "./cloud-api.js";

const state = {
  connected: false,
  loading: true,
  profiles: [],
  displayLimit: 100,
  filter: "all",
  groupFilter: "all",
  search: "",
  menuFor: null,
  deleteTarget: null,
  deleteWorkflowTarget: null,
  workflows: [],
  runs: [],
  draftSteps: [],
  selectedWorkflow: null,
  currentUser: null,
  users: [],
  previewUsers: [],
  roles: {},
  manageableRoles: [],
  userSearch: "",
  editingUser: null,
  deleteUserTarget: null,
  activity: JSON.parse(sessionStorage.getItem("kitkat-activity") || "[]")
};

let runPollTimer = null;

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

const els = {
  connectionDot: $("#connectionDot"),
  connectionLabel: $("#connectionLabel"),
  connectionHint: $("#connectionHint"),
  offlineBanner: $("#offlineBanner"),
  totalCount: $("#totalCount"),
  runningCount: $("#runningCount"),
  groupCount: $("#groupCount"),
  profileTable: $("#profileTable"),
  mobileProfileList: $("#mobileProfileList"),
  loadingState: $("#loadingState"),
  emptyState: $("#emptyState"),
  emptyTitle: $("#emptyTitle"),
  emptyMessage: $("#emptyMessage"),
  searchInput: $("#searchInput"),
  groupFilterWrap: $("#groupFilterWrap"),
  groupFilterSelect: $("#groupFilterSelect"),
  profileModal: $("#profileModal"),
  profileForm: $("#profileForm"),
  createSubmit: $("#createSubmit"),
  confirmModal: $("#confirmModal"),
  confirmMessage: $("#confirmMessage"),
  confirmDelete: $("#confirmDelete"),
  settingsModal: $("#settingsModal"),
  automationModal: $("#automationModal"),
  automationForm: $("#automationForm"),
  stepBuilder: $("#stepBuilder"),
  workflowList: $("#workflowList"),
  runList: $("#runList"),
  runModal: $("#runModal"),
  runForm: $("#runForm"),
  runProfileSelect: $("#runProfileSelect"),
  userModal: $("#userModal"),
  userForm: $("#userForm"),
  userTable: $("#userTable"),
  mobileUserList: $("#mobileUserList"),
  userPreviewSelect: $("#userPreviewSelect"),
  toastRegion: $("#toastRegion"),
  activityList: $("#activityList")
};

const icons = {
  play: '<svg viewBox="0 0 24 24"><path d="m8 5 11 7-11 7z"/></svg>',
  stop: '<svg viewBox="0 0 24 24"><rect x="7" y="7" width="10" height="10" rx="1"/></svg>',
  more: '<svg viewBox="0 0 24 24"><circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/></svg>',
  clone: '<svg viewBox="0 0 24 24"><rect x="8" y="8" width="11" height="11" rx="2"/><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"/></svg>',
  trash: '<svg viewBox="0 0 24 24"><path d="M5 7h14M9 7V4h6v3M8 10v7M12 10v7M16 10v7M6 7l1 14h10l1-14"/></svg>',
  check: '<svg viewBox="0 0 24 24"><path d="m5 12 4 4L19 6"/></svg>',
  error: '<svg viewBox="0 0 24 24"><path d="m6 6 12 12M18 6 6 18"/></svg>'
};

const activeRunStatuses = new Set(["queued", "launching", "running"]);

function applyTheme(theme, { save = false } = {}) {
  const next = theme === "dark" ? "dark" : "light";
  document.documentElement.classList.add("theme-switching");
  document.documentElement.dataset.theme = next;
  if (save) localStorage.setItem("kitkat-theme", next);
  const label = next === "dark" ? "Light mode" : "Dark mode";
  $$("[data-theme-toggle]").forEach((button) => {
    button.setAttribute("aria-label", `Switch to ${label.toLowerCase()}`);
    const text = $(".theme-label", button);
    if (text) text.textContent = label;
  });
  const themeMeta = $('meta[name="theme-color"]');
  if (themeMeta) themeMeta.content = next === "dark" ? "#111318" : "#f4f5f7";
  requestAnimationFrame(() => requestAnimationFrame(() => document.documentElement.classList.remove("theme-switching")));
}

function toggleTheme() {
  applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark", { save: true });
}

function escapeHtml(value = "") {
  return String(value).replace(/[&<>'"]/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;"
  })[character]);
}

function getInfo(raw) {
  return raw.general_profile_information || raw.General_profile_information || raw.generalProfileInformation || {};
}

function normalizeProfile(raw, index) {
  const info = getInfo(raw);
  const id = raw.profile_browser_id || raw.profile_id || info.profile_browser_id || info.profile_id || `unknown-${index}`;
  const name = info.profile_name || raw.profile_name || raw.name || `Profile ${index + 1}`;
  const group = info.profile_group || raw.profile_group || raw.group || "Unassigned";
  const platform = info.simulated_operating_system || raw.platform || raw.simulated_operating_system || "Unknown";
  const status = String(raw.profile_status || raw.status || "checking").toLowerCase();
  return { id, name, group, platform, status, raw };
}

async function api(path, options = {}) {
  if (isCloudMode) return cloudApi(path, options);
  const userId = state.currentUser?.id || localStorage.getItem("kitkat-preview-user") || "";
  const response = await fetch(path, {
    ...options,
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(userId ? { "X-KitKat-User-ID": userId } : {}),
      ...(options.headers || {})
    }
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.message || "Something went wrong");
  return data;
}

function isRunning(status) {
  return ["running", "launched", "launching", "syncing"].includes(String(status).toLowerCase());
}

function isBusy(status) {
  return ["launching", "syncing", "stopping"].includes(String(status).toLowerCase());
}

function initials(name) {
  return name.split(/\s+/).slice(0, 2).map((word) => word[0]).join("").slice(0, 2) || "P";
}

function filteredProfiles() {
  const query = state.search.trim().toLowerCase();
  return state.profiles.filter((profile) => {
    const matchesSearch = !query || `${profile.name} ${profile.group} ${profile.id}`.toLowerCase().includes(query);
    const matchesGroup = state.groupFilter === "all" || profile.group === state.groupFilter;
    const matchesFilter = state.filter === "all"
      || (state.filter === "running" && isRunning(profile.status))
      || (state.filter === "ready" && ["ready", "available"].includes(profile.status));
    return matchesSearch && matchesGroup && matchesFilter;
  });
}

function renderProfileGroupFilter() {
  const isSuperAdmin = state.currentUser?.role === "super_admin";
  els.groupFilterWrap.classList.toggle("hidden", !isSuperAdmin);
  if (!isSuperAdmin) state.groupFilter = "all";

  const groups = availableGroups();
  if (state.groupFilter !== "all" && !groups.includes(state.groupFilter)) state.groupFilter = "all";
  els.groupFilterSelect.innerHTML = '<option value="all">All groups</option>' + groups
    .map((group) => `<option value="${escapeHtml(group)}">${escapeHtml(group)}</option>`)
    .join("");
  els.groupFilterSelect.value = state.groupFilter;
  els.groupFilterSelect.disabled = state.loading || groups.length === 0;
}

function actionMarkup(profile) {
  const running = isRunning(profile.status);
  const busy = isBusy(profile.status);
  const shouldStop = running && !busy;
  return `
    <div class="row-actions">
      <button class="action-button ${shouldStop ? "stop" : "open"}" data-action="${shouldStop ? "stop" : "launch"}" data-id="${escapeHtml(profile.id)}" ${busy ? "disabled" : ""}>
        ${shouldStop ? icons.stop : icons.play}${busy ? "Working…" : (shouldStop ? "Stop" : "Open")}
      </button>
      <div class="action-menu-wrap">
        <button class="more-button" data-action="menu" data-id="${escapeHtml(profile.id)}" aria-label="More actions for ${escapeHtml(profile.name)}">${icons.more}</button>
        ${state.menuFor === profile.id ? `<div class="action-menu">
          <button data-action="clone" data-id="${escapeHtml(profile.id)}">${icons.clone}Clone profile</button>
          <button class="danger" data-action="delete" data-id="${escapeHtml(profile.id)}">${icons.trash}Delete profile</button>
        </div>` : ""}
      </div>
    </div>`;
}

function renderProfiles() {
  renderProfileGroupFilter();
  const profiles = filteredProfiles();
  els.loadingState.classList.toggle("hidden", !state.loading);
  els.profileTable.closest(".table-wrap").classList.toggle("hidden", state.loading || profiles.length === 0);
  els.mobileProfileList.classList.toggle("hidden", state.loading || profiles.length === 0);
  els.emptyState.classList.toggle("hidden", state.loading || profiles.length > 0);

  if (!state.loading && profiles.length === 0) {
    const isSearch = Boolean(state.search || state.filter !== "all" || state.groupFilter !== "all");
    els.emptyTitle.textContent = isSearch ? "No matching profiles" : (state.connected ? "No profiles yet" : "Connection needed");
    els.emptyMessage.textContent = isSearch
      ? "Try another search or clear the current filter."
      : state.connected ? "Create your first profile and it will appear here." : "Start KitKat Bridge on the Incogniton PC to load and manage profiles.";
    $("#emptyAction").textContent = isSearch ? "Clear filters" : (state.connected ? "Create profile" : "Try again");
  }

  const visibleProfiles = profiles.slice(0, state.displayLimit);
  let html = visibleProfiles.map((profile) => `
    <tr>
      <td><div class="profile-cell"><span class="profile-avatar">${escapeHtml(initials(profile.name))}</span><div><span class="profile-name">${escapeHtml(profile.name)}</span><span class="profile-id">${escapeHtml(profile.id)}</span></div></div></td>
      <td>${escapeHtml(profile.group)}</td>
      <td><span class="platform-pill">${escapeHtml(profile.platform)}</span></td>
      <td><span class="status-pill ${escapeHtml(profile.status)}">${escapeHtml(profile.status)}</span></td>
      <td>${actionMarkup(profile)}</td>
    </tr>`).join("");
  
  if (profiles.length > state.displayLimit) {
    html += `<tr><td colspan="5" style="text-align:center; padding: 16px;"><button class="secondary-button" id="loadMoreProfiles" style="margin:auto;">Load more (${profiles.length - state.displayLimit} remaining)</button></td></tr>`;
  }
  els.profileTable.innerHTML = html;

  let mobileHtml = visibleProfiles.map((profile) => `
    <article class="mobile-profile-card">
      <div class="mobile-card-head"><div class="profile-cell"><span class="profile-avatar">${escapeHtml(initials(profile.name))}</span><div><span class="profile-name">${escapeHtml(profile.name)}</span><span class="profile-id">${escapeHtml(profile.id)}</span></div></div><span class="status-pill ${escapeHtml(profile.status)}">${escapeHtml(profile.status)}</span></div>
      <div class="mobile-card-meta"><span>${escapeHtml(profile.group)}</span><span> </span><span class="platform-pill">${escapeHtml(profile.platform)}</span></div>
      <div class="mobile-card-actions">${actionMarkup(profile)}</div>
    </article>`).join("");
  
  if (profiles.length > state.displayLimit) {
    mobileHtml += `<div style="text-align:center; padding: 16px;"><button class="secondary-button" id="loadMoreProfilesMobile" style="margin:auto;">Load more</button></div>`;
  }
  els.mobileProfileList.innerHTML = mobileHtml;

  const loadMoreBtn = document.getElementById("loadMoreProfiles");
  if (loadMoreBtn) loadMoreBtn.addEventListener("click", () => { state.displayLimit += 100; renderProfiles(); });
  const loadMoreBtnMobile = document.getElementById("loadMoreProfilesMobile");
  if (loadMoreBtnMobile) loadMoreBtnMobile.addEventListener("click", () => { state.displayLimit += 100; renderProfiles(); });

  updateCounts();
}

function updateCounts() {
  els.totalCount.textContent = state.loading ? "—" : state.profiles.length;
  els.runningCount.textContent = state.loading ? "—" : state.profiles.filter((profile) => isRunning(profile.status)).length;
  els.groupCount.textContent = state.loading ? "—" : new Set(state.profiles.map((profile) => profile.group).filter(Boolean)).size;
}

function setConnection(connected, message = "") {
  state.connected = connected;
  els.connectionDot.className = `status-dot ${connected ? "online" : "offline"}`;
  els.connectionLabel.textContent = connected ? "Bridge connected" : "Bridge offline";
  els.connectionHint.textContent = connected ? "Incogniton PC online" : "Action required";
  els.offlineBanner.classList.toggle("hidden", connected);
  $("#newProfileButton").disabled = !connected;
  $("#newProfileButton").title = connected ? "Create a new profile" : "Start KitKat Bridge to create profiles";
  if (!connected && message) els.offlineBanner.querySelector("p").textContent = message;
}

async function checkConnection() {
  els.connectionDot.className = "status-dot checking";
  els.connectionLabel.textContent = "Checking connection";
  try {
    const health = await api("/api/health");
    setConnection(health.connected, health.connected ? "" : (health.message || "Start KitKat Bridge on the Incogniton computer."));
    return health.connected;
  } catch (error) {
    setConnection(false, error.message);
    return false;
  }
}

async function loadProfiles({ quiet = false } = {}) {
  if (!quiet) {
    state.loading = true;
    renderProfiles();
  }
  const connected = await checkConnection();
  if (!connected) {
    state.loading = false;
    state.profiles = [];
    renderProfiles();
    return;
  }
  try {
    const data = await api("/api/profiles");
    const rawProfiles = data.profileData || data.profiles || (Array.isArray(data) ? data : []);
    state.profiles = rawProfiles.map(normalizeProfile);
    state.loading = false;
    renderProfiles();
    hydrateStatuses();
  } catch (error) {
    state.loading = false;
    state.profiles = [];
    setConnection(false, error.message);
    renderProfiles();
  }
}

async function hydrateStatuses() {
  const queue = [...state.profiles];
  const worker = async () => {
    while (queue.length) {
      const profile = queue.shift();
      try {
        const result = await api(`/api/profiles/${encodeURIComponent(profile.id)}/status`);
        profile.status = String(result.status || "available").toLowerCase();
      } catch {
        profile.status = "available";
      }
      renderProfiles();
    }
  };
  await Promise.all(Array.from({ length: Math.min(6, queue.length) }, worker));
}

function toast(title, message, type = "success") {
  const node = document.createElement("div");
  node.className = `toast ${type}`;
  node.innerHTML = `<span class="toast-mark">${type === "error" ? "!" : "✓"}</span><div><strong>${escapeHtml(title)}</strong><span>${escapeHtml(message)}</span></div><button aria-label="Dismiss">×</button>`;
  node.querySelector("button").addEventListener("click", () => node.remove());
  els.toastRegion.append(node);
  setTimeout(() => node.remove(), 5000);
}

function addActivity(action, detail, type = "success") {
  state.activity.unshift({ action, detail, type, time: new Date().toISOString() });
  state.activity = state.activity.slice(0, 50);
  sessionStorage.setItem("kitkat-activity", JSON.stringify(state.activity));
  renderActivity();
}

function renderActivity() {
  els.activityList.innerHTML = state.activity.length ? state.activity.map((item) => `
    <div class="activity-item">
      <span class="activity-mark ${item.type === "error" ? "error" : ""}">${item.type === "error" ? icons.error : icons.check}</span>
      <div><strong>${escapeHtml(item.action)}</strong><span>${escapeHtml(item.detail)}</span></div>
      <time datetime="${escapeHtml(item.time)}">${new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(new Date(item.time))}</time>
    </div>`).join("") : '<div class="activity-empty">Actions from this session will appear here.</div>';
}

function roleLabel(role) {
  return state.roles[role]?.label || role.split("_").map((part) => part[0].toUpperCase() + part.slice(1)).join(" ");
}

function groupChips(groups = []) {
  const labels = groups.includes("*") ? ["All groups"] : groups;
  if (!labels.length) return '<span class="group-chip">No profile access</span>';
  const visible = labels.slice(0, 2).map((group) => `<span class="group-chip">${escapeHtml(group)}</span>`).join("");
  return visible + (labels.length > 2 ? `<span class="group-chip more">+${labels.length - 2}</span>` : "");
}

function canManageUser(user) {
  if (!state.currentUser || user.id === state.currentUser.id) return false;
  if (state.currentUser.role === "super_admin") return true;
  return (state.currentUser.role === "fb_admin" && user.role === "fb_operator")
    || (state.currentUser.role === "nd_admin" && user.role === "nd_operator");
}

function renderUsers() {
  const query = state.userSearch.trim().toLowerCase();
  const users = state.users.filter((user) => `${user.name} ${user.email} ${roleLabel(user.role)}`.toLowerCase().includes(query));
  $("#superAdminCount").textContent = state.users.filter((user) => user.role === "super_admin").length;
  $("#fbTeamCount").textContent = state.users.filter((user) => user.role.startsWith("fb_")).length;
  $("#ndTeamCount").textContent = state.users.filter((user) => user.role.startsWith("nd_")).length;
  $("#usersEmpty").classList.toggle("hidden", users.length > 0);
  $("#newUserButton").classList.toggle("hidden", state.manageableRoles.length === 0);
  $("#membersHint").textContent = state.currentUser?.role === "super_admin" ? "All users in this local workspace." : "Users within your management scope.";

  const actions = (user) => canManageUser(user) ? `<div class="member-actions">
    <button class="member-action" data-user-action="edit" data-id="${escapeHtml(user.id)}">Manage</button>
    <button class="member-action" data-user-action="toggle" data-id="${escapeHtml(user.id)}">${user.active ? "Deactivate" : "Activate"}</button>
    <button class="member-action danger" data-user-action="delete" data-id="${escapeHtml(user.id)}">Delete</button>
  </div>` : '<span class="group-chip">Current user</span>';

  els.userTable.innerHTML = users.map((user) => `<tr>
    <td><div class="user-cell"><span class="user-avatar">${escapeHtml(initials(user.name))}</span><div><strong>${escapeHtml(user.name)}</strong><span>${escapeHtml(user.email || "No email added")}</span></div></div></td>
    <td><span class="role-badge ${escapeHtml(user.role)}">${escapeHtml(roleLabel(user.role))}</span></td>
    <td><div class="group-chip-list">${groupChips(user.allowedGroups)}</div></td>
    <td><span class="status-pill ${user.active ? "running" : ""}">${user.active ? "Active" : "Inactive"}</span></td>
    <td>${actions(user)}</td>
  </tr>`).join("");

  els.mobileUserList.innerHTML = users.map((user) => `<article class="mobile-user-card">
    <div class="mobile-user-card-head"><div class="user-cell"><span class="user-avatar">${escapeHtml(initials(user.name))}</span><div><strong>${escapeHtml(user.name)}</strong><span>${escapeHtml(user.email || "No email added")}</span></div></div><span class="role-badge ${escapeHtml(user.role)}">${escapeHtml(roleLabel(user.role))}</span></div>
    <div class="group-chip-list">${groupChips(user.allowedGroups)}</div>${actions(user)}
  </article>`).join("");
}

function renderPreviewUsers() {
  if (state.currentUser && !state.previewUsers.some((user) => user.id === state.currentUser.id)) state.previewUsers.push(state.currentUser);
  els.userPreviewSelect.innerHTML = state.previewUsers.map((user) => `<option value="${escapeHtml(user.id)}" ${user.id === state.currentUser?.id ? "selected" : ""}>${escapeHtml(user.name)} — ${escapeHtml(roleLabel(user.role))}</option>`).join("");
}

function updateSidebarVisibility() {
  if (!state.currentUser) return;
  
  const role = state.currentUser.role;
  const isSuperAdmin = role === "super_admin";
  const isND = role === "nd_admin" || role === "nd_operator";
  const isFB = role === "fb_admin" || role === "fb_operator";
  
  const allowed = state.currentUser.allowedAutomations || [];
  const canSee = (task) => isSuperAdmin || allowed.includes("*") || allowed.includes(task);

  $("#ndAutomationSection").style.display = (isSuperAdmin || isND) ? "block" : "none";
  $("#fbAutomationSection").style.display = (isSuperAdmin || isFB) ? "block" : "none";

  $$('#ndAutomationSection .nav-item[data-view]').forEach(btn => {
    btn.style.display = canSee(btn.dataset.view) ? "flex" : "none";
  });

  $$('#fbAutomationSection .nav-item[data-view]').forEach(btn => {
    btn.style.display = canSee(btn.dataset.view) ? "flex" : "none";
  });
}

async function loadSession({ recover = true } = {}) {
  try {
    const data = await api("/api/session");
    state.currentUser = data.user;
    state.roles = data.roles || {};
    state.manageableRoles = data.manageableRoles || [];
    if (!isCloudMode) localStorage.setItem("kitkat-preview-user", data.user.id);
    
    updateSidebarVisibility();
    
    const canManageUsers = state.manageableRoles.length > 0;
    $("#usersNav").classList.toggle("hidden", !canManageUsers);
    if (!canManageUsers && $("#usersView").classList.contains("active")) {
      $('.nav-item[data-view="profiles"]').click();
    }
    if (isCloudMode) {
      $(".preview-row").classList.add("hidden");
      $("#cloudAccountRow").classList.remove("hidden");
      $("#cloudAccountEmail").textContent = data.user.email || data.user.name;
    } else renderPreviewUsers();
  } catch (error) {
    if (recover && !isCloudMode) {
      localStorage.removeItem("kitkat-preview-user");
      state.currentUser = null;
      return loadSession({ recover: false });
    }
    if (isCloudMode && error.message === "AUTH_REQUIRED") showAuthGate();
    else toast("Couldn’t load permissions", error.message, "error");
  }
}

async function loadUsers() {
  try {
    const data = await api("/api/users");
    state.users = data.users || [];
    state.manageableRoles = data.manageableRoles || [];
    if (!isCloudMode && state.currentUser?.role === "super_admin") state.previewUsers = [...state.users];
    renderUsers();
    if (!isCloudMode) renderPreviewUsers();
  } catch (error) {
    toast("Couldn’t load users", error.message, "error");
  }
}

function availableGroups() {
  return [...new Set(state.profiles.map((profile) => profile.group || "Unassigned"))].sort((a, b) => a.localeCompare(b));
}

function updateUserPermissionFields() {
  const role = $("#userRoleSelect").value;
  const superActor = state.currentUser?.role === "super_admin";
  const showGroups = superActor && role !== "super_admin";
  $("#groupAccessField").classList.toggle("hidden", !showGroups);
  
  const showAutomations = superActor || state.currentUser?.role === "nd_admin" || state.currentUser?.role === "fb_admin";
  $("#automationAccessField").classList.toggle("hidden", !showAutomations);
  
  if (showAutomations) {
    const defaultSelected = state.editingUser ? state.editingUser.allowedAutomations || [] : [];
    renderAutomationOptions(role, defaultSelected);
  }

  const notes = {
    super_admin: "<strong>Full control.</strong> This user can create and manage every role and access every profile group.",
    fb_admin: "<strong>FB management.</strong> Can create and manage FB Operators only.",
    nd_admin: "<strong>ND management.</strong> Can create and manage ND Operators only.",
    fb_operator: "<strong>FB operations.</strong> Can use only the profile groups selected above.",
    nd_operator: "<strong>ND operations.</strong> Can use only the profile groups selected above."
  };
  $("#permissionNote").innerHTML = notes[role] || "Select a role to see its permissions.";
}

function renderGroupOptions(selected = []) {
  const groups = availableGroups();
  $("#groupOptions").innerHTML = groups.length ? groups.map((group) => `<label class="group-option"><input type="checkbox" name="allowedGroups" value="${escapeHtml(group)}" ${selected.includes(group) || selected.includes("*") ? "checked" : ""}/><span>${escapeHtml(group)}</span></label>`).join("") : '<span class="group-chip">No Incogniton groups available</span>';
}

function renderAutomationOptions(role, selected = []) {
  const isND = role === "nd_admin" || role === "nd_operator";
  const isFB = role === "fb_admin" || role === "fb_operator";
  const isSuper = role === "super_admin";
  
  const allOptions = [
    { value: "ndAutoPosting", label: "Auto Posting", type: "nd" },
    { value: "ndAutoListing", label: "Auto Listing", type: "nd" },
    { value: "ndAutoWarmup", label: "Auto Warmup", type: "nd" },
    { value: "ndRandomPosting", label: "Random Posting", type: "nd" },
    { value: "ndAccountCreation", label: "ND Account Creation", type: "nd" },
    { value: "ndBulkCreateProfiles", label: "Bulk Create Profiles", type: "nd" },
    { value: "ndFbListings", label: "FB Listings", type: "fb" }
  ];
  
  const visibleOptions = allOptions.filter(opt => isSuper || (isND && opt.type === "nd") || (isFB && opt.type === "fb"));
  
  $("#automationOptions").innerHTML = visibleOptions.length ? visibleOptions.map((opt) => `<label class="group-option"><input type="checkbox" name="allowedAutomations" value="${opt.value}" ${selected.includes(opt.value) || selected.includes("*") ? "checked" : ""}/><span>${opt.label}</span></label>`).join("") : '<span class="group-chip">No automations for this role</span>';
}

function openUserModal(user = null) {
  state.editingUser = user;
  els.userForm.reset();
  $("#userModalTitle").textContent = user ? "Manage user" : "Add user";
  $("#saveUserButton").textContent = user ? "Save changes" : "Add user";
  const roleOptions = state.currentUser?.role === "super_admin"
    ? Object.entries(state.roles).map(([value, role]) => ({ value, label: role.label }))
    : state.manageableRoles;
  $("#userRoleSelect").innerHTML = roleOptions.map((role) => `<option value="${escapeHtml(role.value)}">${escapeHtml(role.label)}</option>`).join("");
  if (user) {
    els.userForm.elements.name.value = user.name;
    els.userForm.elements.email.value = user.email || "";
    $("#userRoleSelect").value = user.role;
  }
  renderGroupOptions(user?.allowedGroups || []);
  updateUserPermissionFields();
  setModal(els.userModal, true);
}

async function toggleUser(user) {
  try {
    const updated = await api(`/api/users/${encodeURIComponent(user.id)}`, { method: "PUT", body: JSON.stringify({ active: !user.active }) });
    Object.assign(user, updated);
    renderUsers();
    toast(updated.active ? "User activated" : "User deactivated", updated.name);
  } catch (error) {
    toast("Couldn’t update user", error.message, "error");
  }
}

function requestUserDelete(user) {
  state.deleteUserTarget = user;
  state.deleteWorkflowTarget = null;
  state.deleteTarget = null;
  $("#confirmTitle").textContent = "Delete this user?";
  els.confirmMessage.textContent = `“${user.name}” will lose access to KitKat.`;
  els.confirmDelete.textContent = "Delete user";
  setModal(els.confirmModal, true);
}

function renderWorkflows() {
  $("#workflowCount").textContent = `${state.workflows.length} workflow${state.workflows.length === 1 ? "" : "s"}`;
  if (!state.workflows.length) {
    els.workflowList.innerHTML = `<div class="automation-empty"><span class="workflow-logo"><svg viewBox="0 0 24 24"><path d="m13 2-9 12h7l-1 8 10-13h-7z"/></svg></span><strong>No workflows yet</strong><p>Create a simple sequence of browser actions and reuse it with any Incogniton profile.</p><button class="primary-button" data-automation-action="new">Create workflow</button></div>`;
    return;
  }
  els.workflowList.innerHTML = state.workflows.map((workflow) => `
    <article class="workflow-list-card">
      <span class="workflow-logo"><svg viewBox="0 0 24 24"><path d="m13 2-9 12h7l-1 8 10-13h-7z"/></svg></span>
      <div class="workflow-card-copy">
        <strong>${escapeHtml(workflow.name)}</strong>
        <p>${escapeHtml(workflow.description || workflow.url)}</p>
        <div class="workflow-meta"><span>${workflow.steps.length + 1} action${workflow.steps.length ? "s" : ""}</span><span>•</span><span>${escapeHtml(new URL(workflow.url).hostname)}</span></div>
      </div>
      <div class="workflow-card-actions">
        <button class="run-workflow-button" data-automation-action="run" data-id="${escapeHtml(workflow.id)}">${icons.play}Run</button>
        <button class="delete-workflow-button" data-automation-action="delete" data-id="${escapeHtml(workflow.id)}" aria-label="Delete ${escapeHtml(workflow.name)}">${icons.trash}</button>
      </div>
    </article>`).join("");
}

function runStateIcon(status) {
  if (status === "completed") return icons.check;
  if (["failed", "cancelled", "interrupted"].includes(status)) return icons.error;
  return '<svg viewBox="0 0 24 24"><path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M18.4 5.6l-2.8 2.8M8.4 15.6l-2.8 2.8"/></svg>';
}

function renderRuns() {
  const active = state.runs.filter((run) => activeRunStatuses.has(run.status));
  $("#activeRunCount").textContent = active.length ? `${active.length} active run${active.length === 1 ? "" : "s"}` : "No active runs";
  els.runList.innerHTML = state.runs.length ? state.runs.slice(0, 12).map((run) => {
    const progress = run.totalSteps ? Math.round((run.currentStep / run.totalSteps) * 100) : 0;
    const activeRun = activeRunStatuses.has(run.status);
    return `<article class="run-item">
      <span class="run-state-mark ${escapeHtml(run.status)}">${runStateIcon(run.status)}</span>
      <div class="run-copy">
        <div class="run-copy-head"><strong>${escapeHtml(run.workflowName)}</strong><time class="run-time">${new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(new Date(run.createdAt))}</time></div>
        <span>${escapeHtml(run.message || run.status)}</span>
        ${activeRun ? `<div class="run-progress"><i style="width:${Math.max(4, progress)}%"></i></div>` : ""}
        <div class="run-footer"><span class="run-status">${escapeHtml(run.status)}</span>${activeRun ? `<button class="cancel-run-button" data-run-action="cancel" data-id="${escapeHtml(run.id)}">Cancel</button>` : ""}</div>
      </div>
    </article>`;
  }).join("") : '<div class="run-empty">No runs yet.<br />Completed and active workflows will appear here.</div>';

  clearTimeout(runPollTimer);
  if (active.length) runPollTimer = setTimeout(() => loadRuns({ quiet: true }), 900);
}

async function loadAutomations() {
  try {
    const [workflowData, runData] = await Promise.all([api("/api/automations"), api("/api/runs")]);
    state.workflows = workflowData.workflows || [];
    state.runs = runData.runs || [];
    renderWorkflows();
    renderRuns();
  } catch (error) {
    toast("Couldn’t load automations", error.message, "error");
  }
}

async function loadRuns({ quiet = false } = {}) {
  try {
    const data = await api("/api/runs");
    const previous = new Map(state.runs.map((run) => [run.id, run.status]));
    state.runs = data.runs || [];
    if (!quiet) toast("Runs refreshed", "Automation history is up to date.");
    for (const run of state.runs) {
      if (previous.has(run.id) && previous.get(run.id) !== run.status && ["completed", "failed", "cancelled"].includes(run.status)) {
        const successful = run.status === "completed";
        toast(successful ? "Automation completed" : "Automation stopped", `${run.workflowName}: ${run.message}`, successful ? "success" : "error");
        addActivity(successful ? "Automation completed" : "Automation stopped", `${run.workflowName}: ${run.message}`, successful ? "success" : "error");
      }
    }
    renderRuns();
  } catch (error) {
    clearTimeout(runPollTimer);
    if (!quiet) toast("Couldn’t refresh runs", error.message, "error");
  }
}

function makeDraftStep(type = "type") {
  return { id: crypto.randomUUID(), type, selector: "", value: type === "wait" ? "2" : "" };
}

function renderStepBuilder() {
  if (!state.draftSteps.length) {
    els.stepBuilder.innerHTML = '<div class="builder-empty">No extra actions yet. The destination page will still open when this workflow runs.</div>';
    return;
  }
  els.stepBuilder.innerHTML = state.draftSteps.map((step, index) => {
    const needsSelector = ["type", "click"].includes(step.type);
    const needsValue = step.type === "type" || step.type === "wait";
    const valuePlaceholder = step.type === "wait" ? "Seconds" : step.type === "type" ? "Text to enter" : "No value needed";
    return `<div class="builder-step" data-step-id="${escapeHtml(step.id)}">
      <span class="step-number">${index + 1}</span>
      <select data-step-field="type" aria-label="Action type"><option value="type" ${step.type === "type" ? "selected" : ""}>Type text</option><option value="click" ${step.type === "click" ? "selected" : ""}>Click</option><option value="wait" ${step.type === "wait" ? "selected" : ""}>Wait</option></select>
      <input class="step-selector" data-step-field="selector" value="${escapeHtml(step.selector)}" placeholder="CSS selector" ${needsSelector ? "" : "disabled"} aria-label="Element selector" />
      <input class="step-value" data-step-field="value" value="${escapeHtml(step.value)}" placeholder="${valuePlaceholder}" ${needsValue ? "" : "disabled"} ${step.type === "wait" ? 'type="number" min="1" max="60"' : ""} aria-label="Action value" />
      <button type="button" class="remove-step" data-step-remove="${escapeHtml(step.id)}" aria-label="Remove action">${icons.trash}</button>
    </div>`;
  }).join("");
}

function openAutomationModal() {
  state.draftSteps = [];
  els.automationForm.reset();
  renderStepBuilder();
  setModal(els.automationModal, true);
}

function openRunModal(workflowId) {
  const workflow = state.workflows.find((item) => item.id === workflowId);
  if (!workflow) return;
  state.selectedWorkflow = workflow;
  $("#runWorkflowName").textContent = workflow.name;
  $("#runWorkflowMeta").textContent = `${workflow.steps.length + 1} actions · ${new URL(workflow.url).hostname}`;
  els.runProfileSelect.innerHTML = '<option value="">Choose a profile</option>' + state.profiles.map((profile) => `<option value="${escapeHtml(profile.id)}">${escapeHtml(profile.name)} — ${escapeHtml(profile.group)}</option>`).join("");
  setModal(els.runModal, true);
}

async function requestWorkflowDelete(id) {
  const workflow = state.workflows.find((item) => item.id === id);
  if (!workflow) return;
  state.deleteWorkflowTarget = workflow;
  state.deleteUserTarget = null;
  state.deleteTarget = null;
  $("#confirmTitle").textContent = "Delete this workflow?";
  els.confirmMessage.textContent = `“${workflow.name}” will be removed. Previous run history will remain.`;
  els.confirmDelete.textContent = "Delete workflow";
  setModal(els.confirmModal, true);
}

async function cancelRun(id) {
  try {
    await api(`/api/runs/${encodeURIComponent(id)}/cancel`, { method: "POST" });
    toast("Cancelling automation", "KitKat is detaching from the browser.");
    await loadRuns({ quiet: true });
  } catch (error) {
    toast("Couldn’t cancel run", error.message, "error");
  }
}

function setModal(element, open) {
  element.classList.toggle("hidden", !open);
  element.setAttribute("aria-hidden", String(!open));
  document.body.style.overflow = open ? "hidden" : "";
  if (open) setTimeout(() => $("input, button", element)?.focus(), 20);
}

async function launchOrStop(id, action, button) {
  const profile = state.profiles.find((item) => item.id === id);
  if (!profile) return;
  const previousStatus = profile.status;
  profile.status = action === "launch" ? "launching" : "stopping";
  renderProfiles();
  try {
    await api(`/api/profiles/${encodeURIComponent(id)}/${action}`, { method: "POST" });
    profile.status = action === "launch" ? "launched" : "ready";
    toast(action === "launch" ? "Profile opened" : "Profile stopped", profile.name);
    addActivity(action === "launch" ? "Opened profile" : "Stopped profile", profile.name);
  } catch (error) {
    profile.status = previousStatus;
    toast("Action failed", error.message, "error");
    addActivity("Action failed", `${profile.name}: ${error.message}`, "error");
  }
  renderProfiles();
}

async function cloneProfile(id) {
  const profile = state.profiles.find((item) => item.id === id);
  if (!profile) return;
  state.menuFor = null;
  renderProfiles();
  try {
    await api(`/api/profiles/${encodeURIComponent(id)}/clone`, {
      method: "POST",
      body: JSON.stringify({ profile_name: `${profile.name} copy`, target_group: profile.group })
    });
    toast("Profile cloned", `${profile.name} copy was created.`);
    addActivity("Cloned profile", profile.name);
    await loadProfiles({ quiet: true });
  } catch (error) {
    toast("Couldn’t clone profile", error.message, "error");
    addActivity("Clone failed", `${profile.name}: ${error.message}`, "error");
  }
}

function requestDelete(id) {
  const profile = state.profiles.find((item) => item.id === id);
  if (!profile) return;
  state.deleteTarget = profile;
  state.deleteWorkflowTarget = null;
  state.deleteUserTarget = null;
  state.menuFor = null;
  $("#confirmTitle").textContent = "Delete this profile?";
  els.confirmMessage.textContent = `“${profile.name}” will be permanently removed from Incogniton.`;
  els.confirmDelete.textContent = "Delete profile";
  setModal(els.confirmModal, true);
  renderProfiles();
}

async function confirmDeletion() {
  if (state.deleteUserTarget) {
    const user = state.deleteUserTarget;
    els.confirmDelete.disabled = true;
    els.confirmDelete.textContent = "Deleting…";
    try {
      await api(`/api/users/${encodeURIComponent(user.id)}`, { method: "DELETE" });
      state.users = state.users.filter((item) => item.id !== user.id);
      state.previewUsers = state.previewUsers.filter((item) => item.id !== user.id);
      renderUsers();
      renderPreviewUsers();
      setModal(els.confirmModal, false);
      toast("User deleted", user.name);
      addActivity("Deleted user", user.name);
    } catch (error) {
      toast("Couldn’t delete user", error.message, "error");
    } finally {
      els.confirmDelete.disabled = false;
      els.confirmDelete.textContent = "Delete profile";
      state.deleteUserTarget = null;
    }
    return;
  }
  if (state.deleteWorkflowTarget) {
    const workflow = state.deleteWorkflowTarget;
    els.confirmDelete.disabled = true;
    els.confirmDelete.textContent = "Deleting…";
    try {
      await api(`/api/automations/${encodeURIComponent(workflow.id)}`, { method: "DELETE" });
      state.workflows = state.workflows.filter((item) => item.id !== workflow.id);
      toast("Workflow deleted", workflow.name);
      addActivity("Deleted workflow", workflow.name);
      setModal(els.confirmModal, false);
      renderWorkflows();
    } catch (error) {
      toast("Couldn’t delete workflow", error.message, "error");
    } finally {
      els.confirmDelete.disabled = false;
      els.confirmDelete.textContent = "Delete profile";
      state.deleteWorkflowTarget = null;
    }
    return;
  }
  const profile = state.deleteTarget;
  if (!profile) return;
  els.confirmDelete.disabled = true;
  els.confirmDelete.textContent = "Deleting…";
  try {
    await api(`/api/profiles/${encodeURIComponent(profile.id)}`, { method: "DELETE" });
    state.profiles = state.profiles.filter((item) => item.id !== profile.id);
    toast("Profile deleted", profile.name);
    addActivity("Deleted profile", profile.name);
    setModal(els.confirmModal, false);
    renderProfiles();
  } catch (error) {
    toast("Couldn’t delete profile", error.message, "error");
    addActivity("Delete failed", `${profile.name}: ${error.message}`, "error");
  } finally {
    els.confirmDelete.disabled = false;
    els.confirmDelete.textContent = "Delete profile";
    state.deleteTarget = null;
  }
}

function handleProfileAction(event) {
  const button = event.target.closest("[data-action]");
  if (!button) return;
  const { action, id } = button.dataset;
  if (action === "menu") {
    state.menuFor = state.menuFor === id ? null : id;
    renderProfiles();
  } else if (action === "launch" || action === "stop") {
    launchOrStop(id, action, button);
  } else if (action === "clone") {
    cloneProfile(id);
  } else if (action === "delete") {
    requestDelete(id);
  }
}

// ND Automation logic
async function fetchSheetRows(taskType) {
  try {
    const res = await api('/api/nd/fetch-rows', { method: 'POST', body: JSON.stringify({ taskType }) });
    toast('Fetching rows', "Queued fetch for " + taskType);
  } catch (err) {
    toast('Fetch failed', err.message, 'error');
  }
}

async function startAutomation(taskType) {
  try {
    const concurrency = document.getElementById(taskType + '-concurrency')?.value || 3;
    const config = { concurrency: parseInt(concurrency, 10) };
    if (taskType === 'ndAutoPosting') config.targetNames = document.getElementById('ndAutoPosting-targetNames')?.value;
    if (taskType === 'ndAutoListing') config.spammers = document.getElementById('ndAutoListing-spammers')?.value;
    
    await api('/api/nd/start', { method: 'POST', body: JSON.stringify({ taskType, config }) });
    toast('Automation Started', "Started " + taskType);
  } catch (err) {
    toast('Start failed', err.message, 'error');
  }
}

async function stopAutomation(taskId) {
  try {
    await api('/api/nd/stop', { method: 'POST', body: JSON.stringify({ taskId }) });
    toast('Automation Stopped', 'Queued stop command');
  } catch (err) {
    toast('Stop failed', err.message, 'error');
  }
}

async function loadSheetSettings() {
  try {
    const data = await api('/api/sheet-config');
    if (data.config) {
      if(document.getElementById('sheet-gas-url')) document.getElementById('sheet-gas-url').value = data.config.gasUrl || '';
      if(document.getElementById('sheet-browser-provider')) document.getElementById('sheet-browser-provider').value = data.config.provider || 'incogniton';
      if(document.getElementById('sheet-adspower-key')) document.getElementById('sheet-adspower-key').value = data.config.adsPowerKey || '';
      if(document.getElementById('sheet-profile-os')) document.getElementById('sheet-profile-os').value = data.config.os || 'windows';
    }
  } catch (err) {
    console.error('Failed to load sheet settings', err);
  }
}

async function saveSheetSettings() {
  try {
    const config = {
      gasUrl: document.getElementById('sheet-gas-url')?.value,
      provider: document.getElementById('sheet-browser-provider')?.value,
      adsPowerKey: document.getElementById('sheet-adspower-key')?.value,
      os: document.getElementById('sheet-profile-os')?.value
    };
    await api('/api/sheet-config', { method: 'POST', body: JSON.stringify({ config }) });
    toast('Settings saved', 'Sheet settings updated successfully');
  } catch (err) {
    toast('Save failed', err.message, 'error');
  }
}

function renderSheetRows(rows, containerId) {
  const tbody = document.getElementById(containerId);
  if (!tbody) return;
  tbody.innerHTML = rows.map(r => "<tr><td>" + escapeHtml(r.id) + "</td><td><pre style='margin:0; font-size:10px;'>" + escapeHtml(JSON.stringify(r.data)) + "</pre></td><td>" + escapeHtml(r.status) + "</td></tr>").join('');
}

document.addEventListener('click', e => {
  if (e.target.closest('.fetch-rows-btn')) {
    const task = e.target.closest('.fetch-rows-btn').dataset.task;
    fetchSheetRows(task);
  }
  if (e.target.closest('.start-automation-btn')) {
    const task = e.target.closest('.start-automation-btn').dataset.task;
    startAutomation(task);
  }
  if (e.target.closest('.stop-automation-btn')) {
    const task = e.target.closest('.stop-automation-btn').dataset.task;
    stopAutomation(task);
  }
  if (e.target.id === 'saveSheetSettingsBtn') {
    saveSheetSettings();
  }
});

$$('.nav-item[data-view]').forEach((button) => button.addEventListener("click", () => {
  const view = button.dataset.view;
  $$(".nav-item[data-view]").forEach((item) => item.classList.toggle("active", item === button));
  $$(".view").forEach((item) => item.classList.toggle("active", item.id === `${view}View`));
  if (view === "automations") loadAutomations();
  if (view === "users") loadUsers();
  if (view === "sheetSettings") loadSheetSettings();
  $(".sidebar").classList.remove("open");
}));

$$('.filter-tab').forEach((button) => button.addEventListener("click", () => {
  state.filter = button.dataset.filter;
  state.displayLimit = 100;
  $$(".filter-tab").forEach((item) => item.classList.toggle("active", item === button));
  renderProfiles();
}));

els.searchInput.addEventListener("input", (event) => { state.search = event.target.value; state.displayLimit = 100; renderProfiles(); });
els.groupFilterSelect.addEventListener("change", (event) => { state.groupFilter = event.target.value; state.displayLimit = 100; renderProfiles(); });
els.profileTable.addEventListener("click", handleProfileAction);
els.mobileProfileList.addEventListener("click", handleProfileAction);
$("#newProfileButton").addEventListener("click", () => setModal(els.profileModal, true));
$("#retryButton").addEventListener("click", () => loadProfiles());
$("#refreshButton").addEventListener("click", () => loadProfiles());
$("#emptyAction").addEventListener("click", () => {
  if (state.search || state.filter !== "all" || state.groupFilter !== "all") {
    state.search = ""; state.filter = "all"; state.groupFilter = "all"; state.displayLimit = 100; els.searchInput.value = "";
    els.groupFilterSelect.value = "all";
    $$(".filter-tab").forEach((item) => item.classList.toggle("active", item.dataset.filter === "all"));
    renderProfiles();
  } else if (state.connected) setModal(els.profileModal, true);
  else loadProfiles();
});
$("#mobileMenu").addEventListener("click", () => $(".sidebar").classList.toggle("open"));
$$("[data-theme-toggle]").forEach((button) => button.addEventListener("click", toggleTheme));
$("#settingsButton").addEventListener("click", () => setModal(els.settingsModal, true));
$("#confirmDelete").addEventListener("click", confirmDeletion);
$("#newAutomationButton").addEventListener("click", openAutomationModal);
$("#addStepButton").addEventListener("click", () => { state.draftSteps.push(makeDraftStep()); renderStepBuilder(); });
$("#refreshRuns").addEventListener("click", () => loadRuns());
$("#newUserButton").addEventListener("click", () => openUserModal());
$("#userSearchInput").addEventListener("input", (event) => { state.userSearch = event.target.value; renderUsers(); });
$("#userRoleSelect").addEventListener("change", updateUserPermissionFields);
$("#clearActivity").addEventListener("click", () => { state.activity = []; sessionStorage.removeItem("kitkat-activity"); renderActivity(); });

$$('[data-close-modal]').forEach((element) => element.addEventListener("click", () => setModal(els.profileModal, false)));
$$('[data-close-confirm]').forEach((element) => element.addEventListener("click", () => setModal(els.confirmModal, false)));
$$('[data-close-settings]').forEach((element) => element.addEventListener("click", () => setModal(els.settingsModal, false)));
$$('[data-close-automation]').forEach((element) => element.addEventListener("click", () => setModal(els.automationModal, false)));
$$('[data-close-run]').forEach((element) => element.addEventListener("click", () => setModal(els.runModal, false)));
$$('[data-close-user]').forEach((element) => element.addEventListener("click", () => setModal(els.userModal, false)));

function handleUserAction(event) {
  const button = event.target.closest("[data-user-action]");
  if (!button) return;
  const user = state.users.find((item) => item.id === button.dataset.id);
  if (!user) return;
  if (button.dataset.userAction === "edit") openUserModal(user);
  if (button.dataset.userAction === "toggle") toggleUser(user);
  if (button.dataset.userAction === "delete") requestUserDelete(user);
}

els.userTable.addEventListener("click", handleUserAction);
els.mobileUserList.addEventListener("click", handleUserAction);

els.userPreviewSelect.addEventListener("change", async (event) => {
  localStorage.setItem("kitkat-preview-user", event.target.value);
  state.currentUser = null;
  await loadSession();
  await Promise.all([loadUsers(), loadProfiles(), loadAutomations()]);
  toast("Permission preview changed", `You’re viewing KitKat as ${state.currentUser.name}.`);
});

els.userForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = new FormData(event.currentTarget);
  const body = {
    name: data.get("name"),
    email: data.get("email"),
    role: data.get("role"),
    allowedGroups: data.getAll("allowedGroups"),
    allowedAutomations: data.getAll("allowedAutomations")
  };
  const submit = $("#saveUserButton");
  submit.disabled = true;
  submit.textContent = "Saving…";
  try {
    if (state.editingUser) {
      const updated = await api(`/api/users/${encodeURIComponent(state.editingUser.id)}`, { method: "PUT", body: JSON.stringify(body) });
      Object.assign(state.editingUser, updated);
      toast("User updated", updated.name);
      addActivity("Updated user", updated.name);
    } else {
      const created = await api("/api/users", { method: "POST", body: JSON.stringify(body) });
      state.users.push(created);
      if (state.currentUser.role === "super_admin") state.previewUsers.push(created);
      toast("User added", created.name);
      addActivity("Added user", `${created.name} · ${roleLabel(created.role)}`);
    }
    renderUsers();
    renderPreviewUsers();
    setModal(els.userModal, false);
  } catch (error) {
    toast("Couldn’t save user", error.message, "error");
  } finally {
    submit.disabled = false;
    submit.textContent = state.editingUser ? "Save changes" : "Add user";
  }
});

els.workflowList.addEventListener("click", (event) => {
  const button = event.target.closest("[data-automation-action]");
  if (!button) return;
  if (button.dataset.automationAction === "new") openAutomationModal();
  if (button.dataset.automationAction === "run") openRunModal(button.dataset.id);
  if (button.dataset.automationAction === "delete") requestWorkflowDelete(button.dataset.id);
});

els.runList.addEventListener("click", (event) => {
  const button = event.target.closest("[data-run-action='cancel']");
  if (button) cancelRun(button.dataset.id);
});

els.stepBuilder.addEventListener("input", (event) => {
  const row = event.target.closest("[data-step-id]");
  const field = event.target.dataset.stepField;
  if (!row || !field) return;
  const step = state.draftSteps.find((item) => item.id === row.dataset.stepId);
  if (step) step[field] = event.target.value;
});

els.stepBuilder.addEventListener("change", (event) => {
  if (event.target.dataset.stepField !== "type") return;
  const row = event.target.closest("[data-step-id]");
  const step = state.draftSteps.find((item) => item.id === row.dataset.stepId);
  if (!step) return;
  step.type = event.target.value;
  step.selector = "";
  step.value = step.type === "wait" ? "2" : "";
  renderStepBuilder();
});

els.stepBuilder.addEventListener("click", (event) => {
  const button = event.target.closest("[data-step-remove]");
  if (!button) return;
  state.draftSteps = state.draftSteps.filter((step) => step.id !== button.dataset.stepRemove);
  renderStepBuilder();
});

els.automationForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const body = Object.fromEntries(new FormData(event.currentTarget));
  body.steps = state.draftSteps;
  const submit = $("#saveAutomation");
  submit.disabled = true;
  submit.textContent = "Saving…";
  try {
    const workflow = await api("/api/automations", { method: "POST", body: JSON.stringify(body) });
    state.workflows.unshift(workflow);
    renderWorkflows();
    setModal(els.automationModal, false);
    toast("Workflow saved", workflow.name);
    addActivity("Created workflow", workflow.name);
  } catch (error) {
    toast("Couldn’t save workflow", error.message, "error");
  } finally {
    submit.disabled = false;
    submit.textContent = "Save workflow";
  }
});

els.runForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.selectedWorkflow) return;
  const profileId = new FormData(event.currentTarget).get("profileId");
  const submit = $("#startRunButton");
  submit.disabled = true;
  submit.textContent = "Starting…";
  try {
    const run = await api(`/api/automations/${encodeURIComponent(state.selectedWorkflow.id)}/run`, { method: "POST", body: JSON.stringify({ profileId }) });
    state.runs.unshift(run);
    renderRuns();
    setModal(els.runModal, false);
    setModal(els.userModal, false);
    toast("Automation started", state.selectedWorkflow.name);
    addActivity("Started automation", state.selectedWorkflow.name);
  } catch (error) {
    toast("Couldn’t start automation", error.message, "error");
  } finally {
    submit.disabled = false;
    submit.textContent = "Open profile & run";
  }
});

els.profileForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const body = Object.fromEntries(new FormData(event.currentTarget));
  els.createSubmit.disabled = true;
  els.createSubmit.textContent = "Creating…";
  try {
    await api("/api/profiles", { method: "POST", body: JSON.stringify(body) });
    toast("Profile created", body.profile_name);
    addActivity("Created profile", body.profile_name);
    event.currentTarget.reset();
    setModal(els.profileModal, false);
    await loadProfiles({ quiet: true });
  } catch (error) {
    toast("Couldn’t create profile", error.message, "error");
    addActivity("Create failed", error.message, "error");
  } finally {
    els.createSubmit.disabled = false;
    els.createSubmit.textContent = "Create profile";
  }
});

document.addEventListener("keydown", (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
    event.preventDefault();
    els.searchInput.focus();
  }
  if (event.key === "Escape") {
    setModal(els.profileModal, false);
    setModal(els.confirmModal, false);
    setModal(els.settingsModal, false);
    setModal(els.automationModal, false);
    setModal(els.runModal, false);
    state.menuFor = null;
    renderProfiles();
  }
});

document.addEventListener("click", (event) => {
  if (!event.target.closest(".action-menu-wrap") && state.menuFor) {
    state.menuFor = null;
    renderProfiles();
  }
});

let authMode = "signin";

function showAuthGate(message = "") {
  $("#authGate").classList.remove("hidden");
  if (message) {
    $("#authMessage").textContent = message;
    $("#authMessage").classList.remove("hidden");
  }
}

function hideAuthGate() {
  $("#authGate").classList.add("hidden");
  $("#authMessage").classList.add("hidden");
}

function renderAuthMode() {
  const signup = authMode === "signup";
  $("#authTitle").textContent = signup ? "Create your workspace" : "Welcome back";
  $("#authSubtitle").textContent = "Sign in to manage profiles, people, and automations.";
  $("#authNameField").classList.toggle("hidden", true);
  $("#authSubmit").textContent = "Sign in";
  $("#authForm").elements.password.autocomplete = "current-password";
  $("#authMessage").classList.add("hidden");
}

$("#authForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = new FormData(event.currentTarget);
  const submit = $("#authSubmit");
  submit.disabled = true;
  submit.textContent = authMode === "signup" ? "Creating…" : "Signing in…";
  try {
    if (authMode === "signup") {
      const result = await signUp(data.get("email"), data.get("password"), data.get("displayName"));
      if (!result.session) {
        authMode = "signin";
        renderAuthMode();
        showAuthGate("Check your email to confirm the account, then return here and sign in.");
        return;
      }
    } else await signIn(data.get("email"), data.get("password"));
    hideAuthGate();
    await loadSession();
    await Promise.all([loadProfiles(), loadAutomations(), loadUsers()]);
  } catch (error) {
    showAuthGate(error.message);
  } finally {
    submit.disabled = false;
    submit.textContent = authMode === "signup" ? "Create account" : "Sign in";
  }
});

$("#signOutButton").addEventListener("click", async () => {
  await signOut();
  state.currentUser = null;
  showAuthGate();
});

async function bootstrap() {
  renderActivity();
  applyTheme(document.documentElement.dataset.theme || "light");
  if (isCloudMode) {
    const session = await getCloudSession();
    if (!session) {
      renderAuthMode();
      showAuthGate();
      return;
    }
    hideAuthGate();
  }
  await loadSession();
  await Promise.all([loadProfiles(), loadAutomations(), loadUsers()]);
}

bootstrap();

