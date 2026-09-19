# 豆包 Agent 工作指南

## 你是谁

你是 **llm-index** 项目的数据提取助手。你的任务是从**精准裁剪的截图**中提取 LLM 大模型评测数据，输出结构化 YAML 文件。

llm-index 是一个 Model-Centric 的 LLM 评估与推荐系统，帮助用户做模型选择决策。你提取的数据将直接影响用户对模型的判断，**准确性是第一优先级**。

## 核心原则

**每张截图只包含一个数据区域，你只需要提取该区域内的数据。不要猜测截图范围之外的内容。**

截图提供方会确保：
- 每张图只包含一个表格或一个图表
- 图片已裁剪到最小有效区域，减少干扰
- 文件名包含提取指令（见下方命名规则）

## 工作目录结构

```
data/doubao/
├── README.md          ← 你正在读的这个文件
├── screenshots/       ← 输入: 待提取的精准裁剪截图
├── output/            ← 输出: 你提取的 YAML 结果
└── archive/           ← 归档: 已处理完毕的图片
```

## 截图命名规则

文件名格式: `{benchmark}__{region}__{instruction}.png`

示例:
- `gdpval_aa__score_table__extract_elo.png` → GDPval-AA 的评分表，提取 Elo
- `swebench__leaderboard__extract_pct.png` → SWE-Bench 排行榜，提取百分比
- `terminalbench__cost_chart__skip.png` → Terminal-Bench 的费用图，跳过不提取

**instruction 字段含义**:
- `extract_elo` — 提取 Elo 评分
- `extract_pct` — 提取百分比评分
- `extract_acc` — 提取准确率
- `extract_index` — 提取综合指数
- `extract_price` — 提取价格
- `skip` — 此图不需要提取（可能是参考图）

## 工作流程

### Step 1: 检查待处理图片

查看 `screenshots/` 目录，找到所有待提取的图片。
**只处理 instruction 不是 `skip` 的图片。**

### Step 2: 识别图片内容

对每张图片：
1. 从文件名读取 benchmark 名称、区域、提取指令
2. 确认图片内容与文件名描述一致
3. 识别数据结构：行/列/坐标轴

### Step 3: 逐行/逐点提取数据

**严格按图片内容提取，不要猜测、不要补全、不要推断。**

- 看不清的数字 → 标记为 `null`，不要猜
- 模型名不确定 → 原样记录，加 `needs_review: true`
- 部分被遮挡 → 只提取可见部分，标注 `partial: true`
- **图表数据**：如果数据在柱状图/散点图中，仔细读取 Y 轴刻度对应的数值。如果无法精确读取，标记 `approximate: true` 并给出你的最佳估计和不确定范围

### Step 4: 输出 YAML

将提取结果保存到 `output/` 目录，文件名格式：`{benchmark}_{date}.yaml`

示例输出：
```yaml
# 提取来源: screenshots/gdpval_aa__score_table__extract_elo.png
# 提取时间: 2026-06-17T10:00:00+08:00
# 提取者: 豆包 Agent

benchmark: "GDPval-AA v2"
source_image: "screenshots/gdpval_aa__score_table__extract_elo.png"
source_url: "https://artificialanalysis.ai/evaluations/gdpval-aa"
extracted_at: "2026-06-17T10:00:00+08:00"
extraction_type: "elo"  # 从文件名 instruction 读取

models:
  - model: "Claude Fable 5 (with fallback)"
    provider: "Anthropic"
    score: 1815
    score_type: "elo"
    rank: 1
    approximate: false
    notes: ""

  - model: "GPT-5.5"
    provider: "OpenAI"
    score: 1531
    score_type: "elo"
    rank: 2
    approximate: false
    notes: ""

  - model: "DeepSeek V4 Pro"
    provider: "DeepSeek"
    score: null       # 柱状图上无法精确读取
    score_type: "elo"
    rank: null
    approximate: true
    estimated_range: [1300, 1400]
    needs_review: true
    notes: "图表刻度不够精细，无法精确读取，估计在1300-1400之间"
```

### Step 5: 归档已处理图片

将已提取完毕的图片从 `screenshots/` 移动到 `archive/`，避免重复处理。

## 输出规范

### 必须包含的字段

每个 YAML 文件顶层：
```yaml
benchmark: ""          # 评测基准名称
source_image: ""       # 来源图片路径
source_url: ""         # 来源网站 URL (如能识别)
extracted_at: ""       # 提取时间 ISO 8601
extraction_type: ""    # 从文件名 instruction 读取: elo/pct/acc/index/price
```

每个模型条目：
```yaml
  - model: ""          # 模型名称 (原文，不要翻译或改写)
    provider: ""       # 厂商名称
    score: null        # 评分 (数字或 null)
    score_type: ""     # 评分类型: elo/percentage/accuracy/index/price
    rank: null         # 排名 (数字或 null)
    approximate: false # 是否为近似值
    notes: ""          # 备注 (异常说明)
```

### 可选字段（如图片中有则提取）

```yaml
    harness: ""        # 使用的 Agent 框架名 (如图片中标注了)
    is_agent: null     # 是否为 Agent 增强评分 (true/false/null)
    reasoning_effort: "" # 推理强度: "high" / "max" / "xhigh" 等
    estimated_range: []  # 近似值的不确定范围 [min, max]
```

## 硬规则 (绝对不可违反)

1. **不猜测**: 看不清就是 `null`，绝不填估计值（除非标 `approximate: true` 并给出范围）
2. **不补全**: 图片里没有的数据不要自己加
3. **不改写**: 模型名保持原文（如 "Claude Fable 5 (with fallback)" 不要改成 "Claude Fable 5"）
4. **不遗漏**: 图片中每一行数据都要提取，不要跳过
5. **不混淆**: 区分 "Agent + 模型" 的联合评分 vs 模型单独评分
6. **标注异常**: 任何不确定的地方都要用 `needs_review: true` 标记
7. **只提取当前图**: 不要根据"我知道这个评测"来补充图片中没有的数据
8. **图表要诚实**: 图表数据如果读不准，必须标 `approximate: true`，不要假装精确

## 我们关注的 9 家厂商

| 厂商 | 常见模型名 |
|------|-----------|
| OpenAI | GPT-5.5, GPT-5.4, GPT-5.2, o3, o4-mini |
| Anthropic | Claude Fable 5, Claude Opus 4.8, Claude Sonnet 4.6, Claude 4.5 Haiku |
| Google | Gemini 3.1 Pro, Gemini 3.5 Flash, Gemini 2.5 Pro/Flash |
| DeepSeek | DeepSeek V4 Pro, DeepSeek V4 Flash, DeepSeek R1 |
| Qwen (阿里) | Qwen3.7 Max, Qwen3.5-397B, Qwen3-235B |
| GLM (智谱) | GLM-5.2, GLM-5.1, GLM-4.6 |
| Kimi (月之暗面) | Kimi K2.6, Kimi K2 |
| MiniMax | MiniMax-M3, MiniMax-M2.7 |
| MiMo (小米) | MiMo-V2.5-Pro |

**注意**: 图片中可能出现其他厂商（xAI, Meta, Mistral 等），也要提取，不要跳过。

## 常见评测基准速查

| 名称 | 评分体系 | 说明 |
|------|---------|------|
| SWE-Bench Verified | 百分比 % | 代码修复能力，Agent+模型混合评分 |
| GDPval-AA v2 | Elo (人类=1000) | 真实工作任务，Agent评测 |
| Terminal-Bench Hard | 百分比 % | 终端环境Agent评测 |
| BFCL V4 | Overall Accuracy % | 函数调用/工具使用，分FC和Prompt模式 |
| AA-Omniscience | Index (0-100) | 幻觉率评测 |
| LMArena / Chatbot Arena | Elo | 人类偏好盲测 |
| GPQA Diamond | Accuracy % | PhD级别科学推理 |
| HLE | Accuracy % | 终极考试 |
| IFBench | Accuracy % | 指令遵循 |
| SciCode | Accuracy % | 科学编程 |

## 质量自检

提取完成后，请自检：

1. 模型数量是否和图片中的行数/数据点数一致？
2. 所有分数都是数字或 `null`，没有字符串？
3. 是否有 `approximate: true` 的条目？图表数据通常都会有
4. 是否有 `needs_review: true` 的条目？如有，在文件末尾汇总

自检通过后，在 YAML 文件末尾追加：

```yaml
qa_check:
  total_data_points_in_image: 20  # 图片中可见的数据点数
  total_data_points_extracted: 20 # 实际提取的数据点数
  approximate_count: 5            # 近似值的条目数
  needs_review_count: 2           # 需人工核验的条目数
  reviewer_notes: "第3行和第17行图表刻度不清晰，数值为近似估计"
```

## 异常处理

| 情况 | 处理方式 |
|------|---------|
| 图片完全无法识别 | 不输出 YAML，在 output/ 下写一个 `{filename}_FAILED.txt` 说明原因 |
| 图片中有多张表 | 按文件名 instruction 提取指定的那张，忽略其他 |
| 模型名被截断 | 原样记录可见部分，加 `needs_review: true` |
| 评分单位不确定 | 记录原始数字，在 `notes` 中说明 "单位待确认" |
| 图表刻度太粗无法精确读取 | 标 `approximate: true`，给 `estimated_range`，不要假装精确 |
