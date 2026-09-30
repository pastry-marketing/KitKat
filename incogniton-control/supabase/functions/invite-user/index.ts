import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "npm:@supabase/supabase-js@2";

const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  try {
    const authHeader = req.headers.get("Authorization");
    if (!authHeader) throw new Error("Authentication required");
    const url = Deno.env.get("SUPABASE_URL")!;
    const publishable = Deno.env.get("SUPABASE_ANON_KEY")!;
    const serviceRole = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
    const callerClient = createClient(url, publishable, { global: { headers: { Authorization: authHeader } } });
    const adminClient = createClient(url, serviceRole);
    const { data: { user: caller }, error: callerError } = await callerClient.auth.getUser();
    if (callerError || !caller) throw new Error("Invalid session");
    const input = await req.json();
    const workspaceId = String(input.workspaceId || "");
    const role = String(input.role || "");
    const email = String(input.email || "").trim().toLowerCase();
    const name = String(input.name || "").trim();
    const requestedRedirect = String(input.redirectTo || "");
    const redirectTo = new Set([
      "https://kitkat-topaz.vercel.app",
      "https://kitkat-pastry-markting.vercel.app",
    ]).has(requestedRedirect)
      ? requestedRedirect
      : "https://kitkat-topaz.vercel.app";
    if (!workspaceId || !email || !name) throw new Error("Name, email, and workspace are required");
    const { data: callerMembership, error: membershipError } = await adminClient.from("workspace_members").select("role,active").eq("workspace_id", workspaceId).eq("user_id", caller.id).single();
    if (membershipError || !callerMembership?.active) throw new Error("Workspace access denied");
    const allowed = callerMembership.role === "super_admin"
      || (callerMembership.role === "fb_admin" && role === "fb_operator")
      || (callerMembership.role === "nd_admin" && role === "nd_operator");
    if (!allowed) throw new Error("You cannot create a user with that role");
    const { data: invited, error: inviteError } = await adminClient.auth.admin.inviteUserByEmail(email, {
      data: { display_name: name },
      redirectTo,
    });
    if (inviteError || !invited.user) throw inviteError || new Error("Invitation failed");
    const { data: member, error: insertError } = await adminClient.from("workspace_members").insert({ workspace_id: workspaceId, user_id: invited.user.id, display_name: name, role, created_by: caller.id }).select().single();
    if (insertError) { await adminClient.auth.admin.deleteUser(invited.user.id); throw insertError; }
    let groups = Array.isArray(input.allowedGroups) ? input.allowedGroups.map(String) : [];
    if (callerMembership.role !== "super_admin") {
      const { data: inherited } = await adminClient.from("member_group_access").select("group_name").eq("workspace_id", workspaceId).eq("user_id", caller.id);
      groups = (inherited || []).map((row) => row.group_name);
    }
    if (role !== "super_admin" && groups.length) {
      const rows = [...new Set(groups)].map((group_name) => ({ workspace_id: workspaceId, user_id: invited.user.id, group_name }));
      const { error: groupError } = await adminClient.from("member_group_access").insert(rows);
      if (groupError) throw groupError;
    }
    return new Response(JSON.stringify({ id: member.user_id, user_id: member.user_id, name: member.display_name, display_name: member.display_name, email, role: member.role, active: member.active, allowedGroups: role === "super_admin" ? ["*"] : groups }), { status: 201, headers: { ...cors, "Content-Type": "application/json" } });
  } catch (error) {
    return new Response(JSON.stringify({ message: error.message || "Invitation failed" }), { status: 400, headers: { ...cors, "Content-Type": "application/json" } });
  }
});
