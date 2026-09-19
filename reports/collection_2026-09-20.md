# Collection Report — AA Omniscience 2026-09-20

- 工具: `collect_aa_v3`  模式: 已写入
- 来源: file:///tmp/aa_cached.html
- 抓取时刻: 2026-09-19T21:06:36+00:00  HTTP 0  1,232,493 B
- 页面指纹 sha256: `d20f0a55bc5129b36e27a29c8226463e4045d4516ca09cd314574282173f176e`
- RSC 分片数: 118
- 解析: 带分模型 31 / 注册表 653

## 范围与归属
- 入库模型: core 23 + reference 8 + unclassified 0; 范围外排除 0
- 评测行: 写 0, 已存在跳过 545, 因缺 source_url 拒绝 0
- 新建模型行 0 / 更新既有行 31

## 需要人工确认 (needs_manual_review)
- 无

## Schema
- 新增列 index uq_eval_model_benchmark_snapshot (UNIQUE)

## 来源 URL 口径
- 以下 13 个数据源在 config/benchmarks.yaml 未写独立 source_url, 统一回退为 AA omniscience 页面 URL (本批次数值的确切出处):
  `agentic_index`, `aime`, `analyst_agent`, `apex_agents`, `coding_index`, `cost_per_task`, `enterprise_ops_gym`, `intelligence_index`, `itbench_sre`, `mlcr_overall`, `pricing`, `tau_banking`, `terminalbench_v4_0`

## 模型明细

| tier | model_id | 档位 | 发布 | 评测数 |
|---|---|---|---|---|
| core | `anthropic/claude-fable-5` | max | 2026-06-09 | 21 |
| core | `anthropic/claude-fable-5.1` | high | 2026-09-01 | 15 |
| core | `anthropic/claude-fable-5.1` | max | 2026-09-01 | 17 |
| core | `anthropic/claude-fable-5.1` | xhigh | 2026-09-01 | 15 |
| core | `anthropic/claude-opus-5` | max | 2026-07-24 | 19 |
| core | `deepseek/deepseek-v4-pro` | max | 2026-08-13 | 16 |
| core | `deepseek/deepseek-v4.1-flash` | max | 2026-09-10 | 12 |
| core | `google/gemini-3.5-flash-lite` | high | 2026-07-21 | 17 |
| core | `google/gemini-3.8-flash` | high | 2026-09-02 | 16 |
| core | `minimax/minimax-m3` | — | 2026-06-01 | 22 |
| core | `moonshot/kimi-k3` | max | 2026-07-16 | 21 |
| core | `openai/gpt-5.6-luna` | max | 2026-07-09 | 20 |
| core | `openai/gpt-5.6-sol` | max | 2026-07-09 | 23 |
| core | `openai/gpt-5.6-terra` | max | 2026-07-09 | 23 |
| core | `openai/gpt-6-astra` | high | 2026-09-03 | 15 |
| core | `openai/gpt-6-astra` | max | 2026-09-03 | 17 |
| core | `openai/gpt-6-astra` | medium | 2026-09-03 | 15 |
| core | `openai/gpt-6-astra` | xhigh | 2026-09-03 | 15 |
| core | `openai/gpt-oss-120b` | high | 2025-08-05 | 26 |
| core | `qwen/qwen3.8-27b` | xhigh | 2026-08-14 | 17 |
| core | `qwen/qwen3.8-max-0902` | — | 2026-09-02 | 15 |
| core | `zhipu/glm-5.3` | max | 2026-08-18 | 16 |
| core | `zhipu/glm-5.3-flash` | max | 2026-08-26 | 16 |
| reference | `ifm/k2-horizon-375b-a23b` | — | 2026-09-03 | 14 |
| reference | `meta/muse-glimmer` | high | 2026-08-10 | 17 |
| reference | `meta/muse-spark-1.3` | max | 2026-09-02 | 15 |
| reference | `mistral/mistral-medium-3.5` | high | 2026-04-29 | 22 |
| reference | `nvidia/nemotron-3-ultra-550b-a55b` | — | 2026-06-04 | 21 |
| reference | `stepfun/step-5-preview` | — | 2026-09-18 | 12 |
| reference | `thinking_machines/inkling` | xhigh | 2026-07-15 | 18 |
| reference | `xai/grok-4.6` | high | 2026-08-12 | 17 |
