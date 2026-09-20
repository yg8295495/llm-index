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

## 2026-09-20 (第二次更新) · 补两个常选模型

用户指出榜面少了 **Qwen3.8 Flash** 和 **腾讯混元 Hy4 preview**，这两个是他常选的模型，
缺了无法判断。逐个查来源后的处理如下。

**#32 发现 AA 的单模型详情页是公开的补采路径**
- 之前判断"AA 全量分数已加密、拿不到"只对了一半：omniscience 页的 SSR 只内嵌 31 个
  默认对比模型，但 `https://artificialanalysis.ai/models/<slug>` 详情页里
  **内联了该模型的同口径完整分数**（实测约 3.9MB，含数百个带分对象），不需要碰加密 blob。
- 解决：新增 `config/watchlist.yaml` 声明补采清单，`collect_aa_v3.py` 在主批次之后
  逐个抓详情页。补采行的 `source_url` 指向各自的详情页而非 omniscience 页 ——
  溯源精确到页。
- 结果：`qwen3-8-flash-next`（阿里，**属九家核心**）拿到 14 条同口径评测，
  直接进榜并冲到**性价比榜第 2（97.1，$0.23/1M）**；`hy3` 拿到 13 条，作参照。
- 顺带发现详情页里有 `contextWindowTokens` 和 AA 官方的 `price1mBlended0To3To1`
  （正是 3:1 混合单价）。后者可替代本站的估算混合单价，前者可补上一直缺失的上下文
  窗口 —— 列入待办，本次未接。
- 回归测试 `test_find_scored_record_matches_slug_exactly` 锁住"必须精确匹配 slug"：
  详情页内联几百个对象，前缀匹配会让 `hy3` 命中 `hy3-preview`。

**#33 混元 Hy4 preview：AA 未收录，只能用官方自报口径，且必须物理隔离**
- 核实：AA 确实没有它 —— `/models/hy4`、`/models/hy4-preview`、`/models/hunyuan-4`
  全部 404，653 条注册表里只有 `hy3` / `hy3-preview` / `hy3-non-reasoning`。
  Hy4 preview 于 2026-08-28 发布开源（770B 总参 / 49B 激活 / 1M 上下文 / Apache-2.0）。
- 采用数据：腾讯官方发布文的 Terminal-Bench 2.1 = 85.4、DeepSWE = 64.3、
  专家盲测 2.99/4（官方称 GLM-5.3 为 2.92、Kimi K3 为 2.94）、CodeArena WebDev 第 6；
  价格与上下文取自 OpenRouter（$0.834 / $2.501 每百万 token）。
- **不混算的理由是可核验的**：官方称 Hy3 在 Terminal-Bench 2.1 得 70.8，
  而 AA 实测 Hy3 是 64.42 —— 差 6.4 分，说明评测实现/版本/采样不同。
  所以自报指标一律带 `_official` 后缀（天然不会被 `bench_groups` 捞进归一化）、
  `source = tencent_official`、`confidence = 0.45`，前端在榜单下方单列一个
  「厂商自报数据」块并写明不可比。
- 新增 `scripts/ingest_manual_reference.py` + `data/raw/manual/*.yaml` 登记通道，
  默认干跑。回归测试：`test_vendor_official_metrics_never_enter_benchmarks`、
  `test_official_only_model_is_not_scored_as_aa_data`。
- 腾讯在 `config/vendors.yaml` 里登记为 `tier: reference`（遵守用户"严守九家"的决定）。
  若要把混元当选型候选而非参照，把该条改成 `core` 重跑导出即可 —— 一处改动。

**#34 同一天内 AA 页面改版，快照变成两个版本的并集**
- 现象：相隔约 2 小时两次抓取，页面 sha256 从 `d20f0a55…` 变成 `c5fcaf21…`，
  字节数 1,232,493 → 1,232,321，且 AA 撤掉了 `muse-spark-1-3` 的一条 `mlcr_overall`。
  主批次因此从 545 条变成 544 条。
- 风险：快照按日期唯一，同日重跑会把两版数据并在一起，而 `html_sha256` 只记最新值 ——
  别人拿指纹去复现会发现少一条，这恰恰破坏"可核验"。
- 解决：新增 `reconcile()`，每次跑完比对"快照内的行"与"当前页面能产出的行"，
  差异**保留不删**（遵守不覆盖历史），但打印出来、写进 Collection Report 的
  「同日页面改版」段、并追加到快照 notes。
- 另修两处健壮性：`collect_scored_models` 的扫描正则原先要求 `{"id":"` 之间无空格，
  AA 一旦改用格式化 JSON 就会静默产出零记录 —— 放宽为 `\s*`；
  前端 `esc()` 原本是「数据说明」视图里的局部函数，榜单视图调用会 ReferenceError，
  提到模块级。

**#35 自报行挂进批次快照后，把两处统计污染了（我自己引入，被契约测试拦下）**
- 现象：`refresh_data.py --apply` 在契约测试步骤非零退出。快照表记 `eval_count=576`，
  导出的 `raw_eval_count=572`；同时「同日页面改版」误报 5 行（真实漂移只有 1 行）。
- 原因：#33 决定把厂商自报行挂到同一天的批次快照上（避免造出 `2026-09-20-tencent-official`
  这种非日期值把导出器的"取最新快照"逻辑带偏），但快照计数和改版比对都没有按来源分开，
  于是 4 条自报行既被算进 AA 行数、又被当成"AA 已撤掉的脏数据"。
- 解决：快照 `model_count` / `eval_count` 与 `reconcile()` 都只统计
  `benchmark NOT LIKE '%_official' AND source LIKE 'artificial%'` 的行；
  导出器新增 `metadata.official_metric_count` 让自报行数单独可见。
- 修完实测：快照 572 = raw 572，改版告警回到正确的 1 行，`refresh_data.py` exit=0。
- 这条留在日志里是因为它证明了 #30 那条测试断言不是摆设 —— 它拦下的正是我新写的代码。

**#36 参照模型是空壳 —— 实现与我自己的口径说明不一致**
- 现象：Hy3 补采进库、DB 里有 13 条 AA 同口径评测，但榜面上它的维度分、能力分、单价
  全是空。用户要"参照"就是为了能对比，空壳等于白采。
- 原因：`build_scores` 把定标集合和计分集合混成了同一个 `universe`（只有核心模型），
  参照模型因此完全没被算过分。而 `scoring.py` 的模块注释写的是
  "参照模型在同一标尺上取分但不参与排名" —— 代码没兑现文档。
- 解决：`normalize_dim` 拆成 `universe`（定 min/max 标尺，仍只看核心模型）与
  `score_for`（给谁算分，含参照模型）两个集合；成本维与混合单价同样分开。
  参照模型可能算出超出 [0,100] 的值（它的分数比核心模型最好值还高），按既定规则钳位，
  名次仍然只给核心模型。
- 回归测试：`test_reference_model_is_still_scored_on_the_core_scale`。
- 修完实测：Hy3 能力 35.7 / 性价比 49.5（$0.25）、Grok 4.6 能力 73.3、
  Muse Spark 1.3 能力 82.7，均带 `ranked=false`。

**本批数据（第二次更新后）**：29 个模型（核心 19 + 参照 10）/ 34 个推理档位 /
30 项 benchmark / 572 条 AA 评测 + 53 条派生指标 + 4 条厂商自报指标；
`pytest` 102 passed，`ruff` 零告警，`refresh_data.py --apply` exit=0。

---

## 2026-09-21 (第三次更新) · 横向对比补全：一个真采集 bug、一次我自己的报告错误

**触发原因**：用户指出横向对比表数据不全 —— 千问 3.8 Flash 明明有数据却显示为空，
混元 Hy4 完全不知道是什么能力级别；并要求"填不满的要说清原因和做过哪些尝试"，
否则怀疑采集环节有 bug。

**#37 AA 元数据键名不匹配，导致整批 context_window 为 NULL（用户怀疑的 bug 是真的）**
- 发现：2026-09-21 逐 key 比对 AA 的两个 payload。`src/collector/mapping.py` 读的是
  `contextWindow` / `activeParams` / `medianCanonicalAnswerOutputSpeed`，但
  **榜单页 payload 里根本没有 `contextWindow*` 这个键**（只有 activeParams 和速度），
  上下文窗口只出现在单模型详情页且叫 `contextWindowTokens`；激活参数在详情页叫
  `inferenceParametersActiveBillions`；输出速度在详情页藏在 `timescaleData.medianOutputSpeed`。
  结果：2026-09-20 批次 33 个带分行的 `context_window` 全为 NULL，页面明明写着 1,000,000。
- 连带发现：`intelligenceIndexTimePerTask`（单任务墙钟耗时）也只有详情页有，
  而这个数直接决定"夜里 8 小时能跑完多少个任务"。
- 解决：新增 `mapping.model_metadata(record)` 作为元数据唯一入口，内部用 `_pick()`
  做多键名 + 嵌套键 fallback；`scripts/enrich_metadata.py` 拉详情页回填这些列
  （默认干跑、只补 NULL 不覆盖已有值、每模型记录来源 URL + 页面 sha256 到
  `reports/enrich_metadata_*.json`）。新增列 `models.time_per_task_s`。
- 实测：33 个目标里 31 个回填成功，2 个（minimax-m3、step-5）curl rc=35 TLS 失败待重试。
  回填后 Qwen3.8-Flash 256k / 1393 s/task、GLM-5.3-Flash 1M / 566 s/task、
  DS V4.1-Flash 1M / 324 s/task、Qwen3.8-Max 983k / 2402 s/task。
- 回归测试：`test_model_metadata_accepts_detail_page_key_names`。

**#38 重跑采集不得用 NULL 抹掉已知元数据**
- 风险：修完 #37 后，主采集器只解析榜单页（没有 contextWindow），若 UPDATE 语句照例
  全列覆盖，则"补采到上下文窗口 → 第二天日更 → 又变回 NULL"。
- 解决：`snapshot_store._upd_params()` 在 UPDATE 时剔除本次取不到（None）的列。
  追加式快照不该把已知事实洗掉；代价是无法通过重跑清空某列，需要清空时手工 SQL 处理。
- 回归测试：`test_rerun_does_not_wipe_metadata_the_page_lacks`。

**#39 混元 Hy4 preview：官方附表 42 项入库，并给出 AA 口径的换算区间**
- 核实：AA 至今未收录（862 个 slug 里腾讯只有 hy3 系；`/models/hy4*` 仍 404）。
  独立横评确实不存在 —— 钛媒体 2026-08-31 原话："独立机构的大规模横评还没出来…
  目前一半还靠官方自己的数据撑着"。唯一的第三方信号是 Arena 系：Code Arena Elo 1624
  (名次 9–17, 09-12)、前端 WebDev Elo 1641±15 (名次 8–17, Preliminary, 09-16)，
  且本项目直连 lmarena 失败、数值取自第三方镜像，可信度不足以入库，只登记在 YAML 注释里。
- 采用数据：官方附表原图 `Tencent-Hunyuan/Hy4-preview/assets/benchmark-appendix.jpg`
  （4960×10840，下载后切 12 条逐行读图核对，非二手转述）→ 42 项指标入库，
  仍按 #33 的隔离口径（`_official` 后缀 / `source=tencent_official` / `confidence=0.45`）。
- **口径校准（这张表的正确用法）**：同一 harness 下"腾讯自跑"对竞品的系统性偏移
  （vs AA 2026-09-20 实测）：DS V4 Pro +9.2、GLM-5.3 +4.3、Kimi K3 +3.3、Hy3 +6.4、
  Qwen3.8-Max −2.2、GPT-5.6 Sol +0.8 → 中位 +3.3。据此 Hy4 自报 Terminal-Bench 2.1
  的 85.4 折算到 AA 口径约 **79–83**，即与 DeepSeek V4 Pro (78.7) 同档、低于
  GLM-5.3-Flash (84.3)。**不得**把 85.4 直接排到 Kimi K3 (85.0) 之前。
- 例外：附表里的 CritPt 与 GDPval-AA V2 就是 AA 标尺（Hy3 4.9 = 站内 0.049、
  GLM 19.1 = 0.191、Kimi 23.4 = 0.234 完全对得上），这两行可直接横向比。
- 新增护栏：`ingest_manual_reference.py` 现在要求 YAML 显式写 `snapshot_date`，
  且该日期既不早于也不晚于最新 AA 批次，否则拒绝执行 —— 避免 #33/#35 那个
  "自报行开新快照日把整个榜单顶掉"的坑重演。
  回归测试：`test_manual_ingest_refuses_date_older_than_the_latest_batch`。

**#40 我自己的报告错误：表里的"—"来自记忆，不是来自数据库**
- 现象：上一轮横向对比表把 Qwen3.8-Flash 写成"只有 5 个数、attemptRate 未发布"，
  而库里它有 14 项 AA 同口径评测（gpqa 0.923、GDPval 1612、tb2.1 0.861、lcr 0.797…），
  性价比在站内排第 2。用户据此得出的结论被我误导了。
- 原因：那张表是凭上下文里的旧摘要手写的，没有回查数据库；采集层其实是对的。
- 流程修：**任何对外结论表必须由脚本从库里生成**（本轮所有表格出自
  `benchmark_evals WHERE snapshot_id=4` 的一次查询），并且把"—"逐条回到
  AA 详情页做存在性核验，能说出"这个键在该模型页上就是 null"才算数。
- 核验结论：本轮矩阵里剩余的"—"全部是 AA 未发布，而非解析失败 ——
  GLM-5.3/5.3-Flash 无 mmmuPro（榜单页与详情页都是 null）、
  DS V4.1-Flash 无 gpqa/tauBanking/terminalBench21/mlcrOverall、
  Qwen3.8-Flash 无 mlcrOverall/attemptRate/briefcase/enterpriseOpsGym。
  另发现 `itbenchSre` 在详情页与榜单页大小写不同，已在 `build_evals` 加大小写兜底。

**#41 只有成本维的模型拿到了 94.84 的"综合指数"**
- 发现：2026-09-21 给 Hy4 补完 42 条自报指标后回查 `data.json`，它的
  `scores.composite = 94.84`，比 GPT-5.6 Sol 的 76.27 还高。
- 原因：`build_scores` 的综合分是"该模型可用维度上的加权平均"，而 Hy4 没有任何
  AA 同口径评测 → 可用维度只剩 cost 一个 → 纯成本分被当成了综合能力分。
  榜面按 `ranked=false` 不给它名次，但综合分本身仍然可见、仍然会误导。
- 解决：综合分要求**至少有一个非成本维**；成本分照旧单独展示（它确实便宜，
  $1.25/1M 混合价是事实），能力分/性价比/综合分一律 None。
- 回归测试：`test_cost_only_model_gets_no_composite`。

**本批数据（第三次更新后）**：29 个模型（核心 19 + 参照 10）/ 572 条 AA 评测
+ 53 条派生 + **42 条厂商自报**（原 4 条）；28 个带分模型的上下文窗口 28/28、单任务耗时 27/28
覆盖（修复前整批为 NULL）；`pytest` **108 passed**，`refresh_data.py` 干跑 exit=0，
`frontend/data.json` 690 KB。

---

## 待办与已知不足（如实记录，不粉饰）

| 项 | 说明 | 影响 |
|---|---|---|
| 九家中 MiMo（小米）无数据 | 本批 AA payload 里没有任何小米模型 | 榜单 18 个核心模型只覆盖 8 家，前端需明示 |
| 用户点名的"字节 2.1-0915"不存在于 AA | 九家范围外，且该页 653 条注册表里也没有 | 无法纳入，需另找来源 |
| LMArena 维度为空 | 见 #24 | 综合指数实际按四维归一计算 |
| AA 详情页的官方混合单价未接 | `price1mBlended0To3To1`（3:1 混合）等 5 个 blended 价在详情页有，站内成本维仍用 input/output 自算混合价 | 性价比榜的成本是本站口径估算，不是 AA 官方值；contextWindowTokens 已在 #37 接入 |
| 混元 Hy4 preview 无同口径分数 | AA 至今未收录（862 个 slug 里腾讯只有 hy3 系），只有厂商自报数据 42 项（见 #39） | 它不进任何榜；自报口径与 AA 存在中位 +3.3 的系统性偏移，只能按附表内部相对名次用；等 AA 收录后走 watchlist 自动补上 |
| Hy4 的唯一第三方信号未入库 | Code Arena Elo 1624 (名次 9–17)、WebDev Arena 1641±15 (Preliminary) 取自第三方镜像 aitntnews，本机直连 lmarena.ai 失败 | 可信度不足，只登记在 YAML 注释；要入库需拿到 lmarena 原始页 |
| `context_window` / `time_per_task_s` 前端未渲染 | 数据已在 `data.json` 的 `models[]` 里，榜单视图与模型详情没有这两列 | 下一步补 UI：上下文窗口决定能否一次读下整份交接文档，单任务耗时决定夜里能跑多少个任务 |
| `enrich_metadata.py` 已并入 `refresh_data.py` | 默认只拉"还缺元数据"的模型，补过之后这一步近乎零成本 | 但它是**按 model_id 收敛**：若某模型只有兄弟档位行有值，带分行仍留 NULL，导出层靠跨行合并兜底 |
| 详情页抓取偶发 curl rc=35（TLS 抖动） | 首轮 33 个目标失败 8 个，重试后只剩 minimax-m3/step-5 一度失败、再试即通过 | 脚本只补 NULL 不覆盖，重跑即可；`k2-horizon-375b-a23b`（参照层）留到下次 --apply |
| 尚未采 2026-09-21 批次 | 榜面仍是 2026-09-20 快照；09-21 干跑显示主批次 544 条（比 09-20 少 1 条，AA 撤了 muse-spark 的一行） | 用户确认本轮数据无误后再决定是否日更；`refresh_data.py --apply` 一条命令即可 |
| 腾讯的榜面身份待定 | `config/vendors.yaml` 里 `tencent: tier: reference`（遵守"严守九家"） | 若要把混元当选型候选，改这一行为 `core` 重跑导出即可 |
| 库里残留 137 行 `provider='unknown'` | 8 月泄漏的范围外模型，不属本批快照，前端不可见 | 不影响榜面；若要彻底清理需单独一次带审计的归档迁移，未做 |
| `scripts/fetch_openrouter_meta.py`、`load_accessibility.py` 未接入 v3 | 可访问性标签仍是旧数据或空 | 上下文窗口已改由 AA 详情页提供（#37），OpenRouter 通道不再必需，仍未接入 |
| AA 不提供逐项评测日期 | 全 payload 唯一日期是 `releaseDate` | 分数只能标"某日 AA 快照"，已按用户要求如实标注 |
| 无自动调度 | `settings.yaml: ingestion.schedule` 无代码读取；AA 加密化后全自动不可靠 | 采集节奏人工触发 |
| mypy 未安装 | `project_rules.md §4.1` 要求 ruff/mypy/pytest 三道闸门，只跑了 ruff+pytest | 类型检查缺位 |
| 发布仍是手动 | CI 只发布静态 `frontend/`，不跑 Python | 见 docs/deploy.md |
| 前端「榜单」视图为本次新增 | 本机浏览器实测过四个视图 + 三榜切换 + 零 console 错误；最后一轮数据刷新后浏览器工具超时，改用不依赖 DOM 的字段契约校验（node 脚本核对前端实际访问的每个字段路径）代替 | 上线后需在真机再看一遍榜单视图与自报数据块 |

## 本次数据批次

- 快照日 **2026-09-20**，抓取时刻 2026-09-19T20:23Z，页面 1,232,493 B，
  sha256 `d20f0a55bc5129b36e27a29c8226463e4045d4516ca09cd314574282173f176e`
- 带分模型 31 条 → 入库 26 个模型（**核心 18** + 参照 8）/ 31 个推理档位
  （随后第二次更新补到 29 / 34，见上一节 #32–#35）
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

