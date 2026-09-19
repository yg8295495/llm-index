# 经验索引表

> 快速总览：做过什么、踩过什么坑、有什么结论。按时间倒序排列。
> 详细内容查对应 ID 的 `experience_log.md` 条目。

| 时间 | ID | 类别 | 一句话摘要 |
|------|----|------|-----------|
| 2026-06-18 16:48 | EXP-001 | 采集 | AA 网站无公开 API，Next.js App Router 客户端渲染，数据需 Playwright 拦截或 DOM 提取 |
| 2026-06-18 16:09 | EXP-002 | 数据 | Terminal-Bench 的 cost_per_task_usd/output_tokens_per_task 在 YAML 有但 DB 入库遗漏 |
| 2026-06-18 15:56 | EXP-003 | 前端 | data.json 中 models 是 list 不是 dict，observations 字段不存在（实际键名 benchmarks），需适配器 |
| 2026-06-18 12 :30 | EXP-004 | 工作流 | 修改前必须确认，跳过确认导致返工；前端任务必须走工作流 C（frontend-design skill） |
| 2026-06-18 10:16 | EXP-005 | 设计 | 杂志式编辑风格（装饰元素、低信息密度）不适合信息聚合网站 |
| 2026-06-18 09:47 | EXP-006 | 环境 | Playwright MCP 需 symlink chromium_headless_shell-1228→1200 和 chromium-1228→1200 |
| 2026-06-18 16:48 | EXP-007 | 交互 | 用户同时操作浏览器时 Playwright evaluate 返回 undefined，需独占或用后端方式 |
| 2026-06-18 16:21 | EXP-008 | 数据 | BFCL V4 模型偏旧（榜单更新慢）；Gemma 4 31B 等开源模型未注册到 models 表 |
| 2026-06-18 16:48 | EXP-009 | 采集 | AA Omniscience 页面有丰富子数据（参数量、Token usage、Cost breakdown、按语言拆分），JS chunk 中有 omniscience_breakdown 结构 |
| 2026-06-19 01:15 | EXP-010 | 采集 | AA 网站数据在 RSC payload（9MB script 标签）中，无 API 调用；用 curl 下载 HTML + Python 多轮 unescape + 正则+花括号匹配提取，成功获取 209 个厂商模型完整数据 |
| 2026-06-19 01:15 | EXP-011 | 采集 | AA 正确 URL 是 /evaluations/omniscience（非 /leaderboards/omniscience，后者 404）；playwright_expect_response 可捕获网络请求但 AA 不发 API 请求 |
| 2026-06-20 00:12 | EXP-012 | 前端 | --accent-heatmap 必须独立于 --accent-soft；8% 透明度在白色背景不可见，Apple Light 需 35% 才有明显色差 |
| 2026-06-20 00:12 | EXP-013 | 前端 | CSS 类名避免用 `.empty` 等通用名，会误匹配 `.matrix-cell.empty`；改用 `main > .empty` 限定作用域 |
| 2026-06-20 00:12 | EXP-014 | 前端 | 矩阵单元格需 display:flex + align-items:center 垂直居中，否则 32px 行高下内容贴底显示为下划线 |
