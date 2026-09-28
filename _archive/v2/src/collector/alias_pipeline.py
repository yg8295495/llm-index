"""Alias Pipeline — 模型名标准化

核心职责:
1. 加载手动确认的 aliases.yaml
2. 启发式匹配 (fuzzy) 生成候选映射
3. 未匹配的模型进入待审核队列

Canonical ID = OpenRouter model ID (provider/model-slug)
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml
from rich.console import Console
from rich.table import Table

console = Console()

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "aliases.yaml"


class AliasPipeline:
    """模型名标准化管道"""

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or CONFIG_PATH
        self._alias_map: Dict[str, str] = {}  # alias -> canonical
        self._canonical_info: Dict[str, dict] = {}  # canonical -> metadata
        self._load_config()

    def _load_config(self):
        """加载 aliases.yaml"""
        if not self.config_path.exists():
            console.print(f"[yellow]⚠ aliases.yaml 不存在: {self.config_path}[/yellow]")
            return

        with open(self.config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        entries = data.get("aliases", [])
        for entry in entries:
            canonical = entry["canonical"]
            aliases = entry.get("aliases", [])
            sources = entry.get("sources", [])

            self._canonical_info[canonical] = {
                "aliases": aliases,
                "sources": sources,
            }

            # canonical 本身也是自己的 alias
            self._alias_map[canonical] = canonical
            for alias in aliases:
                self._alias_map[alias] = canonical

        console.print(f"[green]✓ 加载 {len(entries)} 个 alias 条目, "
                       f"共 {len(self._alias_map)} 个映射[/green]")

    def resolve(self, name: str) -> Optional[str]:
        """解析模型名 → canonical ID

        优先级:
        1. 精确匹配 aliases.yaml
        2. 启发式匹配 (slug 化后比较)
        3. 返回 None (未匹配)
        """
        # 1. 精确匹配
        if name in self._alias_map:
            return self._alias_map[name]

        # 2. slug 化匹配
        slug = self._slugify(name)
        for alias, canonical in self._alias_map.items():
            if self._slugify(alias) == slug:
                return canonical

        # 3. 部分匹配 (canonical ID 的 model 部分包含在 name 中)
        # 例如 "claude-4-5-opus" 匹配 "anthropic/claude-opus-4-5"
        for alias, canonical in self._alias_map.items():
            canonical_model = canonical.split("/")[-1]
            if canonical_model in slug or slug in canonical_model:
                return canonical

        return None

    def resolve_all(
        self, names: List[str]
    ) -> Tuple[Dict[str, str], List[str]]:
        """批量解析模型名

        Returns:
            (resolved, unmatched)
            resolved: {原始名: canonical ID}
            unmatched: 未匹配的原始名列表
        """
        resolved = {}
        unmatched = []

        for name in names:
            canonical = self.resolve(name)
            if canonical:
                resolved[name] = canonical
            else:
                unmatched.append(name)

        return resolved, unmatched

    @staticmethod
    def _slugify(name: str) -> str:
        """将模型名转为 slug 格式用于比较"""
        # 去括号内容
        s = re.sub(r"\([^)]*\)", "", name)
        # 去版本号后缀 (如 -2024-08-06)
        s = re.sub(r"-\d{4}-\d{2}-\d{2}", "", s)
        # 小写 + 统一分隔符
        s = s.lower().strip()
        s = re.sub(r"[\s\.\_]+", "-", s)
        s = re.sub(r"-+", "-", s)
        s = s.strip("-")
        return s

    def report(self, names: List[str]):
        """输出匹配报告"""
        resolved, unmatched = self.resolve_all(names)

        table = Table(title="Alias Pipeline Report")
        table.add_column("原始名", style="cyan")
        table.add_column("Canonical ID", style="green")

        for name, canonical in sorted(resolved.items()):
            table.add_row(name, canonical)

        console.print(table)

        if unmatched:
            console.print(f"\n[yellow]⚠ {len(unmatched)} 个模型未匹配:[/yellow]")
            for name in sorted(unmatched):
                console.print(f"  - {name}")
        else:
            console.print("\n[green]✓ 所有模型均已匹配[/green]")

        return resolved, unmatched
