# Gemini as a teacher model for distilling into Qwen3-4B-Thinking-2507 (Steady Planner)

Research date: 2026-11-05. Note: the Gemini API docs and terms now 301-redirect from ai.google.dev to aistudio.google.com/docs. The Vertex docs redirect to docs.cloud.google.com. All quotes below are from the pages as fetched on 2026-11-05. Quotes were extracted by a page-reading tool, so verify the exact wording on the live page before relying on it. This is not legal advice.

## Q1. Do Gemini's terms allow using its outputs to train another model?

### Takeaway
No exception covers this project. The Gemini API terms (effective March 23, 2026) say "You may not use the Services to develop models that compete with the Services." They contain no research, non-commercial or educational carve-out. The Vertex AI terms are stricter: they forbid using output to "substitute, replace, or circumvent the use of a Google Model" or to "create or improve models similar to a Google Model."

Google has also said publicly (GTIG, Feb 12, 2026) that "distillation from Google's Gemini models without permission is a violation of our Terms of Service." So fine-tuning Qwen3-4B on Gemini trajectories, even for one club app, carries real ToS risk unless Google gives explicit permission. This is not legal advice.

### Cited Findings
**Gemini API / Google AI Studio Additional Terms ("Effective March 23, 2026")**
- **Competing-model clause:** "You may not use the Services to develop models that compete with the Services." — [Gemini API Additional Terms](https://aistudio.google.com/docs/terms) (ai.google.dev/gemini-api/terms redirects here)
- **Reverse-engineering clause:** "You also may not attempt to reverse engineer, extract or replicate any component of the Services ... including the underlying data or models (e.g., parameter weights)." The page does not use the word "distillation." — [Gemini API Additional Terms](https://aistudio.google.com/docs/terms)
- **No exceptions:** the words "research," "non-commercial" and "educational" do not appear anywhere in the Gemini API Additional Terms. Previous versions are archived, but I did not compare them. — [Gemini API Additional Terms](https://aistudio.google.com/docs/terms)
- **Who the service is for:** "Use of Google AI Studio and Gemini API is for developers building with Google AI models ... for professional or business purposes, not for consumer use." — [Gemini API Additional Terms](https://aistudio.google.com/docs/terms)
- **Incorporated terms:** users "must accept (1) the Google APIs Terms of Service" and "must comply with our Prohibited Use Policy." — [Gemini API Additional Terms](https://aistudio.google.com/docs/terms)
- **Age:** "You must be 18 years of age or older to use the APIs." The terms also restrict use in a service "that is directed towards or is likely to be accessed by individuals under the age of 18." — [Gemini API Additional Terms](https://aistudio.google.com/docs/terms)
- **Region:** "You may use only Paid Services when making API Clients available to users in the European Economic Area," and the same sentence covers Switzerland and the UK. — [Gemini API Additional Terms](https://aistudio.google.com/docs/terms)

**Generative AI Prohibited Use Policy ("Last Modified: December 17, 2024")**
- **No training clause:** the policy has no clause on training or competing models. It covers dangerous or illegal content, security, explicit or hateful content, and misinformation. The closest item is 2.3, "Circumvention of abuse protections or safety filters." — [Generative AI Prohibited Use Policy](https://policies.google.com/terms/generative-ai/use-policy)
- **Exceptions clause:** "We may make exceptions to these policies based on educational, documentary, scientific, or artistic considerations, or where harms are outweighed by substantial benefits to the public." This exception belongs to the Prohibited Use Policy only. It is not stated to apply to the competing-model clause in the API terms. — [Generative AI Prohibited Use Policy](https://policies.google.com/terms/generative-ai/use-policy)

**Google Cloud Service Specific Terms (Vertex AI)**
The AI/ML sections were renumbered on Feb 18, 2026, and I found no "last modified" date.
- **17(a) Competitive Use:** "Customer will not, and will not allow End Users to use an AI/ML Service or Generated Output to develop a similar or competing product or service. Google may immediately suspend or terminate Customer's use of any AI/ML Service based on any suspected violation of the preceding sentence. This restriction does not apply to Vertex AI Platform so long as Customer does not use a Google Pre-Trained Model." — [Google Cloud Service Specific Terms](https://cloud.google.com/terms/service-terms)
- **17(b) Model Restrictions:** "Customer will not ... use output from an AI/ML Service (including Generated Output) to: (i) substitute, replace, or circumvent the use of a Google Model, directly or indirectly, or (ii) create or improve models similar to a Google Model. However, if an AI/ML Service offers the feature of fine-tuning, Customer may use output from that AI/ML Service (including Generated Output) to create and use Fine-Tuned Google Models instead of Google Pre-Trained Models." — [Google Cloud Service Specific Terms](https://cloud.google.com/terms/service-terms)
- **17(c) No Reverse Engineering:** "Customer will not ... reverse engineer or extract any components of an AI/ML Service, Software, or its models (such as using prompts to discover training data)." — [Google Cloud Service Specific Terms](https://cloud.google.com/terms/service-terms)
- **Section 18:** "Google will not use Customer Data to train or fine-tune any AI/ML models without Customer's prior permission or instruction." — [Google Cloud Service Specific Terms](https://cloud.google.com/terms/service-terms)

**Google's public statements (GTIG AI Threat Tracker, Feb 12, 2026)**
- **Definition:** model extraction attacks are defined as cases where "an adversary uses legitimate access to systematically probe a mature machine learning model to extract information used to train a new model ... frequently referred to as 'distillation attacks.'" — [GTIG blog, Feb 12, 2026](https://cloud.google.com/blog/topics/threat-intelligence/distillation-experimentation-integration-ai-adversarial-use)
- **Google's position:** "There are legitimate uses for distillation, and Google Cloud has existing offerings to perform distillation. However, distillation from Google's Gemini models without permission is a violation of our Terms of Service." Also: "Model extraction attacks violate Google's Terms of Service and may be subject to takedowns and legal action." — [GTIG blog](https://cloud.google.com/blog/topics/threat-intelligence/distillation-experimentation-integration-ai-adversarial-use)
- **Who it targets:** Google says it "observed and mitigated frequent model extraction attacks from private sector entities all over the world and researchers seeking to clone proprietary logic." One flagged campaign used more than 100,000 prompts that tried to steer the language of Gemini's "thinking content." — [GTIG blog](https://cloud.google.com/blog/topics/threat-intelligence/distillation-experimentation-integration-ai-adversarial-use)
- **Defenses:** Google uses "real-time proactive defenses that can degrade student model performance." — [GTIG blog](https://cloud.google.com/blog/topics/threat-intelligence/distillation-experimentation-integration-ai-adversarial-use); secondary coverage: [The Register](https://www.theregister.com/2026/02/14/ai_risk_distillation_attacks/), [ITPro](https://www.itpro.com/technology/artificial-intelligence/google-says-hacker-groups-are-using-gemini-to-augment-attacks-and-companies-are-even-stealing-its-models)

**Industry precedent**
- **OpenAI and DeepSeek (Jan 2025):** OpenAI said it had evidence that DeepSeek used its models to train R1. OpenAI's terms forbid using "output to develop models that compete with OpenAI." No evidence was published, and reports said distillation is not illegal under US law but violates the ToS. — [MacRumors, Jan 29, 2025](https://www.macrumors.com/2025/01/29/openai-says-deepseek-used-its-models/); [Vice](https://www.vice.com/en/article/openai-says-it-has-evidence-deepseek-copied-it); [TechRadar](https://www.techradar.com/computing/artificial-intelligence/openai-says-deepseek-used-its-models-illegally-and-it-has-evidence-to-prove-it-new-report-claims)
- **Anthropic (Feb 23, 2026):** Anthropic accused DeepSeek, Moonshot and MiniMax of large-scale distillation of Claude: about 24k fraudulent accounts and more than 16M exchanges, per secondary coverage. Anthropic also called distillation "a widely used and legitimate training method" when used licitly. — [Anthropic](https://anthropic.com/news/detecting-and-preventing-distillation-attacks); [Gigazine](https://gigazine.net/gsc_news/en/20260224-anthropic-deepseek-moonshot-minimax)

**Privacy (free vs paid)**
- **Unpaid Services:** "Google uses the content you submit to the Services and any generated responses to provide, improve, and develop" its products. Also, "human reviewers may read, annotate, and process your API input and output," and "Do not submit sensitive, confidential, or personal information to the Unpaid Services." — [Gemini API Additional Terms](https://aistudio.google.com/docs/terms)
- **Paid Services:** "When you use Paid Services, including, for example, the paid quota of the Gemini API, Google doesn't use your prompts or responses to improve our products." Also, "Google logs prompts and responses for a limited period of time, solely for detecting and preventing violations." — [Gemini API Additional Terms](https://aistudio.google.com/docs/terms)
- **Pricing table:** "Used to improve our products" reads Yes on the free tier and No on the paid tier for every listed text model. — [Gemini API pricing](https://aistudio.google.com/docs/pricing)

### Inferences
**Free, paid and Vertex: same restriction**
- The competing-model clause appears in the same AI Studio/Gemini API terms whether you use the free or paid tier. Paying changes data use, not the training restriction.
- Vertex is not a loophole. Its 17(a) exemption applies only when you are *not* using a Google pre-trained model, which Gemini is. Its 17(b) explicitly bans using output to "substitute, replace, or circumvent the use of a Google Model," and permits training only for fine-tuned *Google* models.

**Does a 4B single-app planner "compete"?** (interpretation)
- The narrow reading: a 4B planning agent inside one club app is not a model "that compete[s] with the Services." It is not offered as an API or as a general model.
- Against that reading:
  - The app would use a model trained on Gemini outputs *instead of* calling Gemini. That is close to what Vertex 17(b)(i) describes ("substitute, replace ... directly or indirectly").
  - Google's own public statement is broader than the API text: distillation "without permission" violates the ToS. It names "researchers" as frequent extractors.
  - Non-commercial status is not mentioned in any of these terms.
- My read: the conservative position is that this is not permitted without written permission from Google.

**Practical risk for a student club** (interpretation)
- The realistic consequences are account suspension or termination. Google says it "may immediately suspend or terminate" on *suspected* violations, and it may silently degrade outputs.
- Legal action is unlikely but explicitly reserved.
- A program of 500 to 2,000 synthetic multi-turn trajectories is far smaller than the 100k+ prompt campaigns Google described, but it has the same shape.

**Other terms that matter for the club**
- **Age:** any club member under 18 cannot use the API under the 18+ rule.
- **Under-18 users:** the rule against services "likely to be accessed by individuals under the age of 18" applies if Gemini were used inside the app. It does not bind a separately trained Qwen model.

**Privacy implication**
- If Gemini is used at all, use the paid tier and only synthetic or fake schedules. Never send real student calendar data through the free tier, where human reviewers may read it.

**Safer paths**
- (1) Ask Google for explicit permission, citing GTIG's "without permission" wording.
- (2) Use a permissively licensed open-weight teacher. GLM-4.6 ranks close to Gemini 3 Pro on BFCL V4 (see Q4). Check its license; I did not verify it here.
- (3) Use Gemini only for things that do not produce training data, such as manual spot checks. Even LLM-judge filtering of training data arguably "uses the Services to develop models" and is ambiguous.

### Gaps
- I did not fetch the full Google APIs Terms of Service text (developers.google.com/terms) to check for its own model-training language.
- I did not compare the archived previous versions of the Gemini API terms, so the exact change history of the competing-model wording before March 23, 2026 is unverified.
- No public case was found of Google enforcing against a small academic or non-commercial distillation project. No Google FAQ was found addressing fine-tuning small open models for a single app.
- I did not research Gemma's license terms as an alternative "Google-sanctioned" teacher.

## Q2. What reasoning does the Gemini API return?

### Takeaway
The Gemini API does not return raw chain of thought. It returns only optional *thought summaries*, and by default "only the final output is returned." Billing is for the full hidden thought tokens.

Thought signatures are encrypted, opaque reasoning state. They must be passed back in multi-turn function calling, and Gemini 3 validates them strictly (400 errors). They are useless as training text. Reasoning depth is set with `thinking_budget` on Gemini 2.5 and `thinking_level` on Gemini 3 and later.

### Cited Findings
**Summaries, not raw thoughts**
- AI Studio thinking doc (Interactions API version): "By default, only the final output is returned. You can enable thought summaries with `thinking_summaries`." Also: "Pricing is based on the full thought tokens the model needs to generate, despite only the summary being output from the API." — [Gemini thinking docs](https://aistudio.google.com/docs/thinking)
- In the Interactions API, "thoughts are a first-class representation as dedicated `thought` steps." The doc notes this "handles thoughts and signatures differently than the `generateContent` API." — [Gemini thinking docs](https://aistudio.google.com/docs/thinking)
- Vertex: "*Thought summaries* display intermediate reasoning steps alongside the model's final response." The page warns that responses may lack summary text and that thinking "isn't guaranteed for every request." — [Vertex AI thinking docs](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/thinking)

**History: raw thoughts removed in May 2025**
- Around Google I/O (May 2025), Google replaced raw thoughts with summaries: "AI Studio will now present thought summaries rather than the detailed raw thoughts." A Google representative acknowledged, "I hear that you all want raw thoughts, the value is clear, there are use cases that require them." — [Google AI developer forum thread](https://discuss.ai.google.dev/t/massive-regression-detailed-gemini-thinking-process-vanished-from-ai-studio/83916); [VentureBeat](https://venturebeat.com/ai/googles-gemini-transparency-cut-leaves-enterprise-developers-debugging-blind?rand=3490)
- Current docs (Nov 2026) still describe summaries only. I found no evidence that raw thoughts have been restored. — [Gemini thinking docs](https://aistudio.google.com/docs/thinking)

**Thinking controls**
- **Gemini 2.5 budgets (Vertex):**

  | Model | thinking_budget range | Can turn off? |
  |---|---|---|
  | 2.5 Flash | 1 to 24,576 tokens | Yes, budget 0 |
  | 2.5 Pro | 128 to 32,768 tokens | No |
  | 2.5 Flash-Lite | 512 to 24,576 tokens | Yes, budget 0 |

  A budget of -1 means dynamic. — [Vertex AI thinking docs](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/thinking)
- **Gemini 3 and later:** `thinking_level` is MINIMAL, LOW, MEDIUM or HIGH, and support varies by model. `thinking_budget` is deprecated for Gemini 3+, and sending both is an error. MINIMAL uses "the fewest possible tokens for thinking." It is not described as fully off. — [Vertex AI thinking docs](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/thinking)
- **Per-model levels (AI Studio doc):**

  | Model | Supported levels |
  |---|---|
  | gemini-3.6-flash | minimal, low, medium, high |
  | gemini-3.5-flash-lite | minimal, low, medium, high |
  | gemini-3-flash-preview | minimal, low, medium, high |
  | gemini-3.1-pro-preview | low, medium, high |
  | gemini-3-pro-preview | low, high |
  | gemini-3.8-flash and gemini-4-argon | low, medium, high |
  | gemini-2.5-flash-lite | thinking "Off" by default |

  — [Gemini thinking docs](https://aistudio.google.com/docs/thinking)

**Thought signatures**
- Definition: "An encrypted representation of the model's internal reasoning state," which is "required to maintain reasoning continuity across multi-turn interactions." In stateless mode you "MUST always resend all `thought` blocks exactly as they were received from the model." — [Gemini thinking docs](https://aistudio.google.com/docs/thinking)
- Vertex says Gemini 3 enforces stricter validation, and a missing required signature returns HTTP 400. For function calls the API did not generate, such as injected or synthetic history, you can set `thought_signature` to `skip_thought_signature_validator`. Google calls this a "last resort because it negatively affects model performance." — [Vertex thought signatures docs](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/thought-signatures?hl=de); developer reports: [Google AI forum](https://discuss.ai.google.dev/t/gemini-3-thought-signature-is-not-valid-cant-do-multi-turn-tool-calling/119360), [n8n community](https://community.n8n.io/t/gemini-3-pro-missing-thought-signature-in-function-calls-error-400/224332)

**Billing**
- "Response pricing is the sum of output tokens and thinking tokens." The count is reported in `total_thought_tokens`. — [Gemini thinking docs](https://aistudio.google.com/docs/thinking)
- Vertex: "You are billed for tokens generated during the thinking process." — [Vertex AI thinking docs](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/thinking)

**Google treats reasoning traces as protected**
- GTIG says its systems recognized the reasoning-extraction campaign "in real time," "protecting internal reasoning traces." — [GTIG blog](https://cloud.google.com/blog/topics/threat-intelligence/distillation-experimentation-integration-ai-adversarial-use)

### Inferences
**What the training data would contain**
- Any Gemini-generated dataset would have, at best:
  - final text and function calls (high quality);
  - optional summaries, which are short, headline-style, and not the actual reasoning;
  - opaque signatures, which are unusable.
- You pay for the hidden reasoning tokens but cannot train on them.

**Generation pipeline implications**
- The pipeline must preserve and return signatures on every turn of a live Gemini 3 conversation.
- Seeding conversations with hand-written synthetic tool calls requires the dummy signature, which Google says degrades quality.
- Prompts that try to make Gemini "think out loud" in its visible answer are close to the reasoning-coercion pattern GTIG flagged, which adds detection risk.

### Gaps
- I did not obtain the exact current `generateContent` parameter name and wording for summaries. It was historically `thinkingConfig.includeThoughts`, but that was not re-verified in this session; the fetched AI Studio page documents the Interactions API's `thinking_summaries`.
- No official statement explains *why* raw thoughts are withheld. Competitive protection is commentator speculation, not a confirmed Google rationale.
- The model names gemini-3.8-flash and gemini-4-argon came from the docs pages via a summarizing fetch tool. Their capabilities were not researched.

## Q3. How well do these training-data options work for a thinking model?

### Takeaway
Since Gemini gives no raw reasoning, the team would have to pick one of four kinds of training data:
- (a) tool-call-only data (no reasoning);
- (b) thin summaries;
- (c) reasoning written by another model;
- (d) reasoning regenerated by the student itself.

The evidence says the *structure and source* of reasoning traces strongly affects what students learn. Small models learn better from shorter, simpler chains. Off-policy SFT (training on another model's trajectories) teaches style more than accuracy.

The most technically sound option is (d): take Gemini's tool-call decisions and have Qwen3-4B-Thinking generate its own `<think>` that reaches the same action, STaR-style. Keep only traces that match. Gemini's function calls also have to be converted to Qwen's hermes `<tool_call>` format, with thinking handled per the Qwen chat template.

### Cited Findings
**Structure and source of traces**
- Li et al. (2025): "the structure of Long CoT is critical to the learning process," while "the content of individual reasoning steps has minimal impact."
  - Training on incorrect samples gives "only 3.2% lower accuracy."
  - Shuffling or deleting steps "significantly degrade[s] accuracy."
  - 17k samples were enough for Qwen2.5-32B-Instruct, using SFT and LoRA.

  — [arXiv 2502.07374](https://arxiv.org/abs/2502.07374)
- Small Model Learnability Gap (Li et al., 2025): small models (≤3B) "perform better when fine-tuned on shorter, simpler reasoning chains" and don't reliably gain from long CoT or larger teachers. The proposed fix, Mix Distillation, combines long and short CoT, including traces from smaller models. — [arXiv 2502.12143](https://arxiv.org/abs/2502.12143)
- Tian et al. (2025): with 1.89M identical queries, students distilled from AM-Thinking-v1 beat those distilled from Qwen3-235B-A22B and DeepSeek-R1. Summaries attribute this to lower perplexity and more varied length in the traces. — [Hugging Face Papers 2505.14464](https://huggingface.co/papers/2505.14464)
- A 2026 paper reports that students trained on R1 data "often get trapped in redundant exploratory branches" and stresses teacher-student compatibility. — [arXiv 2604.01702](https://arxiv.org/html/2604.01702)

**Precedent with Gemini traces**
- s1 used Gemini traces. s1.1 "is a better model than s1 by reusing the same s1K questions but with reasoning traces generated by r1 instead of Gemini." These were raw traces from when Gemini exposed them, and the target was math, not tool use. — [simplescaling/s1 GitHub](https://github.com/simplescaling/s1); [arXiv 2501.19393](https://arxiv.org/abs/2501.19393)
- OpenThoughts deliberately used QwQ-32B as the teacher for 1.2M examples to reach the state-of-the-art OpenThoughts3-7B. — [arXiv 2506.04178](https://arxiv.org/abs/2506.04178)

**Limits of off-policy distillation (Thinking Machines, Oct 27, 2025)**
- In off-policy distillation "the student learns in contexts frequented by the teachers," which "can cause compounding error." Also, "the student can learn to imitate the teacher's style and confidence but not necessarily its factual accuracy."
- "Running SFT on top of Qwen3-32B's own samples degrades performance" on instruction following.
- On-policy distillation needs teacher log-probs on the student's trajectory. The Gemini API cannot score arbitrary student text, so on-policy distillation from Gemini is not feasible (that last point is my inference).

— [Thinking Machines, "On-Policy Distillation"](https://thinkingmachines.ai/blog/on-policy-distillation/)

**Rationalization (STaR)**
- "If the generated answers are wrong, try again to generate a rationale given the correct answer," then "fine-tune on all the rationales that ultimately yielded correct answers." This is the basis for option (d). — [STaR, arXiv 2203.14465](https://arxiv.org/abs/2203.14465)

**Multi-turn tool-trajectory synthesis**
- APIGen-MT builds task blueprints with ground-truth actions, checked by "a committee of LLM reviewers." It turns them into trajectories via "simulated human-agent interplay." The resulting xLAM-2-fc-r models (1B to 70B) outperform GPT-4o and Claude 3.5 on τ-bench and BFCL, with small models notably strong in multi-turn. — [arXiv 2504.03601](https://arxiv.org/abs/2504.03601)

**Student format: Qwen3-4B-Thinking-2507**
- It "supports only thinking mode." Its chat template auto-inserts `<think>`, so output may contain only `</think>`.
- In multi-turn, the historical model output should "only include the final output part" and "does not need to include the thinking content."
- License: Apache-2.0.

— [Qwen3-4B-Thinking-2507 model card](https://huggingface.co/Qwen/Qwen3-4B-Thinking-2507)
- Qwen recommends "Hermes-style tool use for Qwen3 to maximize function calling performance." vLLM parses these calls with `--tool-call-parser hermes`. Qwen warns against stopword-based templates like ReAct for reasoning models. In the thinking-mode example, reasoning is stored as `reasoning_content` before the tool calls. — [Qwen function-calling docs](https://qwen.readthedocs.io/en/latest/framework/function_call.html)

### Inferences
**(a) Tool-call-only data (empty or absent `<think>`)**
- This conflicts with a thinking-only model whose template always opens `<think>`.
- Training on empty thinking blocks likely teaches the model to skip or shorten reasoning. This follows from the "structure matters" finding; I found no direct tool-calling study, so it is inference.
- It may be acceptable for a small share of trivially simple turns.

**(b) Gemini thought summaries as `<think>` content**
- Summaries are short and headline-style, and they are not a faithful process. That is a style and structure mismatch with Qwen's native long first-person reasoning.
- The learnability-gap paper suggests shorter reasoning is not inherently bad for small models. But summaries are written as *descriptions* of reasoning, not as reasoning, and Google notes they can be missing entirely.
- The risk is a student that writes "**Analyzing the schedule**..." headers instead of actually checking the calendar.

**(c) Reasoning written by a different model** (e.g., asking Gemini to write fake visible reasoning, or using another open reasoning model)
- Teacher-source studies show this changes what students learn.
- Asking Gemini to emit its reasoning in plain text also resembles the reasoning-extraction pattern GTIG flagged.

**(d) Regenerate reasoning in the student's own style** (recommended if Gemini data is used at all)
- Give Qwen3-4B-Thinking the same context plus a hint of the gold action, and let it write its own `<think>`.
- Check that its final tool call matches Gemini's (or a programmatic checker), and drop the hint from the stored sample (STaR rationalization).
- This keeps the reasoning close to the student's own distribution and limits thinking collapse.
- An even safer variant: plain rejection sampling of the student's own trajectories, verified by the project's deterministic tools and validators. This needs no Gemini at all.

**Format conversion**
- Gemini returns `functionCall {name, args}` and `functionResponse` parts. These must be mapped to `<tool_call>{"name":..., "arguments":...}</tool_call>` plus tool-role messages, rendered through Qwen's own chat template.
- Signatures and summaries must be stripped or replaced.
- Earlier assistant turns should carry no thinking, per the model card. The safest approach is to split each trajectory into per-step samples that match exactly what the template produces at inference time.

**Teacher quality on this exact task**
- The 4 tools are deterministic and verifiable. Gemini's main value would be choosing good actions and writing good user-facing replies.
- Any teacher's trajectories should be filtered by the project's own validators rather than trusted.

### Gaps
- I found no paper that directly measures fine-tuning a reasoning model on *Gemini thought summaries*, or on any provider's summarized CoT.
- I found no paper that directly studies "reasoning rewriting to student style" for tool-calling agents. The STaR-style recommendation is an inference from adjacent work.
- I did not verify exactly how the Qwen3-4B-Thinking-2507 chat template keeps or strips `reasoning_content` within a single multi-step tool loop versus earlier user turns. Check `chat_template` in the model's tokenizer_config.json.

## Q4. Is Gemini a strong enough teacher for multi-turn tool calling?

### Takeaway
Gemini 3 Pro is a strong multi-turn tool-calling teacher, but it is not best-in-class on BFCL V4. Open-weight GLM-4.6 roughly ties it, and small specialist xLAM-2 models beat it on multi-turn. Gemini 2.5 Flash, and especially 2.5 Flash-Lite, are weak at multi-turn. Flash-Lite scores below the student, Qwen3-4B-Instruct-2507, so the cheapest Gemini models would be poor teachers. τ²-bench numbers for Gemini 3.x are high, but third-party aggregators conflict.

### Cited Findings
**BFCL V4** (last updated 2026-04-12; overall = unweighted average of sub-categories)

| Rank | Model | Overall | Multi-turn |
|---|---|---|---|
| 1 | Claude-Opus-4.5 (FC) | 77.47% | 68.38% |
| 3 | Gemini-3-Pro-Preview (Prompt) | 72.51% | 60.75% |
| 4 | GLM-4.6 (FC thinking) | 72.38% | 68.00% |
| 7 | Gemini-3-Pro-Preview (FC) | 68.14% | 63.12% |
| 15 | Gemini-2.5-Flash (FC) | 56.24% | 36.25% |
| 18 | xLAM-2-32b-fc-r | 54.66% | 69.50% |
| 22 | xLAM-2-70b-fc-r | 53.07% | 77.38% |
| 34 | xLAM-2-8b-fc-r | 46.68% | 70.00% |
| 42 | xLAM-2-3b-fc-r | 41.22% | 58.38% |
| 52 | Gemini-2.5-Flash-Lite (FC) | 36.87% | 13.50% |
| 54 | Qwen3-4B-Instruct-2507 (FC) | 35.68% | 22.12% |

- Gemini 3.x Flash, 3.1 Pro and Qwen3-4B-Thinking-2507 are not in the data I retrieved.

— [BFCL leaderboard](https://gorilla.cs.berkeley.edu/leaderboard.html), [BFCL data CSV](https://gorilla.cs.berkeley.edu/data_overall.csv)

**Qwen's self-reported scores for Qwen3-4B-Thinking-2507**

| Benchmark | Qwen3-4B-Thinking-2507 | Original Qwen3-4B thinking |
|---|---|---|
| BFCL-v3 | 71.2 | 65.9 |
| TAU2-Retail | 53.5 | 38.6 |
| TAU2-Airline | 58.0 | 28.0 |
| TAU2-Telecom | 27.2 | 17.5 |

— [Qwen3-4B-Thinking-2507 model card](https://huggingface.co/Qwen/Qwen3-4B-Thinking-2507)

**τ²-bench (third-party; conflicting)**
- DataLearner (updated Apr 8, 2026): Gemini 3.1 Pro Preview 90.8, Gemini 3.0 Flash 90.2, Qwen3.5-397B-A17B 86.7; Claude Opus 4.6 first at 91.89. — [DataLearner τ²-bench](https://www.datalearner.com/en/benchmarks/Tau-Squared-Benchmark)
- BenchLM lists Gemini 3.1 Pro at 95.6% vs Qwen3 Max 74.3%. Another of its pages gives Gemini 3 Flash 43.3% against Qwen3.6-27B 94.2%, which is inconsistent with other sources. — [BenchLM: Gemini 3.1 Pro vs Qwen3 Max](https://benchlm.ai/compare/gemini-3-1-pro-vs-qwen3-max), [BenchLM: Gemini 3 Flash vs Qwen3.6-27B](https://benchlm.ai/compare/gemini-3-flash-vs-qwen3-6-27b)

### Inferences
- If Gemini were used, only Gemini 3 Pro / 3.1 Pro or a current 3.x Flash at a medium or high thinking level is plausibly a strong enough multi-turn teacher.
- 2.5 Flash-Lite should be ruled out: 13.5% BFCL multi-turn, below the 4B student's base family.
- Permissively licensed open models (GLM-4.6; larger Qwen3/3.5/3.6 models) are competitive multi-turn tool callers.
  - They avoid the ToS problem.
  - They can provide *raw* reasoning traces.
  - Same-family Qwen teachers also reduce style mismatch with the Qwen3-4B student.
- APIGen-MT's result, where small specialized models beat GPT-4o on τ-bench, suggests that data pipeline quality (blueprints, verification, simulated users) matters more than teacher brand.

### Gaps
- The official Sierra τ²-bench leaderboard (taubench.com) was not retrieved; a mirror returned 404. Gemini 3.x τ²-bench figures come only from aggregators and conflict.
- I have no Artificial Analysis data, and no BFCL entries for Gemini 3.6/3.8 Flash or 3.1 Pro.
- BFCL numbers were transcribed from the CSV by a fetch tool. Spot-check against the live leaderboard.

## Q5. What would 500 to 2,000 trajectories cost?

### Takeaway
At about 10k-token trajectories, generating 500 to 2,000 multi-turn trajectories costs roughly:
- under $15 on 2.5 Flash-Lite;
- about $40 to $110 on the Flash-class models (3.1 Flash-Lite, 2.5 Flash, 3.5 Flash-Lite, 3 Flash, 3.6/3.8 Flash);
- about $235 to $310 on Pro-class models, at standard rates for 2,000 trajectories.

The Batch API halves these prices, and 500 trajectories cost a quarter as much. Money is not the constraint; the terms are. Free-tier per-model limits are no longer published on the docs page; they are shown in AI Studio.

### Cited Findings
**Standard paid prices (USD per 1M tokens; output includes thinking)**

| Model | Free tier? | Input | Output | Notes |
|---|---|---|---|---|
| 3.1 Pro Preview | No | $2.00 (≤200k) / $4.00 | $12.00 / $18.00 | |
| 3.8 Flash and 3.6 Flash | Yes | $0.75 | $3.75 | Rising to $1.50 / $7.50 from Jan 1, 2027 |
| 3 Flash Preview (legacy) | Yes | $0.50 | $3.00 | |
| 3.5 Flash-Lite | Yes | $0.30 | $2.50 | |
| 3.1 Flash-Lite | Yes | $0.25 | $1.50 | |
| 2.5 Pro (marked deprecated) | Yes | $1.25 / $2.50 | $10.00 / $15.00 | |
| 2.5 Flash (marked deprecated) | Yes | $0.30 | $2.50 | |
| 2.5 Flash-Lite | Yes | $0.10 | $0.40 | |

- The Batch API gives a "50% cost reduction," e.g., 3.1 Pro at $1.00 / $6.00 and 2.5 Flash-Lite at $0.05 / $0.20.
- The pricing page has no "last updated" date.

— [Gemini API pricing](https://aistudio.google.com/docs/pricing)

**Rate limits and tiers**
- The docs page does not list free-tier RPM/TPM/RPD per model. It says limits are viewable in AI Studio and "Specified rate limits are not guaranteed and actual capacity may vary." — [Gemini API rate limits](https://aistudio.google.com/docs/rate-limits); [AI Studio rate-limit page](https://aistudio.google.com/rate-limit)
- Tier 1 requires linking an active billing account, with a spend limit of $10 per rolling 10-minute window.
  - Tier 2: $100 paid and 3 days.
  - Tier 3: $1,000 paid and 30 days.
- Batch enqueued-token limits at Tier 1 are 3M to 10M depending on model, e.g., 3M for 3.8/3.6 Flash and 5M for 3.1 Pro.

— [Gemini API rate limits](https://aistudio.google.com/docs/rate-limits)

### Inferences
**Assumptions for the estimate**
- One trajectory has about 10k tokens of final transcript over about 5 model calls.
- Re-sending the growing history makes billed input about 30k tokens per trajectory.
- Output plus thinking is about 8k tokens per trajectory.
- So 2,000 trajectories ≈ 60M input + 16M output tokens.

**Estimated cost for 2,000 trajectories (standard rates)**

| Model | Estimated cost |
|---|---|
| 2.5 Flash-Lite | ≈ $12 |
| 3.1 Flash-Lite | ≈ $39 |
| 2.5 Flash / 3.5 Flash-Lite | ≈ $58 |
| 3 Flash Preview | ≈ $78 |
| 3.6/3.8 Flash | ≈ $105 now; ≈ $210 after Jan 1, 2027 |
| 2.5 Pro | ≈ $235 |
| 3.1 Pro Preview | ≈ $312 |

- Divide by 4 for 500 trajectories.

**Caveats on the estimate**
- High thinking levels or a Gemini-simulated user could double or triple the output tokens.
- The batch discount applies only if the agent loop runs in "waves" (one batch job per turn index). This is slow but workable.
- Context caching of the shared system prompt and tool schemas can cut input cost further.
- Even the pessimistic case (about $600 to $900 for 2,000 Pro trajectories at 3× tokens) is affordable. Cost is not the deciding factor.

**Free tier**
- It is a poor fit regardless of quotas:
  - prompts and outputs may be used by Google and read by human reviewers;
  - 3.1 Pro has no free tier;
  - quotas are unpublished and "not guaranteed."
- Generating training data on the free tier also makes the ToS question no better.

### Gaps
- Exact current free-tier RPM/RPD per model could not be retrieved; it is only shown inside AI Studio.
- The token-per-trajectory figures are my assumptions, not measurements. Measure them by running about 20 pilot trajectories and reading `usage_metadata` / `total_thought_tokens`.
- Vertex AI pricing for the same models was not checked separately.
