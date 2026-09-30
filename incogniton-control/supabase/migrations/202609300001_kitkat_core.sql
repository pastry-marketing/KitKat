create extension if not exists pgcrypto with schema extensions;

create type public.app_role as enum (
  'super_admin',
  'fb_admin',
  'nd_admin',
  'fb_operator',
  'nd_operator'
);

create type public.command_status as enum ('queued', 'claimed', 'completed', 'failed', 'cancelled');
create type public.run_status as enum ('queued', 'launching', 'running', 'completed', 'failed', 'cancelled', 'interrupted');

create table public.workspaces (
  id uuid primary key default gen_random_uuid(),
  name text not null check (char_length(name) between 1 and 80),
  created_by uuid not null references auth.users(id) on delete restrict,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.workspace_members (
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  display_name text not null check (char_length(display_name) between 1 and 80),
  role public.app_role not null,
  active boolean not null default true,
  created_by uuid references auth.users(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (workspace_id, user_id)
);

create table public.member_group_access (
  workspace_id uuid not null,
  user_id uuid not null,
  group_name text not null check (char_length(group_name) between 1 and 120),
  created_at timestamptz not null default now(),
  primary key (workspace_id, user_id, group_name),
  foreign key (workspace_id, user_id)
    references public.workspace_members(workspace_id, user_id)
    on delete cascade
);

create table public.agents (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  name text not null check (char_length(name) between 1 and 80),
  machine_label text,
  active boolean not null default true,
  last_seen_at timestamptz,
  created_by uuid not null references auth.users(id) on delete restrict,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.browser_profiles (
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  profile_id text not null,
  agent_id uuid not null references public.agents(id) on delete cascade,
  name text not null,
  group_name text not null default 'Unassigned',
  platform text,
  status text not null default 'unknown',
  last_synced_at timestamptz not null default now(),
  metadata jsonb not null default '{}'::jsonb,
  primary key (workspace_id, profile_id)
);

create table public.commands (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  agent_id uuid not null references public.agents(id) on delete cascade,
  profile_id text,
  action text not null check (action in ('sync_profiles', 'create_profile', 'launch_profile', 'stop_profile', 'clone_profile', 'delete_profile', 'run_workflow', 'cancel_run')),
  payload jsonb not null default '{}'::jsonb,
  status public.command_status not null default 'queued',
  requested_by uuid not null references auth.users(id) on delete restrict,
  claimed_at timestamptz,
  completed_at timestamptz,
  result jsonb,
  error_message text,
  created_at timestamptz not null default now()
);

create table public.workflows (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  name text not null check (char_length(name) between 1 and 80),
  description text not null default '' check (char_length(description) <= 240),
  destination_url text not null,
  created_by uuid not null references auth.users(id) on delete restrict,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.workflow_steps (
  id uuid primary key default gen_random_uuid(),
  workflow_id uuid not null references public.workflows(id) on delete cascade,
  position integer not null check (position >= 0),
  action text not null check (action in ('type', 'click', 'wait', 'press')),
  selector text,
  value text,
  label text check (char_length(label) <= 80),
  unique (workflow_id, position)
);

create table public.automation_runs (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  workflow_id uuid references public.workflows(id) on delete set null,
  agent_id uuid not null references public.agents(id) on delete cascade,
  profile_id text not null,
  requested_by uuid not null references auth.users(id) on delete restrict,
  status public.run_status not null default 'queued',
  current_step integer not null default 0,
  total_steps integer not null default 0,
  message text,
  logs jsonb not null default '[]'::jsonb,
  started_at timestamptz,
  finished_at timestamptz,
  created_at timestamptz not null default now()
);

create index workspace_members_user_id_idx on public.workspace_members(user_id);
create index member_group_access_user_id_idx on public.member_group_access(user_id);
create index agents_workspace_id_idx on public.agents(workspace_id);
create index browser_profiles_agent_id_idx on public.browser_profiles(agent_id);
create index browser_profiles_group_idx on public.browser_profiles(workspace_id, group_name);
create index commands_agent_queue_idx on public.commands(agent_id, status, created_at);
create index commands_workspace_created_idx on public.commands(workspace_id, created_at desc);
create index workflows_workspace_idx on public.workflows(workspace_id, updated_at desc);
create index workflow_steps_workflow_idx on public.workflow_steps(workflow_id, position);
create index automation_runs_workspace_idx on public.automation_runs(workspace_id, created_at desc);
create index agents_created_by_idx on public.agents(created_by);
create index automation_runs_agent_id_idx on public.automation_runs(agent_id);
create index automation_runs_requested_by_idx on public.automation_runs(requested_by);
create index automation_runs_workflow_id_idx on public.automation_runs(workflow_id);
create index commands_requested_by_idx on public.commands(requested_by);
create index workflows_created_by_idx on public.workflows(created_by);
create index workspace_members_created_by_idx on public.workspace_members(created_by);
create index workspaces_created_by_idx on public.workspaces(created_by);

create or replace function public.set_updated_at()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create trigger workspaces_set_updated_at before update on public.workspaces
for each row execute function public.set_updated_at();
create trigger workspace_members_set_updated_at before update on public.workspace_members
for each row execute function public.set_updated_at();
create trigger agents_set_updated_at before update on public.agents
for each row execute function public.set_updated_at();
create trigger workflows_set_updated_at before update on public.workflows
for each row execute function public.set_updated_at();

create or replace function public.current_member_role(target_workspace uuid)
returns public.app_role
language sql
stable
security definer
set search_path = ''
as $$
  select wm.role
  from public.workspace_members wm
  where wm.workspace_id = target_workspace
    and wm.user_id = (select auth.uid())
    and wm.active
  limit 1
$$;

create or replace function public.is_workspace_member(target_workspace uuid)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select public.current_member_role(target_workspace) is not null
$$;

create or replace function public.can_access_group(target_workspace uuid, target_group text)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select case
    when public.current_member_role(target_workspace) = 'super_admin' then true
    else exists (
      select 1
      from public.member_group_access mga
      where mga.workspace_id = target_workspace
        and mga.user_id = (select auth.uid())
        and lower(mga.group_name) = lower(coalesce(target_group, 'Unassigned'))
    )
  end
$$;

create or replace function public.can_manage_role(target_workspace uuid, target_role public.app_role)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select case public.current_member_role(target_workspace)
    when 'super_admin' then true
    when 'fb_admin' then target_role = 'fb_operator'
    when 'nd_admin' then target_role = 'nd_operator'
    else false
  end
$$;

create or replace function public.bootstrap_workspace(workspace_name text, display_name text)
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
  new_workspace_id uuid;
begin
  if (select auth.uid()) is null then
    raise exception 'Authentication required';
  end if;
  if exists (select 1 from public.workspace_members where user_id = (select auth.uid())) then
    raise exception 'User already belongs to a workspace';
  end if;
  insert into public.workspaces (name, created_by)
  values (left(trim(workspace_name), 80), (select auth.uid()))
  returning id into new_workspace_id;
  insert into public.workspace_members (workspace_id, user_id, display_name, role, created_by)
  values (new_workspace_id, (select auth.uid()), left(trim(display_name), 80), 'super_admin', (select auth.uid()));
  return new_workspace_id;
end;
$$;

alter table public.workspaces enable row level security;
alter table public.workspace_members enable row level security;
alter table public.member_group_access enable row level security;
alter table public.agents enable row level security;
alter table public.browser_profiles enable row level security;
alter table public.commands enable row level security;
alter table public.workflows enable row level security;
alter table public.workflow_steps enable row level security;
alter table public.automation_runs enable row level security;

create policy workspaces_select on public.workspaces for select to authenticated
using (public.is_workspace_member(id));
create policy workspaces_update on public.workspaces for update to authenticated
using (public.current_member_role(id) = 'super_admin')
with check (public.current_member_role(id) = 'super_admin');

create policy members_select on public.workspace_members for select to authenticated
using (
  user_id = (select auth.uid())
  or public.current_member_role(workspace_id) = 'super_admin'
  or (public.current_member_role(workspace_id) = 'fb_admin' and role = 'fb_operator')
  or (public.current_member_role(workspace_id) = 'nd_admin' and role = 'nd_operator')
);
create policy members_insert on public.workspace_members for insert to authenticated
with check (public.can_manage_role(workspace_id, role));
create policy members_update on public.workspace_members for update to authenticated
using (public.can_manage_role(workspace_id, role))
with check (public.can_manage_role(workspace_id, role));
create policy members_delete on public.workspace_members for delete to authenticated
using (user_id <> (select auth.uid()) and public.can_manage_role(workspace_id, role));

create policy group_access_select on public.member_group_access for select to authenticated
using (
  user_id = (select auth.uid())
  or public.current_member_role(workspace_id) = 'super_admin'
);
create policy group_access_insert on public.member_group_access for insert to authenticated
with check (public.current_member_role(workspace_id) = 'super_admin');
create policy group_access_delete on public.member_group_access for delete to authenticated
using (public.current_member_role(workspace_id) = 'super_admin');

create policy agents_select on public.agents for select to authenticated
using (public.is_workspace_member(workspace_id));
create policy agents_insert on public.agents for insert to authenticated
with check (public.current_member_role(workspace_id) = 'super_admin' and created_by = (select auth.uid()));
create policy agents_update on public.agents for update to authenticated
using (public.current_member_role(workspace_id) = 'super_admin')
with check (public.current_member_role(workspace_id) = 'super_admin');
create policy agents_delete on public.agents for delete to authenticated
using (public.current_member_role(workspace_id) = 'super_admin');

create policy browser_profiles_select on public.browser_profiles for select to authenticated
using (public.can_access_group(workspace_id, group_name));

create policy commands_select on public.commands for select to authenticated
using (
  public.is_workspace_member(workspace_id)
  and (
    profile_id is null
    or exists (
      select 1 from public.browser_profiles bp
      where bp.workspace_id = commands.workspace_id
        and bp.profile_id = commands.profile_id
        and public.can_access_group(bp.workspace_id, bp.group_name)
    )
  )
);
create policy commands_insert on public.commands for insert to authenticated
with check (
  requested_by = (select auth.uid())
  and public.is_workspace_member(workspace_id)
  and (
    profile_id is null
    or exists (
      select 1 from public.browser_profiles bp
      where bp.workspace_id = commands.workspace_id
        and bp.profile_id = commands.profile_id
        and public.can_access_group(bp.workspace_id, bp.group_name)
    )
  )
);

create policy workflows_select on public.workflows for select to authenticated
using (public.is_workspace_member(workspace_id));
create policy workflows_insert on public.workflows for insert to authenticated
with check (public.is_workspace_member(workspace_id) and created_by = (select auth.uid()));
create policy workflows_update on public.workflows for update to authenticated
using (created_by = (select auth.uid()) or public.current_member_role(workspace_id) in ('super_admin', 'fb_admin', 'nd_admin'))
with check (public.is_workspace_member(workspace_id));
create policy workflows_delete on public.workflows for delete to authenticated
using (created_by = (select auth.uid()) or public.current_member_role(workspace_id) = 'super_admin');

create policy workflow_steps_select on public.workflow_steps for select to authenticated
using (exists (select 1 from public.workflows w where w.id = workflow_steps.workflow_id and public.is_workspace_member(w.workspace_id)));
create policy workflow_steps_insert on public.workflow_steps for insert to authenticated
with check (exists (select 1 from public.workflows w where w.id = workflow_steps.workflow_id and (w.created_by = (select auth.uid()) or public.current_member_role(w.workspace_id) in ('super_admin', 'fb_admin', 'nd_admin'))));
create policy workflow_steps_update on public.workflow_steps for update to authenticated
using (exists (select 1 from public.workflows w where w.id = workflow_steps.workflow_id and (w.created_by = (select auth.uid()) or public.current_member_role(w.workspace_id) in ('super_admin', 'fb_admin', 'nd_admin'))));
create policy workflow_steps_delete on public.workflow_steps for delete to authenticated
using (exists (select 1 from public.workflows w where w.id = workflow_steps.workflow_id and (w.created_by = (select auth.uid()) or public.current_member_role(w.workspace_id) in ('super_admin', 'fb_admin', 'nd_admin'))));

create policy automation_runs_select on public.automation_runs for select to authenticated
using (
  public.is_workspace_member(workspace_id)
  and exists (
    select 1 from public.browser_profiles bp
    where bp.workspace_id = automation_runs.workspace_id
      and bp.profile_id = automation_runs.profile_id
      and public.can_access_group(bp.workspace_id, bp.group_name)
  )
);
create policy automation_runs_insert on public.automation_runs for insert to authenticated
with check (requested_by = (select auth.uid()) and public.is_workspace_member(workspace_id));

revoke execute on function public.current_member_role(uuid) from public, anon;
revoke execute on function public.is_workspace_member(uuid) from public, anon;
revoke execute on function public.can_access_group(uuid, text) from public, anon;
revoke execute on function public.can_manage_role(uuid, public.app_role) from public, anon;
revoke execute on function public.bootstrap_workspace(text, text) from public, anon;
grant execute on function public.current_member_role(uuid) to authenticated;
grant execute on function public.is_workspace_member(uuid) to authenticated;
grant execute on function public.can_access_group(uuid, text) to authenticated;
grant execute on function public.can_manage_role(uuid, public.app_role) to authenticated;
grant execute on function public.bootstrap_workspace(text, text) to authenticated;

alter publication supabase_realtime add table public.commands;
alter publication supabase_realtime add table public.browser_profiles;
alter publication supabase_realtime add table public.automation_runs;
