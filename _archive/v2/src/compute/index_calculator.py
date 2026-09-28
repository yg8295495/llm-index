"""综合指数计算与历史趋势模块"""

from typing import Any, Dict, List, Optional

import numpy as np
from rich.console import Console

from .normalizer import Normalizer
from .weight_manager import WeightManager

console = Console()


class IndexCalculator:
    """综合指数计算器"""

    def __init__(
        self,
        weight_manager: Optional[WeightManager] = None,
        normalizer: Optional[Normalizer] = None,
        config: Optional[Dict[str, Any]] = None
    ):
        """初始化指数计算器

        Args:
            weight_manager: 权重管理器
            normalizer: 归一化器
            config: 额外配置
        """
        self.weight_manager = weight_manager or WeightManager()
        self.normalizer = normalizer or Normalizer()
        self.config = config or {}

        # 缩放配置
        scaling_config = self.config.get("scaling", {})
        self.scaling_enabled = scaling_config.get("enabled", True)
        self.base_epoch = scaling_config.get("base_epoch", "2024-01")
        self.scaling_method = scaling_config.get("method", "linear")

    def calculate_composite_index(
        self,
        normalized_scores: Dict[str, Dict[str, float]],
        weights: Optional[Dict[str, float]] = None,
        preset_name: Optional[str] = None
    ) -> Dict[str, float]:
        """计算综合指数

        Args:
            normalized_scores: 维度 -> (模型 ID -> 归一化得分) 的映射
            weights: 自定义权重，如果为 None 则使用默认或预设权重
            preset_name: 预设名称

        Returns:
            模型 ID -> 综合指数值 的映射
        """
        # 获取权重
        if weights is None:
            weights = self.weight_manager.get_weights(preset_name)

        # 验证权重
        if not self.weight_manager.validate_weights(weights):
            raise ValueError("无效的权重配置")

        # 获取所有模型 ID
        all_model_ids = set()
        for dimension_scores in normalized_scores.values():
            all_model_ids.update(dimension_scores.keys())

        # 计算每个模型的综合指数
        composite_indices = {}

        for model_id in all_model_ids:
            index_value = 0.0

            for dimension, weight in weights.items():
                dimension_scores = normalized_scores.get(dimension, {})
                score = dimension_scores.get(model_id, 0.0)
                index_value += weight * score

            composite_indices[model_id] = index_value

        console.print(f"[green]✓ 综合指数计算完成，共 {len(composite_indices)} 个模型[/green]")
        return composite_indices

    def calculate_dimension_contributions(
        self,
        model_id: str,
        normalized_scores: Dict[str, Dict[str, float]],
        weights: Optional[Dict[str, float]] = None,
        preset_name: Optional[str] = None
    ) -> Dict[str, float]:
        """计算单个模型各维度的贡献值

        Args:
            model_id: 模型 ID
            normalized_scores: 维度 -> (模型 ID -> 归一化得分) 的映射
            weights: 自定义权重
            preset_name: 预设名称

        Returns:
            维度 -> 贡献值 的映射
        """
        if weights is None:
            weights = self.weight_manager.get_weights(preset_name)

        contributions = {}

        for dimension, weight in weights.items():
            dimension_scores = normalized_scores.get(dimension, {})
            score = dimension_scores.get(model_id, 0.0)
            contributions[dimension] = weight * score

        return contributions

    def rank_models(
        self,
        composite_indices: Dict[str, float],
        top_n: Optional[int] = None
    ) -> List[tuple]:
        """对模型进行排名

        Args:
            composite_indices: 模型 ID -> 综合指数值 的映射
            top_n: 返回前 N 名，如果为 None 则返回全部

        Returns:
            排名列表，每个元素为 (排名, 模型 ID, 综合指数值)
        """
        sorted_models = sorted(
            composite_indices.items(),
            key=lambda x: x[1],
            reverse=True
        )

        if top_n is not None:
            sorted_models = sorted_models[:top_n]

        rankings = [
            (rank + 1, model_id, index_value)
            for rank, (model_id, index_value) in enumerate(sorted_models)
        ]

        return rankings

    def calculate_trend(
        self,
        historical_indices: List[Dict[str, float]],
        model_id: str
    ) -> Dict[str, Any]:
        """计算单个模型的历史趋势

        Args:
            historical_indices: 历史综合指数列表，每个元素为 epoch -> (模型 ID -> 指数值)
            model_id: 模型 ID

        Returns:
            趋势信息字典
        """
        values = []
        epochs = []

        for epoch_data in historical_indices:
            if model_id in epoch_data:
                values.append(epoch_data[model_id])
                epochs.append(len(values))

        if len(values) < 2:
            return {
                "model_id": model_id,
                "data_points": len(values),
                "trend": "insufficient_data"
            }

        # 计算趋势方向
        arr = np.array(values)
        slope = np.polyfit(epochs, arr, 1)[0]

        if slope > 0.5:
            trend = "strong_up"
        elif slope > 0.1:
            trend = "up"
        elif slope < -0.5:
            trend = "strong_down"
        elif slope < -0.1:
            trend = "down"
        else:
            trend = "stable"

        return {
            "model_id": model_id,
            "data_points": len(values),
            "trend": trend,
            "slope": slope,
            "min_value": float(np.min(arr)),
            "max_value": float(np.max(arr)),
            "current_value": values[-1],
            "average_value": float(np.mean(arr))
        }

    def compare_models(
        self,
        model_ids: List[str],
        normalized_scores: Dict[str, Dict[str, float]],
        weights: Optional[Dict[str, float]] = None,
        preset_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """比较多个模型

        Args:
            model_ids: 要比较的模型 ID 列表
            normalized_scores: 维度 -> (模型 ID -> 归一化得分) 的映射
            weights: 自定义权重
            preset_name: 预设名称

        Returns:
            比较结果字典
        """
        if weights is None:
            weights = self.weight_manager.get_weights(preset_name)

        comparison = {
            "models": {},
            "rankings": [],
            "dimension_leaders": {}
        }

        # 计算每个模型的综合指数和各维度得分
        for model_id in model_ids:
            # 原写法 {dim: {...} for dim, scores in ...} 把外层键 dim 用在了
            # 内层推导式之前, 一旦调用即 NameError (changelog #19)
            per_model = {
                dim: {model_id: scores.get(model_id, 0.0)}
                for dim, scores in normalized_scores.items()
            }
            composite = self.calculate_composite_index(per_model, weights)

            contributions = self.calculate_dimension_contributions(
                model_id, normalized_scores, weights
            )

            comparison["models"][model_id] = {
                "composite_index": composite.get(model_id, 0.0),
                "dimension_scores": {
                    dim: normalized_scores.get(dim, {}).get(model_id, 0.0)
                    for dim in weights.keys()
                },
                "dimension_contributions": contributions
            }

        # 排名
        composite_indices = {
            model_id: data["composite_index"]
            for model_id, data in comparison["models"].items()
        }
        comparison["rankings"] = self.rank_models(composite_indices)

        # 找出每个维度的领先者
        for dimension in weights.keys():
            dimension_scores = {
                model_id: normalized_scores.get(dimension, {}).get(model_id, 0.0)
                for model_id in model_ids
            }
            leader = max(dimension_scores.items(), key=lambda x: x[1])
            comparison["dimension_leaders"][dimension] = {
                "model_id": leader[0],
                "score": leader[1]
            }

        return comparison
