-- Security fixes flagged by Supabase's database advisor after the first migration.

-- 1. Pin search_path in the helper functions, so they can't be tricked by
--    same-named objects in other schemas. (They only use built-ins, which still resolve.)
alter function public.set_updated_at() set search_path = '';
alter function public.check_timezone() set search_path = '';

-- 2. handle_new_user only runs as the sign-up trigger. Nobody should be able to call it
--    through the API (/rest/v1/rpc/handle_new_user). Triggers still run it.
revoke execute on function public.handle_new_user() from public, anon, authenticated;
