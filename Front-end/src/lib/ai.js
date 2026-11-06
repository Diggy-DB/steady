import { supabase } from "./supabase";

// The AI service (ai/src/ai/server.py). It checks the user's Supabase token itself,
// and only proposes changes; Accept / Decline go through it so they're checked again.
const AI_URL = import.meta.env.VITE_AI_API_URL ?? "http://localhost:8000";

async function call(path, { method = "POST", body } = {}) {
  const { data } = await supabase.auth.getSession();
  const options = {
    method,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${data.session?.access_token ?? ""}`,
    },
  };
  if (body !== undefined) options.body = JSON.stringify(body);
  const response = await fetch(`${AI_URL}${path}`, options);
  const json = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof json.detail === "string" ? json.detail : JSON.stringify(json.detail ?? json);
    throw new Error(detail || `AI service error ${response.status}`);
  }
  return json;
}

export const ai = {
  // history: earlier turns as {role: "user" | "assistant", content}, final answers only.
  chat: (message, history) => call("/chat", { body: { message, history } }),
  accept: (suggestionId) => call(`/suggestions/${suggestionId}/accept`),
  decline: (suggestionId) => call(`/suggestions/${suggestionId}/decline`),

  // Long-term memory: what Steady has learned about the user from chats and journal entries.
  memories: () => call("/memories", { method: "GET" }),
  forgetMemory: (memoryId) => call(`/memories/${memoryId}`, { method: "DELETE" }),
  rememberJournal: (journalId) => call(`/memories/journal/${journalId}`),
  forgetJournal: (journalId) => call(`/memories/journal/${journalId}`, { method: "DELETE" }),
};
