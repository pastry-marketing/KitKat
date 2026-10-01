import { createClient } from "@supabase/supabase-js";

const SUPABASE_URL = "https://mqxpsagrjbwryqgiyzfr.supabase.co";
const SUPABASE_KEY = "sb_publishable_mMEnrqnXRumi1rlNaxXaXw_Wd7bB4t8";

export const isCloudMode = !["localhost", "127.0.0.1"].includes(location.hostname);
export const supabase = createClient(SUPABASE_URL, SUPABASE_KEY, {
  auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true }
});

const roles = {
  super_admin: { label: "Super Admin", family: "all" },
  fb_admin: { label: "FB Admin", family: "fb" },
  nd_admin: { label: "ND Admin", family: "nd" },
  fb_operator: { label: "FB Operator", family: "fb" },
  nd_operator: { label: "ND Operator", family: "nd" }
};

let context = null;

function manageableRoles(role) {
  if (role === "super_admin") return Object.entries(roles).map(([value, item]) => ({ value, label: item.label }));
  if (role === "fb_admin") return [{ value: "fb_operator", label: roles.fb_operator.label }];
  if (role === "nd_admin") return [{ value: "nd_operator", label: roles.nd_operator.label }];
  return [];
}

function fail(error) {
  throw new Error(error?.message || "Supabase request failed");
}

async function requireContext() {
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) throw new Error("AUTH_REQUIRED");
  if (context?.session?.user?.id === session.user.id) return context;
  let { data: membership, error } = await supabase
    .from("workspace_members")
    .select("*")
    .eq("user_id", session.user.id)
    .eq("active", true)
    .maybeSingle();
  if (error) fail(error);
  if (!membership) {
    const displayName = session.user.user_metadata?.display_name || session.user.email?.split("@")[0] || "Super Admin";
    const { error: bootstrapError } = await supabase.rpc("bootstrap_workspace", {
      workspace_name: "KitKat",
      display_name: displayName
    });
    if (bootstrapError) fail(bootstrapError);
    const response = await supabase.from("workspace_members").select("*").eq("user_id", session.user.id).single();
    if (response.error) fail(response.error);
    membership = response.data;
  }
  context = { session, membership };
  return context;
}

async function activeAgent(profileId) {
  const { membership, session } = await requireContext();
  const onlineSince = new Date(Date.now() - 86400_000).toISOString();
  const response = await supabase.from("agents").select("id").eq("workspace_id", membership.workspace_id).eq("active", true).gte("last_seen_at", onlineSince).order("last_seen_at", { ascending: false }).limit(1).maybeSingle();
  if (response.error) fail(response.error);
  if (!response.data) throw new Error("No local KitKat agent is connected yet");
  return response.data.id;
}

async function queueCommand(action, profileId, payload = {}) {
  const { session, membership } = await requireContext();
  const agentId = await activeAgent(profileId);
  const response = await supabase.from("commands").insert({
    workspace_id: membership.workspace_id,
    agent_id: agentId,
    profile_id: profileId || null,
    action,
    payload,
    requested_by: session.user.id
  }).select().single();
  if (response.error) fail(response.error);
  return { status: "ok", message: "Command queued", command: response.data };
}

function mapProfile(row) {
  return {
    profile_browser_id: row.profile_id,
    profile_status: row.status,
    general_profile_information: {
      profile_name: row.name,
      profile_group: row.group_name,
      simulated_operating_system: row.platform
    },
    agent_id: row.agent_id
  };
}

function mapWorkflow(row) {
  return {
    ...row,
    url: row.destination_url,
    steps: (row.workflow_steps || []).sort((a, b) => a.position - b.position).map((step) => ({
      id: step.id,
      type: step.action,
      selector: step.selector || "",
      value: step.value || "",
      label: step.label || ""
    }))
  };
}

export async function getCloudSession() {
  const { data: { session } } = await supabase.auth.getSession();
  return session;
}

export async function signIn(email, password) {
  const response = await supabase.auth.signInWithPassword({ email, password });
  if (response.error) fail(response.error);
  context = null;
  return response.data;
}

export async function signUp(email, password, displayName) {
  const response = await supabase.auth.signUp({
    email,
    password,
    options: {
      data: { display_name: displayName },
      emailRedirectTo: location.origin
    }
  });
  if (response.error) fail(response.error);
  context = null;
  return response.data;
}

export async function signOut() {
  await supabase.auth.signOut();
  context = null;
}

export async function cloudApi(path, options = {}) {
  const method = options.method || "GET";
  const body = options.body ? JSON.parse(options.body) : {};
  const { session, membership } = await requireContext();

  if (path === "/api/session") return { user: { id: session.user.id, name: membership.display_name, email: session.user.email, role: membership.role, allowedGroups: [], allowedAutomations: membership.role === "super_admin" ? ["*"] : (membership.allowed_automations || []), active: membership.active }, roles, manageableRoles: manageableRoles(membership.role) };
  if (path === "/api/health") {
    const response = await supabase.from("agents").select("last_seen_at").eq("workspace_id", membership.workspace_id).order("last_seen_at", { ascending: false }).limit(1).maybeSingle();
    const connected = Boolean(response.data?.last_seen_at && Math.abs(Date.now() - new Date(response.data.last_seen_at).getTime()) < 86400_000);
    return { connected, endpoint: "Supabase command bridge", message: connected ? "" : "Start KitKat Bridge on the Incogniton computer." };
  }
  if (path === "/api/users" && method === "GET") {
    const usersResponse = await supabase.from("workspace_members").select("*").eq("workspace_id", membership.workspace_id).order("created_at");
    if (usersResponse.error) fail(usersResponse.error);
    const groupsResponse = await supabase.from("member_group_access").select("user_id,group_name").eq("workspace_id", membership.workspace_id);
    if (groupsResponse.error) fail(groupsResponse.error);
    const groups = new Map();
    for (const row of groupsResponse.data) groups.set(row.user_id, [...(groups.get(row.user_id) || []), row.group_name]);
    return { users: usersResponse.data.map((user) => ({ ...user, id: user.user_id, name: user.display_name, allowedGroups: user.role === "super_admin" ? ["*"] : (groups.get(user.user_id) || []), allowedAutomations: user.role === "super_admin" ? ["*"] : (user.allowed_automations || []) })), manageableRoles: manageableRoles(membership.role) };
  }
  if (path === "/api/users" && method === "POST") {
    const response = await supabase.functions.invoke("invite-user", {
      body: { ...body, workspaceId: membership.workspace_id, redirectTo: location.origin }
    });
    if (response.error) fail(response.error);
    return response.data;
  }
  const userMatch = path.match(/^\/api\/users\/([^/]+)$/);
  if (userMatch && method === "PUT") {
    const userId = decodeURIComponent(userMatch[1]);
    const updateData = { display_name: body.name, role: body.role, active: body.active };
    if (body.allowedAutomations !== undefined) updateData.allowed_automations = body.allowedAutomations;
    const response = await supabase.from("workspace_members").update(updateData).eq("workspace_id", membership.workspace_id).eq("user_id", userId).select().single();
    if (response.error) fail(response.error);
    if (membership.role === "super_admin" && body.allowedGroups) {
      await supabase.from("member_group_access").delete().eq("workspace_id", membership.workspace_id).eq("user_id", userId);
      if (body.role !== "super_admin" && body.allowedGroups.length) {
        const access = body.allowedGroups.map((group_name) => ({ workspace_id: membership.workspace_id, user_id: userId, group_name }));
        const groupResponse = await supabase.from("member_group_access").insert(access);
        if (groupResponse.error) fail(groupResponse.error);
      }
    }
    return { ...response.data, id: response.data.user_id, name: response.data.display_name, allowedGroups: body.role === "super_admin" ? ["*"] : body.allowedGroups || [], allowedAutomations: body.role === "super_admin" ? ["*"] : body.allowedAutomations || [] };
  }
  if (userMatch && method === "DELETE") {
    const response = await supabase.from("workspace_members").delete().eq("workspace_id", membership.workspace_id).eq("user_id", decodeURIComponent(userMatch[1]));
    if (response.error) fail(response.error);
    return { status: "ok" };
  }
  if (path === "/api/profiles" && method === "GET") {
    let allProfiles = [];
    let from = 0;
    const limit = 1000;
    while (true) {
      const response = await supabase.from("browser_profiles").select("*").eq("workspace_id", membership.workspace_id).order("name").range(from, from + limit - 1);
      if (response.error) fail(response.error);
      allProfiles.push(...response.data);
      if (response.data.length < limit) break;
      from += limit;
    }
    return { status: "ok", profileData: allProfiles.map(mapProfile) };
  }
  if (path === "/api/profiles" && method === "POST") return queueCommand("create_profile", null, body);
  const statusMatch = path.match(/^\/api\/profiles\/([^/]+)\/status$/);
  if (statusMatch) {
    const response = await supabase.from("browser_profiles").select("status").eq("workspace_id", membership.workspace_id).eq("profile_id", decodeURIComponent(statusMatch[1])).single();
    if (response.error) fail(response.error);
    return response.data;
  }
  const actionMatch = path.match(/^\/api\/profiles\/([^/]+)\/(launch|stop|clone)$/);
  if (actionMatch) return queueCommand(`${actionMatch[2]}_profile`, decodeURIComponent(actionMatch[1]), body);
  const profileMatch = path.match(/^\/api\/profiles\/([^/]+)$/);
  if (profileMatch && method === "DELETE") return queueCommand("delete_profile", decodeURIComponent(profileMatch[1]));

  if (path === "/api/automations" && method === "GET") {
    const response = await supabase.from("workflows").select("*,workflow_steps(*)").eq("workspace_id", membership.workspace_id).order("updated_at", { ascending: false });
    if (response.error) fail(response.error);
    return { workflows: response.data.map(mapWorkflow) };
  }
  if (path === "/api/automations" && method === "POST") {
    const workflowResponse = await supabase.from("workflows").insert({ workspace_id: membership.workspace_id, name: body.name, description: body.description || "", destination_url: body.url, created_by: session.user.id }).select().single();
    if (workflowResponse.error) fail(workflowResponse.error);
    if (body.steps?.length) {
      const steps = body.steps.map((step, position) => ({ workflow_id: workflowResponse.data.id, position, action: step.type, selector: step.selector || null, value: String(step.value ?? ""), label: step.label || null }));
      const stepResponse = await supabase.from("workflow_steps").insert(steps).select();
      if (stepResponse.error) fail(stepResponse.error);
      workflowResponse.data.workflow_steps = stepResponse.data;
    }
    return mapWorkflow(workflowResponse.data);
  }
  const automationMatch = path.match(/^\/api\/automations\/([^/]+)$/);
  if (automationMatch && method === "DELETE") {
    const response = await supabase.from("workflows").delete().eq("id", decodeURIComponent(automationMatch[1]));
    if (response.error) fail(response.error);
    return { status: "ok" };
  }
  const runWorkflowMatch = path.match(/^\/api\/automations\/([^/]+)\/run$/);
  if (runWorkflowMatch && method === "POST") {
    const agentId = await activeAgent(body.profileId);
    const workflowId = decodeURIComponent(runWorkflowMatch[1]);
    const workflowResponse = await supabase.from("workflows").select("name,workflow_steps(id)").eq("id", workflowId).single();
    if (workflowResponse.error) fail(workflowResponse.error);
    const runResponse = await supabase.from("automation_runs").insert({ workspace_id: membership.workspace_id, workflow_id: workflowId, agent_id: agentId, profile_id: body.profileId, requested_by: session.user.id, total_steps: (workflowResponse.data.workflow_steps?.length || 0) + 1 }).select().single();
    if (runResponse.error) fail(runResponse.error);
    await queueCommand("run_workflow", body.profileId, { workflowId, runId: runResponse.data.id });
    return { ...runResponse.data, workflowName: workflowResponse.data.name };
  }
  if (path === "/api/runs" && method === "GET") {
    const response = await supabase.from("automation_runs").select("*,workflows(name)").eq("workspace_id", membership.workspace_id).order("created_at", { ascending: false }).limit(100);
    if (response.error) fail(response.error);
    return { runs: response.data.map((run) => ({ ...run, workflowName: run.workflows?.name || "Deleted workflow", currentStep: run.current_step, totalSteps: run.total_steps, createdAt: run.created_at })) };
  }
  const cancelMatch = path.match(/^\/api\/runs\/([^/]+)\/cancel$/);
  if (cancelMatch && method === "POST") {
    const runId = decodeURIComponent(cancelMatch[1]);
    const response = await supabase.from("automation_runs").select("profile_id").eq("id", runId).single();
    if (response.error) fail(response.error);
    return queueCommand("cancel_run", response.data.profile_id, { runId });
  }
  // ── ND Automation Routes ──────────────────────────────────────────────

  // Sheet config
  if (path === "/api/sheet-config" && method === "GET") {
    const response = await supabase.from("sheet_configs").select("*").eq("workspace_id", membership.workspace_id).maybeSingle();
    if (response.error) fail(response.error);
    return response.data || {};
  }
  if (path === "/api/sheet-config" && method === "POST") {
    const payload = { workspace_id: membership.workspace_id, ...body, created_by: session.user.id, updated_at: new Date().toISOString() };
    const response = await supabase.from("sheet_configs").upsert(payload, { onConflict: "workspace_id" }).select().single();
    if (response.error) fail(response.error);
    return response.data;
  }

  // ND automation tasks
  if (path === "/api/nd/tasks" && method === "GET") {
    const response = await supabase.from("nd_automation_tasks").select("*").eq("workspace_id", membership.workspace_id).order("created_at", { ascending: false }).limit(50);
    if (response.error) fail(response.error);
    return { tasks: response.data };
  }
  if (path === "/api/nd/tasks" && method === "POST") {
    const response = await supabase.from("nd_automation_tasks").insert({ workspace_id: membership.workspace_id, agent_id: body.agent_id || null, task_type: body.task_type, sheet_name: body.sheet_name || "", concurrency: body.concurrency || 3, config: body.config || {}, requested_by: session.user.id }).select().single();
    if (response.error) fail(response.error);
    return response.data;
  }
  const ndTaskMatch = path.match(/^\/api\/nd\/tasks\/([^/]+)$/);
  if (ndTaskMatch && method === "PATCH") {
    const response = await supabase.from("nd_automation_tasks").update(body).eq("id", decodeURIComponent(ndTaskMatch[1])).select().single();
    if (response.error) fail(response.error);
    return response.data;
  }
  const ndResultsMatch = path.match(/^\/api\/nd\/tasks\/([^/]+)\/results$/);
  if (ndResultsMatch && method === "GET") {
    const response = await supabase.from("nd_automation_results").select("*").eq("task_id", decodeURIComponent(ndResultsMatch[1])).order("created_at", { ascending: true });
    if (response.error) fail(response.error);
    return { results: response.data };
  }

  // Queue bridge commands for ND automation
  if (path === "/api/nd/fetch-rows" && method === "POST") {
    return queueCommand("fetch_sheet_rows", null, { sheet_name: body.sheet_name });
  }
  if (path === "/api/nd/start" && method === "POST") {
    const agentId = await activeAgent();
    // Create the task record first
    const taskResponse = await supabase.from("nd_automation_tasks").insert({ workspace_id: membership.workspace_id, agent_id: agentId, task_type: body.task_type, sheet_name: body.sheet_name || "", concurrency: body.concurrency || 3, config: body.config || {}, requested_by: session.user.id }).select().single();
    if (taskResponse.error) fail(taskResponse.error);
    // Queue the command to the bridge
    await queueCommand("start_automation", null, { task_id: taskResponse.data.id, task_type: body.task_type, rows: body.rows, concurrency: body.concurrency || 3, config: body.config || {} });
    return taskResponse.data;
  }
  if (path === "/api/nd/stop" && method === "POST") {
    await queueCommand("stop_automation", null, { task_id: body.task_id });
    return { stopped: true };
  }
  if (path === "/api/nd/save-settings" && method === "POST") {
    return queueCommand("save_settings", null, body);
  }

  throw new Error(`Unsupported cloud route: ${method} ${path}`);
}

