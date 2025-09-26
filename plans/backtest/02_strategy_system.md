# Checkpoint 2: 策略系统建设

**每次更新和修改子计划内容，都需要将必要信息同步到总计划中**

## 目标定义

在MVP基础上，建立完整的策略系统，实现S1/S2策略并集成现有的优化组件。重点是**让所有策略都能跑**，建立可比较的执行环境。

## 要解决的核心问题

### 1. 现有系统的集成
**问题**: 如何复用现有的optimizer和prediction模块？
**挑战**: 数据格式匹配、依赖管理、配置传递

### 2. 策略复杂度的管理
**问题**: S0/S1/S2策略复杂度差异很大，如何统一管理？
**挑战**: 保持接口一致的同时支持不同的实现需求

### 3. 转会逻辑的实现
**问题**: 如何在回测环境中实现转会优化？
**挑战**: 预算管理、FPL规则验证、优化算法调用

### 4. 芯片策略的集成
**问题**: 如何在S2中合理使用芯片？
**挑战**: 时机判断、效果评估、与转会的协调

## 策略设计哲学

### S0: 静态基准 - 群体智慧基准
```
设计理念：最简化的基准策略
- 使用预定义的"最优"15人阵容（基于拥有率）
- 每轮只需要优化首发11人和队长选择
- 无转会，无芯片，纯粹的阵容管理
- 目标：提供稳定的比较基准
```

### S1: 转会优化策略
```
设计理念：纯粹的转会价值测试
- 在S0基础上增加转会能力
- 复用现有的best_transfers()函数
- 限制：无芯片，专注转会决策
- 目标：独立测量转会优化的价值
```

### S2: 完整策略
```
设计理念：所有FPL机制的综合运用
- 转会 + 芯片的协调优化
- 应用所有现有配置（黑名单等）
- 使用完整的复杂性工具包
- 目标：测试完整优化的价值上限
```

## 技术实现策略

### 现有系统集成方法
```python
# 集成思路：适配器模式
# 不修改现有代码，创建适配器层

class OptimizerAdapter:
    """将现有optimizer接口适配到回测环境"""

    def prepare_data_for_optimizer(self, historical_data, gw):
        # 将历史数据转换为optimizer期望的格式
        pass

    def call_existing_optimizer(self, prepared_data):
        # 调用现有的best_transfers等函数
        pass

    def adapt_optimizer_results(self, results):
        # 将optimizer结果转换为回测系统格式
        pass
```

### 策略实现方法
```python
# 策略思路：简单的函数式接口
# 避免复杂的类继承，使用组合

def s0_strategy(current_squad, available_data, config):
    """S0策略：静态阵容 + 首发优化"""
    # 实现逻辑...
    return {
        'transfers': [],
        'starting_xi': selected_players,
        'captain': captain_choice,
        'chip': None
    }

def s1_strategy(current_squad, available_data, config):
    """S1策略：S0 + 转会优化"""
    # 使用适配器调用现有optimizer
    pass

def s2_strategy(current_squad, available_data, config):
    """S2策略：完整优化"""
    # 转会 + 芯片的协调决策
    pass
```

## 具体实现计划

### 阶段1: S0策略完善 (1天)
**目标**: 基于MVP的S0实现，完善决策逻辑
- 实现基于预期得分的首发11人优化
- 优化队长选择逻辑
- 添加基本的FPL规则验证（阵型约束等）
- 确保决策的合理性和一致性

### 阶段2: 现有系统适配 (2天)
**目标**: 建立与现有optimizer/prediction的桥接
- 分析现有系统的输入输出格式
- 实现数据格式转换逻辑
- 创建适配器调用现有函数
- 验证集成后的结果正确性

### 阶段3: S1策略实现 (2天)
**目标**: 实现纯转会优化策略
- 集成现有的best_transfers()函数
- 实现预算和转会约束管理
- 添加转会决策的验证逻辑
- 测试S1与S0的性能差异

### 阶段4: S2策略框架 (2天)
**目标**: 实现基本的S2策略框架
- 复用现有的芯片决策逻辑
- 实现转会与芯片的基本协调
- 应用配置中的黑名单等约束
- 先求跑通，效果优化后续进行

### 阶段5: 策略对比验证 (1天)
**目标**: 确保三个策略能够公平比较
- 统一的执行环境设置
- 结果格式的标准化
- 基本的对比分析实现
- 端到端的测试验证

## 数据契约设计

### 策略输入格式
```python
strategy_input = {
    'gw': 15,
    'current_squad': {
        'players': [player_ids],
        'bank': 2.5,
        'free_transfers': 1,
        'chips_available': ['BB', 'TC']
    },
    'available_data': {
        'players': players_df,
        'fixtures': fixtures_df,
        'predictions': predictions_df,
        'ownership': ownership_df  # 如果可用
    },
    'config': {
        'blacklist': [...],
        'max_hits': 0,  # S1特定
        'chips_enabled': False  # S1特定
    }
}
```

### 策略输出格式
```python
strategy_output = {
    'transfers': [
        {'out': player_id, 'in': player_id, 'cost': 0.0},
        # ...
    ],
    'starting_xi': [11个player_ids],
    'captain': player_id,
    'vice_captain': player_id,
    'chip_used': None,  # 或 'BB', 'TC', 'FH', 'WC'
    'reasoning': "可选的决策说明",
    'confidence': 0.8  # 可选的置信度
}
```

## 现有系统集成重点

### Optimizer模块集成
```python
# 需要适配的主要函数
from src.optimizer.ilp import best_transfers
from src.optimizer.squad_builder import SquadBuilder
from src.optimizer.chips import should_use_bench_boost, should_use_triple_captain

# 集成策略
def integrate_best_transfers(current_squad, predictions, budget, free_transfers):
    # 1. 数据格式转换
    # 2. 调用现有函数
    # 3. 结果格式适配
    pass
```

### Prediction模块集成
```python
# 需要适配的主要函数
from src.prediction.baseline import generate_baseline_predictions
from src.prediction.cold_start import generate_cold_start_predictions

# 集成策略
def generate_predictions_for_gw(gw, players_data, fixtures_data, method='baseline'):
    # 根据回测时点选择合适的预测方法
    pass
```

### 配置系统集成
```python
# 复用现有配置
from configs.base import load_base_config

# 集成策略
def adapt_config_for_backtest(base_config, strategy_specific_config):
    # 合并配置，处理策略特定的覆盖
    pass
```

## 验证和测试策略

### 单元测试重点
- 数据格式转换的正确性
- 现有函数调用的成功率
- 策略输出的格式一致性
- FPL规则的正确验证

### 集成测试重点
- S0/S1/S2策略的端到端执行
- 与现有系统的兼容性
- 不同配置下的行为一致性
- 异常情况的处理能力

### 性能测试重点
- 单GW决策的执行时间
- 内存使用的合理性
- 大数据集的处理能力
- 瓶颈点的识别

## 风险管控

### 主要风险
1. **现有系统变更**: 现有optimizer/prediction接口可能变化
2. **数据格式不匹配**: 历史数据与现有系统格式差异
3. **性能问题**: 优化算法在回测环境中执行过慢
4. **配置冲突**: 不同策略的配置需求冲突

### 缓解措施
1. **版本锁定**: 明确依赖的现有系统版本
2. **适配器隔离**: 通过适配器层隔离格式差异
3. **性能监控**: 及时发现和处理性能瓶颈
4. **配置分层**: 设计灵活的配置覆盖机制

## 成功标准

### 功能成功标准
- [ ] S0/S1/S2三个策略都能完整运行单赛季回测
- [ ] S1策略正确调用现有的转会优化逻辑
- [ ] S2策略能够使用芯片并协调转会决策
- [ ] 三个策略在相同条件下的结果可比较

### 质量成功标准
- [ ] 代码结构清晰，模块职责明确
- [ ] 与现有系统的集成稳定可靠
- [ ] 错误处理完善，异常情况有明确反馈
- [ ] 性能满足基本需求（S1 < 10min, S2 < 30min单赛季）

### 业务成功标准
- [ ] S1相比S0显示出转会优化的价值
- [ ] S2相比S1/S0显示出完整策略的优势
- [ ] 策略行为符合预期和FPL规则
- [ ] 为后续基准对比奠定基础

## 下一步计划

完成策略系统建设后，将进入Checkpoint 3，重点实现基准计算系统，为完整的策略vs基准对比分析做准备。关键是要有B1-B4四种基准的实现，形成完整的评估体系。
