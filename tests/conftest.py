import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "src"

# 确保项目根目录可导入（用于 `import scripts` 等）
root_str = str(ROOT_DIR)
if root_str not in sys.path:
    sys.path.insert(0, root_str)

# 确保 src 布局可导入（用于 `import optimizer` 等）
src_str = str(SRC_DIR)
if SRC_DIR.exists() and src_str not in sys.path:
    sys.path.insert(0, src_str)
