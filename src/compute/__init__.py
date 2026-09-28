"""计算模块 — v3 只保留 scoring (双榜 + 参照模型同标尺取分)

v2 的 Normalizer / WeightManager / IndexCalculator 已归档到
_archive/v2/src/compute/, 原因见 _archive/v2/README.md。
权重与维度的唯一权威是 config/settings.yaml 与 config/benchmarks.yaml,
由 scoring.py 直接读取, 不再经过 WeightManager 的 CWD 相对路径逻辑。
"""
