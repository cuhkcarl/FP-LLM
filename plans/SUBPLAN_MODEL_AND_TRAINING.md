# 子计划：模型设计与训练部署

> 每次对该计划的更新和修改，都要将必要信息同步到总计划中。

## 目标
- 基于扩展特征集训练监督模型，输出经校准的 expected_points。
- 构建训练→评估→落盘→服务预测 CLI 的完整流水线，并保证可回测。

## 核心任务
1. **建模方案选型**
   - 定义标签（未来 1 GW 实际分数）与特征窗口。
   - 评估 baseline、线性模型（Ridge/Lasso）、树模型（LightGBM/XGBoost）与简单集成的可行性。
2. **训练与验证**
   - 实现滚动/时间切分交叉验证，产出 RMSE、MAE、NDCG@K、Spearman 指标。
   - 引入模型解释（feature importance / SHAP 轻量版本）。
3. **模型管理**
   - 规范模型落盘格式（`models/gwXX/model.json|pkl`）。
   - 设计模型注册表/metadata（训练数据范围、特征版本、超参）。
4. **预测 CLI 集成**
   - 扩展 `scripts/predict_points.py` 支持 `--mode ml` 和 `--mode blend`（ML + baseline/校准）。
   - 提供 batch 预测与单 GW 快速预测能力。
5. **回测与监控**
   - 构建最小回测脚本（输入 GW 范围 → 输出指标）。
   - 设计部署后监控指标与报警阈值（预测偏差 / ranking 质量）。

## 交付物
- 模型代码与训练脚本（可能放置于 `src/prediction/ml/`）。
- 模型落盘与 metadata 文件示例。
- 回测报告与配置化评估脚本。

## 依赖
- 数据子计划提供的 `features_ml_*` 与校准参数。
- 现有预测 CLI 框架。

## 风险与缓解
- **样本量不足**：优先使用线性/树模型并加入正则；考虑多赛季数据叠加。
- **过拟合**：采用时间折交叉验证、早停与特征筛选。
- **部署复杂度**：保持 CLI 参数向后兼容，必要时添加 `ml_config.yaml` 管理超参。

## Checkpoints
- CP1：完成特征/标签定义与 baseline 对比实验。
- CP2：确定首选模型并通过交叉验证。
- CP3：`predict_points.py --mode ml` 可执行，模型落盘与回测报告产出。

