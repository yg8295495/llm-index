---
name: "web-data-scout"
description: "Systematic web data source discovery and collection for benchmark scores. Invoke when you need to find how to collect data from a website, discover APIs, or gather LLM benchmark scores with cross-validation."
---

# Web Data Scout

Systematic methodology for discovering data access methods and collecting structured data from web sources, with cross-validation and quality control.

## Core Principles

1. **Never fabricate data** — missing data = missing, not zero, not estimated
2. **Every data point must have a source_url** — no URL = not stored
3. **Cache everything** — even preliminary scan results are valuable for cross-validation
4. **Fail explicitly** — stop and report, never silently degrade or guess
5. **Respect rate limits** — ≥2s between requests to same domain, honor robots.txt

## Endpoint Pool

Before discovering new endpoints, **always check `config/endpoint_pool.yaml` first**. It contains:
- Verified endpoints with collection method, status, and coverage
- Untested endpoints worth trying
- Known-broken endpoints to avoid

When a new endpoint is discovered or verified, add it to the pool.

## Three-Layer Collection Architecture

| Layer | Tool | Use Case | Cost |
|-------|------|----------|------|
| **Automated** | MCP Playwright + Integrated Browser | API endpoints, HTML tables, JS-rendered data | Free |
| **Human-Assisted Image** | User + Manual Review (仅用户分享的截图数据) | Free |
| **Manual** | User | Final decisions, disputed data, vendor claims | — |

### Layer 1: Automated (MCP Playwright + Integrated Browser)

For structured data sources:
- **API endpoints**: Use `playwright_get` directly (e.g., OpenRouter `/api/v1/models`)
- **HTML tables**: Use `browser_snapshot` + `playwright_get_visible_html`
- **RSC/SPA payloads**: Use `browser_navigate` + `browser_evaluate` to render, then extract from `<script>` tags or network interception
- **AA (Artificial Analysis)**: Most evaluation pages work with browser_snapshot + browser_evaluate

采集流程（详见 "MCP 工具使用规范"）

### Layer 2: Human-Assisted Image (用户分享的图片数据)

**⚠️ 2026-06-17 重要更新：豆包/DeepSeek 图片 OCR 能力已验证不可靠，识别结果存在严重错误。移除 AI 自动 OCR 路径。**

仅用于采集用户在论坛/社交媒体中分享的截图数据，例如：
- 用户分享的 token consumption 截图
- 真实使用场景中的 cost breakdown
- 非官方 benchmark 数据（无法通过 API/HTML 提取的）

流程：
1. **Playwright captures screenshot** — 保存图片到 `data/raw/user_shared_images/`，记录截图 URL
2. **Manual extraction by user** — 用户手动读取图片中的数字和文字（AI OCR 结果不可信，已舍弃）
3. **Store with metadata** — 每项数据必须有 `source_image_ref: {path}` 和 `needs_manual_review: true`（因为来源是截图而非结构化数据）

⚠️ **严格限制**：图片识别路径永远不应作为 benchmark 官方数据的采集方式。仅当数据无 API/HTML 来源时才使用此通道。

#### Output Location for Images
- 用户分享截图存档：`data/raw/user_shared_images/`
- 图片关联的提取数据 YAML：`data/raw/forum_image_extracted_{date}.yaml`

### Layer 3: Manual (User)

For data that requires human judgment:
- Vendor claim verification
- Disputed scores (>5% deviation across sources)
- New model existence confirmation
- Subscription pricing updates

## Phase 1: Data Source Discovery

Given a target website/data source, systematically discover how to access its data.

### Step 1.1: Web Search for Access Methods

Search queries (execute ALL of these, not just one):
- `"{site_name} API access"`
- `"{site_name} data export"`
- `"{site_name} how to scrape"`
- `"{site_name} API documentation"`
- `"{site_name} data download CSV JSON"`

Record ALL findings. If a query returns nothing, mark it as "no results" — do NOT skip.

### Step 1.2: Check Endpoint Pool

Look up `config/endpoint_pool.yaml` for existing entries matching the target.
If found and `status: verified` → use the documented method directly.
If found and `status: untested` → try it, update status after testing.

### Step 1.3: Check Standard Endpoints

Try these URLs in order:
- `{base_url}/robots.txt` — check for allowed/disallowed paths
- `{base_url}/sitemap.xml` — discover page structure
- `{base_url}/docs` or `{base_url}/api-docs` or `{base_url}/swagger` — API documentation
- `{base_url}/api` — common API root
- `{base_url}/graphql` — GraphQL endpoint

For each: record HTTP status code. 404 = "not found", not "doesn't exist" (could be at different path).

### Step 1.4: Playwright Network Interception

If Steps 1.1-1.3 don't yield a usable API:
1. Open the target page with `browser_navigate`
2. Monitor network requests with `browser_network_requests`
3. Identify backend API endpoints returning JSON data
4. Record: endpoint URL, request method, required headers, response structure

### Step 1.5: Source Discovery Report

Output format:
```
DATA SOURCE DISCOVERY REPORT
Target: {site_name}
Date: {current_datetime}

Discovery Methods Tried:
  - Endpoint pool: {found/not_found} — {key_name}
  - Web search: {found/not_found} — {summary}
  - Standard endpoints: {list with status codes}
  - Playwright interception: {found/not_found} — {endpoints_found}
  - Integrated Browser (DOM evaluation: {found/not_found}

Recommended Collection Method:
  - Method: {api/scrape/playwright/html-table/js-evaluate/image-assisted}
  - Endpoint: {url if applicable}
  - Authentication: {none/api_key/oauth/paywall}
  - Data format: {json/csv/html/image}
  - Cost: {free/paid — price}
  - Limitations: {rate limits, missing data, etc.}

Fallback Options:
  1. {method} — {tradeoff}
  2. {method} — {tradeoff}

BLOCKERS (if any):
  - {description of what cannot be resolved without human intervention}

采集工具使用决策（详见 "MCP 工具使用规范"）:
  - Primary: Integrated Browser / MCP Playwright (自动层)
  - Secondary: 仅当用户分享的图片数据时 → Human-Assisted Image Layer
  - Tertiary: 纯人工确认 (Manual User)
```

## Phase 2: Time-Aware Model & Score Collection

When collecting LLM benchmark scores, follow this specific workflow.

### Step 2.1: Get Current Time & Scan Window

```
current_time = now()
primary_window = 30 days  # main scan
extended_window = 90 days  # catch-up scan
```

### Step 2.2: Broad Scan — Latest Models & Scores

Search queries (execute in parallel):
- `"LLM benchmark comparison {current_year_month}"` — recent comparison articles
- `"latest LLM models released {current_year_month}"`
- `"大模型评测 最新 {current_year_month}"` — Chinese sources
- `"LLM leaderboard update {current_year_month}"`
- `"{specific_benchmark} latest results {current_year_month}"`

**Purpose**: Build a cache of current models AND their reported scores.
**Important**: Cache ALL scores found, even from non-authoritative sources. These serve as cross-validation references.

Output: `scan_cache.json`
```json
{
  "scan_date": "2026-06-16",
  "window_days": 30,
  "entries": [
    {
      "model": "Claude Opus 4.8",
      "provider": "Anthropic",
      "benchmark": "SWE-Bench Verified",
      "score": 87.6,
      "source_url": "https://...",
      "source_type": "media",
      "source_credibility": "medium",
      "source_format": "html",
      "found_date": "2026-06-16"
    }
  ]
}
```

### Step 2.3: Validate Model Existence

For each model in scan_cache, verify it actually exists:
1. Search `"{provider} official" "{model_name}" release announcement`
2. Check the provider's official website/blog for the model
3. If model NOT confirmed → mark `model_confirmed: false`, keep in cache but flag

### Step 2.4: Targeted Score Collection

For confirmed models, search for benchmark scores with higher precision:
1. `"{model_name}" "{benchmark_name}" score`
2. `"{model_name}" "{benchmark_name}" official`
3. Check endpoint pool for authoritative leaderboard URLs
4. Check provider's official technical report/blog

### Step 2.5: Cross-Validation

For each (model, benchmark) pair with multiple sources:

```
sources = all cached entries for this (model, benchmark)
scores = [s.score for s in sources]
median_score = median(scores)

For each source:
  deviation = abs(source.score - median_score) / median_score * 100

credible_count = count where deviation <= 5%
total_count = len(sources)
credible_ratio = credible_count / total_count

IF credible_ratio >= 0.8:
  status = "credible"
  final_score = weighted_average(sources, by=credibility)
  confidence = 0.9
ELIF credible_ratio >= 0.5:
  status = "degraded"
  final_score = median of credible sources only
  confidence = 0.6
  flag = "needs_review"
ELSE:
  status = "unreliable"
  final_score = null
  confidence = 0.3
  flag = "needs_manual_review"
```

### Source Credibility Tiers

| Tier | Source Type | Weight |
|------|-----------|--------|
| 1 | Official technical report / paper | 1.0 |
| 2 | Official blog / announcement | 0.9 |
| 3 | Authoritative leaderboard (swebench.com, artificialanalysis.ai, berkeley BFCL) | 0.8 |
| 4 | Established tech media (36kr, The Verge, etc.) | 0.5 |
| 5 | Community / personal blog / social media | 0.3 |

When sources conflict, prefer higher-tier source. Within same tier, prefer more recent.

## Phase 2.5: Agent Annotation Collection

Agent capability data requires special handling because **Agent = Model + Harness**.

### Key Insight

The same base model can have vastly different scores depending on the harness:
- Example: Terminal-Bench 2.0 — same model, optimized harness: 52.8% → 66.5%
- SWE-Bench scores mix model + harness contributions, making raw comparison misleading

### Agent Data Sources (Priority Order)

1. **GDPval-AA v2** (Primary) — Real-world agentic tasks, Elo rating, shell+web access
2. **Terminal-Bench Hard** (Primary) — Terminal environment coding, auto-verified
3. **BFCL V4** (Secondary) — Function calling/tool use, FC vs Prompt mode distinction
4. **APEX-Agents-AA** (Secondary) — Long-horizon cross-application tasks

### FC vs Prompt: Agent vs Base Proxy

BFCL V4 provides both FC (Function Calling) and Prompt modes for many models:
- **FC mode** = native tool use capability ≈ Agent scenario
- **Prompt mode** = prompt-based simulation ≈ Base model
- **Delta (FC - Prompt)** ≈ Agent capability boost from native tool support

This delta is a quantitative proxy for Agent差异标注.

### Agent Score Normalization

Different Agent benchmarks use different scales:
- GDPval-AA: Elo (human baseline = 1000)
- Terminal-Bench: Percentage (0-100%)
- BFCL: Overall Accuracy (0-100%)

Normalize to a common scale before combining:
```
agent_score_normalized = (score - min_score) / (max_score - min_score)
```

### Agent Annotation Output

```yaml
agent_annotation:
  model: "Claude Fable 5"
  provider: "Anthropic"

  gdpval_aa:
    elo: 1815
    rank: 1
    normalized: 0.95  # relative to max in dataset

  terminalbench_hard:
    score_pct: 62.9
    rank: 1
    normalized: 0.93

  bfcl_v4:
    fc_overall: 77.47
    prompt_overall: null  # not available for this model
    fc_prompt_delta: null
    rank: 1

  composite_agent_score: 0.94  # weighted average of normalized scores
  agent_tier: "S"  # S/A/B/C based on composite score
```

## Phase 3: Data Storage

### Output Format

Each collected data point:
```yaml
- model: "Claude Opus 4.8"
  provider: "Anthropic"
  benchmark: "SWE-Bench Verified"
  score: 87.6
  source_url: "https://www.anthropic.com/..."
  source_type: "official_blog"
  source_credibility: 0.9
  source_format: "html"
  collected_at: "2026-06-16T10:30:00+08:00"
  collector_version: "web-data-scout-v1"
  confidence: 0.9
  validation_status: "credible"  # credible / degraded / unreliable
  needs_manual_review: false
  cross_validation:
    total_sources: 5
    credible_sources: 4
    credible_ratio: 0.8
    score_range: [87.0, 87.6]
    median_score: 87.6
  notes: ""
```

### Storage Location

Save to: `data/raw/{benchmark_slug}_{date}.yaml`

Examples:
- `data/raw/aa_omniscience_2026-06-16.yaml`
- `data/raw/gdpval_aa_v2_2026-06-16.yaml`
- `data/raw/terminalbench_hard_2026-06-16.yaml`
- `data/raw/bfcl_v4_2026-06-16.yaml`
- `data/raw/swe_bench_verified_2026-06-16.yaml`

### Image Evidence Storage

- Automated page screenshots: `data/raw/screenshots/`
- **User-shared images (from forums)**: `data/raw/user_shared_images/`
- Image index & manual extraction data: `data/raw/forum_images_index_{date}.yaml`
- Archived images: `data/raw/screenshots/archive/`

**⚠️ 关键规则**：Never use AI OCR on user-shared images. Always manual extract, always tag `needs_manual_review: true`.

## Hard Rules (NEVER Violate)

1. **No fabrication**: If data not found, store `null`, not 0 or estimated value
2. **Source URL required**: Every score must have `source_url`. No URL = not stored
3. **Minimum 2 sources for confidence ≥ 0.8**: Single source max confidence = 0.5
4. **Log all degradation**: Every downgrade must be recorded with reason
5. **Collection report mandatory**: Every run ends with a summary report
6. **No paywall bypass**: If data requires payment, record the price and stop
7. **No robots.txt violation**: Check before scraping
8. **Rate limit**: ≥2 seconds between requests to same domain
9. **Check endpoint pool first**: Always consult `config/endpoint_pool.yaml` before discovering new endpoints
10. **Three-outcome model**: For each collection attempt → 成功 / 降级 / 停下. Never silently guess.
11. **Agent vs Base distinction**: When collecting SWE-Bench or similar scores, always note whether the score includes harness/agent contributions
12. **No AI OCR on user-shared images**: 豆包/DeepSeek 图片 OCR 能力已验证不可靠。用户分享的截图必须人工读取，每项数据标注 `needs_manual_review: true`，并保留 `source_image_ref`
13. **Image data != benchmark data**: 图片来源的数据永远不得作为 benchmark 官方分数的来源。官方 benchmark 数据必须来自 API/HTML/official report

## Collection Report Template

```
COLLECTION REPORT
Date: {date}
Target: {benchmark/site}
Duration: {time_taken}

Results:
  - Total data points collected: {N}
  - Credible (confidence ≥ 0.8): {N}
  - Degraded (confidence 0.5-0.8): {N}
  - Unreliable (confidence < 0.5): {N}
  - Needs manual review: {N}
  - Failed to collect: {N}

Agent Annotation:
  - Models with agent data: {N}
  - GDPval-AA coverage: {N}/{total}
  - Terminal-Bench coverage: {N}/{total}
  - BFCL FC/Prompt delta available: {N} models

Degradation Log:
  - {model}: {reason for degradation}

Blockers:
  - {description}

Next Steps:
  - {actionable items for human}
```

## Incremental Update Strategy

- **Full refresh**: First run, or >30 days since last
- **Incremental**: Only scan for models released since last run
- **Triggered**: When a provider announces a new model (detected via scan)

Check `data/raw/` for existing files before starting. If files exist within 7 days, consider incremental mode.

## Known Data Sources Quick Reference

| Source | URL | Method | Status |
|--------|-----|--------|--------|
| AA-Omniscience | artificialanalysis.ai/evaluations/omniscience | `browser_snapshot` + `browser_evaluate` | verified |
| AA-GDPval-v2 | artificialanalysis.ai/evaluations/gdpval-aa | `browser_navigate` + `playwright_evaluate` | verified |
| AA-Terminal-Bench-Hard | artificialanalysis.ai/evaluations/terminalbench-hard | `browser_snapshot` + `browser_evaluate` | verified |
| BFCL V4 | gorilla.cs.berkeley.edu/leaderboard.html | `browser_snapshot` + `playwright_get_visible_html` | verified |
| SWE-Bench | swebench.com | `browser_navigate` + `playwright_evaluate` | verified (delayed) |
| OpenRouter | openrouter.ai/api/v1/models | `playwright_get` | verified |
| GAIA | huggingface.co/spaces/gaia-benchmark/leaderboard | TBD | untested |

Full list: `config/endpoint_pool.yaml`

## Forum Data Collection (HackerNews / Community Sources)

For collecting real-world usage data (token consumption, subscription cost, user behavior) from community forums like HackerNews.

### Why Forum Data?

Structured benchmarks tell you model capability. Forum data tells you **real-world cost**:
- How many tokens does a Claude Max 20x subscription actually consume per month?
- What's the cache hit rate in real agentic coding workflows?
- How does API equivalent cost compare to subscription price?

This data cannot be found in official docs — only users share it.

### Two Types of Forum Data

| Type | Source Format | Extraction Method | 可信度 |
|------|--------------|-------------------|--------|
| **Text-based numbers** | 评论正文里的数字/表格文字 | 关键词过滤 + AI NLP 理解 | 较高（可溯源到原句） |
| **Image-based numbers** | 用户上传的截图（CLI 输出、账单截图、ccusage 表格） | **人工读取**（AI OCR 不可靠，已验证排除） | 较低（需人工校验，默认 needs_manual_review: true） |

### Phase F1: Collection (Algolia API)

HackerNews has a public Algolia search API (no auth needed):

```
https://hn.algolia.com/api/v1/search?query={keywords}&tags=story|comment
```

**Search strategy** (run multiple queries, union results):
- `"Claude Code" /cost tokens` — usage tracking discussions
- `"Claude Max" subscription limit tokens` — subscription usage
- `"cache read" "cache hit" tokens` — cache breakdown shares
- `"ccusage" OR "/stats"` — tool-based usage reports
- `"ChatGPT Pro" "hit limit" tokens` — OpenAI subscription usage
- `"DeepSeek" "cache hit" tokens cost` — DeepSeek usage

**Filter rules**:
- Only keep entries with `points >= 0` (don't over-filter, good data can have 0 points)
- Deduplicate by `objectID`
- Save ALL raw results to `data/raw/hn_*.json` — never discard, even seemingly irrelevant entries may contain gold in comments

### Phase F1.5: Image Detection & Capture

论坛帖子中包含截图的需要单独处理，但**不要用 AI OCR 自动读取**（已验证豆包/DeepSeek OCR 结果不可信）。

**流程**：
1. 扫描 HN 评论是否包含图片链接（`imgur`、`.png`、`.jpg`、内嵌图片）
2. 用 Playwright 访问，将截图保存到 `data/raw/user_shared_images/`
3. 在 `data/raw/forum_images_index_{date}.yaml` 建立索引：
```yaml
- image_id: "hn_47536655_01"
  source_comment_url: "https://news.ycombinator.com/item?id=47536655"
  saved_path: "data/raw/user_shared_images/hn_47536655_01.png"
  detected_keywords: ["token", "cache", "cost"]
  extraction_status: "pending_manual_review"  # 等待人工读取
  extracted_data: null  # 由人工填写
```
4. 人工读取后回填 `extracted_data`，并标 `needs_manual_review: true`

### Phase F2: Sentence Filtering (Script, NOT Regex Parsing)

**Critical lesson**: Do NOT use regex to parse token numbers from forum text. Forum posts have wildly inconsistent formats ("182", "182M", "182 million", "1.82B", "~182k") and regex will misinterpret units (e.g., treating "182 tokens" as "182M tokens").

**Correct approach**: Script filters sentences containing keywords, AI does NLP comprehension.

```python
# Script: filter_token_sentences.py
# Input: raw JSON entries
# Output: JSON of sentences containing keywords
# The script does NOT parse numbers — only filters

KEYWORDS = [
    "cache read", "cache hit", "cached", "cache create", "cache miss",
    "input token", "output token", "total token", "tokens in", "tokens out",
    "million tokens", "billion tokens", "tokens a day", "tokens per month",
    "/cost", "/stats", "ccusage", "hit the limit", "used up",
    "max 5x", "max 20x", "claude pro", "chatgpt pro", "chatgpt plus",
    "$/month", "per million", "api equivalent", "api cost",
    "% cache", "% input", "% output", "cache hit rate",
]

def has_keyword(sentence):
    return any(kw in sentence.lower() for kw in KEYWORDS)
```

Output: `data/raw/token_sentences_for_nlp_{date}.json` — each entry is one sentence with its source metadata.

### Phase F3: NLP Comprehension (AI reads each sentence)

Load filtered sentences in batches (50-100 per batch). For each sentence, AI must:

1. **Read the full sentence** (not just the keyword match)
2. **Extract structured data** only if the sentence contains concrete numbers
3. **Record the exact source sentence** as evidence
4. **Mark uncertainty** — if a value is inferred (not explicitly stated), mark `inferred: true`

Output format per entry:
```yaml
- entry_id: "47536655"
  hn_url: "https://news.ycombinator.com/item?id=47536655"
  subscription: "claude_max_20x"
  agent: "claude_code"
  token_breakdown_millions:
    cache_read: 427.0      # explicit
    fresh_input: 5.5       # explicit
    output: 1.8            # explicit
  source_sentences:        # MUST include the exact sentences as evidence
    - "95.1% of my input tokens were cache reads (427M tokens)."
    - "5.5M fresh input + 1.8M output burned budget."
```

### Phase F4: Cross-Validation (MANDATORY before output)

**This is the step that was missing and caused data quality disasters.** Before finalizing any extracted data, run these checks:

#### Check 1: Unit Sanity
For every token number, verify the unit is correct:
- "182" in a table → likely **182 tokens**, NOT 182M
- "182M" → 182 million
- "1.82B" / "1.82 billion" → 1820M
- "182,000" → 0.182M
- **If the raw text says "182" with no unit suffix, it is 182 tokens, not 182M**

#### Check 2: Ratio Sanity (cache_read should dominate)
For Claude Code / agentic coding workflows:
- `cache_read` should be **90-98%** of total tokens
- `fresh_input` should be **2-8%**
- `output` should be **1-5%`
- **If cache_read < fresh_input, the data is WRONG or it's a non-caching scenario** (e.g., first-time chat, no cache enabled)

For non-caching scenarios (e.g., OpenWebUI without cache):
- `cache_read = 0` is valid, but mark `caching_enabled: false`

#### Check 3: Cross-Reference Against Peers
Group entries by subscription type / agent. Within each group:
- Token totals should be within a reasonable range (not 100x apart unless explained)
- Cache hit rates should be consistent (±5%)
- **Outliers need explanation**: Is it a demo session? A test? A different workflow?

Example of catching an error:
```
Entry #3: cache_read=1.58M, fresh_input=182M, output=0.003M
→ cache_read << fresh_input (1.58M vs 182M) — RED FLAG
→ Other Claude Code entries: cache_read = 427M-6244M
→ This entry is a demo (Haiku, $0.22 total cost), not real usage
→ EXCLUDE from baseline, or mark as `demo_data: true`
```

#### Check 4: Context Classification
For each entry, classify the user's behavior profile:
- `heavy_agentic_coder`: cache_read > 500M, uses Claude Code/Codex daily
- `moderate_coder`: cache_read 50-500M, regular but not daily heavy
- `light_user`: cache_read < 50M, occasional use
- `demo/test`: very small numbers + low cost (< $1), likely testing
- `batch_processing`: large fresh_input, no cache, one-off bulk job
- `chat_no_cache`: cache_read=0, OpenWebUI or API without cache

This classification helps when computing medians — don't mix demo sessions with real usage.

#### Check 5: Evidence Completeness
Every extracted number MUST have a `source_sentences` entry showing where it came from. If you cannot find the exact sentence that states a number, **do not include that number** — mark as `null`, never infer or fabricate.

### Phase F5: Output

Final output: `data/raw/token_composition_nlp_extracted_{date}.yaml`

Structure:
```yaml
metadata:
  collected_at: "2026-06-17"
  method: "script filter + NLP comprehension + cross-validation"
  total_raw_entries: N
  filtered_sentences: N
  high_quality_complete: N    # passed all 5 checks
  excluded: N                 # failed checks, with reasons

high_quality_complete:
  - entry_id: ...
    user_profile: "heavy_agentic_coder"  # from Check 4
    token_breakdown_millions: ...
    source_sentences: ...

excluded:
  - entry_id: "47299439"
    reason: "demo_data (Haiku, $0.22 total), unit misread (182 tokens not 182M), cache_read/input ratio inverted"
    original_extraction: ...
```

### Common Pitfalls (Learned the Hard Way)

1. **"182" ≠ "182M"**: A bare number in a table is token count, not millions. Always check the table header and surrounding text for units.

2. **Demo sessions look like real data**: A Show HN post with a cost-tracking skill demo will have a "nice table" of tokens — but it's a tiny test session ($0.22), not real usage. Check total cost: if < $1, likely a demo. **But demo data may still have value as a rigorous test** — the four-dimension semantics (base_input/output/cache_writes/cache_reads) are clear, just mark it as `rigorous_test` rather than excluding.

3. **Cache miss ≠ output**: "5M cache miss output tokens" is ambiguous — "cache miss" refers to fresh input (uncached), not output. Read carefully.

4. **Percentages may be nested**: "85% input, 15% output, 90% cache reads" means cache reads are 90% *of input*, not 90% of total. Decompose: cache_read = 85%×90% = 76.5% of total.

5. **Single-call data ≠ periodic usage**: "22M tokens for one call" is a single API call, not a monthly subscription usage. Don't mix them into subscription baseline.

6. **No cache is valid**: `cache_read = 0` is correct for OpenWebUI or raw API without prompt caching. Don't "fix" it to a non-zero value.

7. **input/output may be swapped in source**: Some HN comments have input/output columns swapped (e.g., KronisLV's table shows "Input 1.95M, Output 19.4M" but real agentic coding has fresh_input >> output because fresh_input includes tool call results). **Validation rule**: if output > fresh_input, suspect the source has them swapped. Cross-check with the rule `cache_read >> fresh_input >> output`. If swapping makes the data pass, swap and mark `corrected: true`.

8. **User-provided data may be strategy-specific, not baseline**: A user may share "real" data that's actually an extreme optimization for a specific pricing scheme (e.g., 50x cache discount). This data is valid but NOT a general baseline. Always ask: "Is this normal usage or an optimization strategy?" Mark strategy-specific data as `is_cache_optimized_extreme: true` and exclude from general baseline calculations. The user's normal-usage estimate (e.g., "200M total, 95% hit rate") is more useful as a baseline than their optimized extreme.

9. **fresh_input includes tool call results**: In agentic coding, `fresh_input` is NOT just user typing — it includes file contents, command outputs, tool call results. So `fresh_input >> output` is the normal pattern (user types short instruction, LLM reads many files, outputs short response + some code). Typical `fresh_input/output` ratio: 3-35x.


