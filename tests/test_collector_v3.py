"""测试 v3 采集与映射 (2026-09-20)

覆盖 AA 改版后的新解析路径, 以及"不覆盖历史 / 无 source_url 不入库"两条硬约束。
"""

import json
import sqlite3

import pytest

from src.collector import aa_omniscience as AA
from src.collector import mapping as M
from src.storage import snapshot_store as S

# ---------------------------------------------------------------------------
# 解析层
# ---------------------------------------------------------------------------


def _rsc_html(payloads: list[str]) -> str:
    parts = [
        '<script>self.__next_f.push([1,"%s"])</script>'
        % json.dumps(p, ensure_ascii=False)[1:-1]
        for p in payloads
    ]
    return "<html>" + "".join(parts) + "</html>"


def test_decode_rsc_and_extract_array():
    payload = 'x:{"initialModels":[' + json.dumps({"slug": "a", "omniscience": 1.0}) + \
              '],"models":[' + json.dumps({"slug": "a", "name": "A"}) + ']}'
    blob = AA.decode_rsc(_rsc_html([payload]))
    assert AA.extract_array(blob, "initialModels")[0]["slug"] == "a"
    assert AA.extract_array(blob, "models")[0]["name"] == "A"


def test_extract_array_survives_brackets_inside_strings():
    payload = '{"models":[{"slug":"a","name":"A [beta] {x}"}]}'
    blob = AA.decode_rsc(_rsc_html([payload]))
    assert AA.extract_array(blob, "models")[0]["name"] == "A [beta] {x}"


def test_decode_rsc_raises_when_no_chunks():
    with pytest.raises(AA.PayloadError):
        AA.decode_rsc("<html><body>nothing</body></html>")


def test_parse_page_raises_when_no_scored_models():
    page = AA.RawPage(url="u", http_status=200, html=_rsc_html(['{"models":[]}']),
                      fetched_at="2026-09-20T00:00:00+00:00")
    with pytest.raises(AA.PayloadError):
        AA.parse_page(page)


def test_raw_page_has_sha256_and_size():
    page = AA.RawPage(url="u", http_status=200, html="abc", fetched_at="t")
    assert page.bytes == 3
    assert len(page.sha256) == 64


# ---------------------------------------------------------------------------
# 命名与厂商归属
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("raw,expected", [
    ("glm-5-3", "glm-5.3"),
    ("gpt-5-6-terra", "gpt-5.6-terra"),
    ("deepseek-v4-1-flash", "deepseek-v4.1-flash"),
    ("qwen3-8-27b", "qwen3.8-27b"),
    ("minimax-m3", "minimax-m3"),
    ("k2-horizon-375b-a23b", "k2-horizon-375b-a23b"),
    ("gpt-oss-120b", "gpt-oss-120b"),
    ("muse-spark-1-3", "muse-spark-1.3"),
])
def test_dotted_version_normalization(raw, expected):
    assert M.dotted(raw) == expected


def test_dotted_does_not_invent_double_dash():
    """回归: 早期实现多插一个连字符, 产出 glm--5.3 这种脏 ID。"""
    out = M.dotted("glm-5-3")
    assert "--" not in out
    assert out == "glm-5.3"


def test_creator_slug_three_level_fallback():
    ids = {"cid1": "anthropic"}
    assert M.creator_slug({"slug": "zai"}) == "zai"
    assert M.creator_slug({"name": "NVIDIA", "logo": "/img/logos/nvidia_small.svg"}) == "nvidia"
    assert M.creator_slug({"id": "cid1", "name": "Anthropic"}, ids) == "anthropic"
    assert M.creator_slug(None) == ""


def test_creator_logo_handles_missing_vendor_id():
    assert M.creator_slug({"id": "x", "logo": "/img/logos/thinking_machines.svg"}) == "thinking-machines"


# ---------------------------------------------------------------------------
# 映射层
# ---------------------------------------------------------------------------


@pytest.fixture
def mapped(fake_scored, fake_registry, benchmarks_cfg, vendors):
    return M.map_records(fake_scored, fake_registry, benchmarks_cfg, vendors, {}, {})


def test_variant_rows_share_one_model_id(mapped):
    models, _ = mapped
    ids = [m.row.model_id for m in models]
    assert ids.count("zhipu/glm-9.9") == 2, "同基座的两个档位应共用 model_id"
    levels = sorted(m.row.reasoning_level for m in models if m.row.model_id == "zhipu/glm-9.9")
    assert levels == ["high", "max"]


def test_aa_creator_slug_maps_to_project_namespace(mapped):
    models, _ = mapped
    glm = next(m for m in models if m.row.aa_slug == "glm-9-9")
    assert glm.row.provider == "zhipu", "AA 用 zai, 本项目历史命名空间是 zhipu"
    assert glm.row.tier == "core"


def test_unknown_creator_becomes_unclassified_not_guessed(mapped):
    models, _ = mapped
    other = next(m for m in models if m.row.aa_slug == "other-9")
    assert other.row.tier == "unclassified"
    assert other.row.needs_manual_review == 1
    assert any("不在 config/vendors.yaml" in n for n in other.row.notes)


def test_release_date_and_deprecated_captured(mapped):
    models, _ = mapped
    glm = next(m for m in models if m.row.aa_slug == "glm-9-9")
    assert glm.row.release_date == "2026-09-01"
    assert glm.row.deprecated == 0


def test_evals_only_for_registered_fields(mapped, aa_benchmark_fields):
    models, _ = mapped
    for m in models:
        for e in m.evals:
            assert e.dimension in ("factual", "workflow", "engineering", "cost", "preference")
            assert e.confidence and 0 < e.confidence <= 1


def test_negative_score_is_preserved_not_clamped(mapped):
    models, _ = mapped
    high = next(m for m in models if m.row.aa_slug == "glm-9-9-high")
    omni = next(e for e in high.evals if e.benchmark == "aa_omniscience")
    assert omni.score_raw == -12.5, "AA-Omniscience 可为负, 采集层不得钳位"


def test_run_cost_derived_from_tokens_and_price(mapped):
    models, _ = mapped
    glm = next(m for m in models if m.row.aa_slug == "glm-9-9")
    gpqa = next(e for e in glm.evals if e.benchmark == "gpqa")
    # input 100000 × $1 + (answer 200000 + reasoning 700000) × $4 = 0.1 + 3.6
    assert gpqa.run_cost_usd == pytest.approx(3.7)
    assert gpqa.input_tokens == 100000
    assert gpqa.output_tokens == 900000
    hle = next(e for e in glm.evals if e.benchmark == "hle")
    assert hle.run_cost_usd == pytest.approx((50000 * 1 + 100000 * 4) / 1e6)


def test_breakdown_json_preserved(mapped):
    models, _ = mapped
    glm = next(m for m in models if m.row.aa_slug == "glm-9-9")
    omni = next(e for e in glm.evals if e.benchmark == "aa_omniscience")
    assert omni.breakdown["hallucinationRate"] == 0.2


def test_no_collisions_on_synthetic_batch(mapped):
    _models, stats = mapped
    assert stats["collisions"] == []


def test_excluded_vendor_is_dropped_entirely(fake_scored, fake_registry, benchmarks_cfg, vendors):
    v = dict(vendors)
    v["zai"] = dict(v["zai"], tier="excluded")
    models, stats = M.map_records(fake_scored, fake_registry, benchmarks_cfg, v, {}, {})
    assert stats["excluded"] == 2
    assert all(m.row.provider != "zhipu" for m in models)


def test_existing_db_identity_is_reused_and_rename_reported(fake_scored, fake_registry,
                                                           benchmarks_cfg, vendors):
    db_by_slug = {"glm-9-9": (7, "zhipu/glm-9-9-old", "", "zhipu")}
    models, stats = M.map_records(fake_scored, fake_registry, benchmarks_cfg, vendors,
                                  db_by_slug, {})
    glm = next(m for m in models if m.row.aa_slug == "glm-9-9")
    assert glm.existing_pk == 7, "命中库内既有行时应原地更新, 不新建"
    assert glm.rename_from == "zhipu/glm-9-9-old"
    assert stats["renames"][0]["to"] == "zhipu/glm-9.9"


# ---------------------------------------------------------------------------
# 存储层
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_db(tmp_path):
    """按 ORM 建表 + ensure_schema 补列, 得到一个干净的可写库"""
    from sqlalchemy import create_engine
    from src.storage.models import Base

    path = tmp_path / "t.db"
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    engine.dispose()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    S.ensure_schema(conn)
    conn.commit()
    yield conn
    conn.close()


def _fake_models(fake_scored, fake_registry, benchmarks_cfg, vendors):
    models, _ = M.map_records(fake_scored, fake_registry, benchmarks_cfg, vendors, {}, {})
    return models


def test_write_requires_source_url(temp_db, fake_scored, fake_registry, benchmarks_cfg, vendors):
    models = _fake_models(fake_scored, fake_registry, benchmarks_cfg, vendors)
    sid = S.upsert_snapshot(temp_db, "2026-09-20", {
        "source": "artificial_analysis", "source_url": "https://example.invalid/x",
        "fetched_at": "2026-09-20T00:00:00+00:00"})
    urls = {}  # 一个都不给
    report = S.write(temp_db, models, sid, "2026-09-20", urls, dry_run=False)
    assert report.rejected, "无 source_url 必须被拒绝而不是静默入库"
    assert report.evals_written == 0


def test_write_then_rerun_is_idempotent(temp_db, fake_scored, fake_registry,
                                        benchmarks_cfg, vendors):
    models = _fake_models(fake_scored, fake_registry, benchmarks_cfg, vendors)
    urls = {e.benchmark: "https://example.invalid/src" for m in models for e in m.evals}
    sid = S.upsert_snapshot(temp_db, "2026-09-20", {
        "source": "artificial_analysis", "source_url": "https://example.invalid/x",
        "fetched_at": "2026-09-20T00:00:00+00:00"})
    first = S.write(temp_db, models, sid, "2026-09-20", urls, dry_run=False)
    temp_db.commit()
    total_after_first = temp_db.execute("SELECT COUNT(*) FROM benchmark_evals").fetchone()[0]

    second = S.write(temp_db, models, sid, "2026-09-20", urls, dry_run=False)
    temp_db.commit()
    total_after_second = temp_db.execute("SELECT COUNT(*) FROM benchmark_evals").fetchone()[0]

    assert first.evals_written > 0
    assert second.evals_written == 0
    assert second.evals_skipped_existing == first.evals_written
    assert total_after_first == total_after_second, "同一快照重复跑不得产生新行"


def test_new_snapshot_appends_without_touching_history(temp_db, fake_scored, fake_registry,
                                                       benchmarks_cfg, vendors):
    models = _fake_models(fake_scored, fake_registry, benchmarks_cfg, vendors)
    urls = {e.benchmark: "https://example.invalid/src" for m in models for e in m.evals}
    s1 = S.upsert_snapshot(temp_db, "2026-09-20", {
        "source": "artificial_analysis", "source_url": "u", "fetched_at": "t1"})
    S.write(temp_db, models, s1, "2026-09-20", urls, dry_run=False)
    temp_db.commit()
    n1 = temp_db.execute("SELECT COUNT(*) FROM benchmark_evals").fetchone()[0]

    s2 = S.upsert_snapshot(temp_db, "2026-10-20", {
        "source": "artificial_analysis", "source_url": "u", "fetched_at": "t2"})
    S.write(temp_db, models, s2, "2026-10-20", urls, dry_run=False)
    temp_db.commit()
    n2 = temp_db.execute("SELECT COUNT(*) FROM benchmark_evals").fetchone()[0]

    assert n2 == n1 * 2, "第二批应追加而不是覆盖"
    dates = [r[0] for r in temp_db.execute(
        "SELECT DISTINCT observed_at FROM benchmark_evals ORDER BY observed_at")]
    assert dates == ["2026-09-20", "2026-10-20"]


def test_every_eval_row_carries_source_url(temp_db, fake_scored, fake_registry,
                                           benchmarks_cfg, vendors):
    models = _fake_models(fake_scored, fake_registry, benchmarks_cfg, vendors)
    urls = {e.benchmark: "https://example.invalid/" + e.benchmark for m in models for e in m.evals}
    sid = S.upsert_snapshot(temp_db, "2026-09-20", {
        "source": "artificial_analysis", "source_url": "u", "fetched_at": "t"})
    S.write(temp_db, models, sid, "2026-09-20", urls, dry_run=False)
    temp_db.commit()
    bad = temp_db.execute(
        "SELECT COUNT(*) FROM benchmark_evals WHERE source_url IS NULL OR source_url = ''"
    ).fetchone()[0]
    assert bad == 0


def test_snapshot_records_page_fingerprint(temp_db):
    sid = S.upsert_snapshot(temp_db, "2026-09-20", {
        "source": "artificial_analysis",
        "source_url": "https://artificialanalysis.ai/evaluations/omniscience",
        "fetched_at": "2026-09-19T20:00:19+00:00",
        "html_sha256": "deadbeef", "html_bytes": 1232493})
    row = temp_db.execute("SELECT * FROM snapshots WHERE id = ?", (sid,)).fetchone()
    assert row["html_sha256"] == "deadbeef"
    # 同一天的重复采集应更新而不是新建快照行
    again = S.upsert_snapshot(temp_db, "2026-09-20", {
        "source": "artificial_analysis", "source_url": "u2", "fetched_at": "t2"})
    assert again == sid
