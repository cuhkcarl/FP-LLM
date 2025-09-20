# 子计划：数据扩展与预测校准

> 每次对该计划的更新和修改，都要将必要信息同步到总计划中。

## 目标
- 获取并整理逐轮 actuals、element-summary 历史、对手强度等补充数据，为 ML 特征构建提供真实样本。
- 建立误差分析与基准校准流程，明确 baseline 的系统性偏差并定义校准策略。

## 核心任务
1. **数据补齐**
   - 抓取当前赛季逐轮 `event/{gw}/live` 数据，形成 per-GW actuals 表（含分钟、分项得分）。
   - 接入 `element-summary/{player_id}`，生成近 N 轮面板数据；拉链式存储到 `data/history/`。
   - 补充对手强度、赛程密度、球员可用性等球队级特征。
2. **数据建模规范**
   - 设计统一的特征 schema（static + rolling）并落地到 `features_ml_gwXX.parquet`。
   - 定义训练样本划分策略（滚动窗口 / expanding window）。
3. **误差分析与校准**
   - 基于 GW1-4 数据统计 baseline 误差分布（按位置、价格区间、availability）。
   - 选择初步校准方法（如等分位缩放、Platt-like 调整），输出校准参数草案。
4. **可复现流水线**
   - 添加脚本/Makefile 步骤：数据抓取 → 特征加工 → 校准输出。
   - 编写文档说明数据刷新频率与成本。

## 交付物
- `data/history/` 与 `data/processed/features_ml_gwXX.parquet` 样例文件。
- 误差分析报告（Markdown/table），用于指导模型与策略。
- 可执行的数据刷新脚本与 README 指南。

## 依赖
- 现有 `scripts/fetch_actuals.py`、`scripts/build_features.py`。（可能需扩展）
- FPL 官方 API 可访问性。

## 风险与缓解
- **API 限频/变动**：增加本地缓存与重试逻辑。
- **数据口径不一致**：在 schema 中记录字段来源与单位，并建立验证脚本。

## Checkpoints
- CP1：逐轮 actuals 与 element-summary 历史成功落地。
- CP2：新特征表 + 误差基线报告完成并评审。
- CP3：校准流程可重复执行，输出参数供模型子计划引用。

