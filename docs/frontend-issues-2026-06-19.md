# 前端问题清单（2026-06-19）

> 来源：用户深度测试反馈
> 更新：2026-06-19 — 全部可执行项已完成

## A. Apple Light 主题太白刺眼 ✅
- **方案**: 背景从纯白改为 #f5f5f7，三主题表面色阶对齐 design-spec.md
- **完成**: CSS 变量已更新，L0-L3 四级表面色阶

## B. 详情页中间列重复当前维度 ✅
- **方案**: 中间列过滤掉当前维度，5卡→4卡=2×2布局
- **完成**: DIMENSIONS.filter 排除当前维度，grid 2列

## C. 详情页维度卡片展开引导不明确 ✅
- **方案**: 第一行2卡默认展开，第二行2卡默认收起+展开提示，级联切换
- **完成**: 前2卡 expanded，后2卡显示"点击展开 ↓"，级联逻辑

## D. 排行榜行内空白大 ✅
- **方案**: "展开"按钮改为小箭头 ▾/▴
- **完成**: action-btn 改为箭头符号

## E. 排序功能缺失 ✅
- **方案**: 排行榜表头加排序（分数/排名）
- **完成**: state.rankingSort + th-sortable 表头点击排序

## F. 聚合显示排序异常 ✅
- **方案**: 确保有数据的模型排在前面
- **完成**: getCompositeRanking() 分离 withScore/withoutScore

## G. 开源/闭源标签映射错误 ✅
- **方案**: 导出脚本做值映射
- **完成**: _normalize_open_source() 5种值→3种 (Open/Proprietary/Hybrid)

## H. 多模态/TTS 标签缺失 ✅
- **方案**: 从 OpenRouter API 获取 modality 更新 DB
- **完成**: 86 个模型更新 supports_vision/supports_audio (43视觉+7视觉音频)

## I. 子维度说明变两行压缩宽度 ✅
- **方案**: CSS 调整子维度说明为两行显示
- **完成**: white-space:normal + line-height:1.3 + max-width:120px

## J. 顶部排行榜需凸显 ✅
- **方案**: top-bar 加背景+2px border + 排行表 accent 色条
- **完成**: top-bar bg + border-bottom + ranking-table::before accent 条

## K. Cost 维度归一化后最贵模型显示 0 分 ✅
- **方案**: 保持0分但加视觉提示区分"无数据"和"成本高"
- **完成**: .cost-zero 红色样式 + "最贵"标签

## L. Gemma 系列模型无数据 ⏳
- **根因**: AA omniscience 页面本身未收录 Gemma
- **方案**: 需从其他数据源补充（OpenRouter / 手动采集）
- **状态**: 待新数据源采集，非前端问题

---

## 设计规范补充修复（2026-06-19 追加）

- font-weight:500 全部改为 400 或 600（4处） ✅
- border-radius 统一: 按钮 6px, Chip 9999px, marker 9999px ✅
- bench-chip 16px→9999px (药丸形) ✅
