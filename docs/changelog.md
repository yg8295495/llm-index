# 更新日志

本文件记录本项目的问题、决策与修复：什么时间、什么问题、什么原因、怎么解决。
代码注释里出现的 `changelog #N` 都指向这里的编号。

数据本身的版本轨迹不在这里，在 `data/raw/snapshots/<快照日>/manifest.json`
与前端「数据说明」页；本文件记的是**工程决策与缺陷修复**。

---

## 2026-09-20 · 数据管线 v3 重构 + 九月模型批次入库

**触发原因**：用户要求把"当前主流在用的新模型"做进榜单，并审计既有实现。
目标口径（用户当日明确）：只关注当前主流、近 1–2 个月发布、常用模型之间的排序；
已过时的模型不再关注；增量发布；每条数据带来源与日期；不覆盖历史；
数值不足处如实标注而不假装精确。

### 采集与解析

**#1 AA 页面改版导致采集器彻底失效**
- 发现：2026-09-20 04:12（干跑 `collect_aa_v2.py` 报 `未找到 defaultData chunk`）
- 原因：AA 把 omniscience 页面从约 8MB 瘦身到约 1.2MB，原本内嵌在 RSC flight
  流里的 `defaultData`（全部模型的逐项分数）被移除，改由前端从
  `https://artificialanalysis.ai/data/241a91dd5b5e7b25.txt` 拉一个约 483KB 的
  **二进制密文 blob**（实测 HTTP 200，头部为随机字节），配合页面里的
  `manifest.key` 在前端解密。这是 AA 主动加的反爬。
- 影响：2026-08-09 之后没有任何新数据进库，且失败方式是"脚本崩掉"而非静默出错，
  所以此前只表现为"数据没更新"。
- 解决：新增 `src/collector/aa_omniscience.py`，改为解析仍然公开内联在页面里的
  `initialModels`（本批 31 条带完整分数的模型）+ `models`（653 条注册表，含
  `creator` / `release` / `effort` / `releaseDate` / `deprecated`）。
  甄别带分记录时按"对象里是否有分数字段"判断，而不是只认一个键名 ——
  AA 下次改名不至于整站失效。
- 决策：**不逆向解密那个 blob**。它能给全量 653 模型分数，但（a）绕过对方刻意设置的
  技术措施存在 ToS 风险，（b）每次改版即失效（这次就是这么崩的），（c）本项目目标
  只需要九家现役模型，SSR 里这 31 条已经覆盖。
- 可复现性补充：AA 官方在 HuggingFace 公开了 `ArtificialAnalysis/AA-Omniscience-Public`
  题库（600 题，10% 子集，Apache-2.0，附方法学论文 PDF；arXiv:2511.13029）。
  已作为「来源与口径」引用写进 `config/benchmarks.yaml: provenance` 和前端数据说明页。
  注意它是**题库不是分数表**，所以不能当分数主干用。huggingface.co 从本机直连不通，
  可经 hf-mirror.com 访问。

**#4 厂商归属靠猜，白名单缺失**
- 原因：`collect_aa_v2.py` 用 120 条 slug 前缀正则（`^claude-` → anthropic 等）猜厂商，
  猜不到写 `provider='unknown'`，且**没有任何范围过滤**，页面上有分的一律入库。
- 影响：2026-08-09 那次造出 122 个 `provider='unknown'` 模型，README 的"九家封闭范围"
  实际失效；库里现存 137 行 unknown 残留。
- 解决：新增 `config/vendors.yaml` 作为厂商归属唯一权威。改用 AA payload 里的
  `creator` 字段做精确归属，三级回退：记录自带 `creator.slug` →
  `creator.logo` 文件名（`/img/logos/zai_small.svg` → `zai`）→ `creator.id` 反查表。
  采集只入库 `tier in (core, reference)`，`excluded` 直接丢弃。
  遇到未登记的厂商不猜，落 `tier='unclassified'` + `needs_manual_review=1` 并在
  Collection Report 里点名。
- 本次实战验证：AA 已把 Grok 的 creator 标为 `spacexai`（不再是 `xai`），
  采集时正确报出"不在 vendors.yaml"，人工归类后统一到既有 `xai` 命名空间，
  避免同一模型出现两条 ID。

**#10 旧前缀规则会撞车**
- 问题：v2 规则 `^claude-fable-5`（无结尾锚定）会把新模型 `claude-fable-5-1`
  解析成 `claude-fable-5`，与 2026-06-09 发布的老模型合成同一条记录。
- 解决：新模型 ID 一律由 AA 注册表的 `release.slug`（基座）+ `effort.slug`（档位）
  生成；库里已存在的 `aa_slug` 优先沿用库内 ID；不再走 120 条旧规则。
  回归测试：`tests/test_collector_v3.py::test_dotted_version_normalization`。
- 附带修掉我自己写错的一处：`dotted()` 初版多插一个连字符，产出 `glm--5.3`
  这种脏 ID（同一批测试的 `test_dotted_does_not_invent_double_dash` 拦住）。

**#12 `observed_at` 被写成跑批日期**
- 原因：v2 把 `date.today()` 写进 `benchmark_evals.observed_at`，冒充观测日期。
- 解决：区分三个日期并写进 `benchmarks.yaml: provenance.date_semantics` ——
  `observed_at` = AA 快照日、`collected_at` = 真实抓取 UTC 时刻、
  `release_date` = 模型发布日期（AA 提供）。快照行同时记录页面 `sha256` 与 URL。

**#14 快照日取错了时区**
- 问题：默认取 UTC 日期，本次抓取发生在 UTC 19:55，会把"9 月 20 日截止"的数据
  标成 09-19。
- 解决：快照日按受众时区（Asia/Shanghai）计，`collected_at` 保留 UTC 原值；
  可用 `--snapshot-date` 覆盖。

### 数据完整性

**#2 强制刷新会删掉历史分数**
- 原因：`collect_aa_v2.py --force-refresh` 的执行序列是
  `UPDATE models` → `DELETE FROM benchmark_evals WHERE model_pk=?` → 重新 INSERT。
  一次误用即抹掉该模型全部历史。
- 解决：v3 禁止任何 DELETE。改为"一个快照一批行"，按
  `(model_pk, benchmark, snapshot_id)` 唯一，重复跑同一快照是**跳过**而不是覆盖。
  回归测试：`test_write_then_rerun_is_idempotent`、
  `test_new_snapshot_appends_without_touching_history`。

**#3 没有版本轨迹**
- 解决：新增 `snapshots` 表（快照日 / 来源 URL / 抓取时刻 / 页面 sha256 / 模型数 /
  评测数 / 备注），并把库里既有的三个历史观测日（2026-06-17 LMArena、06-18 首次
  AA、08-09 二次 AA）回填成快照行，回填行在 `notes` 里写明"旧脚本产生、无页面指纹、
  可信度低于 v3"。前端「数据说明」页展示这张表。

**#21 schema 有两处定义**
- 问题：列定义同时存在于 ORM 和脚本里的裸 SQL，两边会漂移。
- 解决：`src/storage/models.py` 为唯一声明处；`ensure_schema()` 只负责把缺列
  ALTER 到旧库上，并在建唯一索引前检查存量重复，脏数据直接报错中止而不是静默跳过。

**#22 存储层参数绑定错位（我自己写出来又抓到的）**
- 问题：19 列 INSERT 用位置占位符，首版把 `model_pk` 写成 NULL 且整体错位一位；
  另一处把命名参数与位置参数混用。这类 bug 一旦进库就是静默的数据损坏。
- 解决：全部改命名参数，并让干跑与实跑走同一套计数口径。

**#13 干跑统计虚低**
- 问题：首次干跑报"评测行 261"，而映射层实际产出 545 行。原因是命中库内已有模型的
  分支在干跑时提前 `continue`，根本没统计它们的评测行。
- 影响：如果没发现，"跑一次说一次数"会让别人无法核对流程。
- 解决：把计数提到分支之前，干跑/实跑同口径。回归测试：`tests/test_collector_v3.py`。

**#23 rename 只写了审计没执行**
- 问题：报告显示"ID 规范化 8 条"，但导出里仍是旧 ID —— 我只往
  `model_id_renames` 插了记录，漏了真正执行 `UPDATE models SET model_id`。
- 解决：按旧 ID 批量更新（同一模型的多个推理档位行必须一起改，否则同一个物理模型
  会在榜单里出现两条），更新前先检查唯一键冲突，冲突则跳过并记入报告而不是崩掉。
  8 条历史脏 ID 已修正，例如 `openai/gpt-5-6-terra` → `openai/gpt-5.6-terra`、
  `unknown/inkling` → `thinking_machines/inkling`、
  `qwen/qwen3-8-max` → `qwen/qwen3.8-max-0902`。

### 计算与口径

**#7 权重与归一化实现过两份**
- 问题：`src/compute/`（Python）和 `frontend/index.html:1604-1648`（JS）各有一份
  维度定义、benchmark 分组和默认权重，两边不同步。线上生效的是 JS 那份，
  Python 那份对站点而言是死代码。
- 解决：`config/benchmarks.yaml` + `config/settings.yaml` 为唯一权威，由
  `export_frontend_data.py` 注入到 `data.json` 的 `config` 块，前端改为读取注入值
  （保留兜底，使旧 data.json 仍可渲染）。

**#5 #6 归一化在可负数据上算错，且配置与实现不一致**
- 问题：`config/settings.yaml` 声明 `method: min-max`，但前端实际用
  `best / max * 100`（比值法）。AA-Omniscience 本批值域 −49.25 ~ +43.73，
  比值法会算出**负得分**并在极端情况下把名次算反。
- 解决：统一到 min-max 并钳在 `[0, 100]`，参数从 `config.normalization` 读；
  `negative_cap` 写进配置说明。Python 侧 `Normalizer` 本来就是 min-max，
  补了 `test_minmax_is_bounded_with_negative_input` 作为共同回归锚点。

**#11 成本指标错标**
- 问题：v4 把 `cost_per_task`（每次任务成本）当作成本维度主指标，但数值实际是
  "跑完整套评测题一次的消耗"。本批实测 Harvey Lab 中位 **$5235**、HLE **$293**、
  AA-Omniscience **$88**，叫"每任务成本"是量纲错误。
- 解决：改名 `cost_per_eval`（整轮评测消耗中位数），并在 `benchmark_meta` 的
  `note` 里写明它不是每任务成本、以及推理型模型 reasoning token 越多值越高。
  现在它由 `canonicalEvalTokenCounts`（AA 公布的逐项 token 用量）× AA 定价算出，
  比 v4 依赖 terminalbench breakdown 更实。
- 附带：混合单价 `pricing` 明确写出估算假设"输入:输出 = 3:1"，不伪装成实测。

**#24 preference 维度本批为空**
- 现状：LMArena 无新模型数据（库里 69 条属 2026-06-17 快照，全是已下架模型），
  该维度覆盖 0。综合指数按 `weights_no_preference` 把 15% 重新分配给其余四维。
- 处置：不假装。前端维度标注 status=empty，数据说明页写明。补齐需另跑 LMArena
  采集，列入下方待办。

### 前端与数据体积

**#15 data.json 体积失控**
- 问题：本地全量导出 8.68MB，而 `frontend/index.html` 从不引用其中 12 个字段
  （`context_window_fmt`、`parameters`、`homepage`、`supports_tools` 等）。
  访客首屏要整包下载。
- 解决：只导出范围内模型 + 前端实际读取字段 + 溯源字段。**617KB**（比 8.68MB
  降 93%，也低于线上那份 1.63MB 的旧快照）。契约测试
  `test_data_json_size_is_small` 防回弹。

**#16 来源标签从来没显示过**
- 问题：导出器写 `benchmark_meta[k].source_url`，前端读的是 `meta.source`，
  字段名不匹配使 `index.html:2079` 的来源标签恒为空。
- 解决：两个字段都产出且语义明确（`source` 是来源名，`source_url` 是链接），
  并由 config 生成而非手写 —— 旧导出器里那份手写 `BENCHMARK_META` 只覆盖 15 项，
  库里实际有 27 个 benchmark，12 项没有元信息。

**#25 基准对比是缺失功能**
- 现状：`config/settings.yaml` 有 `baseline_model`，但前端全文只有一处 CSS 的
  `align-items:baseline`，没有任何基准对比逻辑。
- 解决：按用户指定把基准设为 `openai/gpt-5.6-terra`（候选含 Luna、DeepSeek V4 Pro），
  注入到前端并提供综合分差列。

### 测试与流程

**#17 `pytest tests/` 在收集阶段就崩**
- 原因：`tests/archive/test_ingester.py` import 已不存在的 `src.ingester`。
  README 里写的 `pytest tests/ -v` 因此完全跑不起来。
- 解决：新增 `pytest.ini`，`norecursedirs` 排除 `tests/archive` 与 `_archive`。

**#18 测试把配置字面量写死**
- 原因：测试停留在 v3 的四维与 5 个英文预设名（developer/enterprise/...），
  配置升到 v4/v5 后 7 个测试红掉 —— 报的是"测试过期"而不是"代码坏了"，
  作为质量闸门等于失效。
- 解决：`tests/conftest.py` 提供从 `config/` 推导的 fixture，测试断言**契约**
  （维度集合等于配置、权重和为 1、预设维度齐全、接口与 registry 同源）。
  现状：78 passed。新增覆盖：解析层、映射层、存储幂等、导出契约。

**#19 `compare_models()` 一调用就 NameError**
- 原因：`src/compute/index_calculator.py:231` 外层字典推导的键 `dim` 在内层推导式
  里才定义。
- 解决：拆成先构造 `per_model` 再计算；补 `test_compare_models_runs`。

**#20 README 的数据更新命令已废弃**
- 解决：README 改为 `scripts/refresh_data.py`（采集→入库→导出→自校验一条命令）。
  6 个失效脚本移到 `_archive/scripts/v2_pipeline/` 并逐条写明废弃原因。

**#26 无 source_url 不入库**
- 落实：`benchmark_evals` 增加行级 `source_url`，`snapshot_store.write()` 对
  配置里没有来源 URL 的数据源**拒绝写入并在报告里点名**，而不是静默入库。
  本批 545 行全部带来源 URL。
- 口径坦白：13 个数据源在 AA 没有独立子页面 URL，配置里未写 `source_url`，
  代码回退到 omniscience 页面 URL（这批数值确实就是从那一页读来的）。
  回退名单会在 Collection Report 的「来源 URL 口径」段逐条列出，不做静默兜底。

**#27 计分逻辑收回到一处，并让 Python 计算层不再是死代码**
- 问题：#7 消除了"配置常量的两份副本"，但**公式**本身仍同时存在于
  `src/compute/`（Python，只有 API 用）和前端 JS（线上真正生效的那份）。
- 解决：新增 `src/compute/scoring.py`，默认榜单的分数由导出器调用它算好、
  写进 `data.json` 的 `models[].scores`，并附 `metadata.scoring` 说明实际生效的
  权重与口径。前端只在用户手调权重时才算综合榜；能力榜/性价比榜是固定口径，
  直接展示服务端算好的数 —— 测试校验的数和访客看到的数出自同一份实现。

**#28 雷达图依赖的 CDN 在真实浏览器里连不通**
- 发现：2026-09-20 本地浏览器实测 `https://cdn.jsdelivr.net/npm/echarts@5.5.0/...`
  报 `ERR_CONNECTION_CLOSED`，`window.echarts` 为 undefined。curl 能下下来但浏览器不通，
  说明这条依赖对国内访客本身就不可靠。
- 解决：echarts 5.5.0（1.03MB）落到 `frontend/vendor/echarts.min.js` 同源加载，
  页面不再依赖任何第三方 CDN。子任务此前已加的"echarts 不可用则降级为文字维度条"
  兜底保留，双保险。

**#29 拆成双榜：能力榜 + 性价比榜**
- 起因：单一综合分里成本该占多少权重没有客观答案。实测本批 18 个核心模型的整轮评测
  消耗从 **$7 到 $1094（156 倍）**，线性 min-max 下三个能力维都第一的
  Claude Fable 5.1 因最贵而在成本维拿 0 分，综合榜掉到第 9，榜首变成发布更早、
  能力更弱的 GPT-5.6 Sol。改对数刻度能缓解，但会让"便宜够用"的模型冲到第 2。
- 决策（用户 2026-09-20 选定）：不藏权重，拆两榜 ——
  **能力榜**不计成本（事实 36% + 工作流 36% + 工程 29%，preference 无数据故重新归一），
  **性价比榜** = 能力分 ÷ 混合单价，**综合榜**保留给坚持要单一数的人并标明成本主导。
- 实测结果：能力榜 Claude Fable 5.1 (95.4) > GPT-6 Astra (90.3) > Claude Opus 5 (85.9)；
  性价比榜 GLM-5.3-Flash (100，$0.24/1M) > GPT-5.6 Luna (47.5) > DeepSeek V4.1 Flash (40.1)。
- 前端新增「榜单」视图，三榜切换，每行显示四个维度分 + 混合单价 + 榜分 + 与基准差值。

**#30 幂等重跑把快照计数覆盖成 0**
- 问题：前端「数据说明」页的快照轨迹里，本批"评测数"显示 0，而 `metadata.eval_count`
  是 595。原因是采集器回填 `snapshots.eval_count` 用了**本次新写入行数**，
  第二次跑同一快照时该值是 0，把第一次写对的数覆盖掉了。
- 解决：改成按库内该快照的实际行数统计（`SELECT COUNT(*) WHERE snapshot_id=?`），
  与"跑几次"无关。回归锚点：`test_raw_and_derived_eval_counts_add_up` 会断言
  快照行的计数必须等于导出的原始行数。
- 顺带修：前端那条一致性提示原来是拿**全部历史快照之和**去比本批数量，永远不相等；
  改成只比对本批快照，并把 AA 原始行数与本站派生行数分开计数
  （`raw_eval_count` 545 / `derived_eval_count` 50）。

**#31 模型显示名取到了推理档位变体的名字**
- 问题：榜上第一行显示成 "Claude Fable 5.1 (Adaptive Reasoning, **High Effort**, ...)"，
  把某个档位变体的名字当成了模型本名。原因是导出器按 SQL 排序取"第一个遇到的行"，
  而 `high` 字典序排在 `max` 前面。
- 解决：按 `aa_slug == family`（AA 基座）优先、其次按档位常见度
  （max > 基座 > adaptive-max > xhigh > high …）挑规范行；同时把每个档位的
  原始名字保留在 `reasoning_levels[level].display_name` 里供钻取展示。
  回归锚点：`test_display_name_is_the_base_variant`。

---

## 待办与已知不足（如实记录，不粉饰）

| 项 | 说明 | 影响 |
|---|---|---|
| 九家中 MiMo（小米）无数据 | 本批 AA payload 里没有任何小米模型 | 榜单 18 个核心模型只覆盖 8 家，前端需明示 |
| 用户点名的"字节 2.1-0915"不存在于 AA | 九家范围外，且该页 653 条注册表里也没有 | 无法纳入，需另找来源 |
| LMArena 维度为空 | 见 #24 | 综合指数实际按四维归一计算 |
| 库里残留 137 行 `provider='unknown'` | 8 月泄漏的范围外模型，不属本批快照，前端不可见 | 不影响榜面；若要彻底清理需单独一次带审计的归档迁移，未做 |
| `scripts/fetch_openrouter_meta.py`、`load_accessibility.py` 未接入 v3 | 上下文窗口、可访问性标签仍是旧数据或空 | 上下文窗口在新 payload 里不存在，如需补应走 OpenRouter |
| AA 不提供逐项评测日期 | 全 payload 唯一日期是 `releaseDate` | 分数只能标"某日 AA 快照"，已按用户要求如实标注 |
| 无自动调度 | `settings.yaml: ingestion.schedule` 无代码读取；AA 加密化后全自动不可靠 | 采集节奏人工触发 |
| mypy 未安装 | `project_rules.md §4.1` 要求 ruff/mypy/pytest 三道闸门，只跑了 ruff+pytest | 类型检查缺位 |
| 发布仍是手动 | CI 只发布静态 `frontend/`，不跑 Python | 见 docs/deploy.md |
| 前端「榜单」视图为本次新增 | 由本次会话补完，只做过本机浏览器验证（四个视图 + 三榜切换 + 零 console 错误） | 上线后需在真机再看一遍 |

## 本次数据批次

- 快照日 **2026-09-20**，抓取时刻 2026-09-19T20:23Z，页面 1,232,493 B，
  sha256 `d20f0a55bc5129b36e27a29c8226463e4045d4516ca09cd314574282173f176e`
- 带分模型 31 条 → 入库 26 个模型（**核心 18** + 参照 8）/ 31 个推理档位
- benchmark 30 项，评测 **545 条 AA 原始数值** + 50 条本站派生指标 = 595 条
- 核心 18 个：Anthropic 3（Claude Fable 5 / 5.1 / Opus 5）、OpenAI 4
  （GPT-6 Astra、GPT-5.6 Sol/Terra/Luna，另 gpt-oss-120b）、DeepSeek 2（V4 Pro、
  V4.1 Flash）、智谱 2（GLM-5.3、5.3 Flash）、Qwen 2（3.8 Max、3.8-27B）、
  Kimi 1（K3）、MiniMax 1（M3）、Google 2（Gemini 3.8 Flash、3.5 Flash-Lite）
- 榜面结果：能力榜 Claude Fable 5.1 第一；性价比榜 GLM-5.3-Flash 第一；
  基准锚点 GPT-5.6 Terra
- 库总量：评测行 7066 → **7611**，历史一行未删；快照 3 → **4**
- 明细见 `reports/collection_2026-09-20.md`
- 质量闸门：`pytest` **94 passed**；`ruff check --select F,E9` 零告警；
  本机浏览器实测四个视图 + 三榜切换 + 零 console 错误

