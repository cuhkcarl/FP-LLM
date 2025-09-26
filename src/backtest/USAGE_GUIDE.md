# FPL回测系统使用指南

## 快速开始

### 1. 运行策略回测
```bash
# 运行S0策略完整赛季回测
python scripts/run_backtest.py --strategy s0 --start-gw 1 --end-gw 38

# 自定义参数
python scripts/run_backtest.py \
    --strategy s0 \
    --season 2023-24 \
    --start-gw 1 \
    --end-gw 10 \
    --formation 3-4-3 \
    --output data/backtest/results/custom_test.yaml
```

### 2. 生成分析报告
```python
from scripts.generate_strategy_report import generate_report_for_strategy

# 为任何策略生成标准化报告
generate_report_for_strategy("S0", "data/backtest/results/s0_full_season_2023_24.yaml")
```

### 3. 对比多个策略
```python
from scripts.generate_strategy_report import compare_strategies

strategies = ["S0", "S1", "S2"]
result_files = [
    "data/backtest/results/s0_full_season_2023_24.yaml",
    "data/backtest/results/s1_full_season_2023_24.yaml",
    "data/backtest/results/s2_full_season_2023_24.yaml"
]

compare_strategies(strategies, result_files)
```

## 为新策略添加分析支持

### 步骤1：配置策略特征
编辑 `configs/backtest/analyzer_config.yaml`：

```yaml
strategy_profiles:
  S1:  # 新策略名称
    name: "转会策略"
    description: "在S0基础上增加转会决策的动态策略"
    characteristics:
      - "基于S0的15人阵容作为起点"
      - "根据伤病、停赛、表现等信息进行转会决策"
      - "保持预算平衡，最大化阵容价值"
    expected_performance: "良好"
    risk_level: "中等"
    complexity: "中等"
```

### 步骤2：实现并运行回测
```bash
# 当S1策略实现后
python scripts/run_backtest.py --strategy s1 --start-gw 1 --end-gw 38
```

### 步骤3：生成报告 (一行代码!)
```python
generate_report_for_strategy("S1", "data/backtest/results/s1_full_season_2023_24.yaml")
```

## 输出文件说明

### 回测结果文件
- **位置**: `data/backtest/results/`
- **格式**: YAML
- **内容**: 每个gameweek的决策、得分、累计结果

### 分析报告文件
- **Markdown报告**: `data/backtest/analysis/{strategy}_strategy_report.md`
  - 人类可读的完整分析报告
  - 包含表现评级、趋势分析、改进建议

- **JSON数据**: `data/backtest/analysis/{strategy}_analysis_data.json`
  - 结构化的分析数据
  - 支持程序化处理和进一步分析

### 策略对比文件
- **JSON对比**: `data/backtest/analysis/strategy_comparison.json`
  - 多策略对比的结构化数据
  - 包含排名、指标对比、汇总表格

## 配置文件说明

### 分析器配置 (`configs/backtest/analyzer_config.yaml`)
- **评级标准**: 定义A/B/C/D等级的分数区间
- **基准值**: FPL平均分、卓越门槛等参考值
- **策略档案**: 每个策略的特征和描述

### S0阵容配置 (`configs/backtest/s0_optimal_squad.yaml`)
- **15人阵容**: 基于群体智慧优化的固定阵容
- **球员信息**: ID、姓名、位置、队伍
- **约束验证**: 预算、位置、每队人数限制

## 系统架构

```
src/backtest/
├── engine.py              # 回测执行引擎
├── analyzer.py             # 数据驱动分析器
├── strategies/             # 策略实现
│   ├── s0_strategy.py      # S0静态策略
│   └── s0_generator.py     # S0阵容生成器
└── README.md              # 技术文档

scripts/
├── run_backtest.py         # 回测主入口
├── generate_strategy_report.py  # 报告生成器
└── verify_backtest.py      # 结果验证

configs/backtest/
├── analyzer_config.yaml    # 分析器配置
└── s0_optimal_squad.yaml  # S0阵容配置
```

## 关键特性

### ✅ 完全数据驱动
- 所有分析基于实际数据，无硬编码描述
- 评级标准和基准值可配置
- 自动生成改进建议和洞察

### ✅ 高度可扩展
- 新策略只需配置+一行代码即可生成完整报告
- 标准化的分析框架适用于所有策略
- 支持任意数量策略的对比分析

### ✅ 专业级输出
- 球员姓名而非ID显示
- 详细的统计指标和趋势分析
- 风险评估和基准对比

### ✅ 验证和质量保证
- 手工计算验证确保准确性
- 完整的约束检查和数据验证
- 清晰的错误提示和调试信息

## 常见用法示例

```python
# 1. 快速分析单个策略
from src.backtest import create_analyzer

analyzer = create_analyzer()
analyzer.load_player_mapping()
analyzer.load_result("S0", "s0_results.yaml")
analysis = analyzer.analyze_strategy("S0")

# 2. 批量生成多个策略报告
strategies = ["S0", "S1", "S2"]
for strategy in strategies:
    if Path(f"{strategy.lower()}_results.yaml").exists():
        generate_report_for_strategy(strategy, f"{strategy.lower()}_results.yaml")

# 3. 自定义配置分析
custom_config = "configs/backtest/custom_analyzer_config.yaml"
analyzer = create_analyzer(custom_config)
# ... 使用自定义评级标准和基准
```

---
*这个系统为FPL策略回测提供了完整的分析解决方案，支持从单策略深度分析到多策略对比的全流程需求。*
