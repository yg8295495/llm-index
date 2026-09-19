# 视觉模型图片提取能力测试结论

> **状态: 人工校验完成**
> **测试日期: 2026-06-17**
> **校验人: 项目用户 + AI Agent**
> **测试模型: 豆包桌面端 Agent + DeepSeek 网页版（参照组）**

## 测试目的

验证视觉模型的图片识别能力是否可用于 LLM 评测数据采集场景。

## 测试方法

1. 用 Playwright 截取评测网站页面
2. 对全页截图做精准区域裁剪，每张图只包含一个数据区域
3. 文件名包含提取指令（benchmark__region__instruction.png）
4. 豆包读取 README.md 了解规范后，对 screenshots/ 目录下的图片做数据提取
5. 输出 YAML 到 output/ 目录
6. 人工对照原图校验提取结果

## 测试样本

| 文件 | 评测基准 | 数据形式 | 提取指令 |
|------|---------|---------|---------|
| `terminalbench_hard__score_chart__extract_pct.png` | Terminal-Bench Hard | 柱状图 | 提取百分比 |
| `gpqa_diamond__score_chart__extract_acc.png` | GPQA Diamond | 柱状图 | 提取准确率 |
| `aa_omniscience__detail_table1__extract_index.png` | AA-Omniscience | 图表 | 提取 Index |
| `aa_omniscience__detail_table2__extract_index.png` | AA-Omniscience | 表格 | 提取 Index |

## 测试结果

### 第一轮（全页截图，13张）

- **结果**: 完全不可用
- **问题**: 全页截图信息量过大，豆包注意力漂移，数据全部编造
- **示例**: GDPval-AA v2 真实 Elo 1815，豆包提取 1285，偏差 -530
- **示例**: Terminal-Bench 真实 62.9%，豆包提取 89.2%，偏差 +26.3
- **特点**: 豆包对编造的数据信心满满，qa_check 声称"无需复核"

### 第二轮（精准裁剪，4张）

#### Terminal-Bench Hard（柱状图）

| 模型 | 豆包估计范围 | 真实值 | 命中 |
|------|------------|--------|------|
| Claude Fable 5 | [60, 65] | 62.9% | ✓ |
| GPT-5.5 | [58, 63] | 60.6% | ✓ |
| DeepSeek V4 Pro | [44, 49] | 46.2% | ✓ |
| Gemini 3.5 Flash | [40, 45] | 40.9% | ✓ |
| Claude Sonnet 4.6 | [35, 40] | 53.0% | ✗ |

- **数值估计**: 前4个命中范围，第5个完全错误
- **模型识别**: 错误。真实 top5 第3-5名是 GPT-5.5 不同 effort 版本，豆包识别成了 DeepSeek/Gemini/Sonnet
- **诚实度**: 全部标了 `approximate: true`，比第一轮有进步

#### GPQA Diamond（柱状图）

- **结果**: 无法验证（无真实数据对比）
- **格式**: 规范，`approximate: true` 标注正确
- **可信度**: 存疑，基于 Terminal-Bench 的表现推断不可信

#### AA-Omniscience table1

- **结果**: 完全失败
- **表现**: 输出 `MODEL_NAME_PLACEHOLDER_1~5`，数值全部 null
- **诚实度**: 诚实承认"视觉识别限制"
- **用户校验备注**: 这张图实际不是散点图，豆包识别内容牛头不对马嘴

#### AA-Omniscience table2

- **结果**: 可疑，疑似编造
- **表现**: 声称"精确读取"，给出了6个模型的分数
- **红旗**: 分数间距过于均匀（2.2-2.5），真实数据不会这么整齐
- **红旗**: table1 完全失败，table2 突然"精确读取"，行为不一致
- **结论**: 无法信任，可能是"自信编造"而非真实识别

## DeepSeek 网页版参照测试

### 测试条件

- 测试模型: DeepSeek 网页版（识图模式）
- 测试图片: `aa_omniscience__detail_table2__extract_index.png`（AA-Omniscience Hallucination Rate 图表）
- 图片特点: 图表未占满窗口，有边缘无效信息，识别难度较高
- 提示词: 标准数据提取提示词，要求不猜测、不补全、看不清标 null

### 测试结果

DeepSeek 提取了 28 个模型的数据，声称全部 `approximate: false`（数值清晰）。

#### 模型名识别：完全不匹配

DeepSeek 提取的全是 2024 年老模型，而真实数据是 2026 年最新模型：

| DeepSeek 提取的模型名 | 真实模型名 |
|----------------------|-----------|
| MiniMax-Text-01 | MiniMax-M3 |
| Qwen2.5-7B-Instruct | Qwen3.7 Max |
| MiniCPM-o-2-6 | MiMo-V2.5-Pro |
| DeepSeek-V3 | GLM-5.1 |
| Qwen2.5-72B-Instruct | MiniMax-M2.7 |
| Mistral-7B-Instruct-v0.3 | Kimi K2.6 |
| GPT-4o-2024-05-13 | GPT-5.5 |
| Claude-3-5-Sonnet-20240620 | Claude Fable 5 |
| Gemini-1.5-Pro-Exp | Gemini 3.1 Pro Preview |
| ... | ... |

**模型名识别准确率: 0/28 (0%)**

#### 数值识别：部分命中

DeepSeek 提取的 hallucination rate 数值与真实数据存在对应关系：

| DeepSeek 提取值 | 真实数据中相同值的模型 |
|----------------|---------------------|
| 16 | MiniMax-M3 (16) ✓ |
| 23 | Qwen3.7 Max (23) ✓ |
| 25 | MiMo-V2.5-Pro (25) ✓ |
| 29 | GLM-5.1 (29) ✓ |
| 34 | MiniMax-M2.7 (34) ✓ |
| 39 | Kimi K2.6 (39) ✓ |

数值能对上，说明 DeepSeek 可能读到了图表上的数值，但模型名看不清，用知识库里的老模型名"填空"。

#### 诚实度

- 全部标 `approximate: false`，声称"数值清晰"
- 实际上模型名完全编造
- 与豆包一样存在"自信编造"问题

### DeepSeek vs 豆包对比

| 维度 | 豆包 | DeepSeek |
|------|------|----------|
| 数值读取 | 柱状图能给估计范围 | 可能读对了数值 |
| 模型名 | 识别错误/编造 | 完全编造（用老模型填空） |
| 诚实度 | 第二轮有进步（标 approximate） | 无进步（全标精确） |
| 数据量 | 5-6条 | 28条（更完整但更危险） |
| 可用性 | 不可用 | 不可用 |

**结论**: DeepSeek 在数值读取上可能略强于豆包（读到了更多数据点），但在模型名识别上同样不可信。两个模型的核心问题一致：看不清模型名时用知识库"填空"，且不自知。

## 最终结论

### 不可用

豆包桌面端 Agent 和 DeepSeek 网页版的图片识别能力**均不适合用于 LLM 评测数据采集**。

### 核心问题

1. **无法区分"看清楚了"和"在合理化猜测"**: table2 案例中，豆包以为自己在精确读取，实际在编造数据
2. **模型名识别错误**: 即使数值估计在范围内，模型名也可能识别错（Terminal-Bench 案例）
3. **注意力漂移**: 信息量大时无法聚焦关键区域
4. **编造数据不自知**: 第一轮中 qa_check 声称"无需复核"，实际数据全部错误

### 两个模型的共同问题

豆包和 DeepSeek 都存在同一个致命缺陷：**数值可能读对了，但模型名不可信**。两个模型都会在模型名看不清时，用自己知识库里的模型名"填空"，而且都标了 `approximate: false`，声称"数值清晰"。这种"自信编造"比能力不足更危险，因为无法通过自检标记区分真实数据和编造数据。

### 对比结论

| 采集方式 | 准确率 | 可信度 | 适用场景 |
|---------|--------|--------|---------|
| WebFetch (HTML提取) | 高 | 高 | 有标准 HTML 表格的页面 |
| Playwright (script标签提取) | 高 | 高 | RSC/SPA 动态页面 |
| 豆包视觉提取 | 低 | 低 | 不推荐用于数据采集 |
| DeepSeek 网页版视觉提取 | 数值中/模型名低 | 低 | 不推荐用于数据采集 |

### 建议

- 评测数据采集继续以 WebFetch + Playwright 为主要手段
- 豆包方案降级为"最后兜底"，仅在没有其他方式时尝试，且必须人工逐条校验
- 后续配置 @playwright/mcp 后，用 MCP 的"先看再截"能力做精准截图，比盲裁更可靠
- 如果未来需要图片识别，考虑用更强的视觉模型（如 GPT-4o 级别），但仍需人工校验

## 测试文件归档

- 测试输入: `screenshots/` （4张精准裁剪截图）
- 测试输出: `output/` （4个 YAML 文件）
- 本结论: `EVALUATION_RESULT.md`
- 工作规范: `README.md`

测试文件保留作为参考，不再用于数据采集。
