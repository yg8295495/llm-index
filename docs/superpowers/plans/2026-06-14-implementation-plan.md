# LLM-INDEX 实施计划

**创建日期**: 2026-06-14
**基于**: [架构设计规格文档](../specs/2026-06-14-architecture-design.md)
**状态**: 待执行

---

## 总体概览

| Phase | 目标 | 核心任务 | 预计工作量 |
|-------|------|---------|-----------|
| Phase 1 | 数据库 + 价格采集 | SQLite 配置 + OpenRouter API 采集 | 2-3 天 |
| Phase 2 | 基准数据采集 | Playwright 采集 SWE-Bench/CursorBench 等 | 3-4 天 |
| Phase 3 | 计算逻辑 | 归一化 + 综合指数 + 权重管理 | 2 天 |
| Phase 4 | 前端 Vue 项目 | Vite + Vue 3 + ECharts 雷达图 | 4-5 天 |
| Phase 5 | 集成联调 | API 对接 + 排名页 + 详情页 | 3-4 天 |

---

## Phase 1: 数据库 + 价格采集

### 目标
- 配置 SQLite 数据库
- 实现 OpenRouter API 价格数据采集
- 数据入库验证

### 任务清单

#### Task 1.1: SQLite 数据库配置
**文件**:
- `src/storage/db_manager.py` (修改)
- `config/settings.yaml` (修改)

**逻辑**:
1. 修改 `DatabaseManager` 类，默认使用 SQLite
2. 数据库路径: `data/llm_index.db`
3. 移除 PostgreSQL 依赖，保留 SQLAlchemy ORM
4. 配置连接参数（`check_same_thread=False` for SQLite）

**验证**:
```bash
python3 -c "from src.storage.db_manager import DatabaseManager; db = DatabaseManager(); db.create_tables()"
ls -la data/llm_index.db
```

#### Task 1.2: OpenRouter 价格采集器
**文件**:
- `src/ingester/price_ingester.py` (修改)

**逻辑**:
1. 调用 `https://openrouter.ai/api/v1/models`
2. 解析 JSON 响应，提取模型价格信息
3. 字段映射: `id` → model_name, `pricing.prompt` → input_price, `pricing.completion` → output_price
4. 计算加权平均价: `avg_price = (input_price + output_price) / 2`
5. 插入 `model_pricing` 表，带时间戳

**验证**:
```bash
python3 -c "
from src.ingester.price_ingester import PriceIngester
ingester = PriceIngester()
data = ingester.fetch_prices()
print(f'采集到 {len(data)} 个模型的价格')
print(data[0])  # 查看第一条数据
"
```

#### Task 1.3: 模型清单初始化
**文件**:
- `scripts/seed_models.py` (新建)

**逻辑**:
1. 读取 `config/models_list.yaml`
2. 将 9 家厂商的模型信息插入 `models` 表
3. 包含: model_name, vendor, model_type (flagship/economy), description

**验证**:
```bash
python3 scripts/seed_models.py
python3 -c "
from src.storage.db_manager import DatabaseManager
db = DatabaseManager()
models = db.session.query(Model).all()
print(f'共 {len(models)} 个模型')
for m in models[:5]:
    print(f'  {m.vendor} - {m.model_name}')
"
```

#### Task 1.4: 价格数据入库测试
**文件**:
- `scripts/test_price_ingest.py` (新建)

**逻辑**:
1. 调用 `PriceIngester.fetch_prices()`
2. 调用 `db.save_pricing_data(data)`
3. 查询验证数据已入库

**验证**:
```bash
python3 scripts/test_price_ingest.py
# 预期输出: 成功采集并入库 N 个模型的价格数据
```

---

## Phase 2: 基准数据采集

### 目标
- 实现 Playwright 无头浏览器采集
- 采集 SWE-Bench Pro、CursorBench 等基准数据
- 数据质量验证

### 任务清单

#### Task 2.1: Playwright 采集器基础框架
**文件**:
- `src/ingester/bench_ingester.py` (修改)

**逻辑**:
1. 使用 Playwright 同步 API
2. 浏览器路径: `~/.cache/puppeteer/chrome/mac-148.0.7778.97/chrome-mac-x64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing`
3. 支持 headless/headful 模式切换（配置文件控制）
4. 通用方法: `fetch_page(url)` → 返回页面内容

**验证**:
```bash
python3 -c "
from src.ingester.bench_ingester import BenchIngester
ingester = BenchIngester()
content = ingester.fetch_page('https://www.example.com')
print(f'页面长度: {len(content)}')
assert 'Example' in content
"
```

#### Task 2.2: SWE-Bench Pro 采集
**文件**:
- `src/ingester/swebench_ingester.py` (新建)

**逻辑**:
1. 目标 URL: `https://scale.com/leaderboard` (或实际 SWE-Bench Pro 页面)
2. 使用 Playwright 打开页面，等待表格加载
3. 解析 HTML 表格，提取: model_name, score, rank
4. 数据清洗: 去除百分号、处理缺失值
5. 插入 `model_benchmark` 表，benchmark_name = 'swe_bench_pro'

**验证**:
```bash
python3 -c "
from src.ingester.swebench_ingester import SWE benchIngester
ingester = SWE benchIngester()
data = ingester.fetch_scores()
print(f'采集到 {len(data)} 个模型的 SWE-Bench 分数')
for item in data[:3]:
    print(f'  {item}')
"
```

#### Task 2.3: CursorBench 采集
**文件**:
- `src/ingester/cursorbench_ingester.py` (新建)

**逻辑**:
1. 需要先确认 CursorBench 公开排行榜地址
2. 类似 SWE-Bench 采集逻辑
3. 如果无公开排行榜，暂时跳过，标记为 TODO

**验证**:
```bash
# 如果已实现
python3 -c "
from src.ingester.cursorbench_ingester import CursorBenchIngester
ingester = CursorBenchIngester()
data = ingester.fetch_scores()
print(f'采集到 {len(data)} 个模型的 CursorBench 分数')
"
```

#### Task 2.4: TruthfulQA 采集
**文件**:
- `src/ingester/truthfulqa_ingester.py` (新建)

**逻辑**:
1. 数据源: HuggingFace 或论文附录
2. 如果是静态数据，可以手动录入到 `data/raw_bench/truthfulqa.json`
3. 提供 `load_from_file()` 方法加载本地数据
4. 插入 `model_benchmark` 表，benchmark_name = 'truthfulqa'

**验证**:
```bash
python3 -c "
from src.ingester.truthfulqa_ingester import TruthfulQAIngester
ingester = TruthfulQAIngester()
data = ingester.load_scores()
print(f'加载到 {len(data)} 个模型的 TruthfulQA 分数')
"
```

#### Task 2.5: 基准数据入库测试
**文件**:
- `scripts/test_bench_ingest.py` (新建)

**逻辑**:
1. 依次调用各基准采集器
2. 数据入库
3. 统计各基准覆盖的模型数量

**验证**:
```bash
python3 scripts/test_bench_ingest.py
# 预期输出: 各基准采集结果统计
```

---

## Phase 3: 计算逻辑

### 目标
- 实现分数归一化
- 实现综合指数计算
- 实现权重管理（预设 + 自定义）

### 任务清单

#### Task 3.1: 归一化模块
**文件**:
- `src/compute/normalizer.py` (修改)

**逻辑**:
1. Min-Max 归一化: `norm_score = (raw - min) / (max - min) * 100`
2. 反向归一化（用于 cost）: `norm_score = (max - raw) / (max - min) * 100`
3. 处理缺失值: 返回 None 或默认值 50
4. 支持批量归一化

**验证**:
```bash
python3 -c "
from src.compute.normalizer import normalize_scores
scores = [80, 60, 90, 70]
normalized = normalize_scores(scores)
print(normalized)  # [66.7, 0, 100, 33.3]
"
```

#### Task 3.2: 权重管理器
**文件**:
- `src/compute/weight_manager.py` (修改)

**逻辑**:
1. 从 `config/settings.yaml` 加载预设权重
2. 支持 5 个预设: developer, enterprise, research, serious, domestic
3. 支持自定义权重，验证总和为 100%
4. 等比缩放算法实现

**验证**:
```bash
python3 -c "
from src.compute.weight_manager import WeightManager
wm = WeightManager()
print(wm.get_preset('developer'))
# {'coding': 0.25, 'engineering': 0.20, ...}
"
```

#### Task 3.3: 综合指数计算器
**文件**:
- `src/compute/index_calculator.py` (修改)

**逻辑**:
1. 从数据库加载各维度原始分数
2. 调用归一化模块
3. 应用权重，计算综合指数
4. 存储到 `composite_scores` 表
5. 支持历史趋势查询

**验证**:
```bash
python3 -c "
from src.compute.index_calculator import IndexCalculator
calc = IndexCalculator()
result = calc.calculate_index('deepseek-v4', preset='developer')
print(f'综合指数: {result.index_value}')
print(f'各维度得分: {result.dimension_scores}')
"
```

#### Task 3.4: 批量计算脚本
**文件**:
- `scripts/calculate_all_indexes.py` (新建)

**逻辑**:
1. 遍历所有模型
2. 对每个模型计算综合指数（使用指定预设）
3. 结果入库
4. 输出排名

**验证**:
```bash
python3 scripts/calculate_all_indexes.py --preset developer
# 预期输出: 所有模型的综合指数排名
```

---

## Phase 4: 前端 Vue 项目

### 目标
- 初始化 Vue 3 + Vite 项目
- 实现雷达图组件（ECharts）
- 实现权重调整面板
- 实现维度详情面板

### 任务清单

#### Task 4.1: Vue 项目初始化
**文件**:
- `frontend/` (新建目录)

**逻辑**:
```bash
cd frontend
npm create vite@latest . -- --template vue
npm install
npm install echarts vue-echarts
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p
```

**验证**:
```bash
cd frontend
npm run dev
# 访问 http://localhost:5173 看到默认页面
```

#### Task 4.2: 雷达图组件
**文件**:
- `frontend/src/components/RadarChart.vue` (新建)

**逻辑**:
1. 使用 ECharts 雷达图
2. Props: `models` (数组), `dimensions` (6 维), `baselineModel`
3. 基准模型高亮显示（不同颜色/线型）
4. 支持多模型叠加
5. 响应式尺寸

**验证**:
```bash
# 在 App.vue 中引入组件，传入测试数据
# 预期: 页面显示雷达图，多模型多边形叠加
```

#### Task 4.3: 权重调整面板
**文件**:
- `frontend/src/components/WeightPanel.vue` (新建)

**逻辑**:
1. 6 个维度滑块（range input）
2. 预设选择下拉框
3. 等比缩放算法（JavaScript 实现）
4. 锁定/解锁维度
5. 实时显示总和（100%）
6. 保存为自定义预设

**验证**:
```bash
# 拖动滑块，观察:
# 1. 其他维度自动缩放
# 2. 总和始终为 100%
# 3. 雷达图实时更新
```

#### Task 4.4: 维度详情面板
**文件**:
- `frontend/src/components/DimensionDetail.vue` (新建)

**逻辑**:
1. 点击维度名称/ⓘ 图标触发
2. 显示: 能力定义、评分标准、数据来源
3. 二级权重调整（子指标权重）
4. 同样采用等比缩放

**验证**:
```bash
# 点击"编程能力"维度
# 预期: 弹出详情面板，显示 SWE-Bench/CursorBench/HumanEval 权重
# 拖动子指标滑块，验证等比缩放
```

#### Task 4.5: 主页布局
**文件**:
- `frontend/src/views/HomePage.vue` (新建)

**逻辑**:
1. 左侧: 雷达图（占 60% 宽度）
2. 右侧: 权重面板 + 基准模型选择器（占 40%）
3. 顶部: 模型选择器（多选）
4. 响应式布局（移动端适配）

**验证**:
```bash
npm run dev
# 访问主页，验证布局正确
# 选择多个模型，雷达图叠加显示
# 调整权重，雷达图实时更新
```

---

## Phase 5: 集成联调

### 目标
- FastAPI 后端 API 实现
- 前端对接 API
- 排名页 + 模型详情页
- 端到端测试

### 任务清单

#### Task 5.1: 后端 API 实现
**文件**:
- `src/api/routes.py` (修改)

**逻辑**:
1. `GET /api/models` - 返回所有模型列表
2. `GET /api/radar` - 返回雷达图数据（参数: model_ids, weights）
3. `GET /api/ranking` - 返回综合指数排名
4. `GET /api/model/{id}` - 返回单模型详情
5. `POST /api/weights/preset` - 保存自定义预设

**验证**:
```bash
uvicorn src.main:app --reload
# 访问 http://localhost:8000/docs 查看 Swagger 文档
# 测试各 API 接口
```

#### Task 5.2: 前端 API 对接
**文件**:
- `frontend/src/api/index.js` (新建)
- `frontend/src/views/HomePage.vue` (修改)

**逻辑**:
1. 使用 axios 调用后端 API
2. 主页加载时调用 `/api/models` 和 `/api/radar`
3. 权重变化时重新调用 `/api/radar`
4. 错误处理 + loading 状态

**验证**:
```bash
# 启动后端 + 前端
uvicorn src.main:app --reload &
cd frontend && npm run dev &
# 访问前端页面，验证数据从后端加载
```

#### Task 5.3: 排名页
**文件**:
- `frontend/src/views/RankingPage.vue` (新建)

**逻辑**:
1. 调用 `/api/ranking` 获取排名数据
2. 表格展示: 排名、模型名称、综合指数、各维度得分
3. 点击模型名称跳转到详情页
4. 支持按维度排序

**验证**:
```bash
# 访问排名页
# 验证表格数据正确
# 点击模型名称，跳转到详情页
```

#### Task 5.4: 模型详情页
**文件**:
- `frontend/src/views/ModelDetailPage.vue` (新建)

**逻辑**:
1. 调用 `/api/model/{id}` 获取详情
2. 显示: 模型基本信息、各维度得分、子指标拆解
3. 雷达图（单模型）
4. 与基准模型的对比（百分比差异）

**验证**:
```bash
# 从排名页点击模型，跳转到详情页
# 验证各维度得分正确显示
# 验证与基准模型的对比数据
```

#### Task 5.5: 端到端测试
**文件**:
- `tests/test_e2e.py` (新建)

**逻辑**:
1. 启动后端服务
2. 使用 Playwright 打开前端页面
3. 测试: 选择模型 → 查看雷达图 → 调整权重 → 查看排名 → 查看详情
4. 截图保存

**验证**:
```bash
pytest tests/test_e2e.py -v
# 预期: 所有测试通过
# 查看截图验证页面正确
```

---

## 依赖关系

```
Phase 1 (数据库 + 价格) ──┐
                          ├──→ Phase 3 (计算逻辑) ──→ Phase 5 (集成联调)
Phase 2 (基准采集) ───────┘                              ↑
                                                         │
Phase 4 (前端 Vue) ─────────────────────────────────────┘
```

- Phase 1 和 Phase 2 可以并行
- Phase 3 依赖 Phase 1 + 2 的数据
- Phase 4 可以独立进行（使用 mock 数据）
- Phase 5 依赖 Phase 3 + 4 完成

---

## 风险与应对

| 风险 | 影响 | 应对方案 |
|------|------|---------|
| 基准网站反爬虫 | 无法采集数据 | 使用 Playwright + 随机 User-Agent + 延时 |
| 数据格式变化 | 采集失败 | 采集器设计为可配置，快速调整解析逻辑 |
| Playwright MCP 不可用 | 调试效率低 | 使用 Python 直接调用 Playwright（已验证可用） |
| 前端性能问题 | 雷达图卡顿 | 使用 ECharts 大数据模式，限制同时显示的模型数量 |

---

## 下一步行动

1. **确认本计划**: 用户审阅后确认
2. **开始 Phase 1**: 数据库配置 + 价格采集
3. **阶段性验证**: 每个 Phase 完成后验证，通过后再进入下一阶段
