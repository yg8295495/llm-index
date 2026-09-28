"""Benchmark Registry — 配置驱动的维度+数据源注册表

设计目标：
- 新增数据源 = 改 yaml + 实现 collector 类，不改 registry 代码
- registry 只负责: 加载 yaml / 列出维度 / 列出数据源 / 取配置 / 反射加载 collector 类

配置结构 (benchmarks.yaml v4, 2026-06-19):
    dimensions:           # 顶层是维度
      factual:
        weight: 0.25
        sources: { ... }  # 维度下的数据源
      workflow:
        weight: 0.25
        sources: { ... }
      engineering:
        weight: 0.20
        sources: { ... }
      cost:
        weight: 0.15
        sources: { ... }
      preference:
        weight: 0.15
        sources: { ... }  # LMArena, 待入库
    tags: { ... }         # 标签(不评分)
    model_scope: { ... }  # 模型范围
"""

import importlib
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from rich.console import Console

console = Console()


class BenchmarkRegistry:
    """维度+数据源注册表（单例风格，类方法 API）

    使用：
        BenchmarkRegistry.list_dimensions()              -> ["workflow", "engineering", ...]
        BenchmarkRegistry.list_sources()                 -> ["arena", "swebench", ...]
        BenchmarkRegistry.get_dimension("workflow")      -> {name, weight, sources, ...}
        BenchmarkRegistry.get_source("arena")            -> {name, tier, collector, ...}
        BenchmarkRegistry.get_collector_class("arena")   -> <class ArenaCollector>
    """

    _config: Optional[Dict[str, Any]] = None
    _config_path: Optional[Path] = None

    # ===== 加载 =====

    @classmethod
    def _default_config_path(cls) -> Path:
        """默认配置文件路径: 项目根/config/benchmarks.yaml"""
        return Path(__file__).resolve().parents[2] / "config" / "benchmarks.yaml"

    @classmethod
    def load(cls, config_path: Optional[Path] = None, force_reload: bool = False) -> Dict[str, Any]:
        """加载 yaml 配置的 dimensions 段(默认缓存,force_reload=True 强制重读)"""
        if not force_reload and cls._config is not None and config_path is None:
            return cls._config
        path = config_path or cls._default_config_path()
        if not path.exists():
            raise FileNotFoundError(f"benchmark 配置文件不存在: {path}")
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        cls._config_path = path
        # 读 dimensions 段 (v4 结构, 2026-06-19)
        cls._config = data.get("dimensions", {})
        if not cls._config:
            console.print(f"[yellow]⚠ 配置 {path.name} 的 dimensions 段为空[/yellow]")
        else:
            console.print(f"[green]✓ 加载 {len(cls._config)} 个维度 ({path.name})[/green]")
        return cls._config

    @classmethod
    def reset(cls) -> None:
        """清空缓存(测试用)"""
        cls._config = None
        cls._config_path = None

    # ===== 维度查询 =====

    @classmethod
    def list_dimensions(cls) -> List[str]:
        """所有评分维度键(排除 tags)"""
        return [k for k, v in cls.load().items()
                if k != "tags" and v.get("weight", 0) > 0]

    @classmethod
    def list_all_dimensions(cls) -> List[str]:
        """所有维度键(含 tags)"""
        return list(cls.load().keys())

    @classmethod
    def get_dimension(cls, dim_key: str) -> Dict[str, Any]:
        """取单个维度配置"""
        config = cls.load()
        if dim_key not in config:
            raise KeyError(
                f"维度 '{dim_key}' 不在注册表. "
                f"可用: {list(config.keys())}"
            )
        return config[dim_key]

    @classmethod
    def get_dimension_weight(cls, dim_key: str) -> float:
        """取维度权重"""
        return cls.get_dimension(dim_key).get("weight", 0.0)

    # ===== 数据源查询 =====

    @classmethod
    def list_sources(cls, dim_key: Optional[str] = None) -> List[str]:
        """所有数据源键(可按维度筛选)

        Args:
            dim_key: 维度键。None=所有维度, "engineering"=仅 engineering 下的
        """
        sources: List[str] = []
        config = cls.load()
        if dim_key:
            dim = config.get(dim_key, {})
            sources.extend(dim.get("sources", {}).keys())
        else:
            for dim_key_iter, dim in config.items():
                if dim_key_iter == "tags":
                    continue
                sources.extend(dim.get("sources", {}).keys())
        return sources

    @classmethod
    def get_source(cls, source_key: str) -> Dict[str, Any]:
        """取单个数据源配置(自动搜索所有维度)"""
        config = cls.load()
        for dim_key, dim in config.items():
            if dim_key == "tags":
                continue
            sources = dim.get("sources", {})
            if source_key in sources:
                result = sources[source_key].copy()
                result["_dimension"] = dim_key
                return result
        raise KeyError(
            f"数据源 '{source_key}' 不在注册表. "
            f"可用: {cls.list_sources()}"
        )

    @classmethod
    def list_sources_by_dimension(cls, dim_key: str) -> List[str]:
        """按维度列出数据源(含子维度)"""
        return cls.list_sources(dim_key)

    @classmethod
    def list_sources_by_tier(cls, tier: str) -> List[str]:
        """按 tier 筛选数据源 (primary/secondary)"""
        result = []
        for source_key in cls.list_sources():
            cfg = cls.get_source(source_key)
            if cfg.get("tier") == tier:
                result.append(source_key)
        return result

    # ===== Collector 类加载 =====

    @classmethod
    def get_collector_class(cls, source_key: str) -> Any:
        """通过反射加载 collector 类

        约定: collector 字段指定模块名 (如 "arena"),
        类名自动推导为 PascalCase + "Collector" (如 "ArenaCollector").
        特殊映射: swe_bench -> SWEBenchCollector.
        """
        cfg = cls.get_source(source_key)
        module_name = cfg.get("collector")
        if not module_name:
            raise ValueError(f"数据源 '{source_key}' 配置缺少 'collector' 字段")

        # 自动推导类名: collector 字段 → PascalCase + Collector
        _special_mappings = {
            "swe_bench": "SWEBenchCollector",
            "livecodebench": "LiveCodeBenchCollector",
            "gpqa": "GPQACollector",
            "openrouter_discoverer": "OpenRouterDiscoverer",
        }
        if module_name in _special_mappings:
            class_name = _special_mappings[module_name]
        else:
            class_name = module_name.replace("_", " ").title().replace(" ", "") + "Collector"

        module_path = f"src.collector.{module_name}"
        try:
            module = importlib.import_module(module_path)
        except ImportError as e:
            raise ImportError(
                f"无法加载 collector 模块 '{module_path}': {e}. "
                f"请确认 src/collector/{module_name}.py 存在."
            ) from e
        if not hasattr(module, class_name):
            raise AttributeError(
                f"模块 '{module_path}' 中找不到类 '{class_name}'"
            )
        return getattr(module, class_name)

    # ===== 元信息 =====

    @classmethod
    def get_dimensions(cls) -> Dict[str, Dict[str, Any]]:
        """读 yaml 里的 dimensions 段 (兼容旧 API)"""
        return cls.load()

    @classmethod
    def get_model_scope(cls) -> Dict[str, Any]:
        """读 yaml 里的 model_scope 段"""
        path = cls._config_path or cls._default_config_path()
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data.get("model_scope", {})

    @classmethod
    def get_tags(cls) -> Dict[str, Any]:
        """读 yaml 里的 tags 段(不参与评分的标签)"""
        config = cls.load()
        return config.get("tags", {})

    @classmethod
    def list_providers(cls) -> List[str]:
        """列出 model_scope 中的所有 provider key"""
        scope = cls.get_model_scope()
        return list(scope.get("providers", {}).keys())
