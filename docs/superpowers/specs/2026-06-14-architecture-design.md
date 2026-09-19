# LLM-INDEX 架构设计规格文档

**日期**: 2026-06-14
**状态**: 待用户审阅确认

---

## 一、项目定位

LLM-INDEX 是一个**多维度动态加权评测系统**，借鉴金融市场综合指数的方法论，持续跟踪和量化 LLM 基础模型与 AI Agent 框架的综合表现。通过雷达图直观呈现各模型的六维能力轮廓，为用户技术选型提供数据驱动的决策参考。

**MVP 目标**: 生产就绪的完整闭环——自动采集 + 计算 + 前端展示 + 定时更新。

---

## 二、六维能力矩阵

### 2.1 维度定义

| 维度 | 英文标识 | 默认权重 | 定义 | 数据源 | 子指标 |
|------|---------|---------|------|--------|--------|
| 编程能力 | `coding` | 20% | 代码正确性、健壮性、合理性 | SWE-Bench Pro, CursorBench, HumanEval | SWE-Bench Pro 50%, CursorBench 30%, HumanEval 20% |
| 工程能力 | `engineering` | 20% | planning + tool_use 合并：任务分解、多步推理、工具调用、复杂任务完成度 | AgentBench, LiveCodeBench, GPQA, ToolBench | AgentBench 35%, LiveCodeBench 30%, ToolBench 20%, GPQA 15% |
| 事实准确性 | `factual_accuracy` | 15% | 知识储备 + 幻觉率 + 专业领域准确性 | MMLU-Pro, TruthfulQA, HealthBench | MMLU-Pro 40%, TruthfulQA 30%, HealthBench 30% |
| 成本效率 | `cost` | 15% | API 价格 + 等效月费（价格越低得分越高） | OpenRouter API + 各厂商官方定价 | API 标准化价格 60%, 等效月费 40% |
| 可用性 | `accessibility` | 15% | 国内访问友好度、封号风险、稳定性 | 手动评估 + 社区反馈 | 国内直连可用性 50%, 封号风险 30%, 服务稳定性 20% |
| 真实工作流 | `workflow` | 15% | 实际应用场景表现、人类偏好 | Chatbot Arena, GAIA | Chatbot Arena 60%, GAIA 40% |

**维度演进说明**:
- `engineering` 由原 `planning` + `tool_use` 合并，因两者在真实项目中高度耦合
- `cost` 和 `accessibility` 独立为两个维度，因两者都是"门槛型"指标，用户关注度极高
- `factual_accuracy` 由原 `knowledge` 扩展，纳入幻觉率评测

### 2.2 事实准确性维度详细说明

```
factual_accuracy = knowledge_score × 0.4 + truthfulness_score × 0.3 + domain_score × 0.3

其中：
- knowledge_score: MMLU-Pro 知识评测（0-100）
- truthfulness_score: TruthfulQA 幻觉控制评测（0-100）
- domain_score: HealthBench 等垂直领域评测（0-100）
```

**关键特征**:
- Claude 系列在幻觉控制上表现最好，不确定时拒绝回答率高达 70%
- GPT 系列回答成功率高，但幻觉率也高
- 医疗法律等严肃场景对幻觉率要求极高

### 2.3 二级权重自定义

每个维度的子指标权重支持用户自定义调整：
- 默认使用预设权重
- 用户可进入二级调整面板，拖动子指标权重滑块
- 同样采用等比缩放机制，保证总和为 100%

**示例**: 严肃场景用户可将 HealthBench（专业领域）权重从 30% 调至 50%

---

## 三、权重体系

### 3.1 一级权重预设

| 预设名称 | coding | engineering | factual_accuracy | cost | accessibility | workflow |
|---------|--------|-------------|-----------------|------|---------------|----------|
| 通用开发者 | 25% | 20% | 15% | 15% | 15% | 10% |
| 企业 IT | 15% | 15% | 20% | 20% | 15% | 15% |
| 研究/竞赛 | 25% | 25% | 15% | 10% | 10% | 15% |
| 严肃场景 | 10% | 15% | 35% | 15% | 10% | 15% |
| 国内优先 | 20% | 20% | 15% | 15% | 25% | 5% |

### 3.2 用户自定义权重

- 用户可自由拖动一级权重滑块
- 采用**等比缩放机制**: 拉高某维度时，其他维度按当前比例自动缩放
- 支持**锁定维度**: 锁定的维度不参与自动缩放
- 底部实时显示总和，始终为 100%
- 数值显示一位小数，提供"全部取整"按钮
- 支持保存为自定义预设

### 3.3 综合指数计算公式

```
IDX_model = Σ w_i × S_i × scale_factor(epoch)

其中：
- w_i: 第 i 个维度的权重（各维度权重之和为 1）
- S_i: 该模型在第 i 个维度的归一化得分（0-100）
- scale_factor(epoch): 动态缩放函数，消除不同轮次基准更新的口径变化
```

---

## 四、模型清单

### 4.1 MVP 阶段（大模型）

| 厂商 | 旗舰模型 | 经济/快速模型 |
|------|---------|-------------|
| OpenAI | GPT-5.x | GPT-4o-mini / GPT-5-flash |
| Anthropic | Claude Opus 4.x | Claude Sonnet 4.x / Haiku |
| Google | Gemini 2.5 Pro | Gemini 2.5 Flash |
| DeepSeek | DeepSeek V4 | DeepSeek V4-Flash |
| Alibaba | Qwen 3 | Qwen 3-Turbo |
| Moonshot | Kimi K2.6 | — |
| Zhipu | GLM-4 | GLM-4-Flash |
| Xiaomi | MiMo | — |
| MiniMax | MiniMax-Text | — |

**后续扩展**: Grok (xAI)、Llama (Meta)、Mistral 等暂不纳入 MVP。

### 4.2 Agent 清单（后续迭代）

| 类型 | 产品 |
|------|------|
| IDE 型 | Cursor, Windsurf, Trae |
| CLI/TUI 型 | Claude Code CLI, Codex CLI |
| Desktop 型 | 待确认 |
| OpenCode 型 | Aider, Cline, Hermes, 小龙虾 |
| 通用 Agent | ChatGPT, Claude.ai, Gemini |

---

## 五、评测基准数据源

### 5.1 基准采集方式

| 数据源 | 网址 | 采集方式 | 数据格式 | 更新频率 |
|--------|------|---------|---------|---------|
| SWE-Bench Pro | scale.com/leaderboard | Playwright 无头浏览器 | 排行榜表格 | 按发布频率 |
| CursorBench | 待确认 | Playwright 或 API | 待确认 | 按发布频率 |
| TruthfulQA | HuggingFace/论文 | 网页抓取 | JSON/表格 | 低频（静态数据） |
| MMLU-Pro | HuggingFace Spaces | API 或网页抓取 | 排行榜 JSON | 按发布频率 |
| Chatbot Arena | lmsys.org | 网页/API | Elo 评分 | 持续更新 |
| GAIA | HuggingFace | 网页抓取 | 排行榜 JSON | 按发布频率 |

**采集工具链**:
- Playwright（**已全局安装**）+ 无头浏览器：用于 JS 渲染的排行榜页面
- httpx：用于 REST API 调用
- BeautifulSoup/lxml：用于 HTML 解析

**Playwright 环境配置**:

浏览器路径（来自 `~/.cache/puppeteer`，已验证可用）：
```bash
# 完整版 Chrome for Testing（推荐用于可视化调试）
/Users/LiYuan/.cache/puppeteer/chrome/mac-148.0.7778.97/chrome-mac-x64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing

# 精简版 headless shell（推荐用于 CI/自动化）
/Users/LiYuan/.cache/puppeteer/chrome-headless-shell/mac-149.0.7827.22/chrome-headless-shell-mac-x64/chrome-headless-shell
```

**MCP 配置**:
- **Trae IDE**: `~/Library/Application Support/Trae CN/User/mcp.json`
- **Trae Work/SOLO**: 设置 → MCP 配置
- **已配置**: playwright, fetch, sequential-thinking
- **状态**: Playwright MCP 已在 Trae Work 中安装，待验证是否可用

使用示例（Python 直接调用）：
```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=False,  # 可视化调试用 False，CI 用 True
        executable_path='/Users/LiYuan/.cache/puppeteer/chrome/mac-148.0.7778.97/chrome-mac-x64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing'
    )
    page = browser.new_page()
    page.goto('https://example.com')
    # 采集逻辑...
    browser.close()
```

**已验证**：两个浏览器路径均可正常启动并访问网页（2026-06-14 测试通过）。

**注意**: 数据采集阶段需要单独做独立测试，确认每个数据源的实际采集方式和数据质量。

### 5.2 价格数据采集

**标准化对比（OpenRouter API）**:
- 采集 API 端点: `https://openrouter.ai/api/v1/models`
- 数据: 输入/输出 token 单价
- 所有模型统一标准，直接对比

**等效月费计算**:
- 需要建立**经验库/模板库**，根据项目类型估算 token 消耗
- 项目类型分类: 测试类、Demo 类、真实生产环境等
- 数据来源: 公开的使用数据、社区报告，交叉验证后生成本地经验库
- 用户可提供准确的日均 token 消耗/调用次数，系统据此推荐最优方案

**等效月费计算逻辑**:
```
等效月费 = f(项目类型, 日均调用量, 模型选择, 订阅计划)

用户输入选项:
- 项目类型: 测试/Demo/生产
- 使用强度: 轻度/中度/重度
- 自定义: 日均 token 消耗、调用次数

系统输出:
- 各模型等效月费对比
- 推荐最优方案
```

---

## 六、技术栈

### 6.1 前端

| 技术 | 用途 | 理由 |
|------|------|------|
| Vue 3 | 前端框架 | 响应式系统适合滑块联动雷达图场景 |
| Vite | 构建工具 | 冷启动快，HMR 即时，Vue 3 官方推荐 |
| ECharts | 图表库 | 雷达图原生支持多系列叠加、动画、tooltip |
| Tailwind CSS | 样式 | 适合自定义 Dashboard 暗色主题风格 |

### 6.2 后端

| 技术 | 用途 | 理由 |
|------|------|------|
| Python 3.12 | 语言 | 用户环境已安装 |
| FastAPI | Web 框架 | 异步支持好，自带 Swagger 文档 |
| SQLAlchemy | ORM | 已有骨架代码 |
| SQLite | 数据库 | 数据量不大，轻量无需额外安装 |
| APScheduler | 定时任务 | 日/周自动采集 |
| Playwright | 网页采集 | 已安装，用于 JS 渲染页面 |
| httpx | HTTP 客户端 | 异步支持好 |

### 6.3 部署

- **MVP 阶段**: 本地开发，监听 `0.0.0.0`，不硬编码 localhost
- **后续**: 云部署，支持局域网共享
- **配置**: 所有端口/地址通过配置文件管理，不硬编码

---

## 七、功能模块

### 7.1 后端模块

| 模块 | 功能 | 优先级 | 状态 |
|------|------|--------|------|
| 数据采集（基准） | 从基准网站采集评分数据 | P0 | 骨架已有 |
| 数据采集（价格） | 从 OpenRouter 采集实时价格 | P0 | 骨架已有 |
| 归一化计算 | 将原始分数归一化到 0-100 | P0 | 骨架已有 |
| 综合指数计算 | 加权求和生成指数 | P0 | 骨架已有 |
| 权重管理 | 预设 + 用户自定义权重 | P0 | 骨架已有 |
| 雷达图数据构建 | 组装前端需要的 JSON 结构 | P0 | 骨架已有 |
| 定时任务 | 自动采集 | P2 | 待开发（部署阶段） |
| 经验库/模板库 | 项目类型 token 消耗估算 | P1 | 待开发 |
| 报告导出 | Markdown/PDF 报告 | P2 | 待开发 |

### 7.2 前端页面（全部纳入 MVP）

| 页面 | 功能 | 优先级 |
|------|------|--------|
| 主页（雷达图） | 多模型雷达图对比 + 权重调整面板 + 维度详情 | P0 |
| 排名页 | 综合指数排名列表 + 趋势变化 | P0 |
| 模型详情页 | 单模型各维度详细得分 + 子指标拆解 | P0 |
| 设置页 | 预设管理 + 自定义预设保存 | P1 |

### 7.3 前端交互设计

**维度信息面板（点击维度名称/ⓘ 图标触发）**:
- 能力定义说明
- 评分标准公式
- 数据来源列表
- 子指标权重自定义调整（二级权重）

**一级权重调整面板**:
- 预设选择下拉框
- 6 个维度滑块（coding, engineering, factual_accuracy, cost, accessibility, workflow）
- 锁定/解锁维度功能
- 总和实时显示（始终 100%）
- 恢复默认 / 全部取整 / 保存为预设

**基准模型选择器**:
- 用户可选择一个熟悉的模型作为"锚点"，用于快速对比
- 默认基准模型：DeepSeek V4（或当前调用量排名第一的模型）
- 雷达图中基准模型高亮显示（不同颜色/线型）
- 其他模型与基准模型的差异用百分比显示（如"比基准高 15%"）
- 支持用户自定义指定任意模型为基准

**等比缩放算法**:
```
用户拉高维度 A 从 w_a 到 w_a'（增量 Δ）
→ 剩余未锁定维度按当前比例分配 (100% - w_a')
→ 每个未锁定维度新值 = 当前值 × (100% - w_a') / (100% - w_a)
```

---

## 八、数据采集频率

| 数据类型 | 频率 | 说明 |
|---------|------|------|
| 基准测试分数 | 按发布频率 | 各基准发布时间不同 |
| 价格数据 | 实时 | 价格变动频繁 |
| Chatbot Arena | 每周 | Elo 评分持续变化 |

---

## 九、项目目录结构

```
llm-index/
├── .trae/rules/              # 项目规则与工作流
├── config/                   # 配置文件
│   ├── settings.yaml         # 权重配置
│   ├── data_sources.yaml     # 数据源配置
│   └── models_list.yaml      # 模型清单
├── frontend/                 # Vue 3 前端项目（待创建）
│   ├── src/
│   │   ├── components/       # 组件（雷达图、权重面板等）
│   │   ├── views/            # 页面（主页、排名页、详情页）
│   │   ├── stores/           # Pinia 状态管理
│   │   └── api/              # API 调用封装
│   └── ...
├── src/                      # Python 后端
│   ├── ingester/             # 数据采集模块
│   ├── compute/              # 计算与权重模块
│   ├── storage/              # 数据库交互模块
│   ├── api/                  # API 接口层
│   └── dashboard/            # 可视化数据准备
├── scripts/                  # 运维脚本
├── tests/                    # 单元测试
├── data/                     # 数据存储（SQLite + 原始缓存）
└── docs/                     # 设计文档
```

---

## 十、Skill 使用规划

| 阶段 | 使用 Skill | 说明 |
|------|-----------|------|
| 架构设计 | `brainstorming` | ✅ 当前阶段 |
| 前端开发 | `frontend-design` | 雷达图看板、权重面板等组件 |
| 完整前端站点 | `web-dev` | 如需从零搭建 Vue 项目 |
| 自定义采集流程 | `skill-creator` | 创建自动化采集 Skill |
| 代码质量 | lint + test + typecheck | 每阶段完成后验证 |

---

## 十一、待确认事项

- [ ] Playwright + 浏览器本地路径（用户后续提供）
- [ ] CursorBench 公开排行榜地址和数据格式
- [ ] 国内模型具体版本确认（Qwen 3、Kimi K2.6 等的最新可用版本）
- [ ] Agent 具体产品清单（Desktop 型、小龙虾等）
