"""AA Omniscience payload 解析层 (v3, 2026-09-20)

只负责"从 AA 页面把结构化数据取出来", 不碰数据库, 便于单测。

为什么重写 (见 docs/changelog.md #1):
    AA 于 2026-08 之后改版。旧页面在 RSC flight 流里内嵌 `defaultData`
    数组 (约 8MB, 含全部模型逐项分数); 新版页面缩到约 1.2MB, `defaultData`
    消失, 全量分数改由前端从 `/data/<hash>.txt` (加密 blob + key) 拉取。
    collect_aa_v2.py 因此直接报 "未找到 defaultData chunk" 而失效。

本模块只使用页面 SSR 中仍然公开可见的两部分:
    initialModels  — 当前 AA 默认展示的带分模型 (本批次 31 条, 含约 35 项指标)
    models         — 全量模型注册表 (本批次 653 条, 含 slug / releaseDate / creator)

不逆向 AA 刻意加密的 data blob: 那会引入 ToS 风险与"每次改版即失效"的脆弱性,
而本项目的目标只是九家范围内、当前主流的在用人物模型选型依据。
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass, field
from typing import Any

SOURCE_URL = "https://artificialanalysis.ai/evaluations/omniscience"
MODEL_URL = "https://artificialanalysis.ai/models/{slug}"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) llm-index-collector/3.0"

_CHUNK_RE = re.compile(r'self\.__next_f\.push\(\[\d+,"((?:[^"\\]|\\.)*)"\]')


class PayloadError(RuntimeError):
    """payload 结构不符合预期 (多半是 AA 又改版了)"""


@dataclass
class RawPage:
    """一次抓取的结果, 自带可核验指纹"""

    url: str
    http_status: int
    html: str
    fetched_at: str                      # UTC ISO8601
    sha256: str = field(init=False)
    bytes: int = field(init=False)

    def __post_init__(self) -> None:
        data = self.html.encode("utf-8", "replace")
        self.sha256 = hashlib.sha256(data).hexdigest()
        self.bytes = len(data)


def fetch_page(url: str = SOURCE_URL, timeout: int = 60, html: str | None = None) -> RawPage:
    """抓取 AA 评测页。

    用 curl 而不是 urllib: 该站在 TLS 指纹层对 python-http 有拦截,
    这与本项目全局约定一致 (海外站点直连, 绝不走代理)。
    传入 html 则跳过网络, 供离线单测复现。
    """
    if html is not None:
        return RawPage(url=url, http_status=0, html=html, fetched_at="offline")

    proc = subprocess.run(
        ["curl", "-s", "-L", "--max-time", str(timeout),
         "-A", USER_AGENT, "-w", "\n__HTTP__%{http_code}", url],
        capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        raise PayloadError(f"curl 失败 rc={proc.returncode}: {proc.stderr.strip()[:200]}")
    body, _, code = proc.stdout.rpartition("__HTTP__")
    status = int(code) if code.strip().isdigit() else 0
    if status != 200 or not body.strip():
        raise PayloadError(f"HTTP {status}, 响应体 {len(body)} 字节")
    from datetime import datetime, timezone

    return RawPage(
        url=url,
        http_status=status,
        html=body,
        fetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )


def decode_rsc(html: str) -> str:
    """把 RSC flight 的分片反转义拼接成一整段可搜索文本。"""
    chunks = _CHUNK_RE.findall(html)
    if not chunks:
        raise PayloadError("页面中找不到 self.__next_f.push 分片, AA 可能再次改版")
    out = []
    for raw in chunks:
        try:
            out.append(json.loads('"' + raw + '"'))
        except json.JSONDecodeError:
            # 单片解码失败不应导致整体丢失, 记录后按原文保留
            out.append(raw)
    return "".join(out)


def _match_bracketed(text: str, start: int) -> str | None:
    """从 text[start] 的 '[' 或 '{' 起做括号配平, 返回完整字面量。"""
    open_ch = text[start]
    close_ch = "]" if open_ch == "[" else "}"
    depth = 0
    in_str = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def extract_array(text: str, key: str) -> list[dict[str, Any]]:
    """取出 `"key": [...]` 数组。找不到返回空列表 (由调用方判定是否致命)。"""
    m = re.search(r'"%s":\s*\[' % re.escape(key), text)
    if not m:
        return []
    literal = _match_bracketed(text, text.index("[", m.end() - 1))
    if literal is None:
        raise PayloadError(f"`{key}` 数组括号未配平, 疑似截断")
    try:
        value = json.loads(literal)
    except json.JSONDecodeError as exc:
        raise PayloadError(f"`{key}` 解析失败: {exc}") from exc
    return value if isinstance(value, list) else []


def _is_scored(record: dict[str, Any]) -> bool:
    return isinstance(record, dict) and "slug" in record and (
        "intelligenceIndex" in record or "omniscience" in record or "gdpval" in record
    )


def collect_scored_models(text: str) -> list[dict[str, Any]]:
    """SSR 中带逐项分数的模型记录。

    `initialModels` 是页面图表的默认选中集, 但 AA 在别处以同一形状内联了相同字段,
    因此这里对全部内联对象做一次甄别, 而不是只认一个键名 —— 这样下次它改名时
    不至于整站失效。
    """
    found: dict[str, dict[str, Any]] = {}
    decoder = json.JSONDecoder()
    # \s* 是刻意的: 当前 AA 输出的是无空格压缩 JSON, 但只要对方换成带空格的
    # 格式化输出, 严格匹配就会静默漏掉全部模型（采集看起来成功、其实零记录）。
    for m in re.finditer(r'\{"id":\s*"[0-9a-f]{8}-', text):
        try:
            obj, _ = decoder.raw_decode(text, m.start())
        except ValueError:
            continue
        if _is_scored(obj):
            found[obj["slug"]] = obj
    return list(found.values())


def collect_registry(text: str) -> list[dict[str, Any]]:
    """全量模型注册表 (含 releaseDate, 未必有分数)。"""
    return [r for r in extract_array(text, "models") if isinstance(r, dict) and r.get("slug")]


def parse_page(page: RawPage) -> dict[str, Any]:
    """一次解析的完整产物, 直接落盘为可复现快照。"""
    text = decode_rsc(page.html)
    scored = collect_scored_models(text)
    registry = collect_registry(text)
    if not scored:
        raise PayloadError("未解析到任何带分模型, 采集终止 (不写库)")
    return {
        "source": {
            "url": page.url,
            "http_status": page.http_status,
            "fetched_at": page.fetched_at,
            "html_sha256": page.sha256,
            "html_bytes": page.bytes,
            "rsc_chunks": len(_CHUNK_RE.findall(page.html)),
        },
        "scored_models": scored,
        "registry": registry,
        "counts": {"scored": len(scored), "registry": len(registry)},
    }


def fetch_model_page(slug: str, timeout: int = 90) -> RawPage:
    """抓取 AA 的单模型详情页 /models/<slug>。

    omniscience 页的 SSR 只带 31 个默认对比模型, 但详情页里内联了该模型的
    同口径完整分数 (实测约 3.9MB, 含数百个带分对象)。这是补采单个模型的
    正规路径 —— 不需要碰那个加密 blob。
    """
    page = fetch_page(MODEL_URL.format(slug=slug), timeout=timeout)
    if page.http_status != 200:
        raise PayloadError(f"{slug}: HTTP {page.http_status}")
    return page


def find_scored_record(page: RawPage, slug: str) -> dict[str, Any]:
    """从详情页里取出指定 slug 的带分记录。

    只认 slug 完全匹配的那一条, 不做前缀匹配 —— 详情页同时内联了其它模型的
    对象, 前缀匹配会取错 (例如 hy3 命中 hy3-preview)。
    """
    text = decode_rsc(page.html)
    for rec in collect_scored_models(text):
        if rec.get("slug") == slug:
            return rec
    raise PayloadError(f"详情页里没有 {slug} 的带分记录 (AA 可能未收录该模型)")
