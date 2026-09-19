# LLM-INDEX 项目规则与工作流

## 一、核心工作流原则

### 1.1 修改前确认机制
- **每次修改代码前**，必须先说明：
  - 要改什么（具体文件/模块）
  - 为什么改（原因/目标）
  - 怎么改（方案概述）
- **等待用户确认后**再动手执行
- 不擅自安装依赖、不执行破坏性操作

### 1.2 阶段性验证
- 完成一个阶段后**必须验证能跑通**
- 验证通过后才进入下一阶段
- 验证方式：运行测试、手动检查、启动服务测试

### 1.3 渐进式开发
- 先搭建骨架，再填充逻辑
- 先核心功能，再扩展功能
- 先本地验证，再部署上线

### 1.4 交互偏好（2026-06-17 补充）
- **"差不多了就可以推进下一步"是预估不是指令**: 这类话是用户对后续动作的预估，"什么时候差不多"由用户判断，AI 不要自行推进到下一阶段
- **宁愿慢不要反复返工**: 关键决策点停下确认是加分的，不要为了速度跳过确认导致返工
- **只在真正需要决策的点确认**: 不要把全量选项抛给用户，大量不需要确认的内容浪费用户精力

### 1.5 自动化优先原则（2026-06-17 补充）
- **能自动化的不要手工维护**: 模型注册表等应通过 skill 采集 + OpenRouter 发现 + 交叉信源验证自动建立
- **能用 AI 能力处理的不要手工映射**: 显示名→canonical_id 等归因任务应优先用 NLP 能力处理
- **回退策略优先级**: NLP 归因 → 网上查询 → 保留标注人工处理。不要一上来就要求手工映射
- **渐进式确认**: 先用自动化方法处理，处理不了的再向用户确认，不要全量给
- **保留不确定标注**: 实在无法确定的保留 `needs_manual_review: true` 标注，不强行入库

---

## 二、MCP 工具与 Skill 使用规范

### 2.1 核心能力矩阵

| 能力层 | 工具/Skill | 适用场景 | 核心职责 |
|--------|-----------|---------|---------|
| **网页自动化（侦察型）** | `browser_navigate`, `browser_snapshot`, `browser_evaluate` | 页面导航、DOM 结构侦察、JavaScript 渲染数据提取 | 侦察页面结构，定位数据所在 DOM/network |
| **网页自动化（采集/测试型）** | `playwright_navigate`, `playwright_get`, `playwright_evaluate`, `playwright_screenshot`, `playwright_click` | 结构化数据采集、API 调用、页面自动化测试、截图证据保存 | 大规模采集 + 自动化测试 + API 端点验证 |
| **代码搜索与理解** | `search` sub-agent | 理解现有代码结构、定位模块、查找引用关系 | 跨文件代码语义搜索 |
| **数据采集方法论** | `web-data-scout` skill | Benchmark 分数采集、论坛真实使用数据采集、OpenRouter 模型发现 | 按采集方法论完成数据发现 → 采集 → 交叉验证 → 入库 |
| **架构/方案设计** | `brainstorming` skill | 新模块设计、数据流调整、权重模型、系统架构变更 | 引导需求对齐，输出设计方案文档 |
| **前端界面开发** | `frontend-design` skill | Web 组件开发、雷达图看板、模型对比页面、报告展示页 | 高质量前端代码生成 |
| **系统测试** | `dogfood` skill, `webapp-testing` skill | 完整流程走查、bug 发现、交互体验测试 | 系统性测试而非单元测试 |
| **前端质量审查** | `web-design-guidelines` skill | UI 代码质量合规性审查 | 检查前端代码是否符合视觉和交互规范 |

### 2.2 MCP 工具使用规范（采集场景）

**标准采集流程**：
1. **侦察**：先用 `browser_navigate` → `browser_snapshot` 了解页面结构
2. **定位**：用 `browser_evaluate` 评估 JS 渲染的数据位置
3. **采集**：使用 `playwright_get`（API 数据）或 `playwright_evaluate` + `playwright_get_visible_html`（页面数据）
4. **证据**：用 `playwright_screenshot` 保存采集时的页面截图
5. **交叉验证**：同一数据至少 2 个来源通道（API + HTML 或 不同页面）

**工具分工明确**：
- **需要浏览器环境渲染的**：使用 Integrated Browser（`browser_*` 系列）
- **可以直接 API 调用的**：使用 `playwright_get`（JSON API 最快路径）
- **需要自动化测试/多次点击/表单**：使用 MCP Playwright 完整流程

### 2.3 Skill 使用决策树（核心）

```
识别任务特征 → 匹配对应工作流 → 向用户确认 → 执行

任务特征识别关键词：
├─ 「采集/更新/刷新/数据来源/benchmark/分数/排行榜」
│   → 标准工作流 A: 数据采集（web-data-scout + MCP 工具）
├─ 「设计/方案/架构/数据流/权重/模型」
│   → 标准工作流 B: 方案设计（brainstorming）
├─ 「页面/组件/前端/UI/样式/展示/排版/可视化」
│   → 标准工作流 C: 前端开发（frontend-design + web-design-guidelines）
├─ 「测试/验证/走查/dogfood/bug/可用性/交互体验」
│   → 标准工作流 D: 系统测试（dogfood + webapp-testing）
├─ 「搜索/哪里有/代码结构/如何理解/定位」
│   → 使用 search sub-agent
└─ 不确定 → 明确询问用户偏好的工作流方式
```

### 2.4 工作流自动检测与确认机制

**核心原则**：当任务特征匹配某个标准工作流时，**先向用户明确确认使用该工作流**，确认后再自动执行。不要跳过确认直接执行。

**标准话术（当识别到任务特征时）**：

> 我识别到这个任务符合【XX 工作流】的特征。
> 计划执行步骤：
> 1. ...
> 2. ...
> 3. ...
> 预计调用的 Skill/MCP 工具：[skill-name / mcp-tool-name]
> 是否按此工作流推进？

**兜底行为**：当不确定适用哪个工作流时 → **向用户明确询问**工作流偏好，不要猜测。

### 2.5 子 Agent 调用规范（双向约束）

**核心原则**：主 Agent（我自己）和子 Agent 是契约关系。主 Agent 派活时必须保证指令与约束一致，子 Agent 执行时必须遵守约束。约束对双方都有约束力。

#### A. 主 Agent 自检清单（派活前必须逐项检查）

主 Agent 在调用 `Task` 工具启动子 Agent 前，**必须逐项自检**：

1. **环境上下文是否完整传递**：子 Agent 不知道主 Agent 的环境，必须显式传递（见下方 B 节清单）
2. **工具名称是否写全**：不能只写"用 Playwright"，必须写 `run_mcp(server_name="mcp_Playwright", tool_name="playwright_navigate")`；不能只写"用浏览器"，必须写明是 `browser_navigate` 还是 `playwright_navigate`
3. **任务是否与约束矛盾**：如果约束了"不得删除文件"，任务中就不能含"清理临时文件"——除非显式授权"本任务授权删除以下文件：xxx"
4. **指令是否模糊**：步骤必须是具体可执行的，不能留解读空间。"测试页面"是模糊的，"用 playwright_navigate 打开 http://localhost:8001，用 playwright_screenshot 截图"是具体的
5. **返回格式是否明确**：必须告诉子 Agent 期望的返回内容（如"返回文件行数和末尾 5 行"）

**如果自检不通过 → 不得调用子 Agent，先修正 query 内容。**

#### B. 子 Agent 必传上下文清单

每次调用 `Task` 工具，`query` 参数中**必须包含**以下环境信息块：

```
【环境上下文】
- 项目路径: /Users/LiYuan/apps/llm-index
- 浏览器二进制: ~/Library/Caches/ms-playwright/ (chromium-1223 + chromium-1228)
- 系统 Chrome: /Applications/Google Chrome.app/ (v149)
- MCP Playwright: 通过 run_mcp(server_name="mcp_Playwright", tool_name="playwright_*") 调用
- 环境变量: PLAYWRIGHT_BROWSERS_PATH 已设置，PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
- 可用端口: 8001+ (8000 可能被占用)

【工具使用规范】
- 浏览器操作: run_mcp(server_name="mcp_Playwright", tool_name="playwright_*")
- 文件读取: Read 工具（禁止 cat/head/tail）
- 文件编辑: Edit/Write 工具（禁止 sed/awk）
- 文件搜索: Grep/Glob 工具（禁止 find/grep 命令）
- 命令执行: 仅用于启动服务、系统操作

【禁止行为】
- 不得下载新的浏览器或依赖（环境已配置好）
- 不得自行编写 CDP/WebSocket 通信代码（已有 MCP 工具）
- 不得安装 npm/pip 包（除非 query 中显式授权）
- 不得删除文件（除非 query 中显式授权删除指定文件）
- 不得自由发挥，只做 query 中指定的步骤
```

#### C. 子 Agent 任务模板

```
【任务】<一句话描述具体目标>

【环境上下文】<上方 B 节的环境信息块>

【执行步骤】
1. <具体步骤，含工具名和参数>
2. <具体步骤>
3. <具体步骤>

【授权操作】<如果需要删除/安装，在此显式列出授权的具体文件/包名；无则写"无">

【返回要求】<期望返回的内容格式，如"返回文件行数 + 末尾 5 行"或"返回截图路径">
```

#### D. 冲突处理规则

| 情况 | 子 Agent 行为 | 主 Agent 责任 |
|------|-------------|-------------|
| 任务步骤需要删除文件，但未在【授权操作】中列出 | **停止执行，返回询问** | 主 Agent 派活前未自检，属于主 Agent 失职 |
| 任务步骤需要安装依赖，但禁止行为中写了"不得安装" | **停止执行，返回询问** | 主 Agent 应在【授权操作】中显式授权 |
| 工具名称在 query 中不明确 | **按环境上下文中的工具规范选择最接近的**，并在返回中说明用了哪个 | 主 Agent 应在步骤中写全工具名 |
| 执行中发现环境与上下文不符 | **停止执行，返回差异说明** | 主 Agent 传递了过时的环境信息 |

#### E. 何时使用子 Agent

| 场景 | 使用子 Agent | 原因 |
|------|-------------|------|
| 代码块过大需要分块写入（主线程输出会超限） | ✅ | 避免截断 |
| 并行探索多个独立方案 | ✅ | 提高效率 |
| 简单单文件编辑 | ❌ | 直接用 Edit |
| 需要多轮交互的调试 | ❌ | 子 Agent 无法交互 |
| 需要调用 MCP 工具的浏览器操作 | ❌ | 主 Agent 直接调 run_mcp，子 Agent 无法访问主 Agent 的 MCP 连接 |

**重要提醒**：子 Agent **无法访问主 Agent 的 MCP 连接**。如果任务需要调用 `mcp_Playwright` 等工具，主 Agent 应该自己做，不要派给子 Agent。子 Agent 主要用于：文件读写、代码生成、命令执行等不依赖 MCP 连接的任务。

---

## 三、四大标准工作流

### 工作流 A：数据采集（web-data-scout + MCP 工具）

**触发关键词**：采集、更新、刷新、数据来源、benchmark、分数、排行榜、token 消耗、OpenRouter

**执行步骤**：
1. **数据源发现**（web-data-scout Phase 1）— endpoint pool + web search + Playwright 侦察
2. **数据采集**（web-data-scout Phase 2）— 结构化数据 + 论坛数据双通道
3. **交叉验证**（web-data-scout Phase 2.5 for Agent Annotation + Phase F4 for Forum）— 多来源比对 + 合理性检查
4. **数据入库** — 写入 `data/raw/*.yaml`，再入 observations 表
5. **报告汇总** — Collection Report 输出，包含数据点数量、可信度、缺失项

**严格约束**：
- 官方 benchmark 数据：API/HTML/official report 通道，禁止图片 OCR
- 用户分享截图数据：人工读取，标 `needs_manual_review: true`
- 每个数据点必须有 `source_url` 和 `collected_at`
- 数据不确定时存 `null`，不要估算

**调用的工具**：web-data-scout skill + playwright_get + browser_navigate + browser_snapshot + browser_evaluate + search（验证模型存在）

---

### 工作流 B：方案设计（brainstorming）

**触发关键词**：设计、方案、架构、数据流、权重、模型、重构、重新设计

**执行步骤**：
1. **需求探索** — 明确目标、范围、约束
2. **brainstorming skill 讨论** — 引导设计思考，产出多个方案对比
3. **设计文档输出** — 模块结构、数据流、接口定义、选型理由
4. **用户确认** — 等待用户确认方案后再编码
5. **编码实现**（确认后）— 按设计方案推进

---

### 工作流 C：前端开发（frontend-design + web-design-guidelines）

**触发关键词**：页面、组件、前端、UI、样式、展示、排版、可视化、雷达图、表格、交互

**执行步骤**：
1. **需求明确** — 功能、交互、视觉风格
2. **frontend-design skill 生成代码**
3. **本地预览验证** — Playwright 打开页面，截图确认
4. **web-design-guidelines 质量审查** — 检查 UI 是否符合规范
5. **用户确认效果**
6. **集成到项目**

---

### 工作流 D：系统测试（dogfood + webapp-testing）

**触发关键词**：测试、验证、走查、dogfood、bug、可用性、交互体验

**执行步骤**：
1. **测试计划** — 明确测试范围、关键路径
2. **dogfood skill 完整流程走查** — 系统性探索测试
3. **webapp-testing skill 自动化测试** — Playwright 自动化交互
4. **问题报告** — 可复现步骤 + 截图证据
5. **修复 + 回归验证**

---

## 四、代码质量保障

### 4.1 代码质量检查

**触发场景**：
- 完成一个模块开发
- 准备提交代码
- 代码审查

**工作流程**：
1. 运行 lint 检查（ruff/black）
2. 运行类型检查（mypy）
3. 运行单元测试（pytest）
4. 手动验证功能
5. 用户确认代码质量

**验证命令**：
```bash
# Lint 检查
ruff check src/

# 类型检查
mypy src/

# 单元测试
pytest tests/ -v

# 启动服务测试
uvicorn src.main:app --reload
```

---

## 五、编码规范

### 5.1 Python 代码规范
- 遵循 PEP 8
- 使用 ruff 做 lint
- 模块导入顺序：标准库 → 第三方库 → 项目内部模块
- 所有公共函数/类需要 docstring
- 类型注解：尽量使用 typing 模块

### 5.2 文件组织规范
```
src/
├── module_name/
│   ├── __init__.py          # 模块导出
│   ├── core.py              # 核心逻辑
│   ├── utils.py             # 工具函数
│   └── types.py             # 类型定义
```

### 5.3 命名规范
- 文件名：snake_case
- 类名：PascalCase
- 函数/变量：snake_case
- 常量：UPPER_SNAKE_CASE
- 配置文件：kebab-case 或 snake_case

---

## 六、阶段验证清单

> 维度体系以 config/benchmarks.yaml 为唯一准 (v4, 2026-06-19)
> 5 维评分: factual / workflow / engineering / cost / preference
> preference 无数据时权重自动重新分配
> accessibility 为标签，不参与评分
> 模型 ID 统一用 OpenRouter 完整 ID: provider/model-slug
> 九家厂商封闭范围: OpenAI/Anthropic/Google/DeepSeek/GLM/Kimi/Qwen/MiMo/MiniMax

### Phase 1: 数据库与基础采集
- [x] 数据库表创建成功 (Model / BenchmarkEval / ModelAlias)
- [x] 能正常插入/查询数据 (209 模型 + 2267 评测 + 498 别名)
- [x] 采集脚本能运行 (extract_aa_omniscience.py + ingest_aa_omniscience.py)
- [x] 维度定义一致 (benchmarks.yaml = settings.yaml = 前端 BENCH_GROUPS)

### Phase 2: 计算与权重逻辑
- [x] 归一化逻辑正确 (5 维, cost 反向归一化)
- [x] 权重配置生效 (默认 5 维, 总和=1.0, 用户自定义方案)
- [x] 综合指数计算正确 (5 维加权, preference 无数据时自动重分配)
- [x] 后端 compute 层适配 5 维 (weight_manager/normalizer/index_calculator/radar_data_builder/registry/routes/schemas)

### Phase 3: 数据入库
- [x] AA Omniscience 数据入库 (209 模型, 15 benchmark, 2267 数据点)
- [x] 九家厂商模型注册到 models 表 (OpenRouter 完整 ID)
- [x] 模型别名解析正确 (aliases.yaml)
- [x] LMArena 数据入库 (第 5 维度 preference, 71 条 Elo 评分)

### Phase 4: 前端看板
- [x] 排行榜视图 (5 维度切换 + 15 benchmark + 下钻面板)
- [x] 矩阵总览 (209 模型 × 15 benchmark heatmap)
- [x] 对比视图 (多模型并排 + 权重实时重算)
- [x] 我的方案 (用户自定义权重 + localStorage 持久化)
- [x] 三主题 (Apple Light / Gold Classic / Dark Pro)
- [ ] 前端微调 (信息密度/交互细节)

### Phase 5: 部署上线
- [ ] CI/CD 流水线配置完成
- [ ] 自动采集任务正常运行
- [ ] 监控告警配置完成
- [ ] 生产环境稳定运行

---

## 七、Skill 决策树（精简版）

```
新任务进入
   ↓
关键词匹配 → 识别工作流类型
   │
   ├─ 匹配工作流 A/B/C/D → 向用户确认使用该工作流 → 执行
   └─ 不确定 → 明确询问用户
```

**决策优先级**：
1. 首先匹配关键词（见 2.3 表）
2. 匹配成功 → 输出工作流计划 + 询问确认
3. 匹配失败 → 明确询问用户意图，不要猜测
4. 编码任务 → 直接编码（无需 skill，但需要修改前说明）

---

## 八、沟通规范

### 8.1 修改前必须说明
```markdown
## 修改计划

**要改什么：**
- 文件：src/storage/db_manager.py
- 模块：DatabaseManager 类

**为什么改：**
- 当前使用 PostgreSQL，需要切换到 SQLite
- 原因：项目数据量不大，SQLite 更轻量

**怎么改：**
- 修改默认数据库 URL 为 sqlite:///data/llm_index.db
- 添加 SQLite 特有的连接参数
- 移除 PostgreSQL 相关依赖

**影响范围：**
- 仅影响数据库连接层
- 不影响业务逻辑

**验证方式：**
- 运行 seed_db.py 验证表创建
- 运行单元测试验证查询功能
```

### 8.2 工作流确认话术（关键新增）
```markdown
## 工作流识别与确认

我识别到这个任务符合【工作流 X：XXX】的特征。

**匹配依据**：
- 关键词：xxx
- 任务类型：xxx

**计划执行步骤**：
1. xxx
2. xxx
3. xxx

**预计调用的 Skill / MCP 工具**：
- [skill-name] skill
- [mcp-tool-name]

是否按此工作流推进？
```

### 8.3 阶段完成后汇报
```markdown
## 阶段完成报告

**已完成：**
- Phase 1: 数据库与基础采集

**验证结果：**
- ✅ 数据库表创建成功
- ✅ 能正常插入/查询数据
- ✅ 采集脚本能运行
- ✅ 单元测试通过

**下一步：**
- 进入 Phase 2: 计算与权重逻辑
- 预计使用 brainstorming skill 设计权重模型

**需要确认：**
- 是否同意进入下一阶段？
```

---

## 九、依赖管理规范

### 9.1 安装前确认
- 列出需要安装的依赖清单
- 说明每个依赖的用途
- 等待用户确认后再安装

### 9.2 版本锁定
- 使用 requirements.txt 锁定版本
- 定期更新依赖（需要用户确认）

---

## 十、文档维护规范

### 10.1 代码注释
- 复杂逻辑必须添加注释
- 公共 API 必须有 docstring
- 配置项必须有说明注释

### 10.2 项目文档
- README.md：项目概述、快速开始
- docs/：详细设计文档
- CHANGELOG.md：版本变更记录

---

## 十一、总结

本项目的核心工作流是：
1. **任务特征识别**：通过关键词匹配标准工作流（A/B/C/D）
2. **工作流确认**：向用户明确确认后再执行，不猜测
3. **Skill + MCP 工具协同**：按工作流定义的步骤调用相应能力
4. **设计先行**：涉及方案设计时使用 brainstorming skill
5. **阶段性验证**：每阶段完成后必须验证
6. **质量保障**：lint + test + typecheck + web-design-guidelines

遵循这个工作流，确保项目质量可控、进度可见、决策透明。

---

## 十二、知识持久化（Knowledge Persistence）

### 12.1 为什么需要持久化

- 采集/搜索类工作的结论容易被新会话遗忘，导致重复踩坑
- 用户交互中的对齐决策需要跨会话保留
- 经过验证的方法论应转化为可复用的 Skill

### 12.2 持久化结构

| 文件 | 用途 | 格式 |
|------|------|------|
| `docs/experience_index.md` | 索引表 — 快速总览 | 表格：时间 \| ID \| 类别 \| 一句话摘要 |
| `docs/experience_log.md` | 总表 — 追加式详细记录 | 按 ID 分段：结论 + 踩坑 + 行动 |
| `project_memory.md` (Lessons Learned) | 核心经验摘要 | 列表式 |
| `.trae/skills/` 目录 | 成熟方法论 → Skill | SKILL.md 格式 |

### 12.3 写入时机

**必须写入的场景**（每次完成后立即执行）：
- ✅ 数据源侦察完成（发现/未发现 API、数据格式、反爬机制）
- ✅ 踩坑记录（环境问题、数据结构差异、工具限制）
- ✅ 用户对齐的决策（主题选择、布局方案、优先级排序）
- ✅ 方法论验证通过（采集流程可行、数据可用）

**写入方式**：
1. 先写 `experience_log.md` 总表（追加新条目，ID 自增）
2. 再更新 `experience_index.md` 索引表（追加一行）
3. 最后更新 `project_memory.md` Lessons Learned（关键条目）

### 12.4 ID 编号规则

- 格式：`EXP-NNN`（N 为数字，从 001 开始递增）
- 类别枚举：`采集` / `数据` / `前端` / `设计` / `工作流` / `环境` / `交互`
- 时间格式：`YYYY-MM-DD HH:MM`

### 12.5 方法论→Skill 转化条件

当以下条件满足时，将方法论转化为 Skill：
- 至少经过 2 次实际验证
- 覆盖 ≥80% 的常见场景
- 有明确的输入输出规范
- 示例：`web-data-scout` skill 已满足此条件

### 12.6 新会话启动时的读取顺序

1. 读 `project_rules.md`（工作流规则）
2. 读 `project_memory.md`（硬约束 + 经验摘要）
3. 读 `docs/experience_index.md`（快速总览历史经验）
4. 按需读 `docs/experience_log.md`（某 ID 的详细信息）
