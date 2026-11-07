# Non-training accuracy levers and evaluation protocol for the Steady Planner agent (Qwen3-4B-Thinking-2507)

Scope: (A) cheap, non-training ways to make a small tool-calling agent more accurate, and (B) how to evaluate it properly with a small suite. Project facts used for the inferences: 4 tools (get_schedule, find_free_slots, propose_new_event, propose_move_event); proposals are validated in code; there is a one-time code "nudge"; 9 to 11 of 12 runs pass (6 scenarios x 2 runs). The failures are: week planning (ignores the existing gym session, forgets an assignment), proposing nothing after describing a plan, tool calls written inside unclosed thinking, and re-proposing moves until the 8-round cap. Thinking runs up to ~16k tokens.

Labels: "Cited Findings" are sourced. "Inferences" are my reasoning or arithmetic, applied to this project. Arithmetic was done in Python: Wilson intervals, Fisher exact, exact McNemar, and normal-approximation sample sizes at alpha = 0.05 and 80% power.

---

## A1. Tool and interface design: do higher-level tools, structured summaries, and explicit remaining-goal counts beat training?

### Takeaway
The strongest evidence points to interface design. It is the cheapest lever with the largest known effects. Anthropic recommends consolidating tools into workflow-level tools, using `schedule_event` as its example. In SWE-agent's ablations, design choices alone moved success by 3 to 8 points absolute on an 18% base. The study used GPT-4 Turbo, not a 4B model, so the effect size for small models is unmeasured. I found no head-to-head study of "better tools vs. fine-tuning" for small models.

### Cited Findings
- Anthropic advises building "a few thoughtful tools targeting specific high-impact workflows, which match your evaluation tasks". Its example is "a `schedule_event` tool which finds availability and schedules an event" instead of separate list and create tools. It also warns that "Too many tools or overlapping tools can also distract agents from pursuing efficient strategies." — [Anthropic, Writing effective tools for agents](https://www.anthropic.com/engineering/writing-tools-for-agents)
- The same guide recommends returning meaningful context: favor "contextual relevance over flexibility". Resolving UUIDs to semantically meaningful language "reduced hallucinations and improved retrieval precision". A "concise" vs. "detailed" response-format option cut tokens to about one-third (72 vs. 206) in their example. — [Anthropic](https://www.anthropic.com/engineering/writing-tools-for-agents)
- Error messages: "Prompt-engineer your error responses to clearly communicate specific and actionable improvements, rather than opaque error codes or tracebacks". Errors can include examples of correct input. — [Anthropic](https://www.anthropic.com/engineering/writing-tools-for-agents)
- Tool descriptions: describe each tool "to a new hire on your team" and use unambiguous parameter names (`user_id`, not `user`). Small description refinements helped Claude Sonnet 3.5 reach state-of-the-art on SWE-bench Verified. — [Anthropic](https://www.anthropic.com/engineering/writing-tools-for-agents)
- SWE-agent's four ACI principles: (1) "Actions should be simple and easy to understand for agents"; (2) "Actions should be compact and efficient", consolidating common operations; (3) "Environment feedback should be informative but concise"; (4) "Guardrails mitigate error propagation and hasten recovery", for example a syntax linter. — [Yang et al., SWE-agent (arXiv 2405.15793)](https://arxiv.org/html/2405.15793)
- SWE-agent ablations on SWE-bench Lite (GPT-4 Turbo, default 18.0% resolved):
  - Edit without the linting guardrail: 15.0 (−3.0)
  - No edit command: 10.3 (−7.7)
  - Iterative search instead of summarized search: 12.0 (−6.0)
  - No search: 15.7
  - 30-line file viewer: 14.3; full-file viewer: 12.7 (vs. 100 lines)
  - Full history instead of the last 5 observations: 15.0
  - No demonstration: 16.3 (−1.7)

  — [SWE-agent HTML, Table 3](https://arxiv.org/html/2405.15793)
- SWE-agent overall: 12.5% pass@1 on SWE-bench and 87.7% on HumanEvalFix, "far exceeding the previous state-of-the-art achieved with non-interactive LMs". — [arXiv 2405.15793](https://arxiv.org/abs/2405.15793)

### Inferences
- **Highest-value change: a goal-aware planning tool or summary.** The week-planning failure is a counting and bookkeeping error: the model ignores the gym session already on the calendar and forgets one assignment. There are two options:
  - Add a higher-level tool such as `check_plan(goals=[{activity:"gym", count:3, minutes:60}, {task:"Assignment A"}, ...])`. It returns, per goal, existing matching events, accepted or pending proposals, **remaining count**, and candidate slots.
  - Or append a code-computed "Goal status" block to every tool result, e.g. `gym: need 3, already scheduled 1 (Tue 7-8am), pending 1, remaining 1`.

  This follows Anthropic's consolidation advice and SWE-agent's "summarized search beats iterative search" result. Expect it to remove most week-planning failures, because the model no longer has to count over raw event lists. This is unproven for this model, so measure it.
- **Guardrails in propose_* results** (SWE-agent principle 4, "linter" analogue). When a move duplicates a pending proposal or targets an already-moved event, reject it with an actionable message, e.g. "Already proposed: move 'Study' to Wed 3-5pm (pending). All 2 requested changes are proposed; now reply to the user." Do the same when remaining goals reach zero. This targets the "re-propose until 8 rounds" loop directly.
- **Fewer, simpler arguments.** Accept natural fields (day name or ISO date, start, duration_minutes) and resolve them in code. Return human-readable event names and times rather than opaque IDs, which follows Anthropic's UUID-resolution finding.
- **Keep tool outputs concise and grouped.** find_free_slots already groups by day, which is good. Also provide a compact option, e.g. only slots ≥ the requested duration. SWE-agent's full-file viewer was worse than a 100-line window (12.7 vs. 18.0).

### Gaps
- No controlled study found comparing "redesign tools" vs. "fine-tune" for a ~4B model on multi-turn tool use. The SWE-agent and Anthropic evidence comes from frontier models.
- Not fetched this session: OpenAI function-calling best-practice docs, and tool-documentation papers such as Hsieh et al. 2023 and EASYTOOL. Their claims are not included.

---

## A2. Prompting: few-shot multi-step examples, planning checklists, ReAct structure: effect sizes on small models

### Takeaway
Few-shot examples help some small models and not others, and fine-tuning beats few-shot in the one 2025 study found. Demonstrations gave a small gain in SWE-agent (+1.7 points). Expect modest, model-dependent gains. One worked example of the exact week-planning pattern is cheap to try, but it lengthens every prompt.

### Cited Findings
- On small language models for function calling (EASE 2025), adding few-shot examples noticeably improved Deepseek-Coder and Phi-3-Mini, especially on JSON parsability and task accuracy. Several other models showed no substantial gain. Fine-tuned models beat both zero-shot and few-shot. Few-shot prompts were more vulnerable to prompt injection. — [Small Models, Big Tasks (arXiv 2504.19277)](https://arxiv.org/html/2504.19277v1) (read via search summaries, not the full text)
- In SWE-agent, removing the demonstration dropped SWE-bench Lite from 18.0% to 16.3%. — [SWE-agent Table 3](https://arxiv.org/html/2405.15793)
- Anthropic suggests having agents output reasoning and feedback blocks before tool calls in evaluation loops, which may trigger chain-of-thought behavior. — [Anthropic](https://www.anthropic.com/engineering/writing-tools-for-agents)

### Inferences
- **ReAct-style "Thought:" scaffolding is likely redundant here.** The model already thinks for up to 16k tokens; adding more reasoning text is more likely to lengthen thinking than to improve it. Better prompt levers:
  - A short **required final-step rule**: "Before replying, every requested item must have a matching existing event or a propose_* call."
  - A **goal checklist the model must restate** in its first visible step. Better still, let code compute it (A1), which is more reliable than asking a 4B model to keep it.
- **One compact few-shot trajectory** for the week-plan pattern may help with the "ignores existing gym" failure. It should show: get_schedule, notice the existing gym session, need = 3 − 1 = 2, find_free_slots, then 2 gym proposals plus 2 assignment proposals. Gains are uncertain (likely a few points), and it adds prompt tokens to every call. Test it with the paired protocol in B1.
- Prompt-only fixes for counting errors are less reliable than computing counts in code, because the failure is bookkeeping, not knowledge.

### Gaps
- No quantitative evidence found for explicit planning checklists in tool-calling agents on small models.
- No 2025–2026 numbers found for few-shot effects on Qwen3-4B or on thinking models specifically.

---

## A3. Constrained decoding and structured outputs for tool calls in vLLM, and their interaction with thinking

### Takeaway
vLLM can guarantee a parsable call (`tool_choice="required"` or a named function), but it does not guarantee a good one. Tool calls are parsed only from `content`, never from the `reasoning` field. So a tool call written inside an unclosed `<think>` is invisible to vLLM, which matches one of the project's observed failures. Two cheap fixes:
- Force a named tool on the nudge round.
- Use `thinking_token_budget` to guarantee the thinking block closes.

### Cited Findings
- vLLM supports `auto`, `required`, `none`, and named function calling. For named calling, "vLLM will use structured outputs to ensure the response matches the tool parameter object", and "You are guaranteed a validly-parsable function call - not a high-quality one." With `required`, "the model is guaranteed to generate one or more tool calls". — [vLLM Tool Calling docs](https://docs.vllm.ai/en/latest/features/tool_calling.html)
- In `auto` mode, structural tags (constrained decoding) are used only "When at least one tool sets `strict: true`, or `--tool-strict-level` is `function` or `parameter`". Otherwise, "vLLM extracts tool calls from raw text, so arguments may occasionally be malformed." `strict` is supported on the Chat Completions, Responses, and Anthropic Messages surfaces. — [vLLM Tool Calling docs](https://docs.vllm.ai/en/latest/features/tool_calling.html)
- The `hermes` parser enables tool calls for Qwen models (`--tool-call-parser hermes`). The docs name Qwen2.5 and QwQ explicitly, not Qwen3. Qwen3-Coder uses `qwen3_xml`. — [vLLM Tool Calling docs](https://docs.vllm.ai/en/latest/features/tool_calling.html)
- "Tool calling only parses functions from the `content` field, not from the `reasoning`." Qwen3 uses `--reasoning-parser qwen3`, and the reasoning is returned in the `reasoning` field (formerly `reasoning_content`). — [vLLM Reasoning Outputs docs](https://docs.vllm.ai/en/latest/features/reasoning_outputs.html)
- Structured outputs and reasoning:
  - The developer section says the structured-output engine (e.g., xgrammar) uses the reasoning end token to detect reasoning and skips structured output while reasoning is in progress.
  - A model note says structured outputs "apply from the first token, so constrained responses answer without reasoning."
  - The page does not clearly say which applies to Qwen3. **This is unresolved.** — [vLLM Reasoning Outputs docs](https://docs.vllm.ai/en/latest/features/reasoning_outputs.html)
- The Qwen3-4B-Thinking-2507 chat template auto-inserts the opening `<think>`, so output "may contain only `</think>`" without an opening tag. Historical turns should contain only the final output, not the thinking; the official Jinja template handles this, and other frameworks must implement it themselves. — [Qwen3-4B-Thinking-2507 model card](https://huggingface.co/Qwen/Qwen3-4B-Thinking-2507)
- Qwen recommends Qwen-Agent for tool calling. On an OpenAI-compatible endpoint, it recommends disabling the server's reasoning and tool-call parsing and letting Qwen-Agent handle them (`'thought_in_content': True`). — [Qwen3-4B-Thinking-2507 model card](https://huggingface.co/Qwen/Qwen3-4B-Thinking-2507)

### Inferences
- **Do not use `tool_choice="required"` globally.** The agent must still end with a text reply. Use a **named** tool_choice only on the nudge round. If the model described times without proposing, re-call with `tool_choice={"type":"function","function":{"name":"propose_new_event"}}` or `propose_move_event`. This turns the "proposing nothing" failure into a schema-valid proposal, which code then validates.
- **Verify the reasoning interaction empirically.** Send one request with reasoning parser on and named tool_choice. Check whether the model still produces `reasoning` before the constrained call, or whether reasoning is suppressed (the doc note conflicts on this).
- **Salvage path for the "tool call inside unclosed think" failure.** If `content` is empty and `reasoning` contains a well-formed `<tool_call>{...}</tool_call>`, either parse and execute it in code, or retry once with a thinking budget. This is a code-only fix that should recover most of these failures.
- **Set `strict: true`** on the four tools so arguments are schema-constrained even in `auto` mode. Check that the vLLM version in the pod supports it and how it interacts with the hermes parser.
- **Ollama on the laptop** has no equivalent of vLLM's named or required tool_choice; I did not verify this. Laptop-mode fixes should rely on code (salvage, retry) rather than decoding constraints.

### Gaps
- Exact vLLM behavior for Qwen3 when combining `--reasoning-parser qwen3`, `tool_choice` named or required, and xgrammar: the docs are ambiguous.
- Ollama's support for tool_choice, strict schemas, and thinking budgets was not researched.

---

## A4. Inference-time scaling with a code verifier: best-of-n, self-consistency, reranking, and costs

### Takeaway
When an automatic verifier exists, repeated sampling converts into accuracy (log-linear coverage gains). This project has partial code verifiers: proposal validation, plus goal-coverage checks that could be added. On the 4090, best-of-2 to best-of-4 with "first candidate that passes the validators, prefer the shortest thinking" is a cheap, plausible lever. On the laptop it is too slow.

### Cited Findings
- Coverage (the fraction of problems solved by at least one sample) grows "often log-linear[ly]" over four orders of magnitude of samples. On SWE-bench Lite, DeepSeek-Coder-V2-Instruct went "from 15.9% with one sample to 56% with 250 samples", beating the single-sample SOTA of 43%. With automatic verifiers, coverage turns directly into performance. Without them, majority voting and reward models "plateau beyond several hundred samples". — [Brown et al., Large Language Monkeys (arXiv 2407.21787)](https://arxiv.org/abs/2407.21787)
- Overthinking in agentic tasks: across 4,018 SWE-bench Verified trajectories, higher overthinking scores correlate with lower performance, and reasoning models overthink more than non-reasoning models. Simply selecting the solution with the lower overthinking score "can improve model performance by almost 30%" while reducing computational cost by 43%. — [Cuadron et al., The Danger of Overthinking (arXiv 2502.08235)](https://arxiv.org/abs/2502.08235)
- T1 (2025) reports that tool-integrated verification (e.g., a code interpreter) significantly improves small-model self-verification under test-time scaling. Evidence that tiny *generative* verifiers can do this alone is mixed: two Stanford CS224R reports disagree. — [T1, arXiv 2504.04718](https://arxiv.org/html/2504.04718v1); [CS224R report](https://cs224r.stanford.edu/projects/pdfs/Joshua%20Delgadillo%20Jui%20Khankari%20submission_416276148/CS_224R_Project_Report__2_.pdf) (search-snippet level only)

### Inferences
- **Design.** Sample N = 2 to 4 full trajectories in parallel on vLLM, or sample N candidate proposal sets at the decision step. Keep candidates that pass code checks: no overlaps, inside free slots, all requested goals covered (remaining count = 0), no duplicate proposals. Among those, pick the one with the fewest thinking tokens or tool rounds, which the overthinking result supports. If none pass, fall back to the best partial and tell the user.
- **Upper-bound arithmetic, assuming independent trials.** At p = 0.83 per trial, best-of-2 = 0.97, best-of-3 = 0.995, best-of-4 = 0.999. At p = 0.5 (e.g., the week-plan scenario), best-of-3 = 0.875. **Real gains will be lower** because failures are correlated within a scenario; a scenario the model systematically misreads fails all N.
- **Cost.**
  - Tokens scale ~N×.
  - On vLLM with batching, wall-clock latency is roughly the slowest of N, not N× (throughput-bound). On a 4090, the 4B model at N = 3 is likely affordable within the 15 to 120 s budget, but tail latency grows; I did not benchmark this.
  - On the Ollama laptop (100 to 900 s per answer), N× serial time is not viable.
  - Early stopping helps: run N in parallel, take the first that validates, cancel the rest.
- **Verifier coverage matters.** Only failures that code can detect are fixable this way: missing goals, duplicates, conflicts, no proposal. "Ignored the existing gym" becomes detectable only if code computes goal status (A1), which makes A1 and A4 complementary.

### Gaps
- No published numbers found for best-of-n on multi-turn tool-calling benchmarks (tau-bench, BFCL) with small Qwen models.
- Latency of parallel sampling for Qwen3-4B on an RTX 4090 with ~16k-token reasoning was not measured.

---

## A5. Thinking budget control, Thinking-2507 vs. Instruct-2507, and whether bigger models fit

### Takeaway
- **Budget:** vLLM has a per-request `thinking_token_budget` that forces `</think>` when reached. This bounds latency and prevents unclosed-think failures, but quality under truncation for this model is unmeasured.
- **Thinking vs. Instruct:** On Qwen's own agent benchmarks, Thinking-2507 beats Instruct-2507 by large margins (TAU2-Airline 58.0 vs. 24.0). Switching to non-thinking to save latency would likely cost accuracy.
- **Bigger models:** Qwen3-30B-A3B-Thinking-2507 adds only +1.2 BFCL-v3 and +0 to +5 on TAU2 over the 4B. The original Qwen3-8B scores *below* 4B-Thinking-2507 on BFCL-v3. Qwen3-Next-80B-A3B is clearly better on TAU2-Retail and Telecom but needs multi-GPU in the examples.

### Cited Findings
- **vLLM thinking budget:**
  - Per-request sampling parameter `thinking_token_budget` (also accepted by `/v1/responses`).
  - Server config `--reasoning-config` with `reasoning_start_str` and `reasoning_end_str`; it requires `--reasoning-parser` (e.g., `qwen3`).
  - Counting starts at `reasoning_start_str`. When the budget is reached, vLLM forces `reasoning_end_str`.
  - Without a budget, the only limit is `max_tokens`. Offline use: `SamplingParams(thinking_token_budget=...)`.

  — [vLLM Reasoning Outputs docs](https://docs.vllm.ai/en/latest/features/reasoning_outputs.html)
- Qwen3-4B-Thinking-2507 "has an increased thinking length". Qwen recommends a 32,768-token output length for most queries and 81,920 for competition math and code. It supports thinking mode only, with 262,144 native context. — [Model card](https://huggingface.co/Qwen/Qwen3-4B-Thinking-2507)
- **Vendor-reported agent benchmarks (Qwen model cards):**

  | Model | BFCL-v3 | TAU1-Retail | TAU1-Airline | TAU2-Retail | TAU2-Airline | TAU2-Telecom |
  |---|---|---|---|---|---|---|
  | Qwen3-4B-Thinking-2507 | 71.2 | 66.1 | 48.0 | 53.5 | 58.0 | 27.2 |
  | Qwen3-4B-Instruct-2507 (non-thinking) | 61.9 | 48.7 | 32.0 | 40.4 | 24.0 | 13.2 |
  | Qwen3-4B Thinking (Apr 2025) | 65.9 | 33.9 | 32.0 | 38.6 | 28.0 | 17.5 |
  | Qwen3-4B Non-thinking (Apr 2025) | 57.6 | 24.3 | 16.0 | 28.1 | 12.0 | 17.5 |
  | Qwen3-30B-A3B-Thinking-2507 (30.5B total / 3.3B active) | 72.4 | 67.8 | 48.0 | 58.8 | 58.0 | 26.3 |
  | Qwen3-30B-A3B Thinking (Apr 2025) | 69.1 | 61.7 | 32.0 | 34.2 | 36.0 | 22.8 |
  | Qwen3-Next-80B-A3B-Thinking (80B total / 3B active) | 72.0 | 69.6 | 49.0 | 67.8 | 60.5 | 43.9 |
  | Qwen3-235B-A22B-Thinking-2507 | 71.9 | 67.8 | 46.0 | 71.9 | 58.0 | 45.6 |
  | Gemini-2.5-Flash Thinking | 68.6 | 65.2 | 54.0 | 66.7 | 52.0 | 31.6 |
  | GPT-4.1-nano | 53.0 | 23.5 | 14.0 | – | – | – |

  — [Qwen3-4B-Thinking-2507](https://huggingface.co/Qwen/Qwen3-4B-Thinking-2507); [Qwen3-4B-Instruct-2507](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507); [Qwen3-30B-A3B-Thinking-2507](https://huggingface.co/Qwen/Qwen3-30B-A3B-Thinking-2507); [Qwen3-Next-80B-A3B-Thinking](https://huggingface.co/Qwen/Qwen3-Next-80B-A3B-Thinking)
- **Qwen3-8B (Apr 2025; no 2507 refresh found):** BFCL-v3 68.1 in thinking mode and 60.2 in non-thinking. Qwen3-4B (Apr 2025) scored 65.9 and 57.6. Qwen evaluated all models in FC format, using YaRN to 64k for multi-turn. — [Qwen3 Technical Report (arXiv 2505.09388), Tables 17–18](https://arxiv.org/html/2505.09388). A search summary flagged possible caption/column confusion; the fetched report text maps 68.1 to thinking and 60.2 to non-thinking. [Search summary](https://arxiv.org/pdf/2505.09388)
- Qwen3-Next-80B-A3B-Thinking's example deployments use 4-way tensor parallelism and require vLLM ≥ 0.10.2. The weights are 81B params in BF16. — [Model card](https://huggingface.co/Qwen/Qwen3-Next-80B-A3B-Thinking)
- Reasoning models overthink more in agentic environments, and overthinking correlates with lower success. — [arXiv 2502.08235](https://arxiv.org/abs/2502.08235)

### Inferences
- **Thinking budget:**
  - Set `thinking_token_budget` to roughly 4k to 8k for planning turns and lower (~1k to 2k) for follow-up rounds after tool results. This caps the 16k-token worst case, roughly halving to quartering the worst-case latency.
  - It also guarantees `</think>`, which addresses "tool calls inside unclosed thinking".
  - Because forced truncation can cut reasoning mid-plan, sweep the budget (2k, 4k, 8k, unlimited) on the larger eval set and pick the knee of the accuracy-vs-latency curve.
- **Do not switch to Instruct-2507 for accuracy.** The vendor numbers show −9 to −34 points on agent benchmarks. Instruct might still be worth testing as a fast laptop mode, where 100 to 900 s is unusable, with code verification and best-of-n compensating.
- **Qwen3-8B:** On BFCL-v3, the original 8B thinking model (68.1) scores below 4B-Thinking-2507 (71.2). It is not a sensible upgrade.
- **Qwen3-30B-A3B-Thinking-2507:**
  - About the same BFCL as the 4B and TAU2-Retail +5.3, so modest gains.
  - Its 3.3B active parameters mean per-token speed is similar to the 4B when memory-bound.
  - Memory is the issue: 30.5B params at BF16 is ~61 GB, which does not fit a 24 GB 4090. A 4-bit quant (~16–18 GB) might fit with a reduced KV cache. These sizes are my estimate, not sourced.
  - Worth one paired A/B run on the held-out suite if a quant fits the pod; expected gain is small to moderate.
- **Qwen3-Next-80B-A3B:** The largest TAU2 gains (+14 Retail, +17 Telecom vs. 4B-Thinking-2507), but at multi-GPU cost. Probably outside the club budget.
- **Benchmark-to-task transfer:** These are vendor-reported numbers, and TAU2 domains differ from calendar planning. Our own held-out suite is the deciding test.

### Gaps
- No published accuracy-vs-thinking-budget curves found for Qwen3-4B-Thinking-2507 on tool-use tasks. The Qwen3 technical report may contain thinking-budget scaling plots; not verified here.
- No independent (non-vendor) BFCL v4 or tau2-bench leaderboard numbers were fetched for these models.
- Ollama's thinking-budget support was not researched.

---

## A6. Recommended sampling settings for Qwen3 thinking models in agentic use

### Takeaway
Use Qwen's recommended settings for the thinking model: T = 0.6, top_p 0.95, top_k 20, min_p 0. Add a moderate `presence_penalty` (Qwen allows 0 to 2) only if repetition or looping appears, since higher values can cause language mixing. Do not lower temperature just to reduce eval variance.

### Cited Findings
- Qwen3-4B-Thinking-2507: Temperature 0.6, TopP 0.95, TopK 20, MinP 0. `presence_penalty` is adjustable between 0 and 2 "to reduce endless repetition", but higher values may cause language mixing and a slight performance drop. — [Model card](https://huggingface.co/Qwen/Qwen3-4B-Thinking-2507)
- Qwen3-30B-A3B-Thinking-2507 uses the same settings. — [Model card](https://huggingface.co/Qwen/Qwen3-30B-A3B-Thinking-2507)
- Qwen3-4B-Instruct-2507: Temperature 0.7, TopP 0.8, TopK 20, MinP 0, and 16,384 output tokens recommended. — [Model card](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507)
- Miller advises against lowering sampling temperature to reduce eval variance, because it can shift the expected score or increase variance across questions. — [Miller, Adding Error Bars to Evals (arXiv 2411.00640)](https://arxiv.org/html/2411.00640v1)
- tau-bench ran the agent at temperature 0.0 and the simulated user at 1.0. Run-to-run variation came from sampling of both. — [tau-bench HTML](https://arxiv.org/html/2406.12045)

### Inferences
- Start at presence_penalty 0 to 0.5. If traces show repeated proposals or repeated thinking loops, try 1.0 and check for language mixing. The guardrails in A1 are a more targeted fix for re-proposal loops than a penalty.
- Evaluate at the same sampling settings used in production. Evaluating at T = 0 would measure a different system and, per Miller, may bias the score.

### Gaps
- I did not verify in this session Qwen's commonly cited warning against greedy decoding for thinking models, or any quantized-model-specific presence_penalty recommendation.
- No agent-specific sampling ablations found for Qwen3 thinking models.

---

## B1. What differences are detectable with 6 scenarios x 2–3 runs? Eval size, repeats, pass@k vs. pass^k, and intervals for small samples

### Takeaway
The current 12-trial suite can only detect very large changes, around 40+ points. 10/12 has a 95% Wilson CI of roughly 55% to 95%. To detect a 10 to 15 point improvement, plan on about 60 to 100 scenarios x 3 runs, analyzed **paired** (same scenarios for A and B). Report Wilson or Bayesian intervals, pass^1 and pass^3, and per-category breakdowns.

### Cited Findings
- **Miller's standard errors:**
  - CLT: SE = sqrt(p(1−p)/n).
  - Clustered SEs apply when questions come in related groups. In one example, the clustered SE was 3.05× the naive SE.
  - Paired comparison on the same questions reduces variance whenever models agree on which questions are easy or hard. With correlation 0.5, variance drops by 1/3.

  — [Miller, arXiv 2411.00640](https://arxiv.org/html/2411.00640v1)
- **Miller on resampling:** taking K answers per question reduces variance. In his uniform-difficulty example the multiplier is (1 + 2/K)/3: K = 2 cuts variance by 1/3, K = 4 by 1/2, with an upper limit of 2/3. At n = 198, raising K from 1 to 10 cut the minimum detectable effect from 13.2% to 7.5%. Do not pool the K·N answers as independent. His power formula is n = (z_{α/2} + z_β)² (ω² + σ_A²/K_A + σ_B²/K_B)/δ². — [Miller](https://arxiv.org/html/2411.00640v1)
- **Bowyer et al. (ICML 2025 position paper):** CLT-based error bars "fail to provide adequate uncertainty estimates" for small benchmarks, "usually dramatically underestimating uncertainty". Even at N = 100, 95% CLT intervals covered only 92.5%. They recommend the **Wilson score interval** or a **Bayesian Beta posterior Beta(1+S, 1+N−S)** for single models. Clopper-Pearson is valid but too conservative, and bootstrap intervals under-cover. For two models on the same questions, they recommend a **paired Bayesian** model. Their Fig. 1 example is the LangChain tool-use benchmark with N = 20. — [Bowyer, Aitchison, Ivanova, arXiv 2503.01747](https://arxiv.org/html/2503.01747v3)
- **tau-bench metrics:** pass^k = E_task[C(c,k)/C(n,k)] (all k i.i.d. trials succeed) and pass@k = 1 − E_task[C(n−c,k)/C(n,k)], where c is successes out of n trials. pass^1 equals mean reward. Main results use ≥3 trials per task, over 115 retail and 50 airline tasks. gpt-4o scored pass^1 61.2 on retail and 35.2 on airline, and retail pass^8 was <25%. — [tau-bench HTML](https://arxiv.org/html/2406.12045); [abstract](https://arxiv.org/abs/2406.12045)
- **Anthropic:** pass@k fits cases where one success is enough. pass^k fits when consistency matters, e.g. customer-facing agents: "With a 75% per-trial rate, three trials pass all three about 42% of the time." Run multiple trials because outputs vary. — [Anthropic, Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)

### Inferences (my calculations)
- **95% Wilson intervals at current scale:**

  | Result | Interval |
  |---|---|
  | 9/12 | [46.8%, 91.1%] |
  | 10/12 | [55.2%, 95.3%] |
  | 11/12 | [64.6%, 98.5%] |
  | 12/12 | [75.8%, 100%] |

  Every recent result (9, 10, 11 of 12) has heavily overlapping intervals. The differences between runs are noise.
- **Clustering makes it worse.** The 12 trials sit in 6 scenario clusters (2 runs each, correlated), so the effective n is between 6 and 12.
- **Fisher exact tests at 12 vs. 12 trials:**

  | Comparison | p |
  |---|---|
  | 9/12 vs. 12/12 | 0.22 |
  | 8/12 vs. 12/12 | 0.09 |
  | 7/12 vs. 12/12 | 0.037 |

  A change must be about 40+ points to reach significance.
- **Paired exact McNemar test** (same scenario and seed slots, before vs. after):

  | Discordant pairs (fixed / broken) | p |
  |---|---|
  | 6 / 0 | 0.031 |
  | 5 / 0 | 0.063 |
  | 8 / 2 | 0.11 |
  | 12 / 4 | 0.077 |

  You need at least 6 discordant pairs, all in one direction, for p < 0.05.
- **Sample sizes (80% power, two-sided alpha 0.05):**
  - Unpaired, trials per arm: 197 for 80→90%, 97 for 75→90%, 59 for 70→90%, 73 for 80→95%.
  - Paired (McNemar, Connor approximation), scenario-trials: about 108 if a change fixes 12% and breaks 2% of items, and about 155 at 15% fixed / 5% broken.
- **Recommended suite:** 60 to 100 held-out scenarios x 3 runs (180 to 300 trials), always run paired across variants.
  - At 150 trials and 80% accuracy, the Wilson CI is about [72.9%, 85.6%] (±6 pts). At 300 trials it is about [75.1%, 84.1%] (±4.5 pts).
  - Miller's K results show diminishing returns past K ≈ 3–4 repeats. Spend extra budget on more scenarios, not more repeats.
- **Metrics to report per variant:**
  - pass^1 with a Wilson or Beta CI.
  - pass^3 per scenario, since a user-facing planner needs consistency. For reference, 0.83 per-trial with independence gives pass^3 ≈ 0.57.
  - pass@3 if best-of-n is used.
  - Per-category rates (week plan, move, due tonight, etc.).
  - Paired difference with McNemar or paired-Bayes.
  - Cost metrics: thinking tokens, wall-clock, tool calls, rounds.
- **Keep production temperature (0.6).** Treat variance as real, per Miller.
- **Use the 6-scenario x 2 suite only as a smoke test.** It is fine for catching crashes or format breaks, not for deciding between levers.

### Gaps
- No source found giving a recommended eval size specifically for small agent suites beyond Anthropic's "20–50 tasks to start". The 60–100 figure is my power-analysis inference.

---

## B2. Avoiding train/test leakage between synthetic training tasks and eval scenarios; building a larger held-out set

### Takeaway
Use a held-out set built from **different templates, phrasings, and calendar fixtures**, not only different seeds. A same-template, different-seed split mostly tests memorized structure. Anthropic explicitly relied on held-out test sets to avoid overfitting tools to the training evals. tau2-bench's compositional task generator is a model for producing many verifiable tasks.

### Cited Findings
- "We relied on held-out test sets to ensure we did not overfit to our 'training' evaluations." — [Anthropic, Writing effective tools for agents](https://www.anthropic.com/engineering/writing-tools-for-agents)
- tau2-bench uses "a compositional task generator" that builds verifiable tasks from atomic components. It reports significant performance drops moving from no-user to dual-control settings (no numbers in the abstract). — [tau2-bench, arXiv 2506.07982](https://arxiv.org/abs/2506.07982)
- Anthropic's eval-construction advice:
  - Begin with "20-50 simple tasks drawn from real failures".
  - Include both positive and negative cases ("One-sided evals create one-sided optimization").
  - Write a reference solution proving each task is solvable.
  - Treat a 0% pass rate across many trials as a likely broken task or grader.

  — [Anthropic, Demystifying evals](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- tau-bench grades by comparing final database state to an annotated goal state. — [tau-bench](https://arxiv.org/abs/2406.12045)

### Inferences
- **Split by family, not by seed.** Partition the generator's request templates, calendar archetypes (e.g., heavy-lecture week, part-time job, exam week), and phrasing styles into train and eval families. No template string, and ideally no calendar fixture, should appear in both.
  - Add a held-out set of **hand-written** requests from club members, phrased in real student language.
  - Check n-gram or embedding overlap between train prompts and eval prompts, and drop near-duplicates.
- **Structure the held-out set** as 60–100 scenarios stratified by category:
  - week plan with pre-existing matching events
  - multi-goal (2+ assignments + recurring activity)
  - move requests
  - fixed or immovable events
  - due-tonight
  - no-feasible-slot (should decline or partially propose)
  - ambiguous requests (should ask or make a reasonable default)
- **Include negative cases** (Anthropic's balance point): requests where the correct behavior is *not* to propose, or to propose fewer items.
- **Grade outcomes, not paths.** Final pending proposals vs. goal spec, with code checks for coverage, conflicts, duplicates, and respect for existing events. Use partial credit for multi-goal tasks, plus a binary pass.
- **Freeze the held-out set and version it** (file hash in eval logs). Never use its failures as training data. Move failures into the *training generator's* templates only after creating fresh eval replacements.

### Gaps
- No published study found quantifying leakage effects specifically for synthetic agent-trajectory fine-tuning. The guidance above is standard practice plus inference.

---

## B3. Measuring regressions in general ability, thinking length, and latency after fine-tuning

### Takeaway
I found no source in this session prescribing a specific post-fine-tune regression battery for small agents. A sensible minimal battery:
- the frozen held-out planner suite (paired)
- a small BFCL-style function-calling subset
- an instruction-following check (IFEval subset)
- a few general chat sanity prompts
- thinking-token and latency distributions

Anthropic's metrics list (tool calls, tokens, errors, runtime) supports logging cost alongside accuracy.

### Cited Findings
- Collect "the total number of tool calls, the total token consumption, and tool errors", plus runtime. "Lots of redundant tool calls might suggest some rightsizing of pagination or token limit parameters is warranted." — [Anthropic, Writing effective tools](https://www.anthropic.com/engineering/writing-tools-for-agents)
- Capability evals start low ("a hill to climb"). Regression evals should sit near 100% to protect against backsliding, and saturated capability evals can "graduate" into regression suites. "An eval at 100% tracks regressions but provides no signal for improvement." — [Anthropic, Demystifying evals](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- Qwen evaluates BFCL v3 in FC format, with YaRN to 64k for multi-turn. — [Qwen3 Technical Report](https://arxiv.org/html/2505.09388)
- Higher overthinking correlates with lower agentic performance, which makes thinking length a useful health metric. — [arXiv 2502.08235](https://arxiv.org/abs/2502.08235)

### Inferences
- **Regression battery after any LoRA:**
  1. The held-out planner suite (paired, 3 runs).
  2. The original 6 smoke scenarios at 100% target, as a regression gate.
  3. About 100–200 BFCL v3 items, including multi-turn and irrelevance categories, to detect general function-calling damage.
  4. About 100 IFEval prompts.
  5. About 20 off-domain chat prompts checked by hand or LLM-judge, for format, language mixing, and refusals.
  6. Thinking tokens (median and p90), wall-clock, rounds per task, and the "unclosed think" rate.

  Report each with CIs.
- **Expected direction.** Fine-tuning on a narrow synthetic distribution often shortens thinking on in-domain tasks but can damage format adherence or irrelevance detection elsewhere. Check this rather than assume it.

### Gaps
- BFCL v3/v4 category definitions and current leaderboard details were not fetched this session.
- IFEval specifics and costs were not researched.
- No 2025–2026 study found measuring capability regression from small-model LoRA tool-use fine-tunes.

---

## B4. Guidance from tau-bench, tau2-bench, BFCL, and Anthropic/OpenAI agent-eval guides

### Takeaway
The consensus:
- Grade final state (outcomes), not exact tool-call paths.
- Run ≥3 trials per task and report a consistency metric (pass^k).
- Isolate trials.
- Read transcripts.
- Separate capability evals (low pass rate, to hill-climb) from regression evals (near 100%).

### Cited Findings
- tau-bench: "compares the database state at the end of a conversation with the annotated goal state". pass^k was introduced for reliability over multiple trials. Agents are "quite inconsistent (pass^8 <25% in retail)". — [tau-bench](https://arxiv.org/abs/2406.12045)
- Anthropic, outcomes over paths: rigid step-order checks are "overly brittle" and penalize valid creative solutions. Use partial credit for multi-part tasks. — [Demystifying evals](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- Anthropic, isolation: start each trial from a clean environment. Shared state can cause correlated failures or inflate scores. — [Demystifying evals](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- Anthropic, transcripts: "You won't know if your graders are working well unless you read the transcripts and grades from many trials." Also: "What agents omit in their feedback and responses can often be more important than what they include." — [Demystifying evals](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents); [Writing tools](https://www.anthropic.com/engineering/writing-tools-for-agents)
- Anthropic, graders: code-based graders are fast, objective, and reproducible but brittle. Model-based graders are flexible but need calibration against humans. Avoid "overly strict verifiers that reject correct responses due to spurious differences like formatting." — [Demystifying evals](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents); [Writing tools](https://www.anthropic.com/engineering/writing-tools-for-agents)
- Miller, reporting: report n and SE for each score. For comparisons, report pairwise differences, paired SEs, CIs, and score correlations. Flag CIs that include zero as not significant. — [Miller](https://arxiv.org/html/2411.00640v1)

### Inferences
- The Steady eval harness already fits the tau-bench pattern: the final pending proposals play the role of the end-state DB. Make the goal-state spec explicit per scenario:
  - required items
  - forbidden overlaps
  - events that must not move
  - expected count of new proposals (accept a range where several answers are valid)
- Log every trial's full transcript (reasoning included) and review a sample of failures after each change. The four failure types listed in the scope were found this way, which is the method working.

### Gaps
- OpenAI's agent-eval and function-calling guides were not fetched this session.
- BFCL v3/v4 multi-turn methodology (e.g., missing-function and long-context categories) was not fetched.

---

## Synthesis: ranked levers and evaluation protocol

### Takeaway
The cheapest, best-evidenced order is:
1. Code-side interface fixes: goal-status summaries, guardrails, salvage of tool calls stuck in thinking, forced named tool on the nudge.
2. A thinking budget.
3. Verifier-filtered best-of-n on the 4090.
4. Prompt tweaks (one worked example).
5. A model swap (30B-A3B-Thinking-2507), only if a quant fits.

None should be judged on the 12-trial suite. Build a 60–100 scenario held-out set first, or in parallel, and compare variants paired.

### Cited Findings
- Evidence anchors (all cited above):
  - interface/ACI effects of −3 to −7.7 points from removing guardrails, summaries, or compact actions — [SWE-agent](https://arxiv.org/html/2405.15793)
  - tool consolidation and actionable errors — [Anthropic](https://www.anthropic.com/engineering/writing-tools-for-agents)
  - parse-only-from-content and named tool_choice guarantees — [vLLM tool calling](https://docs.vllm.ai/en/latest/features/tool_calling.html); [vLLM reasoning](https://docs.vllm.ai/en/latest/features/reasoning_outputs.html)
  - `thinking_token_budget` — [vLLM reasoning](https://docs.vllm.ai/en/latest/features/reasoning_outputs.html)
  - verifier-backed repeated sampling — [Large Language Monkeys](https://arxiv.org/abs/2407.21787)
  - overthinking selection (~30% better, 43% cheaper) — [arXiv 2502.08235](https://arxiv.org/abs/2502.08235)
  - model benchmark deltas — [Qwen model cards](https://huggingface.co/Qwen/Qwen3-30B-A3B-Thinking-2507)
  - small-sample statistics — [Bowyer et al.](https://arxiv.org/html/2503.01747v3); [Miller](https://arxiv.org/html/2411.00640v1)

### Inferences (ranked list; expected effects are my estimates, not measured)

| Rank | Lever | Targets which failure | Expected effect (uncertain) | Cost |
|---|---|---|---|---|
| 1 | Code-computed **goal status / remaining counts** in tool results, or a consolidated `check_plan` tool | week plan: ignores existing gym, forgets assignment | Large on week-plan scenarios (likely fixes most of them); small elsewhere | Low (code only) |
| 2 | **Guardrails in propose_*:** reject duplicate or already-pending moves with an actionable message; say "all goals proposed, reply now" | re-propose loop to 8 rounds | Eliminates most loop failures | Low |
| 3 | **Salvage/retry** when `content` is empty but `reasoning` contains a `<tool_call>` | tool call inside unclosed think | Recovers most of those failures | Low |
| 4 | On the nudge round, **named `tool_choice`** (propose_new_event / propose_move_event) instead of a text reminder; `strict: true` schemas | proposes nothing after describing a plan | Converts most "no proposal" failures into schema-valid proposals (quality still checked by validators) | Low (vLLM only) |
| 5 | **`thinking_token_budget`**, swept 2k / 4k / 8k / ∞ | latency, unclosed think, overthinking | Large latency cut (worst case 16k → ≤8k); accuracy effect unknown, so sweep | Low |
| 6 | **Verifier-filtered best-of-2/3**, preferring the shortest valid trajectory | residual stochastic failures | Meaningful if failures are not scenario-systematic; upper bound 0.83 → 0.97–0.99 under independence, real gain smaller | Medium (~N× tokens; feasible on 4090, not laptop) |
| 7 | Prompt: one compact worked week-plan example + "every goal must be covered" rule | week plan | Small to moderate, model-dependent | Low, but adds prompt tokens |
| 8 | Sampling: keep T 0.6 / top_p 0.95 / top_k 20; presence_penalty 0 → ~1 only if loops persist | repetition | Small | Trivial |
| 9 | Model swap to Qwen3-30B-A3B-Thinking-2507 (quantized) | general | Small to moderate (vendor: +1.2 BFCL, +5.3 TAU2-Retail, +0 TAU2-Airline) | High (memory); Qwen3-8B not recommended (BFCL 68.1 < 71.2) |
| ✗ | Switch to Qwen3-4B-Instruct-2507 for speed | latency | Likely accuracy loss (vendor TAU2-Airline 24.0 vs. 58.0) | — only as a laptop fallback with verification |

**Evaluation protocol:**
1. Freeze a 60–100 scenario held-out set from disjoint templates and calendar fixtures, plus hand-written requests and negative cases, with explicit goal-state specs. Version it.
2. For each variant, run 3 trials per scenario at production sampling settings, from clean state, on the same scenarios as the baseline.
3. Report:
   - pass^1 with a Wilson or Beta CI
   - pass^3
   - per-category rates
   - the paired difference vs. baseline with exact McNemar or paired-Bayes (count fixed vs. broken scenarios)
   - median and p90 thinking tokens, wall-clock, tool rounds, unclosed-think rate
4. Treat the original 6x2 suite as a smoke/regression gate only.
5. After any fine-tune, also run a small BFCL subset, an IFEval subset, and chat sanity prompts.
6. Read transcripts of all failures for each change.

### Gaps
- None of the expected effect sizes in the ranked table have been measured on this agent. They are informed estimates and must be validated with the paired protocol.
- OpenAI function-calling guidance, BFCL v3/v4 methodology pages, and the tool-documentation literature (Hsieh et al. 2023; EASYTOOL) were not covered within this session's budget.
