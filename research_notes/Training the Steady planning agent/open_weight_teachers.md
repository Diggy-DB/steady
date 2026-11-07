# Open-weight teacher models for distilling multi-turn tool-calling trajectories into Qwen3-4B-Thinking-2507

Research date: 2026-11-05. Student: Qwen/Qwen3-4B-Thinking-2507 (reasoning in `<think>...</think>`, hermes-style `<tool_call>{json}</tool_call>`, served with vLLM `--reasoning-parser deepseek_r1 --tool-call-parser hermes`). Budget: about $10–30 total.

Source quality: most benchmark numbers below come from the vendors' own Hugging Face model cards, so they are vendor-reported. Different cards use different tau-bench versions and fixes, so the numbers are often not comparable across cards. Prices come mostly from third-party aggregators and disagree with each other. Treat every price as approximate and check the provider's page before spending.

## Q1. Candidate teachers: license, output-use terms, multi-turn tool-use benchmarks, reasoning visibility

### Takeaway
The best fits on license and format are the Qwen3-2507 thinking models: Qwen3-235B-A22B-Thinking-2507, Qwen3-30B-A3B-Thinking-2507 and Qwen3-Next-80B-A3B-Thinking. All three are Apache-2.0, use the same `<think>` and hermes tool format as the student, and show their full reasoning. The 30B-A3B scores about as well as the 235B on BFCL-v3 and tau1 but is much weaker on tau2-Retail and tau2-Telecom. Newer 2026 Qwen releases are also Apache-2.0 and stronger agents: Qwen3.5 (February–March 2026) and Qwen3.6 (about April 2026). Their catch is a different XML tool-call format (`qwen3_coder`). The cross-family options are DeepSeek (MIT, and its card explicitly allows distillation), GLM-4.7 / GLM-5.x (MIT), Kimi K2 (modified MIT) and gpt-oss (Apache-2.0). They are strong agents, but their formats and reasoning styles differ from the student's, and most are too large to self-host cheaply.

### Cited Findings

**Qwen3-2507 / Qwen3-Next family (same format as the student)**
- Qwen3-235B-A22B-Thinking-2507 is Apache-2.0 and thinking-only. Its card recommends `--reasoning-parser deepseek_r1` in vLLM and up to 32,768 output tokens for most queries (81,920 for hard math and code). For tool calling it recommends Qwen-Agent. — [HF card](https://huggingface.co/Qwen/Qwen3-235B-A22B-Thinking-2507)
- Qwen3-235B-A22B-Thinking-2507 agent scores (vendor-reported): BFCL-v3 71.9; TAU1-Retail 67.8; TAU1-Airline 46.0; TAU2-Retail 71.9; TAU2-Airline 58.0; TAU2-Telecom 45.6. Comparisons on the same card: OpenAI o3 scores BFCL-v3 72.4 and TAU2-Retail/Airline/Telecom 76.3/70.0/60.5. DeepSeek-R1-0528 scores BFCL-v3 63.8 and TAU2 64.9/60.0/33.3. The original Qwen3-235B-A22B Thinking (April 2025) scored only 40.4/30.0/21.9 on TAU2. — [HF card](https://huggingface.co/Qwen/Qwen3-235B-A22B-Thinking-2507)
- Qwen3-30B-A3B-Thinking-2507 is Apache-2.0 and thinking-only. Its default chat template inserts `<think>` automatically, so the output may contain only the closing `</think>`. vLLM: `--reasoning-parser deepseek_r1`. Agent scores: BFCL-v3 72.4; TAU1-Retail 67.8; TAU1-Airline 48.0; TAU2-Retail 58.8; TAU2-Airline 58.0; TAU2-Telecom 26.3. On the same card Gemini 2.5 Flash Thinking scores 68.6, 65.2, 54.0, 66.7, 52.0 and 31.6. — [HF card](https://huggingface.co/Qwen/Qwen3-30B-A3B-Thinking-2507)
- Qwen3-Next-80B-A3B-Thinking is Apache-2.0, 81B total parameters in BF16. Agent scores: BFCL-v3 72.0; TAU1-Retail 69.6; TAU1-Airline 49.0; TAU2-Retail 67.8; TAU2-Airline 60.5; TAU2-Telecom 43.9. The card's examples use 4-GPU tensor parallelism and require vllm>=0.10.2. Reasoning parser: `deepseek_r1`. — [HF card](https://huggingface.co/Qwen/Qwen3-Next-80B-A3B-Thinking)

**Newer Qwen releases (2026): stronger agents, different tool-call format**
- Qwen3.5-397B-A17B (card citation dated February 2026) is Apache-2.0, with 17B active parameters. vLLM: `--reasoning-parser qwen3 --tool-call-parser qwen3_coder`. Thinking is on by default and is emitted as `<think>\n...</think>\n\n`. Vendor scores: BFCL-V4 72.9; TAU2-Bench 86.7; DeepPlanning 34.3; MCP-Mark 46.1; Tool Decathlon 38.3. Comparisons on the same card: GPT-5.2 scores 63.1 / 87.1 / 44.6, Claude 4.5 Opus 77.5 / 91.6 / 33.9, Kimi K2.5 68.3 / 77.0 / 14.5, and the closed Qwen3-Max-Thinking 67.7 / 84.6 / 28.7. — [HF card](https://huggingface.co/Qwen/Qwen3.5-397B-A17B)
- Qwen3.5 medium and large open releases: 397B-A17B, 122B-A10B, 35B-A3B and 27B. The Qwen3.5 Small series (0.8B, 2B, 4B, 9B) came out as open weights around 3 March 2026 under Apache-2.0. — [DeepLearning.AI The Batch](https://charonhub.deeplearning.ai/alibabas-latest-flagship-models-are-open-weights-moe-performers-in-sizes-from-less-than-1b-parameters/); [36Kr](https://eu.36kr.com/en/p/3706916646580358)
- Qwen3.5-35B-A3B: BFCL-V4 67.3 and TAU2-Bench 81.2. These come from the official comparison table copied into a third-party NVFP4 quant's card; I could not open the original card. The setup footnote says all models were run with the airline-domain fixes from the Claude Opus 4.5 system card. Tool calling uses `--tool-call-parser qwen3_coder`. Artificial Analysis reports τ²-Bench 89.2% for the same model, a different setup. — [AxionML NVFP4 card](https://huggingface.co/AxionML/Qwen3.5-35B-A3B-NVFP4); [DeepInfra model page](https://deepinfra.com/Qwen/Qwen3.5-35B-A3B); [GitCode HF mirror](https://ai.gitcode.com/hf_mirrors/Qwen/Qwen3.5-35B-A3B); [Puter, citing Artificial Analysis](https://developer.puter.com/ai/qwen/qwen3.5-35b-a3b/)
- Qwen3.6-35B-A3B (card citation dated April 2026) is Apache-2.0: 35B total, 3B active, 256 experts, 262K native context, thinking by default in `<think>` tags. Parsers: `--reasoning-parser qwen3 --tool-call-parser qwen3_coder`. FP8 checkpoints are published. Vendor scores, with Qwen3.5-35B-A3B / Qwen3.5-27B in brackets: TAU3-Bench 67.2 (68.9 / 68.4); DeepPlanning 25.9 (22.8 / 22.6); MCPMark 37.0 (27.0 / 36.3); Tool Decathlon 26.9 (28.7 / 31.5). TAU3-Bench uses gpt-5.2 (low reasoning effort) as the simulated user. The card does not report BFCL or TAU2. — [HF card](https://huggingface.co/Qwen/Qwen3.6-35B-A3B); [Unsloth GGUF / release listing](https://huggingface.co/unsloth/Qwen3.6-27B-GGUF)

**Cross-family candidates**
- DeepSeek-R1-0528: the weights are MIT, and the card says "DeepSeek-R1 series (including Base and Chat) supports commercial use and distillation." Tool scores: BFCL_v3_MultiTurn 37.0; Tau-Bench 53.5 (Airline) / 63.9 (Retail), with GPT-4.1 as the simulated user. It reasons in `<think>` and has "enhanced support for function calling." — [HF card](https://huggingface.co/deepseek-ai/DeepSeek-R1-0528)
- DeepSeek-V4: news reports say the weights are MIT, with a preview on 24 April 2026 and about 1.6T parameters for V4-Pro. One report says V4-Pro left preview on 12 August 2026. I found no tool-calling benchmark from a primary source, and these are secondary news reports. — [pasqualepillitteri.it](https://pasqualepillitteri.it/en/news/1381/deepseek-v4-open-source-chinese-model-april-2026); [AI Weekly](https://aiweekly.co/alerts/deepseek-v4-pro-exits-preview-with-mit-licensed-17t-weights)
- DeepSeek-V3.2 scores τ²-Bench 85.3, as reported in the GLM-4.7 card's comparison table. — [GLM-4.7 HF card](https://huggingface.co/zai-org/GLM-4.7)
- GLM-4.7 is MIT, 358B total parameters, with an FP8 checkpoint (`zai-org/GLM-4.7-FP8`; the vLLM example uses TP=4). Vendor τ²-Bench is 87.4 (GLM-4.6: 75.2). On the same card: Claude Sonnet 4.5 87.2, Gemini 3.0 Pro 90.7, GPT-5.1-High 82.7, Kimi K2 Thinking 74.3. Parsers: `--tool-call-parser glm47 --reasoning-parser glm45`. It supports "interleaved thinking" before each tool call and a "preserved thinking" mode. — [HF card](https://huggingface.co/zai-org/GLM-4.7)
- GLM-5.1 reportedly ships under plain MIT (secondary article, 2026). — [DEV Community](https://dev.to/rishi_kora/the-open-weight-coding-wave-kimi-k26-glm-51-minimax-m3-5hn9)
- Kimi K2-Thinking is under a Modified MIT license: 1T total / 32B active MoE, natively INT4 through quantization-aware training. The tool parser is Kimi-specific (`kimi_k2`) and reasoning is returned in `message.reasoning_content`. Agentic scores: HLE with tools 44.9; BrowseComp 60.2. The card does not report tau2 or BFCL. — [HF card](https://huggingface.co/moonshotai/Kimi-K2-Thinking)
- The Kimi modification adds one condition. A product with more than 100M monthly active users or more than $20M/month revenue must display "Kimi K2" in its UI. K2.5 and K2.6 reportedly keep the same structure. — [LICENSE](https://huggingface.co/moonshotai/Kimi-K2-Thinking/blob/main/LICENSE); [aitechconnect, 2026](https://aitechconnect-976.pages.dev/news/open-weight-coding-models-wave-kimi-glm-minimax-2026)
- gpt-oss-120b is Apache-2.0: 117B total / 5.1B active, MXFP4 MoE weights, fits on one 80 GB GPU. It "should only be used with the harmony format," exposes "full chain-of-thought" that is "not intended to be shown to end users," and has low/medium/high reasoning levels. — [HF card](https://huggingface.co/openai/gpt-oss-120b)
- MiniMax: one commentary says the newer M2.7 license bans commercial use without written permission, and that a "Permitted Free Uses" clause was added later. I did not verify the original MiniMax-M2 license. — [besthub.dev commentary](https://www.besthub.dev/articles/is-the-era-of-commercial-ready-chinese-open-source-llms-ending-minimax-m2-7-license-update-313bbfd0c888)
- BenchLM's aggregate tau2 table (updated July 2026) ranks GLM-5.2 at 99.1%, DeepSeek V4 Pro (Max) 96.2%, Kimi K2.5/K2.6 95.9% and Qwen3.5-27B 93.9% on the Artificial Analysis τ²-bench variant. BenchLM mixes in telecom-only results, so the rows are not directly comparable. — [BenchLM tau2](https://benchlm.ai/benchmarks/tau2-bench)

### Inferences
- **Benchmarks relevant to our weak spot:** BFCL multi-turn tests sequential tool use, tau2 tests policy-following agents, and DeepPlanning (reported only on Qwen3.5/3.6 cards) tests planning. Among teachers that are cheap to run, Qwen3-235B-Thinking-2507, Qwen3-Next-80B-Thinking and the Qwen3.5/3.6 35B-A3B models clearly beat Qwen3-30B-A3B-Thinking-2507 on tau2-Retail and tau2-Telecom. The 30B-A3B is about equal on BFCL-v3 and tau2-Airline.
- **Not every teacher fits the budget.** GLM-4.7, DeepSeek-V3.2/V4, Kimi K2.x and Qwen3.5-397B all post strong vendor tau2 scores, but they are 358B to 1.6T parameters. They are only usable through APIs, and their formats differ from the student's (see Q2).
- **License ranking for using outputs as training data:**
  - DeepSeek gives the clearest explicit permission ("supports ... distillation").
  - Apache-2.0 (all Qwen, gpt-oss) and MIT (GLM, DeepSeek) put no restrictions on outputs.
  - Kimi's modified MIT only adds an attribution condition above 100M MAU or $20M/month, which is irrelevant for a university club.
  - The MiniMax M2.x licenses are the riskiest to rely on.
- **Reasoning visibility:**
  - Qwen, DeepSeek, GLM and Kimi return their full reasoning (`<think>` or `reasoning_content`).
  - gpt-oss exposes its raw CoT, but in the harmony "analysis" channel and in a different style.
  - Closed models are not candidates here (for example OpenAI o-series, which hide reasoning; see Q4 OpenRouter docs).

### Gaps
- I found no explicit statement in any Qwen, GLM, Kimi or gpt-oss model card that outputs may be used to train other models. The licenses simply do not restrict outputs. Hosted-API terms of service (Alibaba Model Studio, DeepSeek API, Moonshot, Z.ai, OpenRouter's upstream providers) can add terms of their own, and I did not check them.
- I could not confirm the gpt-oss usage-policy file contents, the original MiniMax-M2 / M2.5 license text, or the GLM-5 / GLM-5.x and DeepSeek-V4 model cards from primary sources.
- I found no BFCL-v4 or tau2 numbers for Qwen3.6-35B-A3B. The Qwen3.6 card reports TAU3 instead.
- I found no independent (non-vendor) BFCL multi-turn or tau2 numbers measured under one harness across all the candidates. I did not fetch the official Sierra tau2 leaderboard's open-weight entries.

## Q2. Format compatibility, and same-family vs cross-family distillation

### Takeaway
Only the Qwen3-2507 thinking line (235B, 30B-A3B; Qwen3-Next-80B uses the same parsers) produces exactly the student's format: auto-inserted `<think>`, `deepseek_r1` reasoning parser, hermes JSON `<tool_call>`. Those trajectories can be used nearly as-is. Every other teacher needs a conversion step, Qwen3.5/3.6 included, because they emit `qwen3_coder` XML tool calls and use the `qwen3` reasoning parser. The conversion is mechanical: take structured `tool_calls` plus reasoning from the API and re-render them with the student's chat template. The harder mismatch is reasoning style and length. The 2025 literature says small students learn better from shorter or "closer" traces and that teacher trace quality matters. That argues for a same-family teacher, possibly a mid-size one, and for mixing teachers.

### Cited Findings
- Qwen3-235B-A22B-Thinking-2507, Qwen3-30B-A3B-Thinking-2507 and Qwen3-Next-80B-A3B-Thinking all use `--reasoning-parser deepseek_r1` in vLLM, the same parser the student uses. — [235B card](https://huggingface.co/Qwen/Qwen3-235B-A22B-Thinking-2507); [30B card](https://huggingface.co/Qwen/Qwen3-30B-A3B-Thinking-2507); [Next card](https://huggingface.co/Qwen/Qwen3-Next-80B-A3B-Thinking)
- The Qwen3-2507 and Qwen3-Next cards recommend Qwen-Agent for tool calling. Behind an OpenAI-compatible endpoint, they recommend turning off the server's reasoning and tool-call parsing and letting Qwen-Agent parse instead; the Next card's example sets `thought_in_content: True`. — [Next card](https://huggingface.co/Qwen/Qwen3-Next-80B-A3B-Thinking); [235B card](https://huggingface.co/Qwen/Qwen3-235B-A22B-Thinking-2507)
- Qwen3.5-397B-A17B and Qwen3.6-35B-A3B switch to `--tool-call-parser qwen3_coder` and `--reasoning-parser qwen3`. — [Qwen3.5-397B card](https://huggingface.co/Qwen/Qwen3.5-397B-A17B); [Qwen3.6-35B-A3B card](https://huggingface.co/Qwen/Qwen3.6-35B-A3B)
- The other families each have their own formats:
  - GLM-4.7: `glm47` tool parser, `glm45` reasoning parser. — [GLM-4.7 card](https://huggingface.co/zai-org/GLM-4.7)
  - Kimi K2-Thinking: `kimi_k2` tool-call parser, `reasoning_content` field. — [Kimi card](https://huggingface.co/moonshotai/Kimi-K2-Thinking)
  - gpt-oss: harmony format only. — [gpt-oss card](https://huggingface.co/openai/gpt-oss-120b)
- "Small Models Struggle to Learn from Strong Reasoners" (Li et al., arXiv 2502.12143, ICML 2025) makes three relevant points:
  - Small students (≤3B) do not reliably benefit from long CoT or from larger teachers, and do better with shorter CoT or smaller teachers (the "learnability gap").
  - "Mix Distillation" helps: Mix-Long mixes long and short CoT, and Mix-Large mixes strong and weak teachers, both at roughly 1:4. For example, Qwen2.5-3B-Instruct gained more than 8 points on MATH and AMC with Mix-Long versus training on long CoT alone.
  - Base models show a larger gap than instruct models.
  
  — [arXiv 2502.12143](https://arxiv.org/abs/2502.12143); [project page](https://small-model-gap.github.io)
- "Not All Correct Answers Are Equal: Why Your Distillation Source Matters" (a-m-team, arXiv 2505.14464, May 2025) distilled the same 1.89M queries from AM-Thinking-v1, Qwen3-235B-A22B and DeepSeek-R1, keeping only verified responses.
  - Students trained on AM-Thinking-v1 data did best (AIME24 84.3, AIME25 72.2, MATH500 98.4, LCB 65.9).
  - AM-Thinking-v1 traces had the lowest mean perplexity (2.5, vs Qwen3 3.0 and R1 2.9), and Qwen3-235B produced the longest responses.
  - Takeaway: among correct traces, quality and style still matter. (Figures are from the abstract and secondary summaries; I did not check the tables.)
  
  — [arXiv 2505.14464](https://arxiv.org/abs/2505.14464); [HF papers](https://huggingface.co/papers/2505.14464)
- Thinking Machines' on-policy distillation samples rollouts from the student and scores each token with the teacher using per-token reverse KL. With Tinker they reproduced Qwen3's result that on-policy distillation matches RL performance at a fraction of the cost. — [Thinking Machines blog](https://thinkingmachines.ai/blog/on-policy-distillation) (summarized from search results; I did not fetch the blog directly); [HF dataset discussion summarizing it](https://huggingface.co/datasets/rl-llm-wiki/knowledge-base/discussions/450)

### Inferences
- **Format conversion is cheap for any teacher.** Serve or call the teacher with its own tool and reasoning parsers enabled, so you receive OpenAI-style `tool_calls` (JSON arguments) plus `reasoning`/`reasoning_content`. Then rebuild each trajectory as `messages` and render it with the Qwen3-4B-Thinking-2507 tokenizer's `apply_chat_template`. This produces hermes `<tool_call>` JSON and `<think>` blocks in the student's exact format. Same-family teachers are not needed for format reasons, but they make rendering bugs less likely.
- **Reasoning style is what conversion cannot fix.** Harmony "analysis" CoT, GLM's interleaved thinking and Kimi's long agentic reasoning all differ from Qwen3's thinking style, and the learnability-gap and distillation-source papers suggest this matters for small students. The papers are math/code SFT studies, not agentic tool use, so applying them here is an extrapolation.
- **A practical recipe.** Use a same-family Qwen3-2507 teacher as the main source. Possibly mix about 20% stronger or longer traces (Qwen3-235B-2507, or a Qwen3.5/3.6 teacher after conversion) in the spirit of Mix-Large. Filter everything with the code-checkable success criteria. Prefer the shortest correct trace per task, and cap thinking length per turn, so traces stay learnable for a 4B model.
- **On-policy (logit) distillation needs a teacher with the same tokenizer.** Per-token reverse-KL distillation compares the teacher's and student's next-token distributions, so the teacher must share the student's tokenizer and vocabulary. The Qwen3 / Qwen3-2507 family qualifies. I could not confirm that Qwen3-Next or Qwen3.5/3.6 use exactly the same tokenizer. This favors self-hosting a Qwen3-30B-A3B-Thinking-2507 teacher for any later on-policy phase.
- **Tool-call format consistency matters for training.** If Qwen3.5/3.6 teachers are used, check that converted tool calls contain only valid JSON argument types for our four tool schemas. The XML `qwen3_coder` format passes parameters as strings that the parser converts, so type mismatches are possible.

### Gaps
- I found no paper that directly compares same-family and cross-family teachers for multi-turn agentic tool-calling distillation into a 4B model. The evidence is from math and code reasoning SFT.
- I did not verify whether Qwen3.5/3.6's tokenizer and vocabulary are identical to Qwen3's, which decides whether they can be on-policy (logit) teachers for Qwen3-4B.
- I did not verify how the Qwen3-4B-Thinking-2507 chat template handles `reasoning_content` from earlier assistant turns in multi-step tool loops (whether it keeps or strips past thinking). This affects how converted trajectories should be rendered for SFT. Inspect the template's `last_query_index` logic directly.

## Q3. How Qwen built its small models, and what that implies for us

### Takeaway
The Qwen3 technical report confirms that the small models (0.6B–14B dense and 30B-A3B) were built by strong-to-weak distillation, not by full RL. The first stage was off-policy distillation on teacher outputs in both /think and /no_think modes. The second was on-policy distillation that aligns the student's logits with Qwen3-32B or Qwen3-235B-A22B via KL. On Qwen3-8B, on-policy distillation beat RL using about 1/10 of the GPU hours. So our student is probably already "in distribution" with Qwen3-family teachers. Same-family SFT on filtered trajectories, optionally followed by cheap on-policy distillation from a same-tokenizer teacher, follows the same recipe.

### Cited Findings
- Section 4.5 of the Qwen3 report, "Strong-to-Weak Distillation," covers "5 dense models (Qwen3-0.6B, 1.7B, 4B, 8B, and 14B) and one MoE model (Qwen3-30B-A3B)." — [Qwen3 Technical Report, arXiv 2505.09388](https://arxiv.org/html/2505.09388v1)
- The report describes two phases:
  - Off-policy: combines "outputs of teacher models generated with both /think and /no_think modes" for response distillation, to give students basic reasoning and mode switching.
  - On-policy: the student samples in /think or /no_think mode and is fine-tuned by "aligning its logits with those of a teacher model (Qwen3-32B or Qwen3-235B-A22B)" by minimizing KL divergence.
  
  — [Qwen3 Technical Report](https://arxiv.org/html/2505.09388v1)
- Table 21 (Qwen3-8B, starting from the same off-policy-distilled checkpoint, which scored 55.0 on AIME'24 and 42.8 on AIME'25):

  | Method | GPU hours | AIME'24 (pass@64) | AIME'25 (pass@64) |
  |---|---|---|---|
  | + Reinforcement learning | 17,920 | 67.6 (90.0) | 55.5 (83.3) |
  | + On-policy distillation | 1,800 | 74.4 (93.3) | 65.5 (86.7) |

  RL did not raise pass@64; distillation did. — [Qwen3 Technical Report](https://arxiv.org/html/2505.09388v1)
- Thinking Machines reproduced the Qwen3 on-policy distillation result with their Tinker API, using an off-policy SFT start (OpenThoughts) followed by on-policy distillation from a stronger teacher. — [Thinking Machines blog](https://thinkingmachines.ai/blog/on-policy-distillation) (via search summary)

### Inferences
- Qwen3-4B (and almost certainly the 2507 refresh) learned its thinking and tool-calling style from larger Qwen3 models. Traces from Qwen3-235B/30B-Thinking-2507 should therefore be low-perplexity, "learnable" targets for it. This is consistent with the learnability-gap finding in Q2. The 2507 card itself does not document how the 2507 small models were trained.
- The report's ordering matches a sensible plan for us:
  1. Off-policy SFT on rejection-sampled teacher trajectories, which is the current plan.
  2. Optionally, a short on-policy distillation phase. The student generates trajectories on our synthetic tasks, with tools executed locally, and a self-hosted same-tokenizer teacher (Qwen3-30B-A3B-Thinking-2507 in vLLM) scores those tokens via prompt logprobs.

  Step 2 targets exactly the "student makes its own mistakes mid-trajectory" failure that SFT cannot fix. It is cheaper than RL according to Qwen's own numbers. This is an extrapolation from math to tool use.
- Qwen's on-policy phase used the 32B dense model as a teacher, not only the 235B. That supports using a mid-size Qwen teacher (30B-A3B or Next-80B) instead of insisting on the largest.
- Side note: Qwen3.5-4B (Apache-2.0, March 2026) exists. It could be a stronger student, but it would switch the tool-call format to `qwen3_coder` and match Qwen3.5/3.6 teachers instead. That decision is outside this note's scope.

### Gaps
- The Qwen3 report does not name the off-policy teachers explicitly in the passage I read, beyond "teacher models."
- I found no public documentation of how the Qwen3-2507 small models (4B-Thinking-2507) or the Qwen3.5 Small series were post-trained. I did not read the Qwen3.5 report.
- I found no published results for on-policy distillation applied to multi-turn tool-calling agents at the 4B scale.

## Q4. Cheapest ways to run a teacher for 500–2,000 multi-turn trajectories, with $ estimates

### Takeaway
Two options fit the $10–30 budget:
- **Self-host Qwen3-30B-A3B-Thinking-2507 (FP8) on one 48 GB GPU** (L40S at about $0.79–1.09/hr or A6000 at about $0.33–0.53/hr). Estimated cost is about $2–5 per 1,000 attempted trajectories, and you get logprobs for later on-policy distillation.
- **Call a cheap hosted MoE through an API.** Qwen3-30B-A3B-Thinking-2507 at about $0.05–0.08 input / $0.34–0.40 output per 1M tokens, or Qwen3.5/3.6-35B-A3B at about $0.10–0.15 / $0.95–1.00. Estimated cost is about $4–9 per 1,000 trajectories.

Qwen3-235B-A22B-Thinking-2507 through an API (about $0.23/$2.30 per 1M on OpenRouter) costs about $15–25 per 1,000 trajectories. That fits only a small top-up set of about 300–1,000, for example the hardest planning tasks. Self-hosting the 235B is not worth it on this budget.

### Cited Findings
- **OpenRouter reasoning.** Responses include reasoning tokens by default when the model emits them, in the `reasoning` field (Chat Completions) with `reasoning_details` describing their structure. Some models, such as the OpenAI o-series, do not return them. To keep reasoning across tool-calling turns, pass `message.reasoning` or `reasoning_details` back unchanged on the assistant message. — [OpenRouter reasoning docs](https://openrouter.ai/docs/use-cases/reasoning-tokens)
- **Qwen3-235B-A22B-Thinking-2507 prices:**
  - OpenRouter compare page: $0.23/M input, $2.30/M output. — [OpenRouter](https://openrouter.ai/compare/qwen/qwen3-235b-a22b-thinking-2507)
  - DeepInfra: about $0.30/M input, $2.90/M output. — [Bifrost calculator](https://www.getmaxim.ai/bifrost/llm-cost-calculator/provider/deepinfra/model/qwen3-235b-a22b-thinking-2507)
  - Other aggregators disagree, from $0.11/$0.60 to $0.45/$3.50. — [cloudprice.net](https://cloudprice.net/models/openrouter/qwen/qwen3-235b-a22b-thinking-2507); [llmreference](https://www.llmreference.com/model/qwen3-235b-a22b-thinking-2507/openrouter)
- **Qwen3-30B-A3B-Thinking-2507 prices:** aggregators list about $0.05–0.08/M input and $0.34–0.40/M output, without clear provider attribution. — [pricepertoken](https://pricepertoken.com/pricing-page/model/qwen3-30b-a3b-thinking-2507)
- **Qwen3.5-35B-A3B prices:** about $0.14/M input, $1.00/M output, with DeepInfra cache reads about $0.05/M. — [pricepertoken](https://pricepertoken.com/pricing-page/model/qwen-qwen3.5-35b-a3b); [Bifrost compare](https://www.getmaxim.ai/bifrost/model-library/compare/deepinfra/qwen3.5-35b-a3b)
- **Qwen3.6-35B-A3B prices (DeepInfra):** about $0.10–0.15/M input and $0.95/M output (listing dated 4 August 2026). — [computeprices](https://computeprices.com/providers/deep-infra/models/qwen3-6-35b-a3b)
- **DeepSeek API pricing** is contradictory across sources. One set lists V4-Flash at $0.14/M input on a cache miss and $0.0028/M on a cache hit. Another says time-of-day (peak/off-peak) pricing started on 16 August 2026. I did not obtain an authoritative output price. — [Puter DeepSeek pricing](https://developer.puter.com/tutorials/deepseek-api-pricing/); [zenmux](https://zenmux.ai/blog/deepseek-v4-flash-api-pricing); [activepieces](https://www.activepieces.com/blog/deepseek-api-pricing-2026-models-cache-output.md)
- **RunPod GPU prices** (aggregators, mid–late 2026; they conflict):
  - L40S 48 GB: $0.79/hr (July–August 2026); one tracker shows $1.09/hr after the 31 Aug–7 Sep update.
  - RTX A6000 48 GB: about $0.33–0.53/hr.
  - A100 80 GB PCIe: about $1.19–1.79/hr.
  - H100 PCIe: about $1.99–2.89/hr.
  
  — [computeprices L40S](https://computeprices.com/providers/runpod/gpus/l40s); [pricingsaas RunPod diff, Week 37 2026](https://pricingsaas.com/companies/runpod/diffs/2026W37); [computeprices A6000](https://computeprices.com/providers/runpod/gpus/rtxa6000); [RunPod pricing](https://www.runpod.io/gpu-cloud/pricing)
- **Throughput evidence (indirect):**
  - On an L40S, Llama-3.1-8B under vLLM went from 633 tok/s (BF16) to about 950–970 tok/s (FP8) at concurrency 16. Batching was the biggest lever: 47 tok/s at concurrency 1 versus 3,415 tok/s at concurrency 256. — [Towards AI vLLM L40S playbook](https://pub.towardsai.net/the-vllm-optimization-playbook-for-l40s-backed-by-83-experiments-ae5da228f514)
  - A community benchmark measured about 556 tok/s output for Qwen3-Coder-30B-A3B (AWQ) under vLLM on an RTX 5090.
  - I found no benchmark for Qwen3-30B-A3B FP8 on an L40S under vLLM. — [search summary of community benchmarks](https://reddit.sentinel-team.org/posts/1rm0qd5/snapshots/2026-03-06T19%3A04%3A08.896785Z)
- **Hardware sizes:** gpt-oss-120b fits on one 80 GB GPU (MXFP4). [gpt-oss card](https://huggingface.co/openai/gpt-oss-120b). GLM-4.7-FP8's vLLM example uses TP=4. [GLM-4.7 card](https://huggingface.co/zai-org/GLM-4.7). Qwen3-Next-80B examples use TP=4 in BF16. [Next card](https://huggingface.co/Qwen/Qwen3-Next-80B-A3B-Thinking)

### Inferences
- **Workload assumptions** (my own; adjust to measured traces). One trajectory is about 5 teacher calls. The context grows each turn (system prompt + 4 tool schemas + history), so cumulative input is about 25k tokens and output (thinking + tool calls + final answer) about 5k tokens. Per 1,000 attempted trajectories that is about 25M input and 5M output tokens. With rejection sampling at pass rate p, attempts = accepted / p. Qwen thinking models can emit very long thinking (the 235B card suggests 32k output tokens), so set a per-turn `max_tokens` cap, perhaps 4–8k, and discard truncated traces. Otherwise output cost can triple.
- **API cost per 1,000 attempted trajectories** (list prices, no caching):

  | Teacher | Cost |
  |---|---|
  | Qwen3-235B-Thinking-2507 on OpenRouter | about $5.75 input + $11.50 output = about $17 |
  | Qwen3-235B-Thinking-2507 on DeepInfra | about $22 |
  | Qwen3.5-35B-A3B | about $3.50 + $5.00 = about $8.50 (about $6 with $0.05 cache reads) |
  | Qwen3.6-35B-A3B | about $7–8.50 |
  | Qwen3-30B-A3B-Thinking-2507 | about $1.25–2 + $1.70–2 = about $3–4 |

  Prefix caching matters a lot for multi-turn work, because each turn re-sends the history. Providers that discount cache hits (DeepInfra, DeepSeek) cut input cost several-fold.
- **Self-hosting Qwen3-30B-A3B-Thinking-2507-FP8 on one 48 GB GPU** (estimate, unverified):
  - Memory: FP8 weights are about 31 GB, leaving about 12–14 GB for KV cache. From the model config as I remember it (48 layers, 4 KV heads, head_dim 128, BF16 KV), that is about 96 KB per token, or roughly 130–145k cached tokens. That fits about 12–16 concurrent 10k-token trajectories; an FP8 KV cache roughly doubles it.
  - Speed: assume about 300–600 tok/s aggregate decode (extrapolated from the L40S and 5090 numbers above). 5M output tokens take about 2.5–5 hours, or about $2–5 per 1,000 trajectories at $0.79–1.09/hr. Prefill is cheap with vLLM's `--enable-prefix-caching`.
  - Hardware choice: the A6000 (Ampere, no native FP8 compute; vLLM falls back to weight-only FP8 kernels) is likely slower but cheaper per hour. A 24 GB RTX 4090 cannot hold the FP8 weights. It would need a 4-bit AWQ/GPTQ quant (about 17 GB), leaving little KV cache and low concurrency, and 4-bit quantization may hurt teacher quality.
  - Our Python tool executor already runs locally, so the agent loop can drive many trajectories concurrently against one vLLM server (asyncio with 16–32 in flight).
- **Self-hosting the 235B** (about 235 GB in FP8, needing 4× H100 80 GB at about $8–16/hr) or GLM-4.7-FP8 (TP=4) is worse value than the 235B API at $0.23/$2.30 for this volume.
- **Suggested budget split for $10–30:**
  - About $5–10: self-host or call Qwen3-30B-A3B-Thinking-2507 for the bulk (2,000–4,000 attempts) and keep the passing traces.
  - About $5–15: Qwen3-235B-Thinking-2507 (OpenRouter) or Qwen3.5/3.6-35B-A3B (converted) only on tasks where the 30B fails, such as multi-step planning ("gym 3×/week + two assignments").
  - The rest held back for a few GPU-hours of on-policy distillation or eval.
- **Alibaba Cloud Model Studio** likely offers Qwen models at competitive prices with `enable_thinking` controls, but I have no verified prices. For tool calling, OpenRouter returns reasoning plus structured tool calls through one OpenAI-compatible interface, which simplifies the collection script.

### Gaps
- I did not obtain verified, current per-token prices from the providers' own pages for Together, Fireworks, DeepInfra, Alibaba Cloud Model Studio/DashScope or the DeepSeek API (output prices especially). An earlier attempt to read the OpenRouter models API returned unrelated data. Every price above is from aggregators or a single compare page.
- I found no measured vLLM throughput for Qwen3-30B-A3B-Thinking-2507-FP8 on an L40S, A6000 or 4090. The figures above are extrapolations. A 15-minute `vllm bench serve` run on the rented pod would settle it.
- I did not confirm which API providers return reasoning content for each specific Qwen model, or which ones support `tools` with thinking models. Some providers strip reasoning or do not support tool calling for thinking variants. Check each provider's model page or OpenRouter's per-provider `supported_parameters` before committing.
- I did not verify that `Qwen/Qwen3-30B-A3B-Thinking-2507-FP8` exists as an official Qwen checkpoint, though the 235B and 30B cards point to quantized variants.
