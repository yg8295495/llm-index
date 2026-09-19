# LLM Benchmark Matrix

> 个人模型选型决策工具 — 基于多维度评测数据，回答"这个任务该选哪个模型"

## 项目定位

**不是**综合评测库、学术排行榜、全量模型数据库、公开服务。

**是**个人决策工具：在九家封闭厂商范围内，基于当前在用的主流模型，
给出各任务的选型依据（能力 + 价格 + 特性），并让每个数字都能追到来源。

## 模型范围（九家厂商）

**御三家**: OpenAI / Anthropic / Google
**国内六家**: DeepSeek / GLM(智谱) / Kimi(月之暗面) / Qwen(阿里) / MiMo(小米) / MiniMax

权威定义在 `config/vendors.yaml`（`tier: core`）。范围外厂商若与九家同期发布，
以 `tier: reference` 入库存档，**不进综合榜**，前端灰显并标注"参照"。
除非明确说要加，否则不扩展到综合榜。

## 五维度体系（v5, 2026-09-20）

以 `config/benchmarks.yaml` 为唯一准（维度与数据源），
`config/settings.yaml` 为唯一准（权重、归一化、基准模型、预设）。

| 维度 | Key | 默认权重 | 主要数据源 |
|------|-----|---------|-----------|
| 事实准确 | factual | 0.25 | AA-Omniscience / GPQA / HLE / 智能指数 |
| 工作流 | workflow | 0.25 | GDPval / Briefcase / GDP-PDF / AutomationBench / Tau-2 |
| 工程能力 | engineering | 0.20 | Terminal-Bench 2.1 & 4.0 / SciCode / LCR / MLCR |
| 成本 | cost | 0.15 | 整轮评测消耗 / 混合单价（估算） |
| 人类偏好 | preference | 0.15 | LMArena（**本批无数据，权重自动重新分配**） |

- 归一化：min-max 钳到 [0,100]。AA-Omniscience 是可为负的指数（本批 −49.25 ~ +43.73），
  不用比值法，否则会算出负分（详见 `docs/changelog.md #5 #6`）。
- 基准模型（对比锚点）：默认 `openai/gpt-5.6-terra`，可切 Luna / DeepSeek V4 Pro。
- 用户可自定义权重方案，保存在浏览器 localStorage。

## 当前数据批次

- 快照日 **2026-09-20**，来源 Artificial Analysis 评测页
- **19 个核心模型**（覆盖九家中的 8 家，MiMo 本批 AA 无数据）+ 10 个参照模型，
  共 34 个推理档位；30 项 benchmark；572 条 AA 评测 + 4 条厂商自报指标
- 发布物 `frontend/data.json` 约 650KB
- 库内累计 4 个快照、7611 条评测记录，历史批次从不删除

## 快速开始

### 前端（纯静态）

```bash
cd frontend && python3 -m http.server 8002     # 打开 http://127.0.0.1:8002
```

### 后端 API（本地开发用，线上未部署）

```bash
pip install -r requirements.txt
uvicorn src.main:app --reload                  # 文档 http://127.0.0.1:8000/docs
```

### 更新数据

一条命令跑完「采集 → 入库 → 导出 → 自校验」：

```bash
python3 scripts/refresh_data.py            # 干跑，不写库
python3 scripts/refresh_data.py --apply    # 实际写入
```

分步：

```bash
python3 scripts/collect_aa_v3.py                    # 干跑（含 watchlist 补采）
python3 scripts/collect_aa_v3.py --no-dry-run       # 采集并追加为新快照
python3 scripts/ingest_manual_reference.py          # 登记 AA 未收录模型的厂商自报数据
python3 scripts/export_frontend_data.py             # 导出 data.json
```

**两条数据来源**（口径不同，绝不混算）：

- `config/watchlist.yaml → aa_model_page`：AA 收录但不在 omniscience 默认对比集里的
  模型，走 `/models/<slug>` 详情页取**同口径**分数（Qwen3.8-Flash-Next、Hy3）。
- `config/watchlist.yaml → manual` + `data/raw/manual/*.yaml`：AA 完全没收录的模型
  （混元 Hy4 preview），只能用厂商自报数据。这类指标一律带 `_official` 后缀、
  置信度压到 0.45、前端单独成块，**不参与任何榜单计算** ——
  因为官方称 Hy3 在 Terminal-Bench 2.1 得 70.8，而 AA 实测是 64.4，口径明显不同。

采集器只做**追加**：每个快照一批行，重复跑同一快照会跳过而不是覆盖。
每次采集把页面 HTML（gzip）、解析产物与页面 sha256 落到
`data/raw/snapshots/<快照日>/`，报告落到 `reports/collection_<快照日>.md`。
同一天内 AA 若改版，会显式报出"哪些行已无法从当前页面复现"而不静默合并。

### 运行测试

```bash
python3 -m pytest -q                                  # 101 passed
python3 -m ruff check src scripts tests --select F,E9
```

### 发布

见 `docs/deploy.md`：`git push origin master` → GitHub Actions 发布 `frontend/`
→ GitHub Pages → Cloudflare 映射 `llm.aivey565.shop`。

## 数据来源与可信度声明

- 榜单数值来自 Artificial Analysis 的 AA-Omniscience 评测页快照；
  官方题库 `AA-Omniscience-Public`（600 题，10% 子集，Apache-2.0）与方法学论文
  （arXiv:2511.13029）作为口径引用。
- **AA 不公布逐项评测的执行日期**，因此本站所有分数标注为"某日 AA 快照 + 采集时刻"，
  不标注虚构的评测日期。三个日期字段的含义见
  `config/benchmarks.yaml: provenance.date_semantics`。
- 每条评测在库内和 `data.json` 中都带 `source_url`；配置里没有来源 URL 的数据源
  会被拒绝入库，而不是静默通过。
- 覆盖薄的数据源（本批有 5 项只有 1 个模型有值）在配置里标 `status: stale/empty`，
  前端会显示状态标记，不粉饰成可靠数据。

## 项目结构

```
llm-index/
├── config/
│   ├── benchmarks.yaml        # 维度 + 数据源 + aa_key 映射 + 来源口径（唯一权威）
│   ├── settings.yaml          # 权重 / 归一化 / 基准模型 / 预设（唯一权威）
│   ├── vendors.yaml           # AA creator → 厂商命名空间 + 范围层级（唯一权威）
│   ├── aliases.yaml           # 模型别名映射
│   ├── accessibility.yaml     # 可访问性标签
│   └── endpoint_pool.yaml     # 端点池
├── data/
│   ├── llm_index.db           # SQLite（不入库版本控制）
│   └── raw/snapshots/<日期>/   # 每次采集：HTML(gz) + 解析产物 + manifest（解析产物进 git）
├── src/
│   ├── collector/
│   │   ├── aa_omniscience.py  # 抓取 + RSC 解码 + 数组提取（不碰库，可单测）
│   │   ├── mapping.py         # AA 记录 → schema：厂商、档位、benchmark 映射、成本派生
│   │   └── registry.py        # 读取 benchmarks.yaml 的注册表
│   ├── storage/
│   │   ├── models.py          # schema 唯一声明处
│   │   └── snapshot_store.py  # 只追加不覆盖的快照写入 + 唯一索引 + 审计
│   ├── compute/               # 归一化 / 权重 / 综合指数（API 与测试用）
│   └── api/                    # FastAPI 路由
├── scripts/
│   ├── refresh_data.py        # 编排：采集 → 入库 → 导出 → 契约测试
│   ├── collect_aa_v3.py       # 采集器 CLI
│   └── export_frontend_data.py
├── frontend/                  # 发布产物（CI 只上传这个目录）
├── reports/                   # 每次采集的 Collection Report
├── docs/
│   ├── changelog.md           # 问题 / 原因 / 修法 / 待办（代码里的 #N 指向这里）
│   └── deploy.md              # 发布、缓存核对、回滚、域名
├── tests/                     # 78 项；期望值从 config/ 推导，不重述字面量
└── _archive/                  # 废弃的 v2 采集链等，逐条原因见其 README
```

## 采集标准

1. **准确度** — 不编造，无 `source_url` 不入库，交叉验证，覆盖不足如实标 `stale`
2. **可核验** — 每批保留页面指纹 sha256 + 抓取时刻 + 解析产物，他人可复现
3. **不破坏历史** — 只追加快照，不覆盖、不删除既有评测记录

## 权威文档

| 文档 | 职责 |
|------|------|
| `config/benchmarks.yaml` | 维度、数据源、AA 字段映射、来源口径 |
| `config/settings.yaml` | 权重、归一化、基准模型、预设 |
| `config/vendors.yaml` | 厂商归属与范围层级 |
| `src/storage/models.py` | 数据库 schema |
| `docs/changelog.md` | 问题与决策记录、已知不足 |
| `docs/deploy.md` | 发布与回滚 |
| `.trae/rules/project_rules.md` | 工作流约束 |
