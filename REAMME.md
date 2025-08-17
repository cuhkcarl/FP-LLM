# FP-LLM-otherfucker
免责声明：本项目仅供学习研究，请遵守 FPL 与数据源的服务条款（TOS）。

数据→预测→优化→报告的 FPL（Fantasy Premier League）自动/半自动策略系统。
目标：**总积分最大化**，自动给出每轮首发/队长/替补与转会建议；筹码（Wildcard/BB/FreeHit/TC）给出启发式建议。

## 快速开始（开发环境）
```bash
# 安装 uv（推荐）或用 pip 亦可
pip install -U uv

# 安装项目（含开发依赖）
uv pip install -e ".[dev]"

# 初始化 pre-commit（本地提交自动检查）
pre-commit install

# 运行基础校验与测试
ruff check .
black --check .
isort --check-only .
mypy src
pytest -q
