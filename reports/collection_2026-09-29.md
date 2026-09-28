# Collection Report — AA Omniscience 2026-09-29

- 工具: `collect_aa_v3`  模式: DRY RUN (未写库)
- 来源: https://artificialanalysis.ai/evaluations/omniscience
- 抓取时刻: 2026-09-28T22:27:03+00:00  HTTP 200  1,177,284 B
- 页面指纹 sha256: `32e01ac7bf0773ff130bbec2546c34417c2ac5bc3989a8e5aead60391b3ad455`
- RSC 分片数: 122
- 解析: 带分模型 32 / 注册表 679

## 范围与归属
- 入库模型: core 24 + reference 8 + unclassified 0; 范围外排除 0
- 评测行: 写 536, 已存在跳过 0, 因缺 source_url 拒绝 0
- 新建模型行 7 / 更新既有行 25

## 需要人工确认 (needs_manual_review)
- ID 规范化: `anthropic/claude-fable-5.1` → `anthropic/claude-fable-5.1-xhigh` (aa_slug=claude-fable-5-1-xhigh)
- ID 规范化: `openai/gpt-6-astra` → `openai/gpt-6-astra-xhigh` (aa_slug=gpt-6-astra-xhigh)
- ID 规范化: `openai/gpt-6-astra` → `openai/gpt-6-astra-high` (aa_slug=gpt-6-astra-high)
- ID 规范化: `qwen/qwen3.8-max-0902` → `qwen/qwen3.8-max` (aa_slug=qwen3-8-max)
- ID 规范化: `stepfun/step-5-preview` → `stepfun/step-5` (aa_slug=step-5)
- ID 规范化: `nvidia/nemotron-3-ultra-550b-a55b` → `nvidia/nvidia-nemotron-3-ultra-550b-a55b` (aa_slug=nvidia-nemotron-3-ultra-550b-a55b)

## Schema
- 新增列 index uq_eval_model_benchmark_snapshot (UNIQUE)

## 来源 URL 口径
- 以下 13 个数据源在 config/benchmarks.yaml 未写独立 source_url, 统一回退为 AA omniscience 页面 URL (本批次数值的确切出处):
  `agentic_index`, `aime`, `analyst_agent`, `apex_agents`, `coding_index`, `cost_per_task`, `enterprise_ops_gym`, `intelligence_index`, `itbench_sre`, `mlcr_overall`, `pricing`, `tau_banking`, `terminalbench_v4_0`

## 补采清单 (config/watchlist.yaml → AA 单模型详情页)
- `qwen3-8-flash-next` → 14 条评测（新建 0 / 更新 1），tier={'core': 1}
  - 出处: https://artificialanalysis.ai/models/qwen3-8-flash-next（3,954,171 B, sha256 `6d5263960ccb…`）
  - 原因: 用户常选; 阿里系, 属九家核心范围, 但不在 omniscience SSR 的 31 条内
- `hy3` → 13 条评测（新建 0 / 更新 1），tier={'reference': 1}
  - 出处: https://artificialanalysis.ai/models/hy3（3,950,618 B, sha256 `56c79005fbc1…`）
  - 原因: 腾讯混元当前版本; AA 已收录但未进 omniscience 默认对比集, 作参照锚点

## 模型明细

| tier | model_id | 档位 | 发布 | 评测数 |
|---|---|---|---|---|
| core | `anthropic/claude-fable-5` | max | 2026-06-09 | 21 |
| core | `anthropic/claude-fable-5.1` | max | 2026-09-01 | 18 |
| core | `anthropic/claude-fable-5.1-xhigh` | xhigh | 2026-09-01 | 15 |
| core | `anthropic/claude-opus-5` | max | 2026-07-24 | 19 |
| core | `anthropic/claude-opus-5.5` | max | 2026-09-22 | 15 |
| core | `anthropic/claude-opus-5.5-xhigh` | xhigh | 2026-09-22 | 13 |
| core | `anthropic/claude-sonnet-5.5` | max | 2026-09-28 | 13 |
| core | `deepseek/deepseek-v4.1-flash` | max | 2026-09-10 | 14 |
| core | `google/gemini-3.5-flash-lite` | — | 2026-07-21 | 17 |
| core | `google/gemini-3.8-flash` | — | 2026-09-02 | 17 |
| core | `minimax/minimax-m3` | — | 2026-06-01 | 22 |
| core | `moonshot/kimi-k3` | — | 2026-07-16 | 21 |
| core | `openai/gpt-5.6-luna` | — | 2026-07-09 | 20 |
| core | `openai/gpt-5.6-sol` | — | 2026-07-09 | 23 |
| core | `openai/gpt-6-astra` | — | 2026-09-03 | 18 |
| core | `openai/gpt-6-astra-high` | — | 2026-09-03 | 15 |
| core | `openai/gpt-6-astra-xhigh` | — | 2026-09-03 | 15 |
| core | `openai/gpt-6-luna` | — | 2026-09-22 | 13 |
| core | `openai/gpt-6-sol` | — | 2026-09-22 | 14 |
| core | `qwen/qwen3.8-27b` | — | 2026-08-14 | 17 |
| core | `qwen/qwen3.8-max` | — | 2026-09-02 | 16 |
| core | `xiaomi/mimo-v2.6-pro` | — | 2026-09-21 | 12 |
| core | `zhipu/glm-5.3` | — | 2026-08-18 | 17 |
| core | `zhipu/glm-5.3-flash` | — | 2026-08-26 | 17 |
| reference | `ifm/k2-horizon-375b-a23b` | — | 2026-09-03 | 14 |
| reference | `meta/muse-glimmer` | — | 2026-08-10 | 17 |
| reference | `meta/muse-spark-1.3` | — | 2026-09-02 | 16 |
| reference | `mistral/mistral-medium-3.5` | — | 2026-04-29 | 22 |
| reference | `nvidia/nvidia-nemotron-3-ultra-550b-a55b` | — | 2026-06-04 | 21 |
| reference | `stepfun/step-5` | — | 2026-09-18 | 13 |
| reference | `thinking_machines/inkling` | — | 2026-07-15 | 18 |
| reference | `xai/grok-4.7` | — | 2026-09-21 | 13 |
