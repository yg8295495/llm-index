#!/usr/bin/env python3
"""初始化数据库脚本"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from src.storage import DatabaseManager

console = Console()


def seed_database():
    """初始化数据库"""
    console.print("[bold blue]=== LLM-INDEX 数据库初始化 ===[/bold blue]\n")

    try:
        # 创建数据库管理器
        db_manager = DatabaseManager()

        # 创建所有表
        console.print("[bold]1. 创建数据库表[/bold]")
        db_manager.create_tables()

        console.print("\n[bold green]✓ 数据库初始化完成[/bold green]")
        console.print("\n已创建的表:")
        console.print("  - model_benchmark (模型基准测试得分)")
        console.print("  - model_pricing (模型价格数据)")
        console.print("  - composite_scores (综合指数)")
        console.print("  - agent_eval_scores (Agent 评测得分)")

    except Exception as e:
        console.print(f"[bold red]✗ 数据库初始化失败: {e}[/bold red]")
        raise


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="初始化 LLM-INDEX 数据库")
    parser.add_argument("--drop", action="store_true", help="删除现有表后重新创建")

    args = parser.parse_args()

    if args.drop:
        console.print("[yellow]警告: 即将删除所有表并重新创建[/yellow]")
        response = input("确认操作 (yes/no): ")
        if response.lower() == "yes":
            db_manager = DatabaseManager()
            db_manager.drop_tables()
            seed_database()
        else:
            console.print("[dim]操作已取消[/dim]")
    else:
        seed_database()
