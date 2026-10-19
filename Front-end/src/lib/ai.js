import { supabase } from "./supabase";

// The AI service (ai/src/ai/server.py). It checks the user's Supabase token itself,
// and only proposes changes; Accept / Decline go through it so they're checked again.
const AI_URL = import.meta.env.VITE_AI_API_URL ?? "http://localhost:8000";

async function call(path, body = {}) {
  const { data } = await supabase.auth.getSession();
  const response = await fetch(`${AI_URL}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${data.session?.access_token ?? ""}`,
    },
    body: JSON.stringify(body),
  });
  const json = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof json.detail === "string" ? json.detail : JSON.stringify(json.detail ?? json);
    throw new Error(detail || `AI service error ${response.status}`);
  }
  return json;
}

export const ai = {
  // history: earlier turns as {role: "user" | "assistant", content}, final answers only.
  chat: (message, history) => call("/chat", { message, history }),
  accept: (suggestionId) => call(`/suggestions/${suggestionId}/accept`),
  decline: (suggestionId) => call(`/suggestions/${suggestionId}/decline`),
};
