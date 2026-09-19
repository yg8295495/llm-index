# 经验总表

> 追加式详细记录。每个条目有唯一 ID，对应 experience_index.md 中的索引。

---

## EXP-001 | AA 网站数据采集方法
- **时间**: 2026-06-18 16:48
- **类别**: 采集
- **结论**: AA (artificialanalysis.ai) 无公开 API。网站使用 Next.js App Router，SSR + 客户端渲染。`__NEXT_DATA__` 不存在（App Router 不使用）。数据通过 JS chunk 加载，页面 JS 中有 `omniscience_breakdown`、`model_creators` 等数据结构。
- **采集方式**:
  1. Playwright 拦截网络请求（监听 XHR/Fetch）捕获数据 API
  2. Playwright DOM 提取（等页面完全渲染后提取表格/图表数据）
  3. JS chunk 分析（解析 `/_next/static/chunks/` 中的数据结构）
- **踩坑**: 用户同时操作浏览器时 Playwright evaluate 返回 undefined（焦点冲突），需独占操作
- **可用数据**: Model size(参数量)、Token usage、Cost breakdown、Score vs Release date 散点图、Software Engineering by Language、Cross-domain normalized

---

## EXP-002 | Terminal-Bench 数据入库遗漏
- **时间**: 2026-06-18 16:09
- **类别**: 数据
- **结论**: Terminal-Bench Hard 的 `cost_per_task_usd` 和 `output_tokens_per_task` 在原始 YAML (`data/raw/terminalbench_hard_detailed_2026-06-17.yaml`) 和 `data.json` 中都有，但数据库 observations 表的 extra 字段中缺失。入库脚本遗漏了这两个关键字段。
- **影响**: 前端无法展示 Terminal-Bench 的成本和 Token 消耗数据
- **修复**: 需要重新入库或更新 extra 字段

---

## EXP-003 | data.json 结构适配
- **时间**: 2026-06-18 15:56
- **类别**: 前端
- **结论**: data.json 的实际结构与前端代码假设不一致：
  - `models` 是 list（数组），不是 dict（对象）→ 需要 `buildModelMap()` 适配器
  - `observations` 字段不存在，实际键名是 `benchmarks` → 需要改用 `DATA.benchmarks[key]`
  - `pricing` benchmark 的 observations 为空数组，价格数据在 models 表的 `pricing_input`/`pricing_output` 字段
- **修复**: 新增 `buildModelMap()` + 改用 `DATA.benchmarks[key]` 数组结构

---

## EXP-004 | 工作流遵守
- **时间**: 2026-06-18 12:30
- **类别**: 工作流
- **结论**: 跳过确认直接改代码导致返工。前端任务必须走工作流 C（frontend-design skill + web-design-guidelines skill）。修改前必须说明 What/Why/How 并等待用户确认。
- **教训**: "差不多了就可以推进下一步"是用户的预估，不是指令，AI 不要自行推进

---

## EXP-005 | 信息聚合网站设计
- **时间**: 2026-06-18 10:16
- **类别**: 设计
- **结论**: 杂志式编辑风格（装饰元素、低信息密度、大留白）不适合信息聚合网站。信息密度型网站的核心原则：可读性 + 一眼扫全 + 数据关联。
- **设计决策**: 图表在表格下方（信息优先，可视化辅助）；厂商一横排；中文化所有标签

---

## EXP-006 | Playwright MCP 环境
- **时间**: 2026-06-18 09:47
- **类别**: 环境
- **结论**: Playwright MCP 需要 symlink:
  - `chromium_headless_shell-1228` → `chromium_headless_shell-1200`
  - `chromium-1228` → `chromium-1200`
- **路径**: `/Users/LiYuan/Library/Caches/ms-playwright/`

---

## EXP-007 | Playwright 与用户操作冲突
- **时间**: 2026-06-18 16:48
- **类别**: 交互
- **结论**: 用户同时操作浏览器时，Playwright evaluate 返回 undefined。截图和导航不受影响，但 JS 执行需要页面独占。
- **解决方案**: 采集时让用户停止操作，或使用后端方式（curl + Python）

---

## EXP-008 | BFCL 和开源模型覆盖
- **时间**: 2026-06-18 16:21
- **类别**: 数据
- **结论**: BFCL V4 模型偏旧，榜单本身更新慢。Gemma 4 31B 等开源模型未注册到 models 表（属于 Google 厂商但未收录）。开源/免费模型是用户关注重点。
- **行动**: 补充注册开源模型 + 确认 BFCL 是否有新数据

---

## EXP-009 | AA Omniscience 扩展数据
- **时间**: 2026-06-18 16:48
- **类别**: 采集
- **结论**: AA Omniscience 页面有丰富子数据，我们目前只采集了 score_raw、accuracy_pct、hallucination_pct。缺失的有：
  - Model size（模型总参数量，开源+闭源）
  - Token usage（~20 模型，但测的是什么不明确）
  - Cost breakdown（同任务实际消耗对比，极高价值）
  - omniscience_breakdown（按领域/编程语言拆分，6 大领域 42 主题）
  - Score vs Release date（散点图）
  - Software Engineering by Language（不同编程语言归一化表现）
- **JS chunk**: `page-a8826b0f8c0423ac.js` 中有 `omniscience_breakdown` 和 `model_creators` 结构

---

## EXP-010 | AA RSC Payload 全量提取方法论
- **时间**: 2026-06-19 01:15
- **类别**: 采集
- **结论**: AA 网站数据全部嵌入在 Next.js RSC (React Server Components) payload 中，无任何 API 调用。omniscience 页面的 RSC payload 约 8MB，包含**全部 benchmark 数据**（不仅是 omniscience），其他评测页面只加载 200KB 轻量数据。
- **方法论** (可复用于所有 Next.js App Router 网站):
  1. `curl -s -L URL -o page.html` 下载 HTML（3-5秒）
  2. 用正则提取 `self.__next_f.push([1,"..."])` 中的大 script
  3. 多轮 unescape：`raw.replace('\\"', '"').replace('\\n', '\n')`
  4. 用 `"name":"MODEL_NAME","KEY_FIELD":` 定位模型数据
  5. 用花括号匹配 (`extract_json_object`) 提取完整 JSON 对象
  6. `json.loads()` 解析，按厂商关键词过滤
- **速度**: curl 3秒 + Python 解析 0.12秒 = **总计约 3-5 秒/页面**
- **关键发现**: AA omniscience 页面是"全家桶"，一个页面包含：
  - 12 个 benchmark 分数 (GPQA, HLE, IFBench, TerminalBench, τ2, SciCode, AIME, LiveCodeBench, Coding Index, Agentic Index, GDPval, τ-Banking)
  - omniscience_breakdown (6 大领域 + SWE 按编程语言拆分)
  - eval_token_counts (各 benchmark 的 input/output/reasoning token)
  - intelligenceIndexCostPerTask (cost 拆分: input/output/reasoning/cache)
  - evalCost (跑一轮评测的实际花费)
  - timescaleData (速度数据)
  - pricing (定价 + 混合价格 + cache 价格)
  - gdpval_breakdown (Elo + 置信区间)
  - it_bench_breakdown (IT 任务拆分)
- **脚本**: `scripts/extract_aa_omniscience.py`（可重复运行）
- **数据文件**: `data/raw/aa_omniscience_full_2026-06-18.json` (3.1MB, 209 厂商模型)

---

## EXP-011 | AA 评测页面数据分布
- **时间**: 2026-06-19 01:15
- **类别**: 采集
- **结论**: AA 的 16 个评测页面中，只有 omniscience 页面包含完整 RSC payload（8MB），其他页面（terminalbench-hard, gdpval-aa, tau3-banking, hle, gpqa, ifbench, scicode, critpt, apex-agents, itbench 等）都只加载 200KB 轻量数据（模型列表+基础元数据，无 breakdown）。
- **正确 URL**: `/evaluations/omniscience`（非 `/leaderboards/omniscience`，后者 404）
- **playwright_expect_response**: 可捕获网络请求但 AA 不发 API 请求，只有 `/api/auth/get-session` 认证检查
- **采集策略**: 只需采集 omniscience 页面即可获取 AA 全部数据，无需逐个页面采集

---

## EXP-012 | --accent-heatmap 独立变量与透明度
- **时间**: 2026-06-20 00:12
- **类别**: 前端
- **结论**: 矩阵 heatmap 色块在 Apple Light 主题下几乎不可见。根因是 `--accent-soft` 只有 8% 透明度（`rgba(0,102,204,.08)`），在白色背景上色差极小。
- **修复**: 新增 `--accent-heatmap` 变量，与 `--accent-soft` 分离。三个主题透明度：
  - Apple Light: `.35`（白色背景需高透明度）
  - Dark Pro: `.25`（深色背景对比度好）
  - Gold Classic: `.28`（中间值）
- **heatmap CSS**: `background-image: linear-gradient(to right, var(--accent-heatmap) var(--heat-pct,0%), transparent var(--heat-pct,0%))`
- **教训**: accent-soft 用于 hover/标签等微妙提示，8% 够用；heatmap 需要明显色差，必须用独立变量

---

## EXP-013 | CSS 通用类名误匹配
- **时间**: 2026-06-20 00:12
- **类别**: 前端
- **结论**: 全局 `.empty` 选择器（`padding:64px 24px`，用于空状态页面组件）误匹配了矩阵的 `.matrix-cell.empty`，导致 "—" 字符被 64px 上下 padding 撑到单元格底部，看起来像下划线。
- **修复**: 将 `.empty` 改为 `main > .empty`，只匹配直接子级的空状态页面组件，不影响矩阵单元格。
- **教训**: 避免使用 `.empty`、`.active`、`.selected` 等过于通用的类名，容易与子组件冲突。用作用域选择器或加前缀。

---

## EXP-014 | 矩阵单元格垂直居中
- **时间**: 2026-06-20 00:12
- **类别**: 前端
- **结论**: 矩阵 grid 行高 32px，`.matrix-cell` 原来用 `padding:6px 8px` + `text-align:center`，没有垂直居中。在 32px 行高下，文字贴底显示，"—" 看起来像下划线。
- **修复**: 改为 `display:flex; align-items:center; justify-content:center; padding:0 8px`，确保内容垂直水平居中。
- **教训**: 固定行高的 grid 单元格必须用 flex 居中，不要依赖 padding 模拟居中。

---
