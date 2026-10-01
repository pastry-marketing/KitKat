const fs = require('fs');
const path = require('path');

const publicDir = 'C:\\\\Users\\\\nasbi\\\\Downloads\\\\KitKat\\\\incogniton-control\\\\public';
const indexHtmlPath = path.join(publicDir, 'index.html');
const appJsPath = path.join(publicDir, 'app.js');
const cloudApiJsPath = path.join(publicDir, 'cloud-api.js');
const stylesCssPath = path.join(publicDir, 'styles.css');

let indexHtml = fs.readFileSync(indexHtmlPath, 'utf8');

// index.html changes: navigation
const navInsert = `
          <div class="nav-group-header">ND Automation</div>
          <button class="nav-item" data-view="ndAutoPosting">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
            <span>Auto Posting</span>
          </button>
          <button class="nav-item" data-view="ndAutoListing">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
            <span>Auto Listing</span>
          </button>
          <button class="nav-item" data-view="ndAutoWarmup">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
            <span>Auto Warmup</span>
          </button>
          <button class="nav-item" data-view="ndRandomPosting">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
            <span>Random Posting</span>
          </button>
          <button class="nav-item" data-view="ndFbListings">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
            <span>FB Listings</span>
          </button>
          <button class="nav-item" data-view="ndAccountCreation">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
            <span>ND Account Creation</span>
          </button>
          <button class="nav-item" data-view="ndBulkCreateProfiles">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
            <span>Bulk Create Profiles</span>
          </button>
          <button class="nav-item" data-view="sheetSettings">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21.2 15c.7-1.2 1-2.5.7-3.9-.6-2-2.4-3.5-4.4-3.5h-1.2c-.7-1.9-2.1-3.3-4-3.9-2.4-.8-5.1.2-6.5 2.3l1.8 1.4c1-1.4 2.8-2 4.4-1.5 1.2.4 2 1.4 2.4 2.6V9h1.2c1.3 0 2.4 1 2.8 2.2.3 1 .1 2.1-.4 3l1.7 1z"></path></svg>
            <span>Sheet Settings</span>
          </button>
`;

indexHtml = indexHtml.replace('</nav>', navInsert + '        </nav>');

const createAutomationView = (id, title, desc, extraConfig) => `
        <section class="view" id="${id}View">
          <div class="page-heading">
            <div class="nd-automation-header">
              <p class="eyebrow">ND Automation</p>
              <h1>${title}</h1>
              <p class="page-subtitle">${desc}</p>
            </div>
            <button class="primary-button fetch-rows-btn" data-task="${id}">
              <svg viewBox="0 0 24 24"><path d="M2 12h20M12 2v20"/></svg>
              Fetch Rows
            </button>
          </div>
          <div class="nd-config-panel">
            <div class="two-column">
              <label class="field"><span>Concurrency</span><input type="number" id="${id}-concurrency" value="3" min="1" max="20"></label>
              ${extraConfig}
            </div>
            <div class="nd-actions" style="margin-top: 16px; display: flex; gap: 8px;">
              <button class="primary-button start-automation-btn" data-task="${id}">Start</button>
              <button class="secondary-button stop-automation-btn" data-task="${id}">Stop</button>
            </div>
          </div>
          <div class="nd-progress-area" id="${id}-progress-area" style="margin-top: 24px;">
            <h3>Progress</h3>
            <div class="nd-progress-bar"><div class="progress-fill" style="width: 0%;"></div></div>
            <div class="nd-log-output" id="${id}-log" style="height: 200px; overflow-y: auto; background: var(--panel-soft); padding: 12px; border: 1px solid var(--line); border-radius: 8px; margin-top: 12px;"></div>
          </div>
          <div class="table-wrap" style="margin-top: 24px;">
            <h3>Pending Rows</h3>
            <table class="nd-row-table">
              <thead><tr><th>ID</th><th>Row Data</th><th>Status</th></tr></thead>
              <tbody id="${id}-rows"></tbody>
            </table>
          </div>
        </section>`;

const viewsInsert = 
  createAutomationView('ndAutoPosting', 'Auto Posting', 'Automatically post to ND using provided configuration.', '<label class="field"><span>Target Names</span><input type="text" id="ndAutoPosting-targetNames" placeholder="Comma separated targets"></label>') +
  createAutomationView('ndAutoListing', 'Auto Listing', 'Automatically list items.', '<label class="field"><span>Spammers List</span><input type="text" id="ndAutoListing-spammers" placeholder="Spammers"></label>') +
  createAutomationView('ndAutoWarmup', 'Auto Warmup', 'Warmup accounts.', '') +
  createAutomationView('ndRandomPosting', 'Random Posting', 'Post random content.', '') +
  createAutomationView('ndFbListings', 'FB Listings', 'List items on FB.', '') +
  createAutomationView('ndAccountCreation', 'ND Account Creation', 'Create ND accounts automatically.', '') +
  createAutomationView('ndBulkCreateProfiles', 'Bulk Create Profiles', 'Create multiple profiles at once.', '') +
  `
        <section class="view" id="sheetSettingsView">
          <div class="page-heading">
            <div>
              <p class="eyebrow">Configuration</p>
              <h1>Sheet Settings</h1>
              <p class="page-subtitle">Configure Google Sheets integration and browser provider.</p>
            </div>
          </div>
          <div class="nd-config-panel sheet-settings-form" style="padding: 24px; border: 1px solid var(--line); border-radius: 12px; background: var(--panel);">
            <div class="form-section">
              <label class="field"><span>Google Apps Script URL</span><input type="url" id="sheet-gas-url" placeholder="https://script.google.com/macros/s/.../exec"></label>
              <div class="two-column">
                <label class="field"><span>Browser Provider</span><select id="sheet-browser-provider"><option value="incogniton">Incogniton</option><option value="adspower">AdsPower</option></select></label>
                <label class="field"><span>AdsPower API Key</span><input type="text" id="sheet-adspower-key" placeholder="API Key (if AdsPower)"></label>
              </div>
              <label class="field"><span>Profile OS</span><select id="sheet-profile-os"><option value="windows">Windows</option><option value="android">Android</option></select></label>
              <button class="primary-button" id="saveSheetSettingsBtn" style="margin-top: 16px;">Save Settings</button>
            </div>
          </div>
          <div style="margin-top: 24px; padding: 24px; border: 1px solid var(--line); border-radius: 12px; background: var(--panel);">
            <h3>Apps Script Code</h3>
            <p style="color: var(--muted); font-size: 13px;">Copy and deploy this code to your Google Apps Script project.</p>
            <pre style="background: var(--panel-soft); padding: 12px; border-radius: 8px; font-size: 12px; overflow-x: auto; border: 1px solid var(--line);"><code>// GAS code here</code></pre>
          </div>
        </section>
  `;

indexHtml = indexHtml.replace('</main>', viewsInsert + '</main>');
fs.writeFileSync(indexHtmlPath, indexHtml);

let appJs = fs.readFileSync(appJsPath, 'utf8');

const appJsAdditions = `
// ND Automation additions
async function fetchSheetRows(taskType) {
  try {
    const res = await api('/api/nd/fetch-rows', { method: 'POST', body: JSON.stringify({ taskType }) });
    toast('Fetching rows', \`Queued fetch for \${taskType}\`);
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
    toast('Automation Started', \`Started \${taskType}\`);
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
  tbody.innerHTML = rows.map(r => \`<tr><td>\${escapeHtml(r.id)}</td><td><pre style="margin:0; font-size:10px;">\${escapeHtml(JSON.stringify(r.data))}</pre></td><td>\${escapeHtml(r.status)}</td></tr>\`).join('');
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
    stopAutomation(task); // using task name as ID placeholder for simplicity
  }
  if (e.target.id === 'saveSheetSettingsBtn') {
    saveSheetSettings();
  }
});

// For realtime updates, assuming supabase is exposed or we simulate
// We would add listeners to supabase if it was available here.
`;

appJs = appJs.replace('$$(\'.nav-item[data-view]\').forEach((button) => button.addEventListener("click", () => {', appJsAdditions + '\n$$(\'.nav-item[data-view]\').forEach((button) => button.addEventListener("click", () => {'));
appJs = appJs.replace(/if \(view === "users"\) loadUsers\(\);/, 'if (view === "users") loadUsers();\n  if (view === "sheetSettings") loadSheetSettings();');

fs.writeFileSync(appJsPath, appJs);

let cloudApiJs = fs.readFileSync(cloudApiJsPath, 'utf8');
const cloudApiAdditions = `
  if (path === '/api/nd/tasks' && method === 'GET') {
    const res = await supabase.from('nd_automation_tasks').select('*').eq('workspace_id', membership.workspace_id);
    return { tasks: res.data || [] };
  }
  if (path === '/api/nd/tasks' && method === 'POST') {
    const res = await supabase.from('nd_automation_tasks').insert({ workspace_id: membership.workspace_id, ...body }).select().single();
    return res.data;
  }
  const taskPatchMatch = path.match(/^\\/api\\/nd\\/tasks\\/([^\\/]+)$/);
  if (taskPatchMatch && method === 'PATCH') {
    const res = await supabase.from('nd_automation_tasks').update(body).eq('id', decodeURIComponent(taskPatchMatch[1])).select().single();
    return res.data;
  }
  const taskResultsMatch = path.match(/^\\/api\\/nd\\/tasks\\/([^\\/]+)\\/results$/);
  if (taskResultsMatch && method === 'GET') {
    const res = await supabase.from('nd_automation_results').select('*').eq('task_id', decodeURIComponent(taskResultsMatch[1]));
    return { results: res.data || [] };
  }
  if (path === '/api/sheet-config' && method === 'GET') {
    const res = await supabase.from('workspace_settings').select('settings').eq('workspace_id', membership.workspace_id).maybeSingle();
    return { config: res.data?.settings?.sheetConfig || {} };
  }
  if (path === '/api/sheet-config' && method === 'POST') {
    let res = await supabase.from('workspace_settings').select('settings').eq('workspace_id', membership.workspace_id).maybeSingle();
    let currentSettings = res.data?.settings || {};
    currentSettings.sheetConfig = body.config;
    if (res.data) {
      await supabase.from('workspace_settings').update({ settings: currentSettings }).eq('workspace_id', membership.workspace_id);
    } else {
      await supabase.from('workspace_settings').insert({ workspace_id: membership.workspace_id, settings: currentSettings });
    }
    return { status: 'ok' };
  }
  if (path === '/api/nd/fetch-rows' && method === 'POST') {
    return queueCommand('fetch_sheet_rows', null, { taskType: body.taskType });
  }
  if (path === '/api/nd/start' && method === 'POST') {
    return queueCommand('start_automation', null, { taskType: body.taskType, config: body.config });
  }
  if (path === '/api/nd/stop' && method === 'POST') {
    return queueCommand('stop_automation', null, { taskId: body.taskId });
  }
`;

cloudApiJs = cloudApiJs.replace('throw new Error(`Unsupported cloud route: ${method} ${path}`);', cloudApiAdditions + '\n  throw new Error(`Unsupported cloud route: ${method} ${path}`);');
fs.writeFileSync(cloudApiJsPath, cloudApiJs);

let stylesCss = fs.readFileSync(stylesCssPath, 'utf8');
const stylesCssAdditions = `
.nav-group-header { padding: 12px 13px 4px; font-size: 11px; font-weight: 700; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; }
.nd-automation-header { margin-bottom: 24px; }
.nd-config-panel { padding: 20px; border: 1px solid var(--line); border-radius: 12px; background: var(--panel-soft); }
.nd-progress-bar { height: 8px; background: var(--line); border-radius: 4px; overflow: hidden; }
.nd-progress-bar .progress-fill { height: 100%; background: var(--primary); transition: width 0.3s ease; }
.nd-log-output { font-family: ui-monospace, monospace; font-size: 11px; color: var(--muted); }
.nd-row-table th { background: var(--panel-soft); color: var(--muted); padding: 10px; text-align: left; font-size: 11px; text-transform: uppercase; border-bottom: 1px solid var(--line); }
.nd-row-table td { padding: 10px; border-bottom: 1px solid var(--line); font-size: 12px; }
`;
fs.writeFileSync(stylesCssPath, stylesCss + stylesCssAdditions);

console.log('Successfully updated all 4 files.');
