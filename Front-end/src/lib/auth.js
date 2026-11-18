import { supabase } from "./supabase";

// Google sign-in and linking. Supabase does the OAuth work: Google sends people back to this site's address
// (allowed in Supabase's URL settings), where the client finishes signing in (lib/supabase.js).

export const GOOGLE_PENDING = "google-sign-up"; // sign-up answers waiting for a Google sign-in (lib/onboarding.js)
const RETURN_KEY = "steady.returnTo";

const siteAddress = () => window.location.origin + import.meta.env.BASE_URL;

// Supabase's messages about Google, in plain language.
export function friendlyGoogleError(message = "") {
  const m = message.toLowerCase();
  if (m.includes("manual linking")) return "Connecting Google isn't switched on for this site yet. Ask the team to turn on manual linking in Supabase.";
  if (m.includes("provider is not enabled") || m.includes("unsupported provider")) return "Google sign-in isn't switched on for this site yet.";
  if (m.includes("already") && m.includes("linked")) return "That Google account is already connected to another Steady account.";
  if (m.includes("minimum") || m.includes("single identity")) return "This is your only way to sign in, so it can't be disconnected.";
  return message || "Google sign-in didn't work. Try again.";
}

export async function signInWithGoogle() {
  const { error } = await supabase.auth.signInWithOAuth({ provider: "google", options: { redirectTo: siteAddress() } });
  if (error) throw new Error(friendlyGoogleError(error.message));
}

// Connect Google to the signed-in account; afterwards the app opens Settings again (takeReturnTo).
export async function linkGoogle() {
  try {
    sessionStorage.setItem(RETURN_KEY, "settings");
  } catch {
    // storage blocked: they land on Home instead
  }
  const { error } = await supabase.auth.linkIdentity({ provider: "google", options: { redirectTo: siteAddress() } });
  if (error) throw new Error(friendlyGoogleError(error.message));
}

export async function unlinkGoogle(identity) {
  const { error } = await supabase.auth.unlinkIdentity(identity);
  if (error) throw new Error(friendlyGoogleError(error.message));
}

// The signed-in user's ways to sign in: [{provider: "email" | "google", identity_data: {email, ...}, ...}].
export async function loadIdentities() {
  const { data, error } = await supabase.auth.getUserIdentities();
  if (error) throw new Error(error.message);
  return data?.identities ?? [];
}

export const usesGoogle = (user) =>
  user?.app_metadata?.provider === "google" || (user?.app_metadata?.providers ?? []).includes("google");

// The page to open after coming back from Google, if one was asked for (and forget it).
export function takeReturnTo() {
  try {
    const page = sessionStorage.getItem(RETURN_KEY);
    sessionStorage.removeItem(RETURN_KEY);
    return page;
  } catch {
    return null;
  }
}
