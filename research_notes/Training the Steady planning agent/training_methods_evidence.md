# Post-training methods for small (1–8B) multi-turn tool-calling agents: evidence comparison (SFT/distillation vs RFT vs on-policy distillation vs RLVR)

Scope note: Evidence below is tagged **[MATH]** (math/code reasoning), **[TOOL]** (single-step function calling, e.g. BFCL/API-Bank), or **[AGENT]** (multi-turn tool loops, e.g. tau-bench, BFCL multi-turn). Most strong head-to-head comparisons of SFT vs RL vs on-policy distillation are **[MATH]**. Multi-turn **[AGENT]** evidence for 1–8B models is thinner and mostly from 2025–2026 preprints and workshop papers. Target project: Qwen/Qwen3-4B-Thinking-2507, 4 tools, propose-only, about 9–11/12 eval passes, thinking up to about 16k tokens per task, one 24 GB GPU or a rented 48–80 GB GPU, about $10–30.

## Q1. Off-policy SFT / distillation on stronger-teacher trajectories: gains and failure modes for small students

### Takeaway
Off-policy distillation is the strongest *first* stage for building a reasoning model from a base model. DeepSeek-R1 and Qwen3 both made their small models this way, and it beats RL-from-scratch at 32B and below. But for an already post-trained small model it has well-documented failure modes: a learnability gap for students of 3B or less with long-CoT or much-larger teachers, compounding errors from distribution shift, imitative reasoning that generalizes worse, and forgetting of instruction-following. In tool use, R1-distilled-thought SFT placed before GRPO measurably *hurt* the final result compared with GRPO alone. The best positive [AGENT] evidence for teacher SFT (APIGen-MT/xLAM-2) used *verified, rejection-sampled* teacher trajectories, which makes it closer to RFT than to naive imitation.

### Cited Findings
**Headline "distillation beats RL for small models" results [MATH]**
- DeepSeek-R1, Table 6: on Qwen-32B-Base, large-scale RL (DeepSeek-R1-Zero-Qwen-32B) gets AIME'24 47.0 / MATH-500 91.6 / GPQA-D 55.0 / LiveCodeBench 40.2. SFT-distillation from R1 (DeepSeek-R1-Distill-Qwen-32B) gets 72.6 / 94.3 / 62.1 / 57.2. Authors' conclusions: "distilling more powerful models into smaller ones yields excellent results", but "advancing beyond the boundaries of intelligence may still require more powerful base models" — [DeepSeek-R1 v1](https://arxiv.org/html/2501.12948v1)
- DeepSeek-R1 distilled small models (SFT only, no RL stage): R1-Distill-Qwen-1.5B AIME'24 28.9 / MATH-500 83.9; Qwen-7B 55.5 / 92.8; Llama-8B 50.4 / 89.1. The paper says applying RL to these distilled models "yields significant further gains" but does not report those numbers — [DeepSeek-R1 v1](https://arxiv.org/html/2501.12948v1)
- The distillation set was about 800k samples (804,745 total: about 600k reasoning, about 200k non-reasoning) — [DeepSeek-R1](https://arxiv.org/html/2501.12948)
- Qwen3 small models (0.6B, 1.7B, **4B**, 8B, 14B, 30B-A3B) were *not* RL-trained directly. They used "strong-to-weak distillation": phase 1 off-policy distillation of teacher outputs in thinking and non-thinking modes, then phase 2 on-policy distillation that aligns student logits to a Qwen3-32B or 235B-A22B teacher by minimizing KL — [Qwen3 Technical Report](https://arxiv.org/abs/2505.09388)
- In Qwen3-8B, off-policy distillation alone reached AIME'24 55.0, AIME'25 42.8, GPQA-D 55.6. These were later surpassed by +RL (67.6 / 55.5 / 61.3) and by +on-policy distillation (74.4 / 65.5 / 63.3) — [Qwen3 Technical Report](https://arxiv.org/html/2505.09388)

**Data efficiency (s1/LIMO-style) [MATH, 32B only]**
- LIMO: 817 curated samples gave 57.1% AIME and 94.8% MATH in v1. The revised (COLM 2025) version uses about 800 samples on Qwen2.5-32B-Instruct for 63.3% AIME and 95.6% MATH — [LIMO](https://arxiv.org/abs/2502.03387)

**Learnability gap for small students [MATH]** ("Small Models Struggle to Learn from Strong Reasoners")
- Long-CoT minus short-CoT SFT, averaged over 5 math benchmarks (Qwen2.5 students): 0.5B −4.7, 1.5B −7.1, **3B −3.1**, **7B +1.7**, 14B +4.9, 32B +13.7. The crossover is around 7B for Qwen. For Llama it falls between 3.2-3B (−0.6) and 8B (+3.7) — [Li et al. 2025](https://arxiv.org/html/2502.12143v3)
- Large (72B) teacher minus small (3B) teacher CoT: student 0.5B −3.5, 1.5B −0.8, **3B +0.3**, 7B +6.6, 14B +3.0, 32B +6.5. Qwen2.5-0.5B AMC: 17.5 with the small teacher vs 5.0 with the large teacher — [Li et al. 2025](https://arxiv.org/html/2502.12143v3)
- Fix ("Mix Distillation", Qwen2.5-3B): Mix-Long scores 45.9 vs 40.3 for long-CoT alone (+5.6) and beats short-CoT alone (43.4). Mix-Large scores 45.8 vs 39.7 (+6.1). The best mix weight was α=0.2 (1:4 long:short) — [Li et al. 2025](https://arxiv.org/html/2502.12143v3)

**Failure modes: distribution shift, imitation, forgetting**
- Off-policy distillation trains the student only on states the teacher visits. Early student mistakes the teacher never makes push the student off-distribution, and this compounds over long sequences. Students also copy teacher *style and confidence* without its accuracy (citing Gudibande et al. 2023) — [Thinking Machines, On-Policy Distillation](https://thinkingmachines.ai/blog/on-policy-distillation/)
- Forgetting: midtraining Qwen3-8B on 100% domain documents moved internal-QA from 18% to 43% but dropped IF-eval from 85% to 45%. A 70/30 doc/chat mix gave 36% / 79%. Even SFT on the model's *own* samples degrades IF-eval at any practical nonzero learning rate, because finite-batch noise makes self-training effectively off-policy over time — [Thinking Machines](https://thinkingmachines.ai/blog/on-policy-distillation/)
- SFT of Qwen3-4B on Codeforces data raised LiveCodeBench from 35.1 to 40.3 but dropped IFEval from 83.4 to 79.5 — [HF "Unlocking On-Policy Distillation for Any Model Family"](https://huggingfaceh4-on-policy-distillation.hf.space/)
- LoRA penalty for off-policy SFT at scale: on a 400k-prompt SFT, LoRA rank 32 trailed full fine-tuning by 13% (by 6% after on-policy distillation) — [Thinking Machines](https://thinkingmachines.ai/blog/on-policy-distillation/). LoRA underperforms full fine-tuning when SFT data exceeds its capacity, and at large batch sizes — [Thinking Machines, LoRA Without Regret](https://thinkingmachines.ai/blog/lora/)
- SFT "memorizes" training data and struggles out of distribution, while outcome-reward RL generalizes to rule and visual variants. *But* SFT is still needed to stabilize output format before RL — [Chu et al., SFT Memorizes, RL Generalizes](https://arxiv.org/abs/2501.17161)

**Tool-use specific [TOOL]**
- Tool-N1 (Qwen2.5-7B/14B-Instruct): SFT on 5,518 DeepSeek-R1-distilled reasoning trajectories produces "imitative reasoning that limits generalization." BFCL averages: No-Reason SFT 81.47, Reason-SFT 82.71, Reason-SFT(50%)+RL(50%) 83.17, Pure RL 83.24 (100% data) / 83.01 (50%) — [Tool-N1](https://arxiv.org/html/2505.00024v2)
- ToolRL: SFT on 400 R1-distilled-thought examples *before* GRPO underperformed GRPO from the raw Instruct model on BFCL v3 for every model tested. Qwen2.5-1.5B 40.93 vs 46.20; 3B 46.42 vs 52.98; 7B 39.25 vs 58.38; Llama-3.2-3B 42.54 vs 44.10. SFT-initialized models reached *higher training reward but generalized worse*. Also, SFT on 4k examples sometimes scored *below* the raw model (Qwen2.5-7B BFCL 36.53 vs raw 41.97) — [ToolRL](https://arxiv.org/html/2504.13958)

**Positive [AGENT] evidence for teacher-trajectory SFT (verified)**
- APIGen-MT: about 5K multi-turn trajectories, kept only if the final environment state and responses match ground truth (rejection sampling, up to 3 attempts per task). Trained with "filtered behavioral cloning" (SFT, loss on assistant tokens only, full fine-tuning, at most 3 epochs, mixed with other function-calling data). tau-bench overall: xLAM-2-1b 21.8, **3b 38.2**, **8b 46.7**, 32b 54.6, 70b 56.2, vs GPT-4o 52.9 and Qwen2.5-32B-Instruct 24.7. BFCL v3: 3b 65.11, 8b 72.83 — [APIGen-MT](https://arxiv.org/html/2504.03601)
- EnvFactory: 85 verified environments and 2,575 SFT+RL trajectories gave Qwen3-series gains of up to +15% BFCLv3 and about +6% on tau2-Bench/VitaBench (abstract) — [EnvFactory](https://arxiv.org/abs/2605.18703). A search-result summary (not verified against the full paper) reported Qwen3-4B BFCL multi-turn going from 33.50 to 44.25 after SFT and to 48.50 after a further RL stage.

### Inferences
- Qwen3-4B was itself produced by off-policy, then on-policy, distillation from Qwen3-32B/235B (per the Qwen3 report; the report covers the original Qwen3-4B, not the 2507 refresh). Its thinking style is therefore already a distilled Qwen-teacher distribution. SFT on Gemini trajectories would pull it toward a *different* teacher's style, which is the "style imitation / distribution shift" failure mode.
- A 4B student sits just above the ≤3B learnability-gap zone (3B: −3.1 for long CoT; 7B: +1.7). Gains from a much stronger, longer-reasoning teacher are therefore expected to be small or negative unless traces are filtered or mixed. Caveat: that evidence used non-reasoning Qwen2.5 students on math.
- The ToolRL and Tool-N1 results show that teacher-thought SFT before RL buys little or hurts in tool calling. APIGen-MT shows that teacher SFT works when trajectories are *execution-verified*. If Gemini data is used, it should go through the same code checks and be treated as "rejection-sampled teacher data", not raw imitation.

### Gaps
- No found study compares Gemini-trajectory SFT against self-RFT on a *thinking* 4B model for multi-turn tools.
- Unverified (not fetched here): whether the Gemini API exposes raw reasoning tokens, or only thought summaries. If only summaries are available, the `<think>` content for SFT would be missing or mismatched. Gemini also cannot provide per-token logprobs over Qwen's vocabulary for logit-level distillation.
- I could not retrieve s1 (arXiv 2501.19393) numbers. The Qwen3-4B-Thinking-2507 post-training recipe is not in the Qwen3 report.
- I did not verify MiniLLM numbers.

## Q2. Rejection-sampling fine-tuning / self-distillation / STaR / expert iteration (RFT, ReST-EM): gains and limits

### Takeaway
Self-generated, verifier-filtered SFT (RFT, ReST-EM, STaR) reliably beats SFT on fixed data, especially for weaker models and when many distinct correct paths are kept. It is the cheapest and most on-distribution option and is already built in this project. Its documented limits: it learns nothing from tasks the model never solves; positive-only reinforcement narrows diversity (pass@k); and repeated self-SFT drifts off-policy. Choosing the *shortest* correct sample is also a known, effective length-reduction method (about 30% fewer tokens with accuracy maintained, [MATH]).

### Cited Findings
- RFT (Yuan et al.): LLaMA-7B GSM8K improved from 35.9% (SFT) to 49.3% when rejection samples from multiple models are combined. RFT gives *bigger* gains to weaker models, and samples with *more distinct reasoning paths* help more — [Scaling Relationship on Learning Mathematical Reasoning](https://arxiv.org/abs/2308.01825) [MATH]
- ReST-EM (generate, filter with binary feedback, fine-tune, repeat "a few times") on PaLM-2 for MATH and APPS "significantly surpasses fine-tuning only on human data" and scales with model size. It requires a verifiable/binary reward — [ReST-EM](https://arxiv.org/abs/2312.06585) [MATH/code]
- APIGen-MT's agent data pipeline is effectively teacher-side RFT for multi-turn agents: up to 3 attempts per task, kept only if the final environment state and outputs match ground truth. It produced the xLAM-2 results in Q1 (8B: 46.7 tau-bench overall) — [APIGen-MT](https://arxiv.org/html/2504.03601) [AGENT]
- Self-training on the model's own concise correct samples (best-of-N plus few-shot conditioning) cut output tokens by about 30% on average across GSM8K and MATH while maintaining accuracy, across 5 model families — [Munkhbat et al., Self-Training Elicits Concise Reasoning](https://arxiv.org/abs/2502.20122) [MATH]
- Positive-only reinforcement (which RFT is) raises pass@1 but *hurts* pass@k at high k. Negative-only training preserved diversity (Qwen2.5-Math-7B MATH pass@256 = 96.9, matching base), and upweighting negatives improved pass@k on MATH/AIME25/AMC23 — [Zhu et al., The Surprising Effectiveness of Negative Reinforcement](https://arxiv.org/abs/2506.01347) [MATH]
- Diversity collapse: during SFT and RL, probability mass concentrates on a single reasoning path, causing early pass@k drops — [Dang et al., ICLR 2025 workshop](https://mlanthology.org/iclrw/2025/dang2025iclrw-assessing)
- Self-SFT drifts: SFT on the model's own samples still degraded IF-eval at practical learning rates (finite-batch noise makes it effectively off-policy) — [Thinking Machines](https://thinkingmachines.ai/blog/on-policy-distillation/)
- Community example [AGENT, unverified, search summary]: Qwen3-4B-Instruct trained with SFT, then rejection fine-tuning, then GRPO reported tau2-bench Pass@1 36.0% and Pass@4 59.0% vs a 14.3% Pass@4 baseline. Its metric differs from the official pass^k — [model card](https://featherless.ai/models/Jarrodbarnes/Qwen3-4B-tau2-grpo-v1)

### Inferences
- The project's collector (4 tries, keep the shortest passing) is RFT plus a ShorterBetter-style "sample optimal length" selection in SFT form. The evidence predicts a reliable but modest gain on tasks the model *sometimes* solves (1–3 of 4), plus shorter thinking.
- It will not fix task types the model fails 4/4. Those need more samples per hard task (e.g., 8–16), hint/scaffolded prompts whose traces are then re-generated without hints, RL with negative signal, or a teacher.
- Because RFT is positive-only and reduces diversity, keeping 2+ distinct passing trajectories per task (not only the single shortest) is supported by Yuan et al.'s "distinct paths" finding. One or two RFT rounds are better than many (drift, collapse).

### Gaps
- No found paper reports RFT gains for a *thinking* 1–8B model on multi-turn tool tasks with clean ablations (APIGen-MT is teacher-side and non-thinking).
- STaR rationalization-specific numbers were not retrieved.
- There is no direct measurement of how many RFT iterations help before collapse on agent tasks.

## Q3. On-policy distillation (Thinking Machines 2025, GKD, Qwen3 strong-to-weak, GOLD): results, compute savings, requirements

### Takeaway
On-policy distillation means the student samples and the teacher scores each student token, with per-token reverse KL as the dense reward. It is the best-documented method for small models in [MATH]. It beat RL in Qwen3-8B (AIME'24 74.4 vs 67.6) at about 1/10 the GPU hours, and reached RL-level AIME at a reported 9–30x less compute than SFT scaling. It also recovers capabilities lost to SFT (forgetting). It needs a teacher that (a) is genuinely better on *this* task and (b) can return logprobs on student tokens. A same-tokenizer teacher is simplest; cross-tokenizer needs GOLD/ULD. Applied to tool-integrated reasoning, naive on-policy distillation suffers from compounding erroneous tool calls (SOD, 2026). [AGENT] evidence is very thin.

### Cited Findings
- Qwen3-8B (Table 21): off-policy distill gives AIME'24 55.0 / AIME'25 42.8 / LCB 42.0 / GPQA-D 55.6. **+RL** gives 67.6 / 55.5 / 52.9 / 61.3 using **17,920 GPU-h**. **+On-policy distillation** gives 74.4 / 65.5 / 60.3 / 63.3 using **1,800 GPU-h**. On-policy distillation raised pass@64 (AIME'24 90.0 to 93.3; AIME'25 83.3 to 86.7); RL did not improve pass@64 — [Qwen3 Technical Report](https://arxiv.org/html/2505.09388) [MATH]
- Thinking Machines (Oct 27, 2025), Qwen3-8B-Base student: SFT on 400k OpenThoughts-3 prompts reaches 60% AIME'24, with about 70% extrapolated at 2M. RL reaches about 68%. On-policy distillation from the 400k-SFT checkpoint reaches 70% in about 150 steps (about 77K prompts × 4 samples). Compute is 9x cheaper than SFT-2M if the SFT data exists, about 18x in GPU-hours, and about 30x including teacher sampling — [Thinking Machines](https://thinkingmachines.ai/blog/on-policy-distillation/) [MATH]
- Self-distillation from an RL-trained teacher recovered the RL AIME score in under 10 gradient steps, vs about 70 RL steps, an estimated 50–100x compute efficiency. Distillation gives about 1 bit/token (O(N) bits per episode) vs O(1) bits per episode for RL — [Thinking Machines](https://thinkingmachines.ai/blog/on-policy-distillation/)
- Mechanics: advantage = −(student logprob − teacher logprob) on student-sampled tokens, discount 0, no reward model, one teacher forward pass (no teacher sampling). It is a small change to RL code with a KL regularizer. Weak SFT initializations need larger batches. Training on a single prompt for 20 steps (5,120 sequences) approximately matched teacher AIME — [Thinking Machines](https://thinkingmachines.ai/blog/on-policy-distillation/)
- Forgetting recovery: Qwen3-8B midtrained (70% docs) scored internal-QA 36% / IF-eval 79%. Adding on-policy distillation from the earlier checkpoint gave 41% / 83% (baseline 18% / 85%) — [Thinking Machines](https://thinkingmachines.ai/blog/on-policy-distillation/). Similarly, Qwen3-4B after code SFT went from IFEval 79.5 to 82.8 via on-policy distillation from the original Qwen3-4B, keeping LCB at about 39.8 — [HF GOLD blog](https://huggingfaceh4-on-policy-distillation.hf.space/)
- GKD: trains the student on its own generated sequences using teacher feedback, with flexible divergences for when the student cannot match the teacher. It addresses train/inference distribution mismatch, was tested on summarization, translation, arithmetic reasoning and instruction tuning, and can be combined with RL fine-tuning — [Agarwal et al., GKD](https://arxiv.org/abs/2306.13649)
- HF/TRL (Oct 29, 2025; updated June 2026), Countdown task: GKD with the same tokenizer (Qwen2.5-1.5B student, Qwen2.5-7B teacher) recovered over 80% of teacher performance; fully on-policy (λ=1) was best; GKD reached 2x GRPO's performance. GOLD (cross-tokenizer, e.g. Llama-3.2-1B student and Qwen3-4B-Instruct-2507 teacher) recovered 60% of the teacher vs 10% for ULD, beat GRPO by 20%, and beat SFT by 15%. Available as the experimental `GOLDTrainer` in TRL (`use_uld_loss`, `teacher_tokenizer_name_or_path`) — [HF blog](https://huggingfaceh4-on-policy-distillation.hf.space/); [TRL GOLD docs mirror](https://hf-2025.pages.dev/docs/trl/en/gold_trainer.md)
- SOD (May 2026): standard on-policy distillation on *tool-integrated reasoning* breaks down because erroneous tool calls cascade, increasing student-teacher divergence. Reweighting distillation strength per step by divergence gave up to +20.86% over the second-best baseline (math, science, code). The 0.6B student reached 26.13% on AIME 2025 (self-reported) — [SOD](https://arxiv.org/html/2605.07725v1) [TOOL-integrated MATH]

### Inferences
- For this project, the natural same-tokenizer teachers are larger Qwen3 thinking models (e.g., Qwen3-30B-A3B-Thinking-2507 or Qwen3-32B). Whether any of them scores *higher than the 4B on these 12 tasks* must be measured first: on-policy distillation can only transfer what the teacher does better.
- Gemini cannot serve as an on-policy logit teacher: there are no full logprobs over student tokens (see Q1 gaps). That limits Gemini to off-policy SFT or a reward/judge role.
- A "teacher" can also be the same 4B model with extra context (task-specific hints or a stronger system prompt), or an RL-improved checkpoint (Thinking Machines' self-distillation and personalization setups used earlier or RL checkpoints as teachers). This is cheap and needs no bigger GPU.
- Memory (inference, not from a source): a 4B student plus an 8B teacher in bf16 is about 8 GB + 16 GB of weights before KV cache. That is tight on 24 GB, but comfortable on 48–80 GB.
- On-policy distillation is also a good *repair* step after RFT or GRPO if general skills (chat formatting, refusal behavior, non-planning queries) regress.

### Gaps
- No found result applies on-policy distillation to *multi-turn* tool agents (tau-bench, BFCL multi-turn) at 1–8B. SOD is the closest and is mostly math/code with tools.
- The Thinking Machines post does not state a same-tokenizer requirement explicitly. The GOLD blog implies vanilla GKD needs one.
- MiniLLM numbers were not retrieved.
- There is no evidence on whether on-policy distillation shortens or lengthens thinking for a thinking student.

## Q4. RL with verifiable rewards (GRPO family) for tool use and multi-turn agents: gains at 1.5–8B, steps/samples, SFT-before-RL, reward design, hacking risks

### Takeaway
For [TOOL] single-step calling, GRPO with a format + correctness reward on about 4k samples gives large gains at 1.5–7B over base and over SFT (ToolRL: up to +17 points over base and about +15 over SFT). Pure RL matches or beats SFT→RL (Tool-N1, ToolRL). For [AGENT] multi-turn, the key finding is that RL must run the *actual multi-turn tool loop* in rollouts. Single-turn RLVR did nothing for a 2B agent, while multi-turn GRPO took completion from 4.3% to 58.7%, with most gains by step 25. Risks are concrete: vanilla GRPO *degraded* Qwen3-4B-2507 on BFCL multi-turn (48.0 to 41.6), naive dense per-turn rewards cost up to 14 points, multi-turn RL hits "Echo Trap" variance collapse, and GRPO's length normalization inflates wrong-answer length. Reported multi-turn gains on strong 4B models are modest (+2.9 to +10 points).

### Cited Findings
**[TOOL] single-step, 1.5–8B**
- ToolRL (Qwen2.5-1.5B/3B/7B-Instruct, Llama-3.2-3B): 4K training samples (2K ToolACE, 1K Hammer-masked, 1K xLAM), GRPO via veRL, batch 512, 4 rollouts/query, 15 epochs, LR 1e-6, no KL, temperature 1.0, max response 1024, 2×A100-80GB per run — [ToolRL](https://arxiv.org/html/2504.13958)
- ToolRL BFCL v3 overall, raw vs GRPO cold start: 1.5B 19.41 to 46.20; 3B 33.04 to 52.98; 7B 41.97 to 58.38; Llama-3B 22.09 to 44.10. PPO cold start was lower than GRPO (e.g., 7B 46.68). API-Bank: 1.5B 30.65 to 63.15; Bamboogle: 1.5B 20.8 to 44.0. The abstract reports "17% improvement over base models and a 15% gain over SFT models" — [ToolRL](https://arxiv.org/html/2504.13958)
- ToolRL reward: binary format reward (tags in order) plus correctness in [−3, 3] from tool-name set overlap, parameter-name matching and exact parameter-value matching under optimal call matching, for a total in [−3, 4]. Finer granularity beat coarse (coarse gives sparser signal). Shrinking correctness to [−1, 1] hurt (e.g., 1.5B 39.47). Abrupt two-stage reward scaling destabilized training — [ToolRL](https://arxiv.org/html/2504.13958)
- Tool-N1-7B/14B (Qwen2.5-Instruct, about 9.6k processed ToolACE + 60k xLAM, batch 1024, 5 rollouts, LR 1e-6, KL 1e-3, 7 epochs): BFCL overall 84.82 (7B) and 85.97 (14B) vs GPT-4o 83.97, ToolACE-8B 82.57, Hammer2.1-7B 81.88, xLAM-2-70b 80.70; raw Qwen2.5-7B 67.54 — [Tool-N1](https://arxiv.org/html/2505.00024v2)
- Tool-N1 reward ablation: a *binary* reward (1 only if `<think>` and `<tool_call>` are both present and the call matches) scored 84.82. Without the reasoning-format requirement it scored 81.94 (Live 80.38 to 76.24). Fine-grained partial-credit variants were *worse* (83.74, 82.58) — [Tool-N1](https://arxiv.org/html/2505.00024v2). Note: this conflicts with ToolRL's finding that fine-grained beats coarse, likely because of different reward constructions.
- ResT (token-reweighted policy gradient), BFCL multi-turn overall, base / GRPO / ResT: Qwen3-1.7B 8.62 / 14.50 / 16.00; **Qwen3-4B-2507 48.00 / 41.62 / 50.38**; Qwen3-8B 33.00 / 36.00 / 40.13; Qwen3-14B 36.62 / 38.88 / 44.25. Plain GRPO's output length collapsed to about 125 tokens; ResT kept it above 300. Rule-based rewards concentrate on format tags, tool names and key parameters, and reasoning tokens contribute little early. Training used 4k ToolACE/Hammer/xLAM data with multi-turn dialogues *split into single-step instances*. Thinking mode was unspecified — [ResT](https://arxiv.org/html/2509.21826)

**[AGENT] multi-turn**
- "When the Loop Closes" (NeurIPS 2026 SLM-Agents workshop, single author): seven *single-turn* RLVR objectives on a 2B SFT anchor gave no gain beyond seed noise. Importance ratios collapsed to about 1 and within-group reward variance collapsed early. Multi-turn failures such as "redundant-reload loops that exhaust the turn budget" never occur in single-turn rollouts. *Multi-turn GRPO* that executes the tool loop raised completion from **4.3% to 58.7%** (matching a 4B SFT agent) and grounded answers from 3.7% to 56.0%. **48 of 52 gain points came by step 25**, and later steps neither helped nor preserved the peak. Per-turn vs per-trajectory credit was secondary (p=.086). Two infrastructure bugs each shifted scores by 10–14 points — [When the Loop Closes](https://neurips.cc/virtual/2026/171163); [OpenReview](https://openreview.net/forum?id=txu99R4QRd)
- MT-GRPO + GTPO (Apr 2026), tau-bench airline: **Qwen3.5-4B 63.8 to 66.7 (+2.9)**; Qwen3-30B-A3B 58.0 to 69.5 (+11.5), vs GPT-4.1 49.4 and Claude Sonnet 4.5 70.0. Naively designed dense per-turn rewards *degraded* performance by up to 14 points (reward discriminativeness misaligned with advantage direction). Iterative reward calibration from rollout data fixed this — [Multi-Turn RL with Iterative Reward Calibration](https://arxiv.org/abs/2604.02869)
- RAGEN/StarPO: multi-turn agent RL shows an "Echo Trap" (reward-variance cliffs and gradient spikes). StarPO-S stabilizes it with trajectory filtering, a critic and gradient stabilization. Diverse initial states, medium interaction granularity and frequent sampling help. Without fine-grained, reasoning-aware rewards, reasoning "hardly emerge[s]", giving shallow strategies or hallucinated thoughts — [RAGEN](https://arxiv.org/abs/2504.20073)
- ARPO: entropy-based adaptive branching right after tool calls, plus step-level advantage attribution. It beat trajectory-level RL on 13 benchmarks using "only half of the tool-use budget" — [ARPO](https://arxiv.org/abs/2507.19849)
- Search-result summaries (not verified against full text): PROVE GRPO lifted Qwen3-4B BFCL multi-turn by +10.2 and tau2-bench average from 25.0 to 31.3 — [PROVE](https://arxiv.org/pdf/2606.03892). Another 2026 paper found off-the-shelf user simulators unstable and SFT'd the user model before multi-turn GRPO — [arXiv 2601.22607](https://arxiv.org/pdf/2601.22607v3)
- Evaluation fragility: multi-turn tool-calling scores shift substantially with seed, system prompt, multi-turn template construction and how reasoning history is carried forward. Many RL prompts yield no learning signal (all-pass or all-fail groups), which wastes compute — [On Effectiveness and Efficiency of Agentic Tool-calling and RL Training (ICML 2026)](https://arxiv.org/abs/2606.00135)

**SFT before RL: help or hurt?**
- Hurt or no gain: ToolRL (SFT400+GRPO below GRPO cold start for all 4 models; see Q1) — [ToolRL](https://arxiv.org/html/2504.13958). Tool-N1: SFT→RL 83.17 ≈ pure RL 83.24 — [Tool-N1](https://arxiv.org/html/2505.00024v2)
- Help: SFT stabilizes output format so RL can work — [SFT Memorizes, RL Generalizes](https://arxiv.org/abs/2501.17161). The 2B agent paper's RL started *from an SFT anchor* — [When the Loop Closes](https://neurips.cc/virtual/2026/171163). DeepSeek-R1 reports RL on top of distilled models "yields significant further gains" — [DeepSeek-R1](https://arxiv.org/html/2501.12948v1)

**Algorithm and efficiency details**
- Dr. GRPO: GRPO's normalization introduces an optimization bias that "artificially increases response length (especially for incorrect outputs)". The unbiased variant improves token efficiency at equal accuracy. A minimalist R1-Zero recipe hit 43.3% AIME'24 at 7B — [Understanding R1-Zero-Like Training](https://arxiv.org/abs/2503.20783) [MATH]
- LoRA is fine for RL: LoRA "fully matches" full fine-tuning for policy-gradient RL *even at rank 1* (Llama-3.1-8B on GSM8K/MATH; Qwen3-8B-Base on DeepMath with 8,192-token responses). RL conveys about O(1) bits per episode, so capacity isn't binding. Optimal LoRA LR is about 10x full-FT LR (about 15x for runs under 100 steps). LoRA uses about 2/3 of full-FT FLOPs per pass. Use MLP (not attention-only) LoRA — [LoRA Without Regret](https://thinkingmachines.ai/blog/lora/)

### Inferences
- Several of the project's failure modes map onto documented RL targets. "Re-proposing until hitting the round limit" is the same class as the "redundant-reload loops that exhaust the turn budget" that only multi-turn rollouts expose. "Tool calls inside unclosed thinking" is a format violation that Tool-N1-style binary format gating (closed `</think>` before `<tool_call>`) addresses directly. "Describing a plan instead of calling proposal tools" and "not covering every assignment / counting existing events" are outcome-checkable by the existing code checks.
- Because Qwen3-4B-2507 is already strong (48% BFCL multi-turn), plain GRPO *can* make it worse (ResT). Expect single-digit gains (MT-GRPO 4B: +2.9) rather than the +20–40 point jumps seen on weak 1.5B Instruct models.
- Run few steps with frequent eval. The 2B paper saw near-total saturation by about 25 steps, with later steps not preserving the peak.
- Filter prompts to those with mixed pass/fail across the group, since all-pass or all-fail groups give zero GRPO advantage. The existing 4-try collector already measures this per task.
- Reward recommendation from the evidence: outcome-level binary pass/fail from the task checks, gated by format validity. Avoid hand-designed dense per-turn shaping (up to −14 points) and fixed length rewards (see Q5).
- Reward hacking risks specific to this setup, all inference: (a) proposing many events to "cover" goals (check precision, not just recall); (b) proposing without reading the schedule; (c) emitting a proposal then stopping early to dodge later checks. Each check should be adversarially tested before RL.

### Gaps
- No found result on GRPO/DAPO/GSPO/RLOO specifically for a Qwen3-*Thinking* 4B with 8–16k thinking in multi-turn tool loops. Most tool RL used max response 1024 tokens or non-thinking/Instruct models.
- I did not retrieve primary numbers for DAPO, GSPO, RLOO, ReTool, Agent-R1, SkyRL, ToolACE or Hammer. These are named in the question but unverified here.
- No found compute and cost figures for multi-turn GRPO on a single 24 GB GPU with long thinking. Rental pricing was not researched.
- The ToolRL vs Tool-N1 disagreement on fine-grained vs binary rewards is unresolved.

## Q5. Reducing thinking length while keeping accuracy

### Takeaway
All strong length-reduction evidence is [MATH] on 1.5–7B R1-distilled models. RL with length-aware rewards cuts tokens 50–80% (ShorterBetter) or 53% with +2.4% accuracy (AdaptThink). Self-training on the shortest correct samples cuts about 30% with accuracy maintained, which is the project's current method. Prompted length targets (L1/LCPO) beat budget forcing by 20–25 absolute points at 512–1024 token budgets. In *tool use*, the only direct evidence is negative: ToolRL's fixed 512-token length reward lowered BFCL accuracy, and GRPO length collapse to about 125 tokens accompanied a drop on Qwen3-4B-2507.

### Cited Findings
- ShorterBetter: reward based on "Sample Optimal Length" (the shortest correct response in the group). DeepSeek-R1-Distill-Qwen-1.5B/7B saw a 50–80% output-length reduction with accuracy maintained — [ShorterBetter](https://arxiv.org/abs/2504.21370) [MATH]
- AdaptThink: RL that chooses Thinking vs NoThinking by difficulty. DeepSeek-R1-Distill-Qwen-1.5B saw −53% average response length and +2.4% accuracy on 3 math sets — [AdaptThink](https://arxiv.org/abs/2505.13417) [MATH]
- L1/LCPO (DeepScaleR-1.5B base, 40K math problems, 700 GRPO steps, batch 128, LR 1e-6, 4K training context): beats S1 budget forcing by up to 100% relative / 20% absolute, and by 100–150% relative / 20–25% absolute at 512 and 1024 tokens. L1-Max matches the unconstrained DeepScaleR-4K while often using up to 2x fewer tokens. Mean length-adherence error is about 3% on math and 20–40% out of domain — [L1](https://arxiv.org/html/2503.04697) [MATH]
- Self-training on concise own samples: about −30% output tokens on GSM8K/MATH with accuracy maintained — [Munkhbat et al.](https://arxiv.org/abs/2502.20122) [MATH]
- Dr. GRPO: standard GRPO normalization inflates incorrect-response length. Removing the bias improves token efficiency — [Dr. GRPO](https://arxiv.org/abs/2503.20783) [MATH]
- [TOOL] ToolRL: "longer reasoning traces are not inherently better", but a fixed length reward (target 512) *lowered* BFCL: Qwen2.5-1.5B 46.20 to 33.23 and 3B 52.98 to 48.89 (Llama-3B +0.9). A dynamic length reward also failed to help — [ToolRL](https://arxiv.org/html/2504.13958)
- [TOOL] ResT: plain GRPO's output length collapsed to about 125 tokens on Qwen3 tool tasks, with Qwen3-4B-2507 BFCL multi-turn dropping from 48.00 to 41.62. ResT kept above 300 tokens and improved — [ResT](https://arxiv.org/html/2509.21826)
- Learnability-gap paper: small (≤3B) students learn better from shorter chains — [Li et al.](https://arxiv.org/html/2502.12143v3)

### Inferences
- The cheapest supported path is what the project already does: select the shortest passing trajectory for RFT (ShorterBetter's SOL, applied as SFT). Optionally add a soft cap during RL rollouts (a max thinking budget; L1 trained at 4K context) and a Dr. GRPO-style unbiased loss, rather than an explicit length-penalty term.
- If a length term is added, make it *conditional on passing* (shortest-correct-relative, as in ShorterBetter) rather than a fixed target (ToolRL's fixed target hurt). Watch for collapse to very short thinking (ResT).
- 16k-token thinking makes RL rollouts expensive. Shortening thinking via RFT *before* RL should cut RL rollout cost proportionally (inference, not measured in a source).

### Gaps
- No found length-reduction study on multi-turn tool agents or on Qwen3-4B-Thinking-2507 specifically.
- s1 budget-forcing accuracy numbers were not retrieved; only L1's comparison against it.
- No evidence on whether shortening thinking hurts *multi-step planning* (counting events, covering all assignments), which is exactly where this project fails.

## Q6. Synthesis: which ordering of methods does the evidence support for a 4B thinking model with verifiable synthetic tasks and a $10–30 budget?

### Takeaway
The evidence best supports a staged sequence of on-distribution methods:
1. Enlarge the eval.
2. Run 1–2 rounds of self-RFT (shortest *and* diverse passing trajectories, LoRA).
3. Run a short multi-turn GRPO with LoRA, a binary outcome + format reward, an unbiased (Dr. GRPO-style) loss, a filtered prompt set, and early stopping.
4. Optionally use on-policy distillation as a repair or boost step only if a same-tokenizer Qwen teacher measurably beats the 4B on these tasks.

Off-policy Gemini SFT ranks last: learnability gap, style/distribution shift, SFT-before-RL hurting in ToolRL, imitative reasoning in Tool-N1, forgetting, and practical issues around thinking traces and logprobs. Most of the strongest supporting numbers are [MATH]. The multi-turn [AGENT] evidence is a handful of 2026 preprints and workshop papers.

### Cited Findings
- For small models the field's own recipes distill first (off-policy, then on-policy) instead of RL-from-scratch. On-policy distillation beat RL at about 1/10 the GPU hours in Qwen3-8B — [Qwen3](https://arxiv.org/html/2505.09388); [DeepSeek-R1](https://arxiv.org/html/2501.12948v1); [Thinking Machines](https://thinkingmachines.ai/blog/on-policy-distillation/)
- In tool calling, GRPO from the Instruct model beat R1-distilled-SFT→GRPO for 1.5–7B — [ToolRL](https://arxiv.org/html/2504.13958). Pure RL ≈ SFT→RL — [Tool-N1](https://arxiv.org/html/2505.00024v2)
- Multi-turn RL must close the tool loop. Gains saturate by about 25 steps on a 2B agent — [When the Loop Closes](https://neurips.cc/virtual/2026/171163)
- Strong 4B models gain modestly from multi-turn RL (+2.9 tau-bench airline) — [MT-GRPO](https://arxiv.org/abs/2604.02869). Plain GRPO can regress Qwen3-4B-2507 — [ResT](https://arxiv.org/html/2509.21826)
- Verified-trajectory SFT (rejection-sampled, execution-checked) is effective for small multi-turn agents (xLAM-2-3b 38.2 and 8b 46.7 on tau-bench vs Qwen2.5-32B-Instruct 24.7) — [APIGen-MT](https://arxiv.org/html/2504.03601)
- LoRA suffices for RL even at rank 1, with an LR about 10x full-FT. LoRA lags on large SFT sets — [LoRA Without Regret](https://thinkingmachines.ai/blog/lora/)
- On-policy distillation recovers forgotten instruction-following after domain SFT (Qwen3-4B IFEval 79.5 to 82.8) — [HF GOLD blog](https://huggingfaceh4-on-policy-distillation.hf.space/)
- Evaluation noise and infrastructure issues can move multi-turn scores by 10–14 points — [When the Loop Closes](https://neurips.cc/virtual/2026/171163); [ICML 2026 tool-calling eval paper](https://arxiv.org/abs/2606.00135)

### Inferences
**Ranking for this project (best evidence-supported value per dollar first):**
1. **Expand the eval first (near $0).** With 12 runs, one run is 8.3 points, so "9 vs 11 of 12" is within noise given the documented seed/prompt sensitivity. A held-out set of about 50–100 synthetic tasks × 2–3 seeds, stratified by failure type, is needed to detect the single-digit gains the literature predicts for a strong 4B model.
2. **Self-RFT, 1–2 rounds (cheapest; collector exists).** Use more tries on hard task types (8–16) so that 0/4 tasks get some passes. Keep shortest *plus* 1–2 diverse passing trajectories. Use LoRA at a low LR, few epochs, and mix in some general/chat samples to limit drift. Expected effect: modest accuracy gain on "sometimes-solved" tasks and about 30% shorter thinking (by analogy with math results).
3. **Multi-turn GRPO with LoRA on the synthetic generator** (the main lever for the loop/format/coverage failures):
   - Run the real tool loop in rollouts, with the round limit enforced.
   - Reward: binary pass from the code checks, gated by valid format (closed `</think>`, then a tool call). Do not use dense per-turn shaping.
   - Use a Dr. GRPO-style unbiased loss and a thinking cap (e.g., 4–8k) to control rollout cost.
   - Keep only prompts with mixed outcomes. Run a few dozen steps with eval every few steps and keep the best checkpoint.
   - Watch for length collapse and regression (ResT).
   - Starting from the RFT checkpoint is reasonable: the anchor in the 2B paper was SFT'd, and self-RFT is on-distribution, unlike ToolRL's teacher-thought SFT that hurt. This ordering is inference, not directly tested.
4. **On-policy distillation (conditional).** This applies only if a Qwen3 thinking teacher, e.g. 30B-A3B-Thinking-2507 or 32B (same tokenizer), scores better on the expanded eval. It likely needs the rented 48–80 GB GPU. It is also useful as a cheap "repair" pass against forgetting, with the original 4B as teacher on general prompts.
5. **Off-policy Gemini SFT (lowest).** If used at all, run Gemini trajectories through the same code checks (APIGen-MT-style), and convert them to the student's format only where Gemini actually provides reasoning. Mix them with the student's own passing samples (Mix-Distillation-style ratios), rather than replacing them. Use Gemini mainly to generate *solutions for tasks the 4B never solves*, since that is the one gap RFT and GRPO cannot close.
- Where evidence is thin:
  - (a) Every method comparison with clean ablations at scale is [MATH].
  - (b) Multi-turn tool RL at 1–8B is 2025–2026 preprint and workshop evidence, often on non-thinking Instruct models with short (about 1k-token) responses.
  - (c) There is no direct evidence on 16k-token thinking models in tool loops, on Gemini-to-Qwen distillation, or on RFT→GRPO ordering for agents.

### Gaps
- No head-to-head study of RFT→GRPO vs teacher-SFT→on-policy distillation on a multi-turn tool agent at 4B.
- No cost data for running multi-turn GRPO with long thinking within $10–30. Rollout throughput for Qwen3-4B with 8–16k thinking on a 24 GB GPU was not researched.
- I found no evidence on how well LoRA-RL on a thinking model preserves general chat ability without a repair step.
