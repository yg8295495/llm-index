#!/usr/bin/env python3
"""Terminal Bench Hard 详细数据采集脚本

采集内容：
1. Score 排名（已有）
2. Cost per Task 详细分解（input/cache/reasoning/answer）
3. Token Usage 详细分解（reasoning/answer）
4. 评测方法论

数据来源: https://artificialanalysis.ai/evaluations/terminalbench-hard
"""

from datetime import datetime
from pathlib import Path

# 从 WebFetch 获取的 HTML 内容
HTML_CONTENT = """
[从之前获取的页面内容，模型顺序]

# Score 排名（按分数从高到低）
SCORE_RANKING = [
    "Claude Fable 5 (with fallback)",
    "GPT-5.5 (xhigh)",
    "GPT-5.5 (high)",
    "Claude Opus 4.8 (max)",
    "GPT-5.5 (medium)",
    "Gemini 3.1 Pro Preview",
    "Claude Sonnet 4.6 (max)",
    "GPT-5.4 mini (xhigh)",
    "Qwen3.7 Max",
    "DeepSeek V4 Pro (Max)",
    "Muse Spark",
    "Kimi K2.6",
    "MiMo-V2.5-Pro",
    "GLM-5.1",
    "MiniMax-M3",
    "Gemini 3.5 Flash",
    "Qwen3.5 397B A17B",
    "MiniMax-M2.7",
    "Grok 4.3 (high)",
    "Gemma 4 31B",
    "Nemotron 3 Ultra",
    "DeepSeek V4 Flash (Max)",
    "Mistral Medium 3.5",
    "Claude 4.5 Haiku",
    "Nova 2.0 Pro Preview (medium)",
    "gpt-oss-120b (high)",
    "K2 Think V2",
    "gpt-oss-20B (high)",
    "Solar Pro 3",
]

# Score 值（%）
SCORE_VALUES = [62.9, 60.6, 59.8, 58.3, 57.6, 53.8, 53.0, 52.3, 50.8, 46.2,
                45.5, 43.9, 43.2, 43.2, 42.4, 40.9, 40.9, 39.4, 37.9, 36.4,
                36.4, 35.6, 33.3, 27.3, 24.2, 23.5, 10.6, 7.6, 6.8]

# Cost per Task 排名（按成本从低到高）
COST_RANKING = [
    "gpt-oss-20B (high)",
    "gpt-oss-120b (high)",
    "DeepSeek V4 Flash (Max)",
    "MiniMax-M2.7",
    "MiniMax-M3",
    "MiMo-V2.5-Pro",
    "DeepSeek V4 Pro (Max)",
    "Nemotron 3 Ultra",
    "Qwen3.5 397B A17B",
    "GLM-5.1",
    "Kimi K2.6",
    "Grok 4.3 (high)",
    "Nova 2.0 Pro Preview (medium)",
    "Claude 4.5 Haiku",
    "Gemini 3.1 Pro Preview",
    "Gemini 3.5 Flash",
    "Mistral Medium 3.5",
    "GPT-5.4 mini (xhigh)",
    "Qwen3.7 Max",
    "GPT-5.5 (medium)",
    "Claude Sonnet 4.6 (max)",
    "GPT-5.5 (high)",
    "GPT-5.5 (xhigh)",
    "Claude Opus 4.8 (max)",
    "Claude Fable 5 (with fallback)",
    "K2 Think V2",
    "Solar Pro 3",
    "Muse Spark",
    "K2 Think V2",  # 重复，需要核实
]

# Cost 值（$/task）
COST_VALUES = [0.02, 0.07, 0.11, 0.17, 0.21, 0.27, 0.31, 0.41, 0.47, 0.52,
               0.55, 0.62, 0.64, 0.81, 0.92, 1.07, 1.19, 1.21, 1.32, 1.41,
               1.42, 1.50, 1.63, 2.25, 4.94, 5.91]

# Token Usage 排名（按 token 数从低到高）
TOKEN_RANKING = [
    "GPT-5.5 (medium)",
    "Muse Spark",
    "MiniMax-M3",
    "GPT-5.5 (high)",
    "MiMo-V2.5-Pro",
    "Gemini 3.5 Flash",
    "Kimi K2.6",
    "MiniMax-M2.7",
    "Grok 4.3 (high)",
    "Nemotron 3 Ultra",
    "Gemma 4 31B",
    "Qwen3.5 397B A17B",
    "Gemini 3.1 Pro Preview",
    "GPT-5.5 (xhigh)",
    "GLM-5.1",
    "Nova 2.0 Pro Preview (medium)",
    "Claude 4.5 Haiku",
    "gpt-oss-20B (high)",
    "DeepSeek V4 Flash (Max)",
    "Qwen3.7 Max",
    "Mistral Medium 3.5",
    "Solar Pro 3",
    "gpt-oss-120b (high)",
    "Claude Sonnet 4.6 (max)",
    "DeepSeek V4 Pro (Max)",
    "Claude Fable 5 (with fallback)",
    "K2 Think V2",
    "Claude Opus 4.8 (max)",
    "GPT-5.4 mini (xhigh)",
]

# Token 值（output tokens per task）
TOKEN_VALUES = [12, 13, 14, 15, 16, 16, 17, 18, 18, 18, 19, 19, 20, 21, 25, 26,
                27, 27, 29, 30, 31, 31, 31, 34, 35, 42, 44, 45, 48, 49, 59, 63, 72,
                78, 84, 100, 245]
"""

def parse_provider(model_name: str) -> str:
    """从模型名推断厂商"""
    name_lower = model_name.lower()
    if "claude" in name_lower:
        return "Anthropic"
    elif "gpt" in name_lower or "openai" in name_lower:
        return "OpenAI"
    elif "gemini" in name_lower or "gemma" in name_lower:
        return "Google"
    elif "deepseek" in name_lower:
        return "DeepSeek"
    elif "qwen" in name_lower:
        return "Qwen"
    elif "glm" in name_lower:
        return "GLM"
    elif "kimi" in name_lower or "moonshot" in name_lower or "k2" in name_lower:
        return "Kimi"
    elif "minimax" in name_lower:
        return "MiniMax"
    elif "mimo" in name_lower:
        return "MiMo"
    elif "grok" in name_lower:
        return "xAI"
    elif "mistral" in name_lower:
        return "Mistral"
    elif "nvidia" in name_lower or "nemotron" in name_lower:
        return "NVIDIA"
    elif "nova" in name_lower or "amazon" in name_lower:
        return "Amazon"
    elif "solar" in name_lower:
        return "Upstage"
    else:
        return "Unknown"

def build_cost_map():
    """构建成本映射表"""
    cost_ranking = [
        "gpt-oss-20B (high)",
        "gpt-oss-120b (high)",
        "DeepSeek V4 Flash (Max)",
        "MiniMax-M2.7",
        "MiniMax-M3",
        "MiMo-V2.5-Pro",
        "DeepSeek V4 Pro (Max)",
        "Nemotron 3 Ultra",
        "Qwen3.5 397B A17B",
        "GLM-5.1",
        "Kimi K2.6",
        "Grok 4.3 (high)",
        "Nova 2.0 Pro Preview (medium)",
        "Claude 4.5 Haiku",
        "Gemini 3.1 Pro Preview",
        "Gemini 3.5 Flash",
        "Mistral Medium 3.5",
        "GPT-5.4 mini (xhigh)",
        "Qwen3.7 Max",
        "GPT-5.5 (medium)",
        "Claude Sonnet 4.6 (max)",
        "GPT-5.5 (high)",
        "GPT-5.5 (xhigh)",
        "Claude Opus 4.8 (max)",
        "Claude Fable 5 (with fallback)",
    ]

    # Cost per task values (from HTML)
    cost_values = [0.02, 0.07, 0.11, 0.17, 0.21, 0.27, 0.31, 0.41, 0.47, 0.52,
                   0.55, 0.62, 0.64, 0.81, 0.92, 1.07, 1.19, 1.21, 1.32, 1.41,
                   1.42, 1.50, 1.63, 2.25, 4.94]

    # 合并映射
    cost_map = {}
    for i, model in enumerate(cost_ranking):
        if i < len(cost_values):
            cost_map[model] = cost_values[i]

    return cost_map

def build_token_map():
    """构建 Token 使用量映射表"""
    # 从 HTML 提取的 token 数据（按顺序对应）
    # 表格中的模型顺序（从低到高）
    token_ranking = [
        "GPT-5.5 (medium)",
        "Muse Spark",
        "MiniMax-M3",
        "GPT-5.5 (high)",
        "MiMo-V2.5-Pro",
        "Gemini 3.5 Flash",
        "Kimi K2.6",
        "MiniMax-M2.7",
        "Grok 4.3 (high)",
        "Nemotron 3 Ultra",
        "Gemma 4 31B",
        "Qwen3.5 397B A17B",
        "Gemini 3.1 Pro Preview",
        "GPT-5.5 (xhigh)",
        "GLM-5.1",
        "Nova 2.0 Pro Preview (medium)",
        "Claude 4.5 Haiku",
        "gpt-oss-20B (high)",
        "DeepSeek V4 Flash (Max)",
        "Qwen3.7 Max",
        "Mistral Medium 3.5",
        "Solar Pro 3",
        "gpt-oss-120b (high)",
        "Claude Sonnet 4.6 (max)",
        "DeepSeek V4 Pro (Max)",
        "Claude Fable 5 (with fallback)",
        "K2 Think V2",
        "Claude Opus 4.8 (max)",
        "GPT-5.4 mini (xhigh)",
    ]

    # Output tokens per task (k)
    token_values = [12, 13, 14, 15, 16, 16, 17, 18, 18, 18, 19, 19, 20, 21, 25, 26,
                    27, 27, 29, 30, 31, 31, 31, 34, 35, 42, 44, 45, 48]

    token_map = {}
    for i, model in enumerate(token_ranking):
        if i < len(token_values):
            token_map[model] = token_values[i] * 1000  # 转换为 tokens

    return token_map

def generate_yaml():
    """生成完整的 YAML 数据"""

    # Score 数据（从现有数据）
    score_ranking = [
        ("Claude Fable 5 (with fallback)", "Anthropic", 62.9),
        ("GPT-5.5 (xhigh)", "OpenAI", 60.6),
        ("GPT-5.5 (high)", "OpenAI", 59.8),
        ("Claude Opus 4.8 (max)", "Anthropic", 58.3),
        ("GPT-5.5 (medium)", "OpenAI", 57.6),
        ("Gemini 3.1 Pro Preview", "Google", 53.8),
        ("Claude Sonnet 4.6 (max)", "Anthropic", 53.0),
        ("GPT-5.4 mini (xhigh)", "OpenAI", 52.3),
        ("Qwen3.7 Max", "Qwen", 50.8),
        ("DeepSeek V4 Pro (Max)", "DeepSeek", 46.2),
        ("Muse Spark", "Muse", 45.5),
        ("Kimi K2.6", "Kimi", 43.9),
        ("MiMo-V2.5-Pro", "MiMo", 43.2),
        ("GLM-5.1", "GLM", 43.2),
        ("MiniMax-M3", "MiniMax", 42.4),
        ("Gemini 3.5 Flash", "Google", 40.9),
        ("Qwen3.5 397B A17B", "Qwen", 40.9),
        ("MiniMax-M2.7", "MiniMax", 39.4),
        ("Grok 4.3 (high)", "xAI", 37.9),
        ("Gemma 4 31B", "Google", 36.4),
        ("Nemotron 3 Ultra", "NVIDIA", 36.4),
        ("DeepSeek V4 Flash (Max)", "DeepSeek", 35.6),
        ("Mistral Medium 3.5", "Mistral", 33.3),
        ("Claude 4.5 Haiku", "Anthropic", 27.3),
        ("Nova 2.0 Pro Preview (medium)", "Amazon", 24.2),
        ("gpt-oss-120b (high)", "OpenAI", 23.5),
        ("K2 Think V2", "Kimi", 10.6),
        ("gpt-oss-20B (high)", "OpenAI", 7.6),
        ("Solar Pro 3", "Upstage", 6.8),
    ]

    cost_map = build_cost_map()
    token_map = build_token_map()

    # 构建完整数据
    models = []
    for i, (model_name, provider, score) in enumerate(score_ranking):
        model_entry = {
            "model": model_name,
            "provider": provider,
            "score_pct": score,
            "rank": i + 1,
            "source_type": "authoritative_leaderboard",
            "source_credibility": 0.8,
        }

        # 添加 Cost 数据
        if model_name in cost_map:
            model_entry["cost_per_task_usd"] = cost_map[model_name]

        # 添加 Token 数据
        if model_name in token_map:
            model_entry["output_tokens_per_task"] = token_map[model_name]

        # 添加 reasoning model 标注
        if "reasoning" in model_name.lower() or "(max)" in model_name.lower() or \
           "(xhigh)" in model_name.lower() or "(high)" in model_name.lower() or \
           "(medium)" in model_name.lower():
            model_entry["is_reasoning_model"] = True

        models.append(model_entry)

    return {
        "benchmark": "Terminal-Bench Hard",
        "source_url": "https://artificialanalysis.ai/evaluations/terminalbench-hard",
        "collected_at": datetime.now().strftime("%Y-%m-%d"),
        "total_models": len(models),
        "models": models,
        "methodology": {
            "description": "Terminal-Bench Hard 是 Terminal-Bench 的困难子集",
            "developer": "Stanford University + Laude Institute",
            "evaluation_method": "Docker 环境中的自动化验证脚本",
            "task_categories": [
                "软件工程 (Software Engineering)",
                "系统管理 (System Administration)",
                "数据处理 (Data Processing)",
                "游戏 (Games)",
            ],
            "scoring": "通过率 = 成功完成任务数 / 总任务数 × 100%",
            "notes": "Hard 版本只包含最难的任务，任务难以通过训练数据模式匹配"
        }
    }

if __name__ == "__main__":
    import yaml

    data = generate_yaml()

    # 保存到 YAML
    output_path = Path("/Users/LiYuan/apps/llm-index/data/raw/terminalbench_hard_detailed_2026-06-17.yaml")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False)

    print(f"数据已保存到: {output_path}")
    print(f"共 {data['total_models']} 个模型")
