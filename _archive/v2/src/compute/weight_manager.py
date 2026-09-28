"""权重配置与动态调整模块"""

from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from rich.console import Console

console = Console()


class WeightManager:
    """权重管理器"""

    def __init__(self, config_path: Optional[str] = None):
        """初始化权重管理器

        Args:
            config_path: 配置文件路径; 缺省用项目根下的 config/settings.yaml。
                原先写死相对路径 "config/settings.yaml", 换个工作目录就
                读到空配置并静默返回空权重 —— 见 docs/changelog.md #9。
        """
        if config_path is None:
            from src.paths import config_path as _cfg

            path = _cfg("settings.yaml")
        else:
            path = Path(config_path)
        self.config_path = Path(path)
        self.config = self._load_config()
        if not self.config:
            raise RuntimeError(
                f"读不到权重配置或配置为空: {self.config_path} (cwd={Path.cwd()})"
            )
        self.weights = self.config.get("weights", {})
        self.weights_no_preference = self.config.get("weights_no_preference", {})
        self.presets = self.config.get("presets", {})

    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        if not self.config_path.exists():
            console.print(f"[yellow]警告: 配置文件不存在 {self.config_path}[/yellow]")
            return {}

        with open(self.config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def get_weights(self, preset_name: Optional[str] = None) -> Dict[str, float]:
        """获取权重配置

        Args:
            preset_name: 预设名称，如果为 None 则使用默认权重

        Returns:
            维度名称到权重的映射
        """
        if preset_name is None:
            return self.weights.copy()

        preset = self.presets.get(preset_name)
        if preset is None:
            console.print(f"[yellow]警告: 预设 {preset_name} 不存在，使用默认权重[/yellow]")
            return self.weights.copy()

        return preset.get("weights", {}).copy()

    def get_weights_no_preference(self) -> Dict[str, float]:
        """获取 preference 无数据时的等效权重（自动重新分配）

        Returns:
            重新分配后的权重映射，preference 权重为 0
        """
        if self.weights_no_preference:
            return self.weights_no_preference.copy()

        # 兜底：从默认权重手动计算
        total_without_pref = sum(
            w for k, w in self.weights.items() if k != "preference"
        )
        if total_without_pref == 0:
            return self.weights.copy()

        result = {}
        for key, weight in self.weights.items():
            if key == "preference":
                result[key] = 0.0
            else:
                result[key] = round(weight / total_without_pref, 2)

        return result

    def validate_weights(self, weights: Dict[str, float]) -> bool:
        """验证权重配置是否有效

        Args:
            weights: 权重配置

        Returns:
            是否有效
        """
        if not weights:
            console.print("[red]错误: 权重配置为空[/red]")
            return False

        total = sum(weights.values())
        if abs(total - 1.0) > 1e-6:
            console.print(f"[red]错误: 权重总和为 {total}，应为 1.0[/red]")
            return False

        for dimension, weight in weights.items():
            if weight < 0:
                console.print(f"[red]错误: 维度 {dimension} 的权重为负数 {weight}[/red]")
                return False

        return True

    def list_presets(self) -> Dict[str, str]:
        """列出所有可用的预设

        Returns:
            预设名称到描述的映射
        """
        return {
            name: preset.get("description", "无描述")
            for name, preset in self.presets.items()
        }

    def get_preset_info(self, preset_name: str) -> Optional[Dict[str, Any]]:
        """获取预设的详细信息

        Args:
            preset_name: 预设名称

        Returns:
            预设信息字典，如果不存在则返回 None
        """
        return self.presets.get(preset_name)

    def update_weights(self, new_weights: Dict[str, float]) -> None:
        """更新默认权重配置

        Args:
            new_weights: 新的权重配置
        """
        if not self.validate_weights(new_weights):
            raise ValueError("无效的权重配置")

        self.weights = new_weights.copy()
        console.print("[green]✓ 权重配置已更新[/green]")

    def save_config(self) -> None:
        """保存配置到文件"""
        self.config["weights"] = self.weights

        with open(self.config_path, "w", encoding="utf-8") as f:
            yaml.dump(self.config, f, allow_unicode=True, default_flow_style=False)

        console.print(f"[green]✓ 配置已保存到 {self.config_path}[/green]")
