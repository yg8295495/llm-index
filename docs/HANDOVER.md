# HANDOVER — 交给托管维护方（人或 AI agent）的运行手册

> 本文件是**自包含**的：不依赖任何本机路径（`~/.agent-shared`、`~/.qoder` 之类都不算数）。
> 接手方只需要这个仓库 + 本文件 + `docs/changelog.md`。
> 最后更新：2026-09-29。

---

## 0. 这个项目是什么

一个**模型选型决策站**：回答"当前主流在用的模型里，哪个平台用哪个模型做哪类任务最划算"。
服务对象是单一用户的金融量化因子研究工作流（夜间 23:00–07:00 跑批），不是通用排行榜。

- 线上形态：**纯静态站**。GitHub Pages 只发布 `frontend/`，页面读同目录 `data.json`。没有后端。
- 数据权威：**Artificial Analysis（AA）** 的同口径评测。厂商自报数据物理隔离，绝不混算。
- 发布方式：**push 到 master 即发布**（`.github/workflows/deploy.yml`）。所以 push 权 = 发布权。

## 1. 五条数据口径铁律（违反任何一条都是事故）

1. **无 source_url 不入库。** 每条评测行必须能指回它来自哪一页。
2. **只追加，不覆盖，不删除历史。** 快照按日期唯一；同日重跑走幂等跳过。
   想"修"历史数据 = 新开一个快照，不改旧行。
3. **observed_at = AA 快照日（受众时区 Asia/Shanghai），collected_at = 真实抓取时刻（UTC）。**
   AA 不提供逐项评测日期，**不得编造**。
4. **厂商自报数据一律 `_official` 后缀 + `source=<provider>_official` + confidence 0.45，
   且 `snapshot_date` 必须等于最新 AA 批次日。** 它不进任何榜。
   理由可核验：官方称 Hy3 Terminal-Bench 2.1 = 70.8，AA 实测 64.42。
5. **不逆向 AA 刻意加密的 `/data/<hash>.txt` + `manifest.key`。** 只用页面 SSR 里公开可见的
   `initialModels` / `models` / 单模型详情页内联数据。逆向 = ToS 风险 + 每次改版即失效。

## 2. 日常维护命令序列（含验收）

```bash
pip install -r requirements.txt            # sqlalchemy / pyyaml / pytest / ruff
python3 scripts/refresh_data.py            # 干跑：采集→登记→导出→契约测试，不写库
python3 scripts/refresh_data.py --apply    # 实跑：写库 + 覆盖 frontend/data.json
git add -A && git commit && git push       # push 即发布，先过 §6 的确认清单
```

`refresh_data.py` 内部顺序：`collect_aa_v3`（主批次 + watchlist 补采）→
`enrich_metadata`（详情页元数据，只补缺）→ `ingest_manual_reference`（自报登记）→
`export_frontend_data` → 契约测试。任一步非零退出即中止，**不要跳过失败步骤继续**。

验收三条（全绿才算完成）：

```bash
python3 -m pytest -q                                   # 78 passed
python3 -m ruff check src scripts tests --select F,E9  # 零告警
python3 scripts/refresh_data.py                        # exit 0
```

## 3. 数据漂移处理（weekly-drift-check 开 issue 之后）

`.github/workflows/weekly-drift-check.yml` 每周两次比对"当前 AA 页面"与
"已提交的 `data/raw/snapshots/<最新>/`"（页面指纹 / 带分模型数 / 评测对数），
**只开 issue，不写库不发布**。看到 issue 后：

1. 本地跑 `refresh_data.py`（干跑），读完整输出：新建/更新模型数、评测行数、补采清单、
   "同日页面改版"告警、被拒绝入库的行。
2. 人工过目：榜面前五有没有反常跳动；`reports/collection_<日期>.md`。
3. 有反常 → 先查是不是 AA 改版或我们解析漏字段（对照 §4），**不要直接 --apply**。
4. 正常 → `--apply`，更新 README/changelog 的批次数字，commit + push。

## 4. AA 改版 / 抓取失败适配流程（硬约束在 §1.5）

已知失败模式与处置（编号对应 `docs/changelog.md`）：

| 现象 | 原因 | 处置 |
|---|---|---|
| `未找到 defaultData chunk` | AA 又改版瘦身 | 看 RSC flight 里还剩什么键；改 `aa_omniscience.py` 的提取逻辑，**加回归测试** |
| 解析出 0 条带分模型 | 正则假设了 JSON 无空格等格式 | `collect_scored_models` 的正则要容忍格式变化（#34 修过一次） |
| 某模型某字段突然变 NULL | AA 两个 payload 键名不一致（`contextWindowTokens` vs `contextWindow`、`itbenchSre` vs `itBenchSre`） | 用 `mapping._pick()` 加候选键，**逐 key 比对详情页确认是"没发布"还是"没解析到"**（#37/#40） |
| 同日两次抓取结果不同 | AA 同日内改版 | `reconcile()` 会报"当前页面已不再产出的行"；保留不删，写进报告（#34） |
| `curl rc=35` | TLS 握手抖动 | 重跑即可；`enrich_metadata.py` 只补 NULL 不覆盖，重跑安全 |
| 榜单只剩一个模型 | 自报数据开了新快照日 | 已被 `ingest_manual_reference.py` 的日期护栏挡住；若仍发生，查 YAML 的 `snapshot_date`（#31/#35/#39） |

**适配改动的验收**：新解析逻辑必须对**旧的已提交快照产物**也能跑通（离线复现：
`collect_aa_v3.py --from-file`），否则就是只对新页面成立的脆弱代码。

## 5. 决策权边界（托管 agent 必读）

| 可以自决 | 必须先问人 |
|---|---|
| AA 改版后的解析修复（带回归测试） | 任何**口径/权重/维度**变更（config/*.yaml） |
| 新模型的身份解析、命名规范化 | 新厂商进 `config/vendors.yaml` 或改 tier |
| 元数据补采、失败重试 | 是否收录厂商自报数据（`data/raw/manual/*.yaml`） |
| 死代码归档、CI/工作流修复 | **发布**（push master）——见 §6 |
| 文档/注释/测试补充 | 删除任何历史快照行 |
| | 把参照模型提为核心、或反过来 |

原则：**机械的归机器，判断的归人。** 这个站的价值在于"每个数都能说出从哪来、为什么可信"，
一旦 agent 开始自己决定口径，这个价值就没了。

## 6. 发布闸门（push = 发布）

push 前逐条确认：

- [ ] `refresh_data.py --apply` exit 0，且干跑与实跑报数一致
- [ ] 78 测试 + ruff F,E9 全绿
- [ ] `frontend/data.json` 体积在 1MB 内（超出说明导出了不该导出的字段）
- [ ] 榜面前五与上一批的差异能逐条解释（新模型上榜 / AA 撤数据 / 我们修 bug）
- [ ] changelog 记了本次"什么时候、什么问题、什么原因、怎么解决"
- [ ] 站点「数据说明」页显示的快照日 = 本批快照日

## 7. 目录地图（活代码）

```
config/benchmarks.yaml   维度 + AA 字段映射 + 溯源（aa_key / source_url / 量纲）
config/settings.yaml     权重、预设、归一化方法、基准锚、双榜定义
config/vendors.yaml      厂商命名空间 + tier（core 进榜 / reference 存档）
config/watchlist.yaml    详情页补采名单 + 人工登记名单
src/collector/           aa_omniscience.py（解析） mapping.py（映射）
src/compute/scoring.py   双榜计分；参照模型同标尺取分但 ranked=false
src/storage/             models.py（ORM） snapshot_store.py（追加写入）
scripts/                 5 个：collect_aa_v3 / enrich_metadata /
                         ingest_manual_reference / export_frontend_data / refresh_data
frontend/                index.html + data.json + vendor/echarts.min.js（自托管）
data/raw/snapshots/      每批的解析产物（manifest/scored_models/registry），可复现
reports/                 采集报告 + 元数据补采凭据（含每模型来源 URL 与页面 sha256）
_archive/v2/             退役的 v2 多源框架（README 说明退役理由）
```

## 8. 接手自检（第一次跑通才算交接完成）

1. 全新 clone，`pip install -r requirements.txt`
2. `python3 -m pytest -q` → 78 passed
3. `python3 scripts/refresh_data.py` → exit 0（会真抓 AA，约 1–3 分钟）
4. 读一遍 `docs/changelog.md` 的 #1、#13、#31、#35、#37、#39、#41 —— 这七条是
   这个项目踩过的最深的坑，也是所有"看起来多余"的代码存在的原因。
