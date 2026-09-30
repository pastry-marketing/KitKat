import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { randomUUID } from "node:crypto";

export const ROLES = {
  super_admin: { label: "Super Admin", family: "all" },
  fb_admin: { label: "FB Admin", family: "fb" },
  nd_admin: { label: "ND Admin", family: "nd" },
  fb_operator: { label: "FB Operator", family: "fb" },
  nd_operator: { label: "ND Operator", family: "nd" }
};

const ADMIN_CHILD_ROLE = {
  fb_admin: "fb_operator",
  nd_admin: "nd_operator"
};

function cleanGroups(groups) {
  if (!Array.isArray(groups)) return [];
  return [...new Set(groups.map((group) => String(group).trim()).filter(Boolean))];
}

export class AccessStore {
  constructor(dataDir) {
    this.file = path.join(dataDir, "users.json");
    this.users = [];
  }

  async init() {
    await mkdir(path.dirname(this.file), { recursive: true });
    try {
      const parsed = JSON.parse(await readFile(this.file, "utf8"));
      this.users = Array.isArray(parsed) ? parsed : [];
    } catch (error) {
      if (error.code !== "ENOENT") throw error;
    }
    if (!this.users.some((user) => user.role === "super_admin")) {
      this.users.unshift({
        id: "local-super-admin",
        name: "Local Super Admin",
        email: "",
        role: "super_admin",
        allowedGroups: ["*"],
        active: true,
        createdAt: new Date().toISOString(),
        createdBy: "system"
      });
      await this.persist();
    }
  }

  async persist() {
    await writeFile(this.file, JSON.stringify(this.users, null, 2), "utf8");
  }

  resolveActor(id) {
    const fallback = this.users.find((user) => user.role === "super_admin" && user.active);
    if (!id) return fallback;
    const actor = this.users.find((user) => user.id === id && user.active);
    if (!actor) {
      const error = new Error("The selected user is unavailable");
      error.status = 401;
      throw error;
    }
    return actor;
  }

  visibleUsers(actor) {
    if (actor.role === "super_admin") return this.users;
    const childRole = ADMIN_CHILD_ROLE[actor.role];
    if (childRole) return this.users.filter((user) => user.id === actor.id || user.role === childRole);
    return this.users.filter((user) => user.id === actor.id);
  }

  manageableRoles(actor) {
    if (actor.role === "super_admin") return Object.entries(ROLES).map(([value, role]) => ({ value, label: role.label }));
    const childRole = ADMIN_CHILD_ROLE[actor.role];
    return childRole ? [{ value: childRole, label: ROLES[childRole].label }] : [];
  }

  canManage(actor, target) {
    if (actor.role === "super_admin") return true;
    return Boolean(ADMIN_CHILD_ROLE[actor.role] && target.role === ADMIN_CHILD_ROLE[actor.role]);
  }

  normalizeGroupsForCreate(actor, requested) {
    if (actor.role === "super_admin") {
      const groups = cleanGroups(requested);
      return groups.length ? groups : [];
    }
    return [...actor.allowedGroups];
  }

  async create(actor, input) {
    const roles = this.manageableRoles(actor).map((role) => role.value);
    if (!roles.includes(input.role)) {
      const error = new Error("You cannot create a user with that role");
      error.status = 403;
      throw error;
    }
    const name = String(input.name || "").trim();
    if (!name) {
      const error = new Error("User name is required");
      error.status = 400;
      throw error;
    }
    const user = {
      id: randomUUID(),
      name: name.slice(0, 80),
      email: String(input.email || "").trim().slice(0, 160),
      role: input.role,
      allowedGroups: input.role === "super_admin" ? ["*"] : this.normalizeGroupsForCreate(actor, input.allowedGroups),
      active: true,
      createdAt: new Date().toISOString(),
      createdBy: actor.id
    };
    this.users.push(user);
    await this.persist();
    return user;
  }

  async update(actor, id, input) {
    const target = this.users.find((user) => user.id === id);
    if (!target) {
      const error = new Error("User not found");
      error.status = 404;
      throw error;
    }
    if (!this.canManage(actor, target)) {
      const error = new Error("You cannot manage this user");
      error.status = 403;
      throw error;
    }
    if (actor.role !== "super_admin" && input.role && input.role !== target.role) {
      const error = new Error("Only the Super Admin can change roles");
      error.status = 403;
      throw error;
    }
    if (input.role && !ROLES[input.role]) throw new Error("Unknown role");
    if (input.name !== undefined) target.name = String(input.name).trim().slice(0, 80) || target.name;
    if (input.email !== undefined) target.email = String(input.email).trim().slice(0, 160);
    if (input.active !== undefined && target.id !== actor.id) target.active = Boolean(input.active);
    if (actor.role === "super_admin" && input.role) target.role = input.role;
    if (target.role === "super_admin") target.allowedGroups = ["*"];
    else if (actor.role === "super_admin" && input.allowedGroups !== undefined) target.allowedGroups = cleanGroups(input.allowedGroups);
    await this.persist();
    return target;
  }

  async delete(actor, id) {
    const target = this.users.find((user) => user.id === id);
    if (!target) throw new Error("User not found");
    if (target.id === actor.id) {
      const error = new Error("You cannot delete your current user");
      error.status = 400;
      throw error;
    }
    if (!this.canManage(actor, target)) {
      const error = new Error("You cannot delete this user");
      error.status = 403;
      throw error;
    }
    this.users = this.users.filter((user) => user.id !== id);
    await this.persist();
  }

  canAccessGroup(actor, group) {
    if (actor.role === "super_admin" || actor.allowedGroups.includes("*")) return true;
    const normalized = String(group || "Unassigned").trim().toLowerCase();
    return actor.allowedGroups.some((allowed) => allowed.toLowerCase() === normalized);
  }

  filterProfiles(actor, profiles) {
    return profiles.filter((profile) => {
      const info = profile.general_profile_information || profile.General_profile_information || profile.generalProfileInformation || {};
      const group = info.profile_group || profile.profile_group || profile.group || "Unassigned";
      return this.canAccessGroup(actor, group);
    });
  }

  assertGroupAccess(actor, group) {
    if (!this.canAccessGroup(actor, group)) {
      const error = new Error("This profile group is outside your access");
      error.status = 403;
      throw error;
    }
  }
}
