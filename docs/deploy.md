# 发布与部署说明

最后更新：2026-09-20。此前全仓库关于部署只有一句括号注释
（`docs/初赛帖子草稿.md`：「GitHub Pages 部署 + Cloudflare CDN 缓存」），
本篇是第一次把它写清楚。线上站点：**https://llm.aivey565.shop**

---

## 一、链路是什么样

```
本地 data/llm_index.db
   │  scripts/refresh_data.py --apply   (采集 → 入库 → 导出 → 自校验)
   ▼
frontend/  (index.html + data.json + 图片)
   │  git push origin master
   ▼
GitHub Actions  .github/workflows/deploy.yml
   │  upload-pages-artifact  path: ./frontend
   ▼
GitHub Pages  (Fastly CDN, via: 1.1 varnish)
   ▲
   │  DNS + 反向代理 (cf-cache-status: HIT)
Cloudflare  →  llm.aivey565.shop
```

关键事实：

- **CI 只发布静态文件**。`.github/workflows/deploy.yml` 里没有任何 Python：
  不装依赖、不跑采集、不跑测试。它做的就三件事 —— checkout、把 `./frontend`
  当成 Pages 产物上传、部署。
- 所以**网站内容 = 提交进 git 的 `frontend/` 目录**。数据库、`data/raw/`、
  `config/`、`scripts/` 都不在线上，它们只在本地产出 `data.json`。
- 后端 FastAPI（`src/main.py`）**从未部署**，线上不存在 `/api/*`。
- 增量发布：一次更新只产生一个新的 `data.json` 提交，不需要重发历史批次。

## 二、怎么发布一次更新

```bash
cd /Users/LiYuan/apps/llm-index

# 1. 干跑：看将要写什么，不动库、不动 data.json
python3 scripts/refresh_data.py

# 2. 实跑：采集入库 + 导出 + 契约测试
python3 scripts/refresh_data.py --apply

# 3. 本地核对（必须人看一眼再发）
cd frontend && python3 -m http.server 8021   # 打开 http://127.0.0.1:8021
#   看：数据截止日是否为新快照日、九家模型是否齐、来源与日期标注是否出现、
#       成本维度是否合理、参照模型是否被灰显在榜外

# 4. 质量闸门
python3 -m pytest -q                    # 期望全绿
python3 -m ruff check src scripts tests --select F,E9

# 5. 发布
git add frontend/data.json frontend/index.html config/ data/raw/snapshots/ \
        src/ scripts/ tests/ docs/ reports/
git commit -m "data: AA 快照 2026-09-20 — 九家现役模型 + v3 采集管线"
git push origin master
```

推送后看部署进度与结果：

```bash
gh run list --workflow "Deploy to GitHub Pages" --limit 3
gh run watch                      # 或 gh run view <id> --log-failed
```

## 三、怎么确认线上真的更新了

Pages + Cloudflare 两层都有缓存，**返回 200 不代表是新内容**。核对指纹：

```bash
# 线上数据的快照日
curl -s https://llm.aivey565.shop/data.json | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print(d['metadata']['snapshot_date'], d['metadata']['model_count'])"

# 页面指纹是否等于本地这一批
curl -s https://llm.aivey565.shop/data.json | python3 -c \
  "import sys,json; print(json.load(sys.stdin)['metadata']['html_sha256'])"
```

后者应与 `data/raw/snapshots/<快照日>/manifest.json` 里的 `html_sha256` 一致。
若线上仍是旧值，是缓存没刷：等 Cloudflare 缓存 TTL 过期，或在
Cloudflare 控制台对该 URL 做 Purge Cache（**这一步需要你在控制台操作，
我没有 Cloudflare 访问权限，也无法代为验证**）。

## 四、回滚

站点是纯静态，回滚就是回退 `frontend/` 再推一次：

```bash
git log --oneline -- frontend/data.json      # 找到要回到的提交
git checkout <commit> -- frontend/
git commit -m "revert: 回退到 <快照日> 数据批次"
git push origin master
```

数据库侧不需要回滚：v3 采集是**按快照追加**的，历史批次从不删除。
想验证上一批数据，用导出器指名快照日即可：

```bash
python3 scripts/export_frontend_data.py --snapshot-date 2026-08-09 --out /tmp/aug.json
```

## 五、自定义域名（两处都放了 CNAME，说明）

- `CNAME`（仓库根）：内容是 `llm.aivey565.shop`，但它**不在发布产物里** ——
  CI 上传的路径是 `./frontend`。它实际不生效，属于放错位置的历史遗留。
- `frontend/CNAME`（2026-09-20 新增）：这才是 Pages 会读到的位置。
- 站点当前能正常按域名访问，说明域名配置至少在 Pages 设置或 Cloudflare DNS 里
  已经存在。**具体是哪一处生效、Cloudflare 是 DNS only 还是 Proxied、TLS 模式
  是 Full 还是 Flexible，仓库里没有任何记录，我也无法从这里读到。**
  请到 Cloudflare 控制台核对后补进本节 —— 这是本项目唯一一个"只存在于网页后台、
  没有进版本库"的必要配置。

## 六、CI 不做的事（以及要不要补）

现在**没有任何自动更新**。`config/settings.yaml` 里的 `ingestion.schedule`
是一段没有代码读取的注释；`requirements.txt` 装了 apscheduler 但从未启用；
原先的 `scripts/daily_update.py` 因 import 已删除的模块而必然崩溃（已归档）。

要不要加一个定时 workflow（GitHub Actions 定时跑采集 → 导出 → 自动提交 `data.json`）？
本次**刻意没加**，原因见 `docs/changelog.md #1`：AA 已把全量分数改成加密 blob +
前端解密，无人值守的自动采集会在对方下次改版时静默产出空榜或旧榜。
如果将来要加，前置条件是：

1. 先让 `collect_aa_v3.py` 在解析结果为空或模型数骤降时**非零退出**
   （目前带分模型为 0 会抛 `PayloadError` 退出码 2，可复用）；
2. workflow 里加一步比对 `data.json` 的 `metadata.snapshot_date` 与提交日期，
   不一致就不发布；
3. 保留人工审核：先开 `workflow_dispatch` 手动触发跑顺，再谈定时。
