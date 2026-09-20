"""快照式存储层 (v3, 2026-09-20)

职责: 只追加、不覆盖的评测数据写入。

对旧采集器的三处纠正 (见 docs/changelog.md #2 #3 #12):
    1. collect_aa_v2.py 的 --force-refresh 会先 `DELETE FROM benchmark_evals
       WHERE model_pk=?` 再重插, 直接把历史抹掉。本层禁止任何删除,
       同一模型的新一轮数值以 snapshot_id 区分追加。
    2. 旧层把"跑脚本的日期"写进 observed_at, 冒充观测日期。本层区分
       observed_at (= AA 快照日) 与 collected_at (= 真实抓取 UTC 时刻),
       并在 snapshots 表记录页面 sha256 与 URL, 便于他人核验。
    3. 用户要求"无 source_url 不存储": 本层对每条评测写入 source_url,
       取自 config/benchmarks.yaml 的对应数据源; 配置里缺 source_url 的
       数据源会被拒绝入库而不是静默通过。
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

from src.collector.mapping import MappedModel

DDL_SNAPSHOTS = """
CREATE TABLE IF NOT EXISTS snapshots (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date DATE NOT NULL UNIQUE,      -- AA 快照日 (本站口径: 采集当日)
    source        TEXT NOT NULL,
    source_url    TEXT NOT NULL,
    fetched_at    TEXT NOT NULL,             -- 真实抓取 UTC 时刻
    html_sha256   TEXT,
    html_bytes    INTEGER,
    parsed_path   TEXT,                      -- 解析产物落盘位置, 供复现
    model_count   INTEGER,
    eval_count    INTEGER,
    notes         TEXT,
    created_at    TEXT DEFAULT (datetime('now'))
)
"""

DDL_RENAMES = """
CREATE TABLE IF NOT EXISTS model_id_renames (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    old_model_id TEXT NOT NULL,
    new_model_id TEXT NOT NULL,
    aa_slug      TEXT,
    reason       TEXT,
    snapshot_id  INTEGER REFERENCES snapshots(id),
    changed_at   TEXT DEFAULT (datetime('now'))
)
"""

# models 表补充列: 厂商范围层级 + AA 权威归属字段
MODEL_NEW_COLUMNS = {
    "tier": "VARCHAR(20)",
    "aa_base_slug": "VARCHAR(100)",
    "deprecated": "INTEGER DEFAULT 0",
    "openness_index": "FLOAT",
    "answer_speed": "FLOAT",
    "active_params": "FLOAT",
    "time_per_task_s": "FLOAT",
    "needs_manual_review": "INTEGER DEFAULT 0",
}

EVAL_NEW_COLUMNS = {
    "snapshot_id": "INTEGER REFERENCES snapshots(id)",
    "dimension": "VARCHAR(20)",
    "direction": "VARCHAR(10)",
    "source_url": "TEXT",
    "run_cost_usd": "FLOAT",
}

UNIQUE_EVAL_INDEX = """
CREATE UNIQUE INDEX IF NOT EXISTS uq_eval_model_benchmark_snapshot
ON benchmark_evals(model_pk, benchmark, snapshot_id)
"""

LOOKUP_EVAL_INDEX = """
CREATE INDEX IF NOT EXISTS idx_eval_benchmark_snapshot
ON benchmark_evals(benchmark, snapshot_id)
"""


@dataclass
class WriteReport:
    snapshot_id: int | None = None
    models_new: int = 0
    models_updated: int = 0
    evals_written: int = 0
    evals_skipped_existing: int = 0
    renames: list[dict[str, str]] = field(default_factory=list)
    provider_fixes: list[dict[str, str]] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)


def ensure_schema(conn: sqlite3.Connection) -> list[str]:
    """建表 + 补列, 返回本次新增的内容描述 (幂等)"""
    changes: list[str] = []
    conn.execute(DDL_SNAPSHOTS)
    conn.execute(DDL_RENAMES)
    existing_cols = {r[1] for r in conn.execute("PRAGMA table_info(models)")}
    for name, ddl in MODEL_NEW_COLUMNS.items():
        if name not in existing_cols:
            conn.execute(f"ALTER TABLE models ADD COLUMN {name} {ddl}")
            changes.append(f"models.{name} {ddl}")
    existing_cols = {r[1] for r in conn.execute("PRAGMA table_info(benchmark_evals)")}
    for name, ddl in EVAL_NEW_COLUMNS.items():
        if name not in existing_cols:
            conn.execute(f"ALTER TABLE benchmark_evals ADD COLUMN {name} {ddl}")
            changes.append(f"benchmark_evals.{name} {ddl}")
    # 唯一索引: 同一快照内一个模型一个 benchmark 只能有一条。
    # 老库若存在脏重复会让建索引失败, 这里显式报出来而不是静默跳过,
    # 因为"跳过"会让下一轮的幂等判断失去依据。
    conn.execute(LOOKUP_EVAL_INDEX)
    dup = conn.execute(
        """SELECT COUNT(*) FROM (
             SELECT 1 FROM benchmark_evals
             GROUP BY model_pk, benchmark, snapshot_id HAVING COUNT(*) > 1)"""
    ).fetchone()[0]
    if dup:
        raise RuntimeError(
            f"benchmark_evals 里有 {dup} 组 (model, benchmark, snapshot) 重复行, "
            "无法建立唯一索引; 请先人工核对再重跑"
        )
    conn.execute(UNIQUE_EVAL_INDEX)
    changes.append("index uq_eval_model_benchmark_snapshot (UNIQUE)")
    return changes


def backfill_legacy_snapshots(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """把历史数据按 observed_at 归组成快照行。

    旧库有三个观测日 (2026-06-17 LMArena / 06-18 首次 AA / 08-09 二次 AA),
    它们没有 snapshots 记录。补上之后"取最新快照"的查询才对全部数据成立。
    注意: 06-18 与 08-09 的 observed_at 是旧脚本写入的"跑批日", 语义上确实
    等于我们的采集日, 因此可以直接作为快照日使用, 但 notes 里要写明来源不可靠。
    """
    made = []
    for row in conn.execute(
        "SELECT DISTINCT observed_at FROM benchmark_evals WHERE observed_at IS NOT NULL"
    ):
        date = row[0]
        cur = conn.execute("SELECT id FROM snapshots WHERE snapshot_date = ?", (date,))
        if cur.fetchone():
            continue
        n_evals = conn.execute(
            "SELECT COUNT(*) FROM benchmark_evals WHERE observed_at = ?", (date,)
        ).fetchone()[0]
        n_models = conn.execute(
            """SELECT COUNT(DISTINCT model_pk) FROM benchmark_evals WHERE observed_at = ?""",
            (date,),
        ).fetchone()[0]
        sources = [
            r[0]
            for r in conn.execute(
                "SELECT DISTINCT source FROM benchmark_evals WHERE observed_at = ?", (date,)
            )
        ]
        conn.execute(
            """INSERT INTO snapshots (snapshot_date, source, source_url, fetched_at,
                                      model_count, eval_count, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                date,
                "+".join(sources) or "unknown",
                "https://artificialanalysis.ai/evaluations/omniscience",
                f"{date}T00:00:00+00:00",
                n_models,
                n_evals,
                "回填快照: 由旧采集脚本产生, 无页面指纹 (html_sha256 缺失), "
                "observed_at 为跑批日期, 数据可信度低于 v3 采集",
            ),
        )
        sid = conn.execute("SELECT id FROM snapshots WHERE snapshot_date = ?", (date,)).fetchone()[0]
        conn.execute(
            """UPDATE benchmark_evals SET snapshot_id = ?
               WHERE observed_at = ? AND snapshot_id IS NULL""",
            (sid, date),
        )
        made.append({"snapshot_id": sid, "date": date, "evals": n_evals, "models": n_models})
    return made


def load_identity_index(
    conn: sqlite3.Connection,
) -> tuple[dict[str, tuple[int, str, str, str]], dict[str, tuple[int, str, str, str]]]:
    """(aa_slug -> 身份, aa_base_slug -> 身份); 身份 = (pk, model_id, reasoning_level, provider)"""
    by_slug: dict[str, tuple[int, str, str, str]] = {}
    by_base: dict[str, tuple[int, str, str, str]] = {}
    for pk, mid, level, provider, slug, base in conn.execute(
        "SELECT id, model_id, reasoning_level, provider, aa_slug, aa_base_slug FROM models"
    ):
        ident = (pk, mid, level or "", provider or "")
        if slug:
            by_slug[slug] = ident
        if base and base not in by_base:
            by_base[base] = ident
    return by_slug, by_base


def upsert_snapshot(
    conn: sqlite3.Connection,
    snapshot_date: str,
    meta: dict[str, Any],
) -> int:
    cur = conn.execute("SELECT id FROM snapshots WHERE snapshot_date = ?", (snapshot_date,))
    row = cur.fetchone()
    if row:
        conn.execute(
            """UPDATE snapshots SET source=?, source_url=?, fetched_at=?, html_sha256=?,
                      html_bytes=?, parsed_path=?, notes=? WHERE id=?""",
            (meta["source"], meta["source_url"], meta["fetched_at"], meta.get("html_sha256"),
             meta.get("html_bytes"), meta.get("parsed_path"), meta.get("notes"), row[0]),
        )
        return int(row[0])
    conn.execute(
        """INSERT INTO snapshots (snapshot_date, source, source_url, fetched_at, html_sha256,
                                  html_bytes, parsed_path, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (snapshot_date, meta["source"], meta["source_url"], meta["fetched_at"],
         meta.get("html_sha256"), meta.get("html_bytes"), meta.get("parsed_path"),
         meta.get("notes")),
    )
    return int(conn.execute(
        "SELECT id FROM snapshots WHERE snapshot_date = ?", (snapshot_date,)
    ).fetchone()[0])


def _model_params(row, tier_col_ok: bool = True) -> dict[str, Any]:
    return {
        "model_id": row.model_id,
        "reasoning_level": row.reasoning_level or "",
        "aa_slug": row.aa_slug,
        "aa_base_slug": row.aa_base_slug,
        "display_name": row.display_name,
        "provider": row.provider,
        "family": row.family,
        "release_date": row.release_date,
        "deprecated": row.deprecated,
        "tier": row.tier,
        "context_window": row.context_window,
        "context_window_fmt": row.context_window_fmt,
        "supports_vision": row.supports_vision,
        "supports_audio": row.supports_audio,
        "is_reasoning": row.is_reasoning,
        "open_source": row.open_source,
        "size_class": row.size_class,
        "parameters": row.parameters,
        "active_params": row.active_params,
        "pricing_input": row.pricing_input,
        "pricing_output": row.pricing_output,
        "pricing_cache_input": row.pricing_cache_input,
        "openness_index": row.openness_index,
        "answer_speed": row.answer_speed,
        "time_per_task_s": row.time_per_task_s,
        "needs_manual_review": row.needs_manual_review,
        "status": "deprecated" if row.deprecated else "active",
    }


def _upd_params(params: dict[str, Any]) -> dict[str, Any]:
    """UPDATE 用的字段集: 剔除主键列, 并剔除本次取不到的 None。

    为什么剔除 None (changelog #37): AA 榜单页 payload 压根没有 contextWindow*,
    只有单模型详情页有。若允许 None 覆盖, 则"先补采详情页元数据、再跑一次日更"
    会把已经拿到的上下文窗口重新洗成 NULL。追加式快照不该抹掉已知事实。
    """
    return {k: v for k, v in params.items()
            if k not in ("model_id", "reasoning_level") and v is not None}


def write(
    conn: sqlite3.Connection,
    mapped: Iterable[MappedModel],
    snapshot_id: int,
    snapshot_date: str,
    source_urls: dict[str, str],
    dry_run: bool = True,
) -> WriteReport:
    """追加一个快照的数据。幂等: 同一 (model, benchmark, snapshot) 已存在则跳过。

    source_urls: benchmark canonical key -> 来源 URL。缺失即拒绝写入该条,
    落实"无 source_url 不存储"。
    """
    report = WriteReport(snapshot_id=snapshot_id)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    for m in mapped:
        p = _model_params(m.row)
        # 先把本快照将写入/将拒绝的评测条数算出来, 保证干跑与实跑报数口径一致。
        # (旧实现在干跑分支里对命中库内已有的模型提前 continue, 导致 2026-09-20
        #  首次干跑只报了 17 个新模型的 261 行, 实际 545 行 —— 见 changelog #13)
        eligible = [e for e in m.evals if source_urls.get(e.benchmark)]
        if dry_run:
            report.evals_written += len(eligible)
            report.rejected.extend(
                {"model_id": p["model_id"], "benchmark": e.benchmark,
                 "reason": "config/benchmarks.yaml 未提供 source_url, 按标准拒绝入库"}
                for e in m.evals if not source_urls.get(e.benchmark)
            )
        if m.existing_pk:
            report.models_updated += 1
            if m.rename_from:
                report.renames.append(
                    {"from": m.rename_from, "to": p["model_id"], "aa_slug": p["aa_slug"]}
                )
            if m.provider_fixed_from:
                report.provider_fixes.append(
                    {"model_id": p["model_id"], "from": m.provider_fixed_from,
                     "to": p["provider"]}
                )
            if dry_run:
                continue
            upd = _upd_params(p)
            assignments = ", ".join(f"{k} = :{k}" for k in upd)
            conn.execute(
                f"UPDATE models SET {assignments}, updated_at = :__now WHERE id = :__pk",
                {**upd, "__now": now, "__pk": m.existing_pk},
            )
            if m.rename_from:
                # 重命名要落到同一 model_id 的全部推理档位行, 否则同一个物理模型
                # 会在榜单里出现两条 (旧 ID 的档位 + 新 ID 的档位)。
                clash = conn.execute(
                    """SELECT 1 FROM models
                       WHERE model_id = ? AND reasoning_level IN
                             (SELECT reasoning_level FROM models WHERE model_id = ?)
                         AND id NOT IN (SELECT id FROM models WHERE model_id = ?)""",
                    (p["model_id"], m.rename_from, m.rename_from),
                ).fetchone()
                if clash:
                    report.rejected.append(
                        {"model_id": p["model_id"], "benchmark": "-",
                         "reason": f"重命名 {m.rename_from} → {p['model_id']} 会与既有行撞唯一键, 已跳过"}
                    )
                else:
                    conn.execute(
                        "UPDATE models SET model_id = ?, updated_at = ? WHERE model_id = ?",
                        (p["model_id"], now, m.rename_from),
                    )
                    conn.execute(
                        """INSERT INTO model_id_renames
                           (old_model_id, new_model_id, aa_slug, reason, snapshot_id)
                           VALUES (?, ?, ?, ?, ?)""",
                        (m.rename_from, p["model_id"], p["aa_slug"],
                         "v3 采集按 AA creator/release 规范命名", snapshot_id),
                    )
                    conn.execute(
                        """INSERT OR IGNORE INTO model_alias (alias, canonical_model_id, source)
                           VALUES (?, ?, 'id_rename')""",
                        (m.rename_from, p["model_id"]),
                    )
            pk = m.existing_pk
        else:
            # 调用方的身份索引可能来自上一次读取 (例如同一次采集里两个 AA slug
            # 规范化成同一个 (model_id, reasoning_level), 或重复跑同一个快照)。
            # 这里再查一次库, 命中就转成更新而不是让 INSERT 撞唯一键崩掉 ——
            # "可反复跑" 要求存储层自身幂等, 不能只依赖调用方传对 existing_pk。
            hit = conn.execute(
                "SELECT id FROM models WHERE model_id = ? AND reasoning_level = ?",
                (p["model_id"], p["reasoning_level"]),
            ).fetchone()
            if hit:
                pk = int(hit[0])
                report.models_updated += 1
                if dry_run:
                    continue
                upd = _upd_params(p)
                assignments = ", ".join(f"{k} = :{k}" for k in upd)
                conn.execute(
                    f"UPDATE models SET {assignments}, updated_at = :__now WHERE id = :__pk",
                    {**upd, "__now": now, "__pk": pk},
                )
            else:
                report.models_new += 1
                if dry_run:
                    pk = None
                else:
                    cur = conn.execute(
                    """INSERT INTO models (model_id, reasoning_level, aa_slug, aa_base_slug,
                        display_name, provider, family, release_date, deprecated, tier,
                        context_window, context_window_fmt, supports_vision, supports_audio,
                        is_reasoning, open_source, size_class, parameters, active_params,
                        pricing_input, pricing_output, pricing_cache_input, openness_index,
                        answer_speed, time_per_task_s, needs_manual_review, status,
                        created_at, updated_at)
                       VALUES (:model_id, :reasoning_level, :aa_slug, :aa_base_slug,
                        :display_name, :provider, :family, :release_date, :deprecated, :tier,
                        :context_window, :context_window_fmt, :supports_vision,
                        :supports_audio, :is_reasoning, :open_source, :size_class, :parameters,
                        :active_params, :pricing_input, :pricing_output, :pricing_cache_input,
                        :openness_index, :answer_speed, :time_per_task_s,
                        :needs_manual_review, :status,
                        :__now, :__now)""",
                        {**p, "__now": now},
                    )
                    pk = int(cur.lastrowid)

        if dry_run:
            continue

        assert pk is not None
        for e in m.evals:
            url = source_urls.get(e.benchmark)
            if not url:
                report.rejected.append(
                    {"model_id": p["model_id"], "benchmark": e.benchmark,
                     "reason": "config/benchmarks.yaml 未提供 source_url, 按标准拒绝入库"}
                )
                continue
            exists = conn.execute(
                """SELECT 1 FROM benchmark_evals
                   WHERE model_pk = ? AND benchmark = ? AND snapshot_id = ?""",
                (pk, e.benchmark, snapshot_id),
            ).fetchone()
            if exists:
                report.evals_skipped_existing += 1
                continue
            # 命名参数而非位置参数: 19 列的 INSERT 用位置绑定极易错位 (v2 就出过),
            # 这里让每个值与列名显式配对。
            conn.execute(
                """INSERT INTO benchmark_evals
                   (model_pk, benchmark, score, score_raw, score_type, input_tokens,
                    output_tokens, reasoning_tokens, cost_usd, breakdown, source, confidence,
                    observed_at, collected_at, snapshot_id, dimension, direction, source_url,
                    run_cost_usd)
                   VALUES (:model_pk, :benchmark, NULL, :score_raw, :score_type, :input_tokens,
                    :output_tokens, :reasoning_tokens, NULL, :breakdown, :source, :confidence,
                    :observed_at, :collected_at, :snapshot_id, :dimension, :direction,
                    :source_url, :run_cost_usd)""",
                {
                    "model_pk": pk,
                    "benchmark": e.benchmark,
                    "score_raw": e.score_raw,
                    "score_type": e.score_type,
                    "input_tokens": e.input_tokens,
                    "output_tokens": e.output_tokens,
                    "reasoning_tokens": e.reasoning_tokens,
                    "breakdown": json.dumps(e.breakdown, ensure_ascii=False) if e.breakdown else None,
                    "source": e.source,
                    "confidence": e.confidence,
                    "observed_at": snapshot_date,
                    "collected_at": now,
                    "snapshot_id": snapshot_id,
                    "dimension": e.dimension,
                    "direction": e.direction,
                    "source_url": url,
                    "run_cost_usd": e.run_cost_usd,
                },
            )
            report.evals_written += 1
    return report
