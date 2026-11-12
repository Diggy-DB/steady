import { supabase } from "./supabase";

// The AI service (ai/src/ai/server.py). It checks the user's Supabase token itself,
// and only proposes changes; Accept / Decline go through it so they're checked again.
const AI_URL = import.meta.env.VITE_AI_API_URL ?? "http://localhost:8000";

async function call(path, { method = "POST", body, form } = {}) {
  const { data } = await supabase.auth.getSession();
  const options = {
    method,
    headers: { Authorization: `Bearer ${data.session?.access_token ?? ""}` },
  };
  if (form !== undefined) {
    options.body = form; // the browser sets the multipart Content-Type itself
  } else if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  let response;
  try {
    response = await fetch(`${AI_URL}${path}`, options);
  } catch {
    throw new Error("Can't reach the AI server. It may be restarting or switched off; try again in a minute.");
  }
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
  // The same in the background: start it, then ask for it until it's done (a long answer can't time out).
  startChat: (message, history) => call("/chat/start", { body: { message, history } }),
  chatJob: (chatId) => call(`/chat/jobs/${chatId}`, { method: "GET" }),
  accept: (suggestionId) => call(`/suggestions/${suggestionId}/accept`),

  // The daily overview of yesterday: written once a day (then saved), or again on refresh.
  overview: () => call("/overview", { method: "GET" }),
  refreshOverview: () => call("/overview/refresh"),

  // Syllabus import: upload starts reading the file; ask for the result until it's done.
  uploadSyllabus: (file) => {
    const form = new FormData();
    form.append("file", file);
    return call("/syllabus", { form });
  },
  syllabusImport: (importId) => call(`/syllabus/${importId}`, { method: "GET" }),
  decline: (suggestionId) => call(`/suggestions/${suggestionId}/decline`),

  // Long-term memory: what Steady has learned about the user from chats and journal entries.
  memories: () => call("/memories", { method: "GET" }),
  forgetMemory: (memoryId) => call(`/memories/${memoryId}`, { method: "DELETE" }),
  rememberJournal: (journalId) => call(`/memories/journal/${journalId}`),
  forgetJournal: (journalId) => call(`/memories/journal/${journalId}`, { method: "DELETE" }),
};
