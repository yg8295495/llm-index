"""雷达图数据构建器

维度体系 (v3, 2026-06-17):
  4 个评分维度: workflow / engineering / cost / factual
  engineering 下含 agent_annotation 子维度 (gdpval_aa / terminalbench_hard / bfcl_v4 / apex_agents_aa)
  accessibility 为标签,不参与评分
"""

from typing import Any, Dict, List, Optional

from rich.console import Console

console = Console()


class RadarDataBuilder:
    """雷达图数据构建器"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """初始化雷达图数据构建器

        Args:
            config: 配置字典
        """
        self.config = config or {}

        # 维度标签映射 (v4, 2026-06-19)
        self.dimension_labels = {
            "factual": "事实准确",
            "workflow": "工作流",
            "engineering": "工程能力",
            "cost": "成本",
            "preference": "人类偏好",
        }

        # engineering 子维度标签 (agent_annotation)
        self.sub_dimension_labels = {
            "swe_bench": "SWE-Bench",
            "gdpval_aa": "GDPval-AA",
            "terminalbench_hard": "Terminal-Bench",
            "bfcl_v4": "BFCL V4",
            "apex_agents_aa": "APEX-Agents",
        }

    def build_indicator(
        self,
        dimensions: List[str],
        max_score: float = 100.0
    ) -> List[Dict[str, Any]]:
        """构建雷达图指示器配置

        Args:
            dimensions: 维度列表
            max_score: 最大分数

        Returns:
            指示器配置列表，用于 ECharts radar.indicator
        """
        indicator = []
        for dim in dimensions:
            label = self.dimension_labels.get(dim, dim)
            indicator.append({
                "name": label,
                "max": max_score
            })

        return indicator

    def build_series(
        self,
        model_ids: List[str],
        model_names: Dict[str, str],
        normalized_scores: Dict[str, Dict[str, float]],
        dimensions: List[str]
    ) -> List[Dict[str, Any]]:
        """构建雷达图系列数据

        Args:
            model_ids: 模型 ID 列表
            model_names: 模型 ID 到名称的映射
            normalized_scores: 维度 -> (模型 ID -> 归一化得分) 的映射
            dimensions: 维度列表

        Returns:
            系列数据列表，用于 ECharts radar.series
        """
        series = []

        for model_id in model_ids:
            model_name = model_names.get(model_id, model_id)
            values = []

            for dim in dimensions:
                dim_scores = normalized_scores.get(dim, {})
                score = dim_scores.get(model_id, 0.0)
                values.append(score)

            series_data = {
                "name": model_name,
                "value": values,
                "areaStyle": {
                    "opacity": 0.1
                },
                "lineStyle": {
                    "width": 2
                }
            }

            series.append(series_data)

        return series

    def build_radar_data(
        self,
        model_ids: List[str],
        model_names: Dict[str, str],
        normalized_scores: Dict[str, Dict[str, float]],
        dimensions: Optional[List[str]] = None,
        max_score: float = 100.0
    ) -> Dict[str, Any]:
        """构建完整的雷达图数据

        Args:
            model_ids: 模型 ID 列表
            model_names: 模型 ID 到名称的映射
            normalized_scores: 维度 -> (模型 ID -> 归一化得分) 的映射
            dimensions: 维度列表，如果为 None 则使用所有可用维度
            max_score: 最大分数

        Returns:
            完整的雷达图数据字典
        """
        # 确定要展示的维度
        if dimensions is None:
            dimensions = list(normalized_scores.keys())

        # 构建指示器
        indicator = self.build_indicator(dimensions, max_score)

        # 构建系列数据
        series = self.build_series(
            model_ids,
            model_names,
            normalized_scores,
            dimensions
        )

        radar_data = {
            "indicator": indicator,
            "series": series,
            "metadata": {
                "model_count": len(model_ids),
                "dimension_count": len(dimensions),
                "dimensions": dimensions
            }
        }

        console.print(
            f"[green]✓ 雷达图数据构建完成: "
            f"{len(model_ids)} 个模型, {len(dimensions)} 个维度[/green]"
        )

        return radar_data

    def build_comparison_radar(
        self,
        model_ids: List[str],
        model_names: Dict[str, str],
        dimension_scores: Dict[str, Dict[str, float]],
        preset_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """构建用于模型对比的雷达图数据

        Args:
            model_ids: 要比较的模型 ID 列表
            model_names: 模型 ID 到名称的映射
            dimension_scores: 维度 -> (模型 ID -> 得分) 的映射
            preset_name: 预设名称

        Returns:
            雷达图数据字典
        """
        # 使用所有维度
        dimensions = list(dimension_scores.keys())

        radar_data = self.build_radar_data(
            model_ids=model_ids,
            model_names=model_names,
            normalized_scores=dimension_scores,
            dimensions=dimensions,
            max_score=100.0
        )

        # 添加额外元数据
        radar_data["metadata"]["preset_name"] = preset_name
        radar_data["metadata"]["comparison_mode"] = True

        return radar_data

    def build_single_model_radar(
        self,
        model_id: str,
        model_name: str,
        dimension_scores: Dict[str, float],
        include_sub_dimensions: bool = False
    ) -> Dict[str, Any]:
        """构建单个模型的雷达图数据

        Args:
            model_id: 模型 ID
            model_name: 模型名称
            dimension_scores: 维度 -> 得分 的映射
            include_sub_dimensions: 是否包含 engineering 子维度

        Returns:
            雷达图数据字典
        """
        dimensions = list(dimension_scores.keys())

        # 如果不包含子维度，只保留 4 个评分维度
        if not include_sub_dimensions:
            base_dimensions = ["workflow", "engineering", "cost", "factual"]
            dimensions = [d for d in dimensions if d in base_dimensions]

        # 构建单模型数据
        normalized_scores = {
            dim: {model_id: dimension_scores.get(dim, 0.0)}
            for dim in dimensions
        }

        radar_data = self.build_radar_data(
            model_ids=[model_id],
            model_names={model_id: model_name},
            normalized_scores=normalized_scores,
            dimensions=dimensions,
            max_score=100.0
        )

        radar_data["metadata"]["single_model_mode"] = True

        return radar_data
