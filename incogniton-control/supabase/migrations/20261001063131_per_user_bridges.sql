-- Each KitKat user runs a bridge on their own Incogniton PC.
-- Bridge writes are restricted to agents owned by the signed-in user, while
-- profile rows and commands continue to respect workspace group access.

drop policy if exists agents_insert on public.agents;
drop policy if exists agents_update on public.agents;
drop policy if exists agents_delete on public.agents;

create policy agents_insert
on public.agents
for insert
to authenticated
with check (
  created_by = (select auth.uid())
  and (select public.is_workspace_member(workspace_id))
);

create policy agents_update
on public.agents
for update
to authenticated
using (
  (
    created_by = (select auth.uid())
    and (select public.is_workspace_member(workspace_id))
  )
  or (select public.current_member_role(workspace_id)) = 'super_admin'
)
with check (
  (
    created_by = (select auth.uid())
    and (select public.is_workspace_member(workspace_id))
  )
  or (select public.current_member_role(workspace_id)) = 'super_admin'
);

create policy agents_delete
on public.agents
for delete
to authenticated
using (
  (
    created_by = (select auth.uid())
    and (select public.is_workspace_member(workspace_id))
  )
  or (select public.current_member_role(workspace_id)) = 'super_admin'
);

drop policy if exists browser_profiles_bridge_insert on public.browser_profiles;
drop policy if exists browser_profiles_bridge_update on public.browser_profiles;
drop policy if exists browser_profiles_bridge_delete on public.browser_profiles;

create policy browser_profiles_bridge_insert
on public.browser_profiles
for insert
to authenticated
with check (
  (select public.can_access_group(workspace_id, group_name))
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
  (select public.can_access_group(workspace_id, group_name))
  and exists (
    select 1
    from public.agents a
    where a.id = browser_profiles.agent_id
      and a.workspace_id = browser_profiles.workspace_id
      and a.created_by = (select auth.uid())
  )
)
with check (
  (select public.can_access_group(workspace_id, group_name))
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
  (select public.can_access_group(workspace_id, group_name))
  and exists (
    select 1
    from public.agents a
    where a.id = browser_profiles.agent_id
      and a.workspace_id = browser_profiles.workspace_id
      and a.created_by = (select auth.uid())
  )
);

drop policy if exists commands_insert on public.commands;

create policy commands_insert
on public.commands
for insert
to authenticated
with check (
  requested_by = (select auth.uid())
  and (select public.is_workspace_member(workspace_id))
  and (
    (
      profile_id is null
      and exists (
        select 1
        from public.agents a
        where a.id = commands.agent_id
          and a.workspace_id = commands.workspace_id
          and a.created_by = (select auth.uid())
          and a.active = true
      )
      and (
        action <> 'create_profile'
        or (select public.can_access_group(
          workspace_id,
          coalesce(nullif(payload ->> 'profile_group', ''), 'Unassigned')
        ))
      )
    )
    or exists (
      select 1
      from public.browser_profiles bp
      where bp.workspace_id = commands.workspace_id
        and bp.profile_id = commands.profile_id
        and bp.agent_id = commands.agent_id
        and (select public.can_access_group(bp.workspace_id, bp.group_name))
    )
  )
);

drop policy if exists commands_bridge_update on public.commands;

create policy commands_bridge_update
on public.commands
for update
to authenticated
using (
  (select public.is_workspace_member(workspace_id))
  and exists (
    select 1
    from public.agents a
    where a.id = commands.agent_id
      and a.workspace_id = commands.workspace_id
      and a.created_by = (select auth.uid())
  )
)
with check (
  (select public.is_workspace_member(workspace_id))
  and exists (
    select 1
    from public.agents a
    where a.id = commands.agent_id
      and a.workspace_id = commands.workspace_id
      and a.created_by = (select auth.uid())
  )
);
