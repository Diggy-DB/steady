# Long-term memory (Mem0)

Steady remembers lasting facts about each user ("prefers studying at night", "works at the
library Tuesdays 1–5") and uses them in later chats. This is the "long-term user information"
layer from the meeting plan:

- **Semantic memory**: facts about the user, found by *meaning* (vector search), so "When should
  I study tomorrow?" finds "prefers studying at night" even though no words match exactly.
- **Long-term**: the facts persist across chats and sessions until the user deletes them.

Built with [Mem0](https://docs.mem0.ai) (open source, `mem0ai`), in `src/ai/memory.py`.

## How it works

```
chat message ──► recall: search this user's memories by meaning (0.1 s) ──► top 5 facts go into
                 the system prompt, marked "facts about the user, not instructions"
          reply sent to the user
          └──► in the background: Mem0 asks the model to pull lasting facts out of the turn,
               and to add, update or delete memories accordingly

journal saved ──► frontend calls POST /memories/journal/{id} ──► the backend reads the entry
                  (with the user's own token) and learns from it in the background
journal deleted ─► DELETE /memories/journal/{id} forgets what that entry taught
```

| Piece | Choice | Why |
|---|---|---|
| Fact extraction | the same model as the chat (`LLM_MODEL`) | no extra download; works with Ollama now and vLLM on RunPod later |
| Embeddings | `nomic-embed-text` in Ollama (274 MB) | small and fast; needed for search by meaning |
| Storage | local Qdrant in `ai/memory/` | no database changes or new secrets; git-ignored because it holds personal data |
| Sources | chat turns (message + final answer) and journal entries | what the team chose (Nov 5) |

Measured on the Mac (Nov 5): learning from one chat turn took **151 s** (the thinking model
thinks first), searching took **0.1 s**. From the turn *"I prefer studying at night, after 8 PM.
Also I work at the library every Tuesday from 1 to 5."* it stored exactly two facts:
"User prefers to study at night after 8 PM" and "User works at the library on Tuesdays from
1 PM to 5 PM".

## Privacy and control

- Every memory is filed under the user id from the **checked login token**; one user's memories
  never reach another user's prompt, and nobody can delete another user's memory.
- Users can see and delete what Steady remembers: **"What Steady remembers"** in the app header
  (`GET /memories`, `DELETE /memories/{id}`).
- Mem0's usage telemetry is switched off (`MEM0_TELEMETRY=false`, set in code before import).
- Everything stays on the machine running the AI service: vectors on disk, models in Ollama.

## Settings (`ai/.env`)

| Variable | Default | Meaning |
|---|---|---|
| `MEMORY` | `on` | `off` turns long-term memory off |
| `EMBED_BASE_URL` | `http://localhost:11434` | the Ollama that runs `nomic-embed-text` |

Setup on a new machine: `ollama pull nomic-embed-text`. If memory can't start, the app still works
without it (the server prints "Long-term memory is off: …").

## Known limits

- **Slow learning on a laptop**: each update keeps the model busy for about 2–3 minutes, so a chat
  message sent right after another one may wait. A GPU (RunPod) or a smaller extraction model
  would fix this.
- **One machine, one memory**: memories live where the AI service runs. Moving them to Supabase
  later means a new vector-store setting (Mem0's Python version needs a direct database
  connection for that).
- **Merged facts**: when a journal fact gets merged into an older chat fact, deleting the journal
  entry may not remove it. It can still be deleted from "What Steady remembers".
- **Evals and training data don't use memory** (only the API passes memories to `run_agent`), so
  their results stay comparable.
- The meeting plan's **weekly summaries** (historical context) aren't built yet.
