# Coach 淘宝商品数据分析与销量预测系统

基于淘宝公开数据，对 COACH 品牌商品进行全链路商业分析：数据采集 → 清洗入库 → 多维分析 → LSTM 销量预测 → 可视化大屏。

**在线静态报告**：https://lulu1766.github.io/taobao-coach-product-analysis/

## 核心分析结论

| 维度 | 结论 |
|---|---|
| 价格策略 | 1000–2000 元为黄金价位，贡献 55% 销量；3000+ 元在淘宝渠道基本无市场 |
| 销量结构 | 典型长尾市场：TOP10 爆款贡献 73.5% 销量，43% 商品零动销 |
| 渠道格局 | 官方奥莱以 5% 的款数贡献 38.3% 销量，单品动销效率约为大盘 7 倍 |
| 数据质量 | 识别出香水品类 71% 销量来自蹭名款的数据污染风险 |

## 技术栈

- **数据采集**：影刀 RPA（采集淘宝公开商品数据）
- **数据处理**：Python（pandas / numpy / 正则表达式）
- **数据库**：MySQL 8.0（商品、月度销量、预测结果、模型指标 4 张表）
- **深度学习**：TensorFlow 2 / Keras 3，双层 LSTM 时序预测
- **后端**：Django 5.2（MTV 架构 + ORM + Admin 后台）
- **可视化**：ECharts 5（双轴组合图、漏斗、堆叠柱、词云、预测曲线）
- **文本挖掘**：jieba 中文分词（商品标题关键词提取）

## 项目结构

```
├── python/                 # 01-10 编号数据流水线（检查/清洗/EDA/分类/渠道）
├── scripts/                # 影刀 RPA 数据接收脚本
├── data/processed/         # 清洗后的最终数据集（352 条商品）
├── logs/ outputs/          # 清洗与 EDA 过程留痕
├── charts/                 # 静态分析图表（matplotlib/seaborn）
├── docs/                   # GitHub Pages 在线报告源文件（Pages 从该目录发布）
├── Coach商品分析报告.md     # 管理层商业分析报告
├── 数据分析口径说明.md      # 指标口径与数据边界说明
└── coach_web/              # Django + LSTM 可视化系统
    ├── config/             # Django 配置
    └── dashboard/
        ├── ml/             # data_builder 数据构造 / lstm_forecast 模型
        ├── ml_models/      # 已训练模型 lstm_sales.keras
        └── templates/      # 6 页 ECharts 分析前端
```

## LSTM 模型说明

- **结构**：Input(6×1) → LSTM(64) → Dropout → LSTM(32) → Dropout → Dense(16) → Dense(1)
- **训练**：6 个月滑动窗口，整体/包袋/香水/配饰 4 条序列联合训练，EarlyStopping
- **验证**：Walk-forward（前 18 月训练 → 后 6 月回测），整体序列 MAPE 22.7%
- **预测**：全量重训后递归滚动预测未来 6 个月，准确复现双 11 峰值与春节低谷

> 数据口径：原始数据为单次采集截面快照，月度序列依据各对象近 12 个月真实累计销量
> （整体 145,549 件）结合电商季节因子构造，用于模型验证；接入真实月度流水后可直接重训。

## 本地运行

### 方式一：一键运行（推荐，无需安装 MySQL 和 TensorFlow）

项目已内置数据库快照 fixture（352 条商品 + 96 条月度序列 + LSTM 预测结果与评估指标），
预测为预计算结果，因此运行时只需 Django + jieba，自动使用免安装的 SQLite。

**Windows**：双击 `coach_web/run.bat`

**macOS / Linux**：

```bash
cd coach_web
bash run.sh        # 自动建虚拟环境、装依赖、初始化并启动
```

启动后访问 http://127.0.0.1:8000/

手动方式（效果相同）：

```bash
cd coach_web
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py loaddata coach_data
python manage.py runserver
```

### 方式二：完整重建（MySQL + 重新训练 LSTM，复现数据与建模全过程）

```bash
# 环境要求：Python 3.10+、MySQL 8.0
pip install -r requirements-full.txt
mysql -u root -p -e "CREATE DATABASE coach_db DEFAULT CHARACTER SET utf8mb4"

# 通过环境变量切换 MySQL（密码不写入代码）
export USE_MYSQL=1 DB_PASSWORD=你的密码     # Windows PowerShell: $env:USE_MYSQL='1'; $env:DB_PASSWORD='你的密码'
cd coach_web
python manage.py migrate
python manage.py init_data        # 导入CSV → 构造月度序列 → 训练LSTM → 预测入库（约数分钟）
python manage.py runserver
```

> 说明：LSTM 预测依赖月度历史序列。原始公开数据为单次采集的截面快照，
> 月度序列由真实累计销量结合电商季节因子构造用于模型验证，详见 `数据分析口径说明.md`。
> `dashboard/ml_models/lstm_sales.keras` 为已训练好的模型文件。

