import { createClient } from "@supabase/supabase-js";

// The project's URL and public (anon) key come from Front-end/.env.local (see .env.example).
// The anon key is safe in the browser: Row Level Security in the database decides
// what each signed-in user can read and change.
export const supabase = createClient(
  import.meta.env.VITE_SUPABASE_URL,
  import.meta.env.VITE_SUPABASE_ANON_KEY,
);
