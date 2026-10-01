-- ND Full Automated: Automation Tasks & Results
-- Adds tables for managing sheet-driven automation tasks (auto posting, listing, warmup, etc.)

-- 1. Enum for ND automation task types
CREATE TYPE public.nd_task_type AS ENUM (
    'auto_posting',
    'auto_listing',
    'auto_warmup',
    'auto_random_posting',
    'fb_listing',
    'nd_account_creation',
    'bulk_create'
);

-- 2. Enum for ND task status
CREATE TYPE public.nd_task_status AS ENUM (
    'queued',
    'running',
    'completed',
    'failed',
    'stopped'
);

-- 3. Enum for individual row result status
CREATE TYPE public.nd_result_status AS ENUM (
    'pending',
    'running',
    'success',
    'failed',
    'skipped',
    'stopped'
);

-- 4. Sheet configuration per workspace (Google Apps Script URL, browser provider settings)
CREATE TABLE public.sheet_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    apps_script_url TEXT NOT NULL DEFAULT '',
    browser_provider TEXT NOT NULL DEFAULT 'incogniton' CHECK (browser_provider IN ('incogniton', 'adspower')),
    adspower_api_key TEXT DEFAULT '',
    profile_os TEXT NOT NULL DEFAULT 'windows' CHECK (profile_os IN ('windows', 'android')),
    incogniton_path TEXT DEFAULT '',
    adspower_path TEXT DEFAULT '',
    created_by UUID NOT NULL DEFAULT auth.uid() REFERENCES auth.users(id),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(workspace_id)
);

-- 5. Automation tasks (each represents one batch run triggered from the web UI)
CREATE TABLE public.nd_automation_tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    agent_id UUID REFERENCES public.agents(id) ON DELETE SET NULL,
    task_type public.nd_task_type NOT NULL,
    sheet_name TEXT NOT NULL DEFAULT '',
    status public.nd_task_status NOT NULL DEFAULT 'queued',
    concurrency INT NOT NULL DEFAULT 3 CHECK (concurrency BETWEEN 1 AND 20),
    config JSONB NOT NULL DEFAULT '{}',
    progress JSONB NOT NULL DEFAULT '{"total": 0, "completed": 0, "failed": 0}',
    error_message TEXT,
    requested_by UUID NOT NULL DEFAULT auth.uid() REFERENCES auth.users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

-- 6. Individual automation results (one row per profile/sheet-row processed)
CREATE TABLE public.nd_automation_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL REFERENCES public.nd_automation_tasks(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    profile_name TEXT NOT NULL DEFAULT '',
    profile_id TEXT DEFAULT '',
    row_number INT,
    status public.nd_result_status NOT NULL DEFAULT 'pending',
    state TEXT DEFAULT 'QUEUED',
    post_link TEXT DEFAULT '',
    screenshot_url TEXT DEFAULT '',
    chat_count INT,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 7. Indexes
CREATE INDEX idx_nd_tasks_workspace ON public.nd_automation_tasks(workspace_id);
CREATE INDEX idx_nd_tasks_agent ON public.nd_automation_tasks(agent_id);
CREATE INDEX idx_nd_tasks_status ON public.nd_automation_tasks(status);
CREATE INDEX idx_nd_results_task ON public.nd_automation_results(task_id);
CREATE INDEX idx_nd_results_workspace ON public.nd_automation_results(workspace_id);
CREATE INDEX idx_sheet_configs_workspace ON public.sheet_configs(workspace_id);

-- 8. Auto-update updated_at on nd_automation_results
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_nd_results_updated
    BEFORE UPDATE ON public.nd_automation_results
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TRIGGER trg_sheet_configs_updated
    BEFORE UPDATE ON public.sheet_configs
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- 9. Enable RLS
ALTER TABLE public.sheet_configs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.nd_automation_tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.nd_automation_results ENABLE ROW LEVEL SECURITY;

-- 10. RLS Policies for sheet_configs
CREATE POLICY sheet_configs_select ON public.sheet_configs FOR SELECT
    USING (public.is_workspace_member(workspace_id));

CREATE POLICY sheet_configs_insert ON public.sheet_configs FOR INSERT
    WITH CHECK (
        public.current_member_role(workspace_id) IN ('super_admin', 'nd_admin', 'fb_admin')
    );

CREATE POLICY sheet_configs_update ON public.sheet_configs FOR UPDATE
    USING (
        public.current_member_role(workspace_id) IN ('super_admin', 'nd_admin', 'fb_admin')
    );

-- 11. RLS Policies for nd_automation_tasks
CREATE POLICY nd_tasks_select ON public.nd_automation_tasks FOR SELECT
    USING (public.is_workspace_member(workspace_id));

CREATE POLICY nd_tasks_insert ON public.nd_automation_tasks FOR INSERT
    WITH CHECK (public.is_workspace_member(workspace_id));

-- Bridge can update task status (running, completed, failed)
CREATE POLICY nd_tasks_update ON public.nd_automation_tasks FOR UPDATE
    USING (public.is_workspace_member(workspace_id));

-- 12. RLS Policies for nd_automation_results
CREATE POLICY nd_results_select ON public.nd_automation_results FOR SELECT
    USING (public.is_workspace_member(workspace_id));

CREATE POLICY nd_results_insert ON public.nd_automation_results FOR INSERT
    WITH CHECK (public.is_workspace_member(workspace_id));

CREATE POLICY nd_results_update ON public.nd_automation_results FOR UPDATE
    USING (public.is_workspace_member(workspace_id));

-- 13. Enable Realtime for live progress tracking
ALTER PUBLICATION supabase_realtime ADD TABLE public.nd_automation_tasks;
ALTER PUBLICATION supabase_realtime ADD TABLE public.nd_automation_results;
