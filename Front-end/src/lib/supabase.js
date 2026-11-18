import { createClient } from "@supabase/supabase-js";

// The project's URL and public (anon) key come from Front-end/.env.local (see .env.example).
// The anon key is safe in the browser: Row Level Security in the database decides
// what each signed-in user can read and change.
//
// PKCE: after Google sign-in, Supabase sends people back with ?code=… in the query string, which this client
// trades for a session on load. The default way puts the tokens after the #, where this app's routes (#/login,
// #/settings) live, and the two would trip over each other.
export const supabase = createClient(
  import.meta.env.VITE_SUPABASE_URL,
  import.meta.env.VITE_SUPABASE_ANON_KEY,
  { auth: { flowType: "pkce" } },
);
