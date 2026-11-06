# Training: collecting data and the plan for fine-tuning

The goal from the start: if the model struggles, fine-tune it; if it works but is slow, train it
to think less (or distill it into a smaller model). Stage 3 shows both: planning works (11/12)
but is slow and needs a code reminder to create suggestions. Training should teach it to
**propose directly** and **think less**.

## 1. Training tasks (`src/ai/synth.py`)

Random, reproducible tasks (`make_task(seed)`): a random week for a fake student, a fake "now",
a question, and checks of the same kind the evals use. Six types:

| Type | Example question | Checks |
|---|---|---|
| look_up | What's on my calendar tomorrow? | looked it up, mentions the day's events, proposed nothing |
| move_flexible | Can you move my run on Friday to 2:00 PM? | moved that event to that time |
| move_fixed | Please move my PHY 183 lecture to Tuesday evening. | proposed nothing, said it's fixed |
| task_time | I still need to do my WRA 101 essay. When should I work on it? | proposals covering the task's hours |
| activity_today | When could I practice piano today? | searched free time, proposed something |
| weekly_goal | I want to go to the gym twice this week, an hour each. | exactly the right number of new events |

**Kept apart from the evals** (tests in `tests/test_synth.py` enforce it): other weeks (never
Oct 5–11, 2026), other time zones, other courses and wording, and no question equal to an eval
question.

## 2. Collecting (`scripts/collect_traces.py`)

For each task the teacher model (the current model) tries several times:

- a try is kept only if it **passes every check** and finished on its own;
- of the kept tries, the one with the **fewest tokens** becomes the example: the model learns
  from its own shortest correct answers ("think less");
- tries that passed only after the code reminder are used when no try passed without it: the
  text-only answer and the reminder are cut out, so the example shows the model proposing
  directly; if its later thinking mentions the reminder, the try is skipped. These examples are
  marked `"reminded": true` so they can be filtered out.

Output: `data/<date>-<model>.jsonl`, one conversation per line with `messages` and `tools`, the
format Hugging Face TRL and Unsloth read. The thinking is in `reasoning_content`, which Qwen's
chat template turns back into `<think>…</think>`; `tests/test_collect.py` checks an example
renders with the real template. `data/` is git-ignored (it can get large).

```bash
uv run scripts/collect_traces.py --tasks 5 --samples 2                              # a quick local test
uv run scripts/collect_traces.py --tasks 200 --samples 4 --start 1000 --workers 8    # on a RunPod GPU
```

Use new `--start` seeds for new data, so tasks never repeat.

## 3. Fine-tuning (`scripts/train_lora.py`)

**LoRA**: the model's 4 billion numbers stay frozen; small extra matrices (rank 16, about 33M
numbers) are trained next to its attention and feed-forward layers. It fits on one 24 GB GPU,
and the result is a ~130 MB **adapter** that vLLM loads on top of the original model
(`--enable-lora`), so the original and the fine-tuned model can be served side by side.

| Choice | Value | Why |
|---|---|---|
| What it learns from | the model's own turns only: thinking, tool calls, final answers, each up to `<|im_end|>` | system prompt, question and tool results are context, not text to imitate |
| Rank / alpha | 16 / 32 | a common starting point for behavior changes on small data |
| Learning rate | 1e-4, warm-up then cosine decay | gentle: the goal is to sharpen habits, not teach new knowledge |
| Epochs | 2 | small data (~100 conversations); more risks memorizing it |
| Update size | 8 conversations | one conversation at a time on the GPU, the gradients added up over 8 |
| Max length | 16,384 tokens | longer conversations are skipped, not cut |

Two memory savers make 16k-token conversations fit in 24 GB: **gradient checkpointing**
(recompute instead of store) and a **chunked loss** that scores only the trained positions, a
chunk at a time, instead of all 151,936 vocabulary entries at every position (~10 GB alone).
`tests/test_train.py` checks the chunked loss equals the usual one, and that only the model's
own turns are learned.

Written as a plain PyTorch loop (no TRL or Unsloth): fewer moving parts, and it doesn't depend
on library versions that change monthly. The training libraries aren't project dependencies;
they're added for the run with `uv run --with torch --with peft==0.21.2`.

## 4. The training session (`deploy/runpod_train.sh`)

One script on one pod does it all, about 2 hours (~$2 on an RTX 4090):

1. **Install** vLLM, the code and the training libraries (fails early if anything's missing).
2. **Collect** for at most `MINUTES` (60) with 12 tasks at a time: about 100–150 tasks, 4 tries
   each, the shortest passing try kept. The time limit keeps the cost bounded.
3. **Fine-tune** (`train_lora.py`), 15–30 minutes.
4. **Evaluate** the original and the fine-tuned model at the same time on the held-out suite,
   3 runs per scenario each.
5. **Print the comparison** (pass rate, tokens, seconds, reminders) and pack everything into
   `/workspace/steady-results.tar.gz`.

How to run it:

1. Mac: `bash ai/deploy/make_pod_bundle.sh` → `~/Downloads/steady-pod.tar.gz` (the repo is private).
2. RunPod: an RTX 4090 pod (CUDA 13 machine, like the Nov 5 one), PyTorch template, a 40 GB
   volume disk at `/workspace` (so Jupyter's file list works; deleted with the pod), HTTP port
   8888 (Jupyter, the default). Open Jupyter Lab, drag the file in.
3. Jupyter terminal:

   ```bash
   cd /workspace && tar xzf steady-pod.tar.gz && nohup bash steady/ai/deploy/runpod_train.sh > session.log 2>&1 &
   tail -f /workspace/session.log
   ```

4. When it says Done: download `steady-results.tar.gz` (right-click → Download), then
   **terminate** the pod. As a safety net, the pod stops itself an hour after the script ends or
   fails (`touch /workspace/keep-running` cancels that).

It keeps going if the browser is closed, and running it again skips finished steps.
Settings are environment variables, e.g. `MINUTES=30 EVAL_RUNS=2 TRAIN_ARGS="--skip-reminded"`.

**Training worked if** the fine-tuned model passes planning more often **without** the reminder
(`remind` column) and uses fewer tokens, compared with the original model in the same session.

Variants once that works: train only on the non-reminded examples (`--skip-reminded`), a
stronger teacher for the data (e.g. a bigger Qwen3 on a larger GPU; `collect_traces.py --model`),
or distill the same data into a smaller model such as `Qwen/Qwen3-1.7B` (`train_lora.py --base`).

## Caveats

- The teacher is the model itself, so this teaches it to repeat its own best behavior, not new
  skills. A stronger teacher (a bigger open model on RunPod) would give better data.
- The eval suite is small: add scenarios before trusting small improvements.
- Never train on eval scenarios or `logs/evals.jsonl`.
