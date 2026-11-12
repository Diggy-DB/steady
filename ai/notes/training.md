# Training: self-RFT for Qwen3.5-4B

The plan (from `reports/Training the Steady planning agent.md`): the model learns from **its own
shortest passing tries** on practice tasks (rejection sampling, "self-RFT"). That teaches it to
**propose directly** (no code reminder), **think less**, and handle the newer requests (deletes,
journal, tasks, "next week", several goals at once) the way its best tries already do. It can't
teach skills the model never shows; a stronger teacher or a short RL stage would be the next step.

Updated Nov 12, 2026 for Qwen3.5-4B (the pipeline was first written for Qwen3-4B-Thinking-2507).

## 1. Practice tasks (`src/ai/synth.py`)

`make_task(seed)` gives a reproducible task: a random week for a fake student, a fake "now", a
question, and checks of the same kind the evals use. 15 types:

| Type | Example question | Checks |
|---|---|---|
| look_up | What's on my calendar tomorrow? | looked it up, names the day's events, proposed nothing |
| move_flexible | Can you move my run on Friday to 2:00 PM? | moved that event to that time |
| move_fixed | Please move my PHY 183 lecture to Tuesday evening. | proposed nothing, said it's fixed |
| task_time | Help me find time for my WRA 101 essay before it's due. | blocks covering the hours, all before the due day ends |
| activity_today | When could I practice piano today? | searched free time, proposed something |
| weekly_goal | I want to go to the gym twice this week, an hour each. | exactly the missing number of sessions |
| **multi_goal** | Can you fit my MTH 234 quiz prep into my week, plus time to go for a run twice? | the sessions **and** each assignment's hours before its due day |
| **delete_event** | Drop the gym on Thursday, I don't need it. | suggests deleting that event and nothing else |
| **delete_task** | Get rid of the PSY 101 project task, please. | suggests deleting that task and nothing else |
| **delete_fixed** | Delete my CHM 141 lecture on Wednesday. | deletes nothing, says it's fixed |
| **journal_add** | Journal note for today: I missed the bus and was late to class. | a journal suggestion for that day with the key word |
| **journal_edit** | In yesterday's journal, change 'two hours' to 'three hours'. | an edit that keeps the rest and drops the old words |
| **new_task** | Add a task to email my advisor by Thursday. | a new task due that day, no moves |
| **next_week** | What's due next week? (asked 2-6 days before the week) | looked up next week, names both assignments |
| **conflict** | Move my run to Wednesday at 1:15 PM. (during a lecture) | mentions the clash, never touches the lecture |

Every task also checks that nothing unasked was deleted or journaled, and that it finished.

**Kept apart from the evals** (`tests/test_synth.py`): other weeks (never an eval week), other
time zones, courses and wording, and no question equal to an eval question.

## 2. Collecting (`scripts/collect_traces.py`)

For each task the model tries several times (4 on the pod). A try is kept only if it **passes
every check** and finished on its own; of those, the one with the **fewest tokens** becomes the
example. Tries that passed only after a code reminder are used when no try passed without one,
with the reminder and the answer before it cut out (`"reminded": true` in their meta).

Never kept: tries where a round was redone without thinking (the model would learn to skip
thinking), and tries with a tool call whose arguments aren't a JSON object.

Output: `data/<date>-<model>.jsonl`, one conversation per line with `messages` and `tools`, the
format Hugging Face TRL and Unsloth read. It matches what vLLM shows the model when it serves it:

- the **tools** are the ones the agent offered for that question (`offered_tools`), not all of them;
- tool-call **arguments are objects**: Qwen3.5's chat template needs that, and vLLM converts them the same way;
- each turn's thinking is in `reasoning_content`; vLLM 0.33 passes it back to the template too.

`tests/test_collect.py` renders examples with the real Qwen3.5 template. `data/` is git-ignored.

```bash
uv run scripts/collect_traces.py --model qwen3.5:4b --tasks 5 --samples 2          # a quick local test
```

### A bug this found (fixed Nov 12)

Qwen3.5's chat template refuses any system message after the first one. The agent sent its two
reminders ("you recommended times but created no suggestions", "you said you suggest a delete but
made none") as system messages, so **on the vLLM pod every reminder was an HTTP 400 and the chat
failed**. Ollama on the Mac doesn't use that template, so local tests never saw it; the earlier pod
model (Qwen3-4B-Thinking) allowed it. Reminders are now user messages starting "(Automatic reminder
from the Steady app, not from the user.)", and a test renders one with the real template.

## 3. Fine-tuning (`scripts/train_lora.py`)

**LoRA** on the text part of the model only (transformers loads it alone as `Qwen3_5ForCausalLM`;
the picture reader isn't touched): rank 16 matrices next to **every projection in all 32 text
layers**: the 8 full-attention layers (q, k, v, o), the 24 linear-attention (Gated DeltaNet) layers
(in_proj_qkv, in_proj_z, in_proj_b, in_proj_a, out_proj) and every feed-forward part. That's 32.5M
trained numbers in 248 places, which fits on one 24 GB GPU.

| Choice | Value | Why |
|---|---|---|
| What it learns from | the model's own turns only, from after `<think>\n` (the server writes that) to `<\|im_end\|>` | system prompt, question and tool results are context, not text to imitate |
| Rank / alpha | 16 / 32 | a common starting point for behavior changes on small data |
| Learning rate | 1e-4, warm-up then cosine decay | gentle: sharpen habits, don't teach new knowledge |
| Epochs | 2 | small data (a few hundred conversations); more risks memorizing it |
| Update size | 8 conversations | one at a time on the GPU, gradients added up over 8 |
| Max length | 16,384 tokens | longer conversations are skipped, not cut |

Memory savers: **gradient checkpointing** and a **chunked loss** that scores only the trained
positions, a chunk at a time, instead of all 248,320 vocabulary entries everywhere. On the GPU,
`flash-linear-attention` gives the linear-attention layers their fast kernels (transformers uses it
when it's installed; without it training is many times slower). The script stops if any weight is
missing when loading, so a renaming problem can't silently start from random numbers.

## 4. Merging (`scripts/merge_lora.py`)

vLLM can't load LoRA adapters for Qwen3.5's linear-attention layers, so the adapter is **added into
a full copy of the model** (`W + (alpha/r)·B·A`, in float32, stored as bf16). Only the 248 trained
weights change; the picture reader, the `mtp` head, config, tokenizer, chat template and image
settings are copied as they are, so the result loads with the same `vllm serve` flags and still
reads syllabus photos. Training names layers `model.layers.N`; the checkpoint has
`model.language_model.layers.N`; every adapter matrix must land on exactly one weight.

`tests/test_train_merge.py` does it all on a tiny random Qwen3.5 (4 layers, real tokenizer): trains 3
steps, merges, and checks the text-only loader got every weight, the merged model gives the same
outputs as model + adapter, exactly the 31 trained weights changed (the picture reader and `mtp` didn't),
and the files were copied. It also checks the label masking on the real tokenizer.

```bash
uv run --with torch --with peft==0.21.2 pytest tests/test_train.py tests/test_train_merge.py
```

## 5. The training session (`deploy/runpod_train.sh`)

One script on one pod, about 2-2.5 hours (~$1.50 on an RTX 4090):

1. **Install** vLLM (the same environment the website's pod uses), the code, and the training
   libraries with the same torch version as vLLM (fails early if anything's missing).
2. **Original model:** the full eval suite (3 runs per case) and the syllabus import eval, while
   **collecting** at the same time: up to 400 tasks x 4 tries, at most 60 minutes.
3. **Fine-tune** (20-40 minutes) and **merge** into `/workspace/steady-ft`.
4. **Fine-tuned model:** the same evals.
5. **Compare** (`compare_evals.py`: cases fixed vs broken, with a sign test), by category, the
   syllabus totals, and the training data per task type; pack it all (not the 9 GB model) into
   `/workspace/steady-results.tar.gz`.

How to run it:

1. Mac: `bash ai/deploy/make_pod_bundle.sh` → `~/Downloads/steady-pod.tar.gz`.
2. RunPod: an RTX 4090 (or any 24 GB+) pod, PyTorch template, a 50 GB volume at `/workspace`,
   HTTP port 8888 (Jupyter). Not the pod the team is testing on: training stops the website's AI.
3. Jupyter terminal:

   ```bash
   cd /workspace && tar xzf steady-pod.tar.gz && nohup bash steady/ai/deploy/runpod_train.sh > session.log 2>&1 &
   tail -f /workspace/session.log
   ```

4. When it says Done: download `steady-results.tar.gz`. The pod stops itself an hour later
   (`touch /workspace/keep-running` cancels that). To try the fine-tuned model in the website on
   the same pod: `touch /workspace/keep-running && MODEL=/workspace/steady-ft RESTART_MODEL=1 bash steady/ai/deploy/runpod_app.sh`.

Running it again skips finished steps (delete `/workspace/results` to start over). Settings are
environment variables, e.g. `MINUTES=30 EVAL_RUNS=2 TRAIN_ARGS="--skip-reminded"`.

**Adopt the fine-tuned model only if** `compare_evals.py` shows more cases fixed than broken with
p < 0.05, nothing important broke (deletes, fixed events, injection), and the syllabus import
didn't get worse. Fewer tokens and fewer reminders are a bonus.

## Caveats

- The teacher is the model itself: this repeats its best behavior, it doesn't add new skills.
  Task types the model almost never passes give little or no data (see the collect summary).
- Never train on eval cases or `logs/evals.jsonl`.
