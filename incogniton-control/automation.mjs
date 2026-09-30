import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { randomUUID } from "node:crypto";

const ALLOWED_STEP_TYPES = new Set(["type", "click", "wait", "press"]);
const ALLOWED_KEYS = new Set(["Enter", "Tab", "Escape", "ArrowDown", "ArrowUp", "Space"]);

function safeUrl(value) {
  let url;
  try {
    url = new URL(value);
  } catch {
    throw new Error("Enter a valid destination URL");
  }
  if (!["http:", "https:"].includes(url.protocol)) throw new Error("Destination must use http or https");
  return url.toString();
}

function safePuppeteerUrl(value) {
  const url = new URL(value);
  const loopbackHosts = new Set(["127.0.0.1", "localhost", "[::1]"]);
  if (!loopbackHosts.has(url.hostname)) throw new Error("Incogniton returned a non-local automation address");
  return url.toString();
}

function sanitizeSteps(steps = []) {
  if (!Array.isArray(steps)) throw new Error("Workflow steps must be a list");
  if (steps.length > 30) throw new Error("A workflow can contain at most 30 steps");
  return steps.map((step, index) => {
    const type = String(step.type || "").toLowerCase();
    if (!ALLOWED_STEP_TYPES.has(type)) throw new Error(`Step ${index + 1} has an unsupported action`);
    if (["type", "click"].includes(type) && !String(step.selector || "").trim()) {
      throw new Error(`Step ${index + 1} needs an element selector`);
    }
    if (type === "type" && !String(step.value ?? "").length) throw new Error(`Step ${index + 1} needs text to enter`);
    if (type === "press" && !ALLOWED_KEYS.has(String(step.value))) throw new Error(`Step ${index + 1} uses an unsupported key`);
    const seconds = type === "wait" ? Math.min(60, Math.max(1, Number(step.value) || 1)) : undefined;
    return {
      id: step.id || randomUUID(),
      type,
      selector: String(step.selector || "").trim(),
      value: type === "wait" ? seconds : String(step.value ?? ""),
      label: String(step.label || "").trim().slice(0, 80)
    };
  });
}

function publicRun(run) {
  const { browser, ...safe } = run;
  return safe;
}

export class AutomationAgent {
  constructor({ dataDir, incogniton }) {
    this.dataDir = dataDir;
    this.workflowsFile = path.join(dataDir, "workflows.json");
    this.runsFile = path.join(dataDir, "runs.json");
    this.incogniton = incogniton;
    this.workflows = [];
    this.runs = [];
    this.activeRuns = new Map();
  }

  async init() {
    await mkdir(this.dataDir, { recursive: true });
    this.workflows = await this.readCollection(this.workflowsFile);
    this.runs = (await this.readCollection(this.runsFile)).map((run) =>
      ["queued", "launching", "running"].includes(run.status)
        ? { ...run, status: "interrupted", message: "KitKat stopped before this run finished", finishedAt: new Date().toISOString() }
        : run
    );
    await this.persistRuns();
  }

  async readCollection(file) {
    try {
      const parsed = JSON.parse(await readFile(file, "utf8"));
      return Array.isArray(parsed) ? parsed : [];
    } catch (error) {
      if (error.code === "ENOENT") return [];
      throw error;
    }
  }

  async persistWorkflows() {
    await writeFile(this.workflowsFile, JSON.stringify(this.workflows, null, 2), "utf8");
  }

  async persistRuns() {
    const recent = this.runs.slice(0, 100).map(publicRun);
    await writeFile(this.runsFile, JSON.stringify(recent, null, 2), "utf8");
  }

  listWorkflows() {
    return this.workflows;
  }

  async createWorkflow(input) {
    const name = String(input.name || "").trim();
    if (!name) throw new Error("Workflow name is required");
    const now = new Date().toISOString();
    const workflow = {
      id: randomUUID(),
      name: name.slice(0, 80),
      description: String(input.description || "").trim().slice(0, 240),
      url: safeUrl(input.url),
      steps: sanitizeSteps(input.steps),
      createdAt: now,
      updatedAt: now
    };
    this.workflows.unshift(workflow);
    await this.persistWorkflows();
    return workflow;
  }

  async deleteWorkflow(id) {
    const before = this.workflows.length;
    this.workflows = this.workflows.filter((workflow) => workflow.id !== id);
    if (this.workflows.length === before) throw new Error("Workflow not found");
    await this.persistWorkflows();
  }

  listRuns() {
    return this.runs.map(publicRun);
  }

  getRun(id) {
    const run = this.runs.find((item) => item.id === id);
    if (!run) throw new Error("Run not found");
    return publicRun(run);
  }

  async startRun(workflowId, profileId) {
    const workflow = this.workflows.find((item) => item.id === workflowId);
    if (!workflow) throw new Error("Workflow not found");
    if (!String(profileId || "").trim()) throw new Error("Choose a browser profile");
    if ([...this.activeRuns.values()].some((active) => active.profileId === profileId)) {
      throw new Error("This profile already has an automation running");
    }
    const now = new Date().toISOString();
    const run = {
      id: randomUUID(),
      workflowId,
      workflowName: workflow.name,
      profileId,
      status: "queued",
      currentStep: 0,
      totalSteps: workflow.steps.length + 1,
      message: "Preparing automation",
      createdAt: now,
      startedAt: null,
      finishedAt: null,
      logs: [{ time: now, message: "Run queued" }]
    };
    this.runs.unshift(run);
    this.activeRuns.set(run.id, run);
    await this.persistRuns();
    this.executeRun(run, workflow).catch(() => {});
    return publicRun(run);
  }

  async updateRun(run, updates, logMessage) {
    Object.assign(run, updates);
    if (logMessage) run.logs.push({ time: new Date().toISOString(), message: logMessage });
    await this.persistRuns();
  }

  async executeRun(run, workflow) {
    let browser;
    try {
      await this.updateRun(run, { status: "launching", startedAt: new Date().toISOString(), message: "Opening Incogniton profile" }, "Opening profile");
      const launch = await this.incogniton(`/automation/launch/puppeteer/${encodeURIComponent(run.profileId)}`);
      const browserURL = safePuppeteerUrl(launch.puppeteerUrl);
      const puppeteerModule = await import("puppeteer-core");
      const puppeteer = puppeteerModule.default || puppeteerModule;
      browser = await puppeteer.connect({ browserURL, defaultViewport: null });
      run.browser = browser;
      const pages = await browser.pages();
      const page = pages[0] || await browser.newPage();

      await this.updateRun(run, { status: "running", currentStep: 1, message: "Opening destination" }, `Navigating to ${workflow.url}`);
      await page.goto(workflow.url, { waitUntil: "domcontentloaded", timeout: 45_000 });

      for (let index = 0; index < workflow.steps.length; index += 1) {
        if (run.cancelRequested) throw new Error("Run cancelled");
        const step = workflow.steps[index];
        const number = index + 2;
        const description = step.label || this.describeStep(step);
        await this.updateRun(run, { currentStep: number, message: description }, description);
        await this.executeStep(page, step);
      }

      await this.updateRun(run, {
        status: "completed",
        message: "Workflow completed",
        finishedAt: new Date().toISOString()
      }, "All steps completed");
    } catch (error) {
      const cancelled = run.cancelRequested || error.message === "Run cancelled";
      await this.updateRun(run, {
        status: cancelled ? "cancelled" : "failed",
        message: cancelled ? "Run cancelled" : error.message,
        finishedAt: new Date().toISOString()
      }, cancelled ? "Run cancelled" : `Failed: ${error.message}`);
    } finally {
      try { browser?.disconnect(); } catch {}
      delete run.browser;
      this.activeRuns.delete(run.id);
      await this.persistRuns();
    }
  }

  describeStep(step) {
    if (step.type === "type") return "Entering text";
    if (step.type === "click") return "Clicking element";
    if (step.type === "press") return `Pressing ${step.value}`;
    return `Waiting ${step.value} second${Number(step.value) === 1 ? "" : "s"}`;
  }

  async executeStep(page, step) {
    if (step.type === "wait") {
      await new Promise((resolve) => setTimeout(resolve, Number(step.value) * 1000));
      return;
    }
    if (step.type === "press") {
      await page.keyboard.press(step.value);
      return;
    }
    const element = await page.waitForSelector(step.selector, { visible: true, timeout: 30_000 });
    if (!element) throw new Error(`Could not find ${step.selector}`);
    if (step.type === "click") {
      await element.click();
      return;
    }
    if (step.type === "type") {
      await element.click({ clickCount: 3 });
      await page.keyboard.press("Backspace");
      await element.type(step.value, { delay: 18 });
    }
  }

  async cancelRun(id) {
    const run = this.activeRuns.get(id);
    if (!run) throw new Error("This run is no longer active");
    run.cancelRequested = true;
    await this.updateRun(run, { message: "Cancelling…" }, "Cancellation requested");
    try { run.browser?.disconnect(); } catch {}
    return publicRun(run);
  }
}
