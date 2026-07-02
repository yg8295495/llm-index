# LLM-INDEX 项目导航

> 本文件为项目级导航，叠加全局 `~/.agent-shared/AGENTS.md` 的基础配置。
> 先读全局，再读本文件，项目配置优先。

---

## 一、全局配置引用

- **核心铁律**：读取 `~/.agent-shared/rules/core-rules.md`
- **网络采集规范**：读取 `~/.agent-shared/rules/web-research-rules.md`
- **角色定义**：读取 `~/.agent-shared/roles/` 下对应角色文件
- **通用 Skills**：读取 `~/.agent-shared/skills/` 下对应 skill

---

## 二、项目目录结构

```
llm-index/
├── AGENTS.md                       # 你正在读的文件
├── .agent/                         # 项目 agent 配置（仅项目特有的）
│   ├── memory/                     # 项目记忆
│   │   ├── memory.md               # 摘要索引
│   │   ├── EXP-001-*.md            # 详细记录
│   │   └── snapshots/              # 快照
│   └── skills/                     # 项目特有 skills（如有）
├── src/                            # 源代码
├── data/                           # 数据
│   ├── raw/                        # 原始采集数据
│   ├── raw_agent/
│   ├── raw_bench/
│   └── raw_pricing/
├── docs/                           # 文档
│   ├── experience_index.md         # 旧格式，逐步迁移到 .agent/memory/
│   └── experience_log.md           # 旧格式
├── tests/                          # 测试
└── config/                         # 配置
```

---

## 三、角色导航

### 3.1 数据采集
- **触发词**：采集、抓取、爬取、数据来源、入库、刷新、benchmark、分数、排行榜
- **角色定义**：`~/.agent-shared/roles/role-data-collector.md`
- **工具**：web-data-scout skill + Playwright MCP + browser 工具
- **数据路径**：`data/raw/` 存原始数据，入库需用户确认

**采集标准工作流**：
1. 数据源发现 — endpoint pool + web search + Playwright 侦察
2. 数据采集 — 结构化数据 + 论坛数据双通道
3. 交叉验证 — 多来源比对 + 合理性检查
4. 数据入库 — 写入 `data/raw/*.yaml`，再入数据库
5. 报告汇总 — Collection Report 输出

### 3.2 网络调研
- **触发词**：调研、搜索、查一下、了解、找找、看看、竞品分析
- **角色定义**：`~/.agent-shared/roles/role-web-researcher.md`
- **工具优先级**：Web search → Web fetch → Playwright MCP → Agent Browser

### 3.3 方案设计
- **触发词**：设计、方案、架构、数据流、权重、模型、重构
- **工作流**：需求对齐 → 多方案对比 → 用户确认 → 进入实现
- **建议**：此阶段手动选择更强的模型

### 3.4 代码开发
- **触发词**：写代码、实现、开发、创建功能、重构
- **角色定义**：`~/.agent-shared/roles/role-code-developer.md`
- **流程**：计划确认 → TDD → review → commit → report
- **修改前**：必须说明 What/Why/How 并等确认

### 3.5 前端开发
- **触发词**：页面、组件、前端、UI、样式、展示、可视化
- **角色定义**：`~/.agent-shared/roles/role-designer.md`
- **工作流**：需求明确 → 设计方案 → 代码实现 → 预览验证 → 质量审查

### 3.6 测试与调试
- **触发词**：报错、bug、问题、异常、调试、测试、不工作
- **角色定义**：`~/.agent-shared/roles/role-debugger.md`

---

## 四、MCP 工具使用规范

### 工具分工
- **浏览器环境渲染**：Integrated Browser（`browser_*` 系列）
- **直接 API 调用**：`playwright_get`（JSON API 最快路径）
- **自动化测试/多次点击/表单**：MCP Playwright 完整流程

### 标准采集流程
1. **侦察**：`browser_navigate` → `browser_snapshot` 了解页面结构
2. **定位**：`browser_evaluate` 评估 JS 渲染的数据位置
3. **采集**：`playwright_get`（API）或 `playwright_evaluate`（页面数据）
4. **证据**：`playwright_screenshot` 保存截图
5. **交叉验证**：同一数据至少 2 个来源通道

---

## 五、Memory 机制

### 5.1 目录
```
.agent/memory/
├── memory.md               # 摘要索引
├── EXP-001-20260625.md     # 详细记录
└── snapshots/              # 快照
```

### 5.2 写入时机
- 数据源侦察完成
- 踩坑记录
- 用户对齐的决策
- 方法论验证通过
- 用户说"保存一下"时

### 5.3 格式参考
- 摘要索引：`~/.agent-shared/memory/template/memory-template.md`
- 详细记录：`~/.agent-shared/memory/template/exp-template.md`
- 快照：`~/.agent-shared/memory/template/snapshot-template.md`

### 5.4 旧格式兼容
`docs/experience_index.md` 和 `docs/experience_log.md` 为旧格式，逐步迁移到 `.agent/memory/`。

---

## 六、阶段验证清单

### Phase 1: 数据库与基础采集
- [x] 数据库表创建成功
- [x] 能正常插入/查询数据
- [x] 采集脚本能运行

### Phase 2: 计算与权重逻辑
- [x] 归一化逻辑正确
- [x] 权重配置生效
- [x] 综合指数计算正确

### Phase 3: 数据入库
- [x] AA Omniscience 数据入库
- [x] 九家厂商模型注册
- [x] 模型别名解析正确

### Phase 4: 前端看板
- [x] 排行榜视图
- [x] 矩阵总览
- [x] 对比视图
- [x] 我的方案
- [x] 三主题
- [ ] 前端微调

### Phase 5: 部署上线
- [ ] CI/CD 流水线
- [ ] 自动采集任务
- [ ] 监控告警
- [ ] 生产环境稳定运行
