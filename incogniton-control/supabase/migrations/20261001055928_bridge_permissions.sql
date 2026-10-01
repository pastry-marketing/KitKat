-- A KitKat Bridge runs under the signed-in Super Admin who paired the PC.
-- Keep bridge writes limited to agents owned by that same user and workspace.

create unique index agents_owner_machine_unique
on public.agents (workspace_id, created_by, machine_label)
where machine_label is not null;

create policy browser_profiles_bridge_insert
on public.browser_profiles
for insert
to authenticated
with check (
  (select public.current_member_role(workspace_id)) = 'super_admin'
  and exists (
    select 1
    from public.agents a
    where a.id = browser_profiles.agent_id
      and a.workspace_id = browser_profiles.workspace_id
      and a.created_by = (select auth.uid())
      and a.active = true
  )
);

create policy browser_profiles_bridge_update
on public.browser_profiles
for update
to authenticated
using (
  (select public.current_member_role(workspace_id)) = 'super_admin'
  and exists (
    select 1
    from public.agents a
    where a.id = browser_profiles.agent_id
      and a.workspace_id = browser_profiles.workspace_id
      and a.created_by = (select auth.uid())
  )
)
with check (
  (select public.current_member_role(workspace_id)) = 'super_admin'
  and exists (
    select 1
    from public.agents a
    where a.id = browser_profiles.agent_id
      and a.workspace_id = browser_profiles.workspace_id
      and a.created_by = (select auth.uid())
      and a.active = true
  )
);

create policy browser_profiles_bridge_delete
on public.browser_profiles
for delete
to authenticated
using (
  (select public.current_member_role(workspace_id)) = 'super_admin'
  and exists (
    select 1
    from public.agents a
    where a.id = browser_profiles.agent_id
      and a.workspace_id = browser_profiles.workspace_id
      and a.created_by = (select auth.uid())
  )
);

create policy commands_bridge_update
on public.commands
for update
to authenticated
using (
  (select public.current_member_role(workspace_id)) = 'super_admin'
  and exists (
    select 1
    from public.agents a
    where a.id = commands.agent_id
      and a.workspace_id = commands.workspace_id
      and a.created_by = (select auth.uid())
  )
)
with check (
  (select public.current_member_role(workspace_id)) = 'super_admin'
  and exists (
    select 1
    from public.agents a
    where a.id = commands.agent_id
      and a.workspace_id = commands.workspace_id
      and a.created_by = (select auth.uid())
  )
);
