"""维度分数归一化模块"""

from typing import Any, Dict, List, Optional

import numpy as np
from rich.console import Console

console = Console()


class Normalizer:
    """分数归一化器"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """初始化归一化器

        Args:
            config: 归一化配置，包含 method, min_score, max_score, cost_reverse 等
        """
        if config is None:
            config = {}

        self.method = config.get("method", "min-max")
        self.min_score = config.get("min_score", 0)
        self.max_score = config.get("max_score", 100)
        self.cost_reverse = config.get("cost_reverse", True)

    def normalize_minmax(
        self,
        values: List[float],
        reverse: bool = False
    ) -> List[float]:
        """Min-Max 归一化

        Args:
            values: 原始值列表
            reverse: 是否反向归一化（值越小得分越高）

        Returns:
            归一化后的值列表，范围在 [min_score, max_score]
        """
        if not values:
            return []

        arr = np.array(values, dtype=float)
        min_val = np.min(arr)
        max_val = np.max(arr)

        # 避免除以零
        if max_val - min_val == 0:
            normalized = np.full_like(arr, (self.min_score + self.max_score) / 2)
        else:
            normalized = (arr - min_val) / (max_val - min_val)
            normalized = normalized * (self.max_score - self.min_score) + self.min_score

        if reverse:
            normalized = self.max_score - normalized + self.min_score

        return normalized.tolist()

    def normalize_zscore(
        self,
        values: List[float],
        reverse: bool = False
    ) -> List[float]:
        """Z-Score 标准化

        Args:
            values: 原始值列表
            reverse: 是否反向标准化

        Returns:
            标准化后的值列表，映射到 [min_score, max_score]
        """
        if not values:
            return []

        arr = np.array(values, dtype=float)
        mean = np.mean(arr)
        std = np.std(arr)

        # 避免除以零
        if std == 0:
            normalized = np.full_like(arr, (self.min_score + self.max_score) / 2)
        else:
            z_scores = (arr - mean) / std
            # 将 z-score 映射到目标范围（假设 z-score 在 [-3, 3] 范围内）
            normalized = (z_scores + 3) / 6 * (self.max_score - self.min_score) + self.min_score
            normalized = np.clip(normalized, self.min_score, self.max_score)

        if reverse:
            normalized = self.max_score - normalized + self.min_score

        return normalized.tolist()

    def normalize_scores(
        self,
        scores: Dict[str, float],
        dimension: str
    ) -> Dict[str, float]:
        """归一化单个维度的所有模型得分

        Args:
            scores: 模型 ID 到原始得分的映射
            dimension: 维度名称

        Returns:
            模型 ID 到归一化得分的映射
        """
        if not scores:
            return {}

        model_ids = list(scores.keys())
        values = list(scores.values())

        # 判断是否需要反向归一化
        reverse = (dimension == "cost" and self.cost_reverse)

        # 根据配置选择归一化方法
        if self.method == "z-score":
            normalized_values = self.normalize_zscore(values, reverse)
        else:  # default: min-max
            normalized_values = self.normalize_minmax(values, reverse)

        return dict(zip(model_ids, normalized_values))

    def normalize_all_dimensions(
        self,
        all_scores: Dict[str, Dict[str, float]]
    ) -> Dict[str, Dict[str, float]]:
        """归一化所有维度的得分

        Args:
            all_scores: 维度 -> (模型 ID -> 原始得分) 的映射

        Returns:
            维度 -> (模型 ID -> 归一化得分) 的映射
        """
        normalized_all = {}

        for dimension, scores in all_scores.items():
            normalized_all[dimension] = self.normalize_scores(scores, dimension)
            console.print(
                f"[green]✓ 维度 {dimension} 归一化完成，"
                f"共 {len(scores)} 个模型[/green]"
            )

        return normalized_all
