import http from "node:http";
import { readFile, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { AutomationAgent } from "./automation.mjs";
import { AccessStore, ROLES } from "./access.mjs";

const HOST = process.env.HOST || "127.0.0.1";
const PORT = Number(process.env.PORT || 4173);
const INCOGNITON_URL = (process.env.INCOGNITON_URL || "http://127.0.0.1:35000").replace(/\/$/, "");
const ROOT = path.join(path.dirname(fileURLToPath(import.meta.url)), "public");
const DATA_ROOT = path.join(path.dirname(fileURLToPath(import.meta.url)), "data");
const MAX_BODY_SIZE = 1024 * 1024;

const mimeTypes = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".ico": "image/x-icon"
};

function sendJson(res, status, data) {
  res.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff"
  });
  res.end(JSON.stringify(data));
}

async function readJson(req) {
  const chunks = [];
  let size = 0;
  for await (const chunk of req) {
    size += chunk.length;
    if (size > MAX_BODY_SIZE) throw new Error("Request is too large");
    chunks.push(chunk);
  }
  if (!chunks.length) return {};
  try {
    return JSON.parse(Buffer.concat(chunks).toString("utf8"));
  } catch {
    throw new Error("Invalid JSON body");
  }
}

async function incogniton(endpoint, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 20_000);
  try {
    const response = await fetch(`${INCOGNITON_URL}${endpoint}`, {
      ...options,
      headers: options.body ? { "Content-Type": "application/json" } : undefined,
      signal: controller.signal
    });
    const text = await response.text();
    let data;
    try {
      data = text ? JSON.parse(text) : {};
    } catch {
      data = { message: text || "Unexpected response from Incogniton" };
    }
    if (!response.ok || data?.status === "error") {
      const error = new Error(data?.message || `Incogniton returned ${response.status}`);
      error.status = response.status;
      error.details = data;
      throw error;
    }
    return data;
  } catch (error) {
    if (error.name === "AbortError") throw new Error("Incogniton did not respond in time");
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

const automationAgent = new AutomationAgent({ dataDir: DATA_ROOT, incogniton });
await automationAgent.init();
const accessStore = new AccessStore(DATA_ROOT);
await accessStore.init();

function profileGroup(profile) {
  const info = profile.general_profile_information || profile.General_profile_information || profile.generalProfileInformation || {};
  return info.profile_group || profile.profile_group || profile.group || "Unassigned";
}

async function assertProfileAccess(actor, profileId) {
  const data = await incogniton(`/profile/get/${encodeURIComponent(profileId)}`);
  const group = profileGroup(data.profileData || data);
  accessStore.assertGroupAccess(actor, group);
  return group;
}

function profileIdFrom(pathname, suffix) {
  const match = pathname.match(new RegExp(`^/api/profiles/([^/]+)/${suffix}$`));
  return match ? decodeURIComponent(match[1]) : null;
}

async function handleApi(req, res, url) {
  try {
    if (req.method === "GET" && url.pathname === "/api/health") {
      try {
        await incogniton("/profile/all");
        return sendJson(res, 200, { connected: true, endpoint: INCOGNITON_URL });
      } catch (error) {
        return sendJson(res, 200, { connected: false, endpoint: INCOGNITON_URL, message: error.message });
      }
    }

    const actor = accessStore.resolveActor(req.headers["x-kitkat-user-id"]);

    if (req.method === "GET" && url.pathname === "/api/session") {
      return sendJson(res, 200, { user: actor, roles: ROLES, manageableRoles: accessStore.manageableRoles(actor) });
    }

    if (req.method === "GET" && url.pathname === "/api/users") {
      return sendJson(res, 200, { users: accessStore.visibleUsers(actor), manageableRoles: accessStore.manageableRoles(actor) });
    }

    if (req.method === "POST" && url.pathname === "/api/users") {
      return sendJson(res, 201, await accessStore.create(actor, await readJson(req)));
    }

    const userMatch = url.pathname.match(/^\/api\/users\/([^/]+)$/);
    if (req.method === "PUT" && userMatch) {
      return sendJson(res, 200, await accessStore.update(actor, decodeURIComponent(userMatch[1]), await readJson(req)));
    }
    if (req.method === "DELETE" && userMatch) {
      await accessStore.delete(actor, decodeURIComponent(userMatch[1]));
      return sendJson(res, 200, { status: "ok" });
    }

    if (req.method === "GET" && url.pathname === "/api/automations") {
      return sendJson(res, 200, { workflows: automationAgent.listWorkflows() });
    }

    if (req.method === "POST" && url.pathname === "/api/automations") {
      return sendJson(res, 201, await automationAgent.createWorkflow(await readJson(req)));
    }

    const automationMatch = url.pathname.match(/^\/api\/automations\/([^/]+)$/);
    if (req.method === "DELETE" && automationMatch) {
      await automationAgent.deleteWorkflow(decodeURIComponent(automationMatch[1]));
      return sendJson(res, 200, { status: "ok" });
    }

    const runAutomationMatch = url.pathname.match(/^\/api\/automations\/([^/]+)\/run$/);
    if (req.method === "POST" && runAutomationMatch) {
      const body = await readJson(req);
      await assertProfileAccess(actor, body.profileId);
      const run = await automationAgent.startRun(decodeURIComponent(runAutomationMatch[1]), body.profileId);
      return sendJson(res, 202, run);
    }

    if (req.method === "GET" && url.pathname === "/api/runs") {
      return sendJson(res, 200, { runs: automationAgent.listRuns() });
    }

    const runMatch = url.pathname.match(/^\/api\/runs\/([^/]+)$/);
    if (req.method === "GET" && runMatch) {
      return sendJson(res, 200, automationAgent.getRun(decodeURIComponent(runMatch[1])));
    }

    const cancelRunMatch = url.pathname.match(/^\/api\/runs\/([^/]+)\/cancel$/);
    if (req.method === "POST" && cancelRunMatch) {
      return sendJson(res, 200, await automationAgent.cancelRun(decodeURIComponent(cancelRunMatch[1])));
    }

    if (req.method === "GET" && url.pathname === "/api/profiles") {
      const data = await incogniton("/profile/all");
      const profiles = data.profileData || data.profiles || (Array.isArray(data) ? data : []);
      const filtered = accessStore.filterProfiles(actor, profiles);
      if (Array.isArray(data)) return sendJson(res, 200, filtered);
      return sendJson(res, 200, { ...data, [data.profileData ? "profileData" : "profiles"]: filtered });
    }

    if (req.method === "POST" && url.pathname === "/api/profiles") {
      const body = await readJson(req);
      if (!body.profile_name?.trim()) return sendJson(res, 400, { message: "Profile name is required" });
      const payload = {
        profile_name: body.profile_name.trim(),
        platform: body.platform || "windows",
        profile_group: body.profile_group?.trim() || "Unassigned",
        ...(body.userAgent?.trim() ? { userAgent: body.userAgent.trim() } : {})
      };
      accessStore.assertGroupAccess(actor, payload.profile_group);
      return sendJson(res, 201, await incogniton("/profile/add", {
        method: "POST",
        body: JSON.stringify(payload)
      }));
    }

    let profileId = profileIdFrom(url.pathname, "status");
    if (req.method === "GET" && profileId) {
      await assertProfileAccess(actor, profileId);
      return sendJson(res, 200, await incogniton(`/profile/status/${encodeURIComponent(profileId)}`));
    }

    profileId = profileIdFrom(url.pathname, "launch");
    if (req.method === "POST" && profileId) {
      await assertProfileAccess(actor, profileId);
      return sendJson(res, 200, await incogniton(`/profile/launch/${encodeURIComponent(profileId)}`));
    }

    profileId = profileIdFrom(url.pathname, "stop");
    if (req.method === "POST" && profileId) {
      await assertProfileAccess(actor, profileId);
      return sendJson(res, 200, await incogniton(`/profile/stop/${encodeURIComponent(profileId)}`));
    }

    profileId = profileIdFrom(url.pathname, "clone");
    if (req.method === "POST" && profileId) {
      const sourceGroup = await assertProfileAccess(actor, profileId);
      const body = await readJson(req);
      const payload = {
        profile_browser_id: profileId,
        profile_name: body.profile_name?.trim() || undefined,
        target_group: body.target_group?.trim() || undefined,
        clone_cookies: body.clone_cookies !== false,
        clone_advanced_other_settings: true,
        clone_useragent: true,
        clone_other_browser_data: true
      };
      accessStore.assertGroupAccess(actor, payload.target_group || sourceGroup);
      Object.keys(payload).forEach((key) => payload[key] === undefined && delete payload[key]);
      return sendJson(res, 201, await incogniton("/profile/clone", {
        method: "POST",
        body: JSON.stringify(payload)
      }));
    }

    const deleteMatch = url.pathname.match(/^\/api\/profiles\/([^/]+)$/);
    if (req.method === "DELETE" && deleteMatch) {
      profileId = decodeURIComponent(deleteMatch[1]);
      await assertProfileAccess(actor, profileId);
      return sendJson(res, 200, await incogniton(`/profile/delete/${encodeURIComponent(profileId)}`));
    }

    return sendJson(res, 404, { message: "API route not found" });
  } catch (error) {
    const unavailable = /fetch failed|ECONNREFUSED|did not respond/i.test(`${error.message} ${error.cause || ""}`);
    return sendJson(res, unavailable ? 503 : (error.status || 500), {
      message: unavailable
        ? "Incogniton is unavailable. Open the Incogniton desktop app and enable its API."
        : error.message,
      details: error.details
    });
  }
}

async function serveStatic(req, res, url) {
  let requested = decodeURIComponent(url.pathname);
  if (requested === "/") requested = "/index.html";
  const filePath = path.resolve(ROOT, `.${requested}`);
  if (!filePath.startsWith(ROOT)) {
    res.writeHead(403);
    return res.end("Forbidden");
  }
  try {
    const info = await stat(filePath);
    if (!info.isFile()) throw new Error("Not a file");
    const body = await readFile(filePath);
    res.writeHead(200, {
      "Content-Type": mimeTypes[path.extname(filePath)] || "application/octet-stream",
      "Cache-Control": path.extname(filePath) === ".html" ? "no-cache" : "public, max-age=3600",
      "X-Content-Type-Options": "nosniff",
      "Referrer-Policy": "no-referrer"
    });
    res.end(body);
  } catch {
    const body = await readFile(path.join(ROOT, "index.html"));
    res.writeHead(200, { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-cache" });
    res.end(body);
  }
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://${req.headers.host || `${HOST}:${PORT}`}`);
  if (url.pathname.startsWith("/api/")) return handleApi(req, res, url);
  return serveStatic(req, res, url);
});

server.listen(PORT, HOST, () => {
  console.log(`KitKat is ready at http://${HOST}:${PORT}`);
  console.log(`Incogniton endpoint: ${INCOGNITON_URL}`);
});
