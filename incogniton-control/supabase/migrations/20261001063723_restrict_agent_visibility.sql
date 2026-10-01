drop policy if exists agents_select on public.agents;

create policy agents_select
on public.agents
for select
to authenticated
using (
  (
    created_by = (select auth.uid())
    and (select public.is_workspace_member(workspace_id))
  )
  or (select public.current_member_role(workspace_id)) = 'super_admin'
);
