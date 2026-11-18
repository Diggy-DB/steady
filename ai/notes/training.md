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

## Round 1 results (Nov 14, 2026, RTX 4090)

384 examples from 400 practice tasks (the model passed 90% of its 1,600 tries), 2 epochs = 96 updates, 19 minutes.
Loss 0.17 → 0.13, mostly at the start of the second pass. The weights moved by 0.43% of their size (attention
0.38%, linear attention 0.38%, feed-forward 0.49%; layers 15-18 the most). Peak GPU memory 16.5 GB.
Logged to W&B (project steady-planner, run lora-r16-384ex-1114-0207). Files: `evals/2026-11-14-*`; the adapter
and the training data in `out/lora-selfrft-round1/` (not in git).

Both models on vLLM, the full suite (296 cases x 3 runs):

| | original | round 1 |
|---|---|---|
| runs passed | 701/888 (79%) | 707/888 (80%) |
| cases right in most runs | 236 | 239 (20 fixed, 17 broken: p = 0.74, could be luck) |
| tokens per run | 1,239 | 1,071 (-14%; fewer in 229 of 296 cases, p < 1e-20) |
| seconds per run | 23.2 | 19.0 (-18%) |
| reminders needed | 90 | 65 (-28%) |
| gave up | 33 | 33 |
| syllabus import (26 syllabi) | 91.1% of dates, classes 36/36 | the same |

So round 1 made the model **faster and more direct without making it more accurate**: by the rule above, not
yet a switch. Better: conflict 70 → 80%, plan 31 → 39%, journal 87 → 94%, injection 77 → 83%. Worse: tight
52 → 43% ("not enough time": saying it doesn't fit), time 80 → 73% ("8 AM is already over"), and two "that
event isn't yours / doesn't exist" cases that now search until they give up. **None of those three behaviors
has a practice task type**, while every practice task rewards proposing something: round 2 should add them
(not enough time, an event that doesn't exist, a time that's already over) and favor tasks the model passes
only 1-3 of 4 tries, which teach more than ones it always passes.

## Round 2 setup (Nov 14)

- **Three new practice types** in `synth.py` (wording and names differ from the eval cases):
  `not_enough` (more hours today than are free: say so, suggest only what fits today), `missing_event` (an event
  the student doesn't have, or another person's event by id: say it isn't there, change nothing) and `time_over`
  (a time earlier today, or "tonight" at 11 PM: notice it, suggest nothing in the past).
- **Weighted task mix**: the new types and the two weakest from round 1 (multi_goal, weekly_goal) come up twice as
  often, conflict and new_task 1.5 times. In 400 tasks: about 90 of the new types, 41 multi_goal, 30 weekly_goal.
- **Fewer easy examples**: `train_lora.py --easy-keep 0.5` keeps half of the examples from tasks the model passed
  on every try and all the others.
- **More data**: round 1's 384 examples go along (`PRIOR_DATA=... make_pod_bundle.sh` puts them in the bundle's
  `prior-data/`; the session trains on both). Training still starts from the original model; the
  hyperparameters are unchanged, so the difference from round 1 is the data.
- Run: `START=5000 TRAIN_ARGS="--easy-keep 0.5" nohup bash steady/ai/deploy/runpod_train.sh > session.log 2>&1 &`
  (new seeds, so no task repeats round 1's).

## Round 2 results (Nov 14, 2026)

454 examples (half of the always-passed ones left out; 17 from not_enough, where the model was right in only 23 of
136 tries), 114 updates, 21.7 minutes, loss 0.177 → 0.116, weights moved 0.46%. W&B run lora-r16-454ex-1114-0400.
Files: `evals/2026-11-14-*run2*`, `*round2*`; adapter and data in `out/lora-selfrft-round2/`.

The original model was evaluated in both sessions and scored 79% and 78%: **a 1-point difference between two runs of
the same model is noise**, so the comparison below pools both (6 runs per case):

| | original (6 runs) | round 1 | round 2 |
|---|---|---|---|
| runs passed | 78.3% | 79.6% | 79.4% |
| cases better / worse than original | | 59 / 46 (p = 0.24) | 55 / 44 (p = 0.32) |
| tokens per run | 1,254 | 1,071 | 1,086 |
| seconds per run | 24.3 | 19.0 | 19.2 |
| reminders needed | 9.4% | 7.3% | 6.8% |
| gave up | 3.4% | 3.7% | 2.3% |
| syllabus import (same session's original) | | 91.1% (91.1%) | 94.6% (90.9%), 19 made up (30) |

By category, round 2 against the original: unclear 77 → 85%, conflict 75 → 85%, plan 32 → 39%, journal 89 → 94%;
the round-1 regressions on "that event isn't yours" and "8 AM is already over" are gone. Still worse: tight
44 → 35% (saying the hours don't fit today); 17 examples weren't enough, because the model almost never does it
right on its own, and self-training can only reinforce what the model already does sometimes.

**Accuracy: no significant change in either round. Speed: about 21% faster, with fewer reminders and (round 2)
fewer give-ups.** Next for "tight": a harness fix (find_free_slots reporting the total free time, so the model
doesn't have to add it up) or a stronger teacher model for those examples.

## Caveats

- The teacher is the model itself: this repeats its best behavior, it doesn't add new skills.
  Task types the model almost never passes give little or no data (see the collect summary).
- Never train on eval cases or `logs/evals.jsonl`.
