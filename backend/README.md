# 基于 Prompt Chain 的自动化内容生成系统 - 后端

## 技术栈
- **框架**: FastAPI
- **工作流引擎**: LangGraph
- **LLM**: 多Provider兼容 (OpenAI, Anthropic, Ollama)
- **数据存储**: PostgreSQL / SQLite
- **包管理**: uv (快速、可复现)
- **代码质量**: ruff + pre-commit

## 快速开始

### 前置要求
- Python 3.14+
- [uv](https://docs.astral.sh/uv/) (推荐使用 `brew install uv`)

### 开发环境设置

```bash
# 安装依赖并创建虚拟环境
uv sync

# 配置环境变量
cp .env.example .env
# 编辑 .env 文件，填入 API Keys

# 启动服务
uv run uvicorn main:app --reload --port 8000

# 或者激活虚拟环境后直接运行
source .venv/bin/activate  # macOS/Linux
uvicorn main:app --reload --port 8000
```

### 常用命令

```bash
# 添加新依赖
uv add package-name

# 添加开发依赖
uv add --dev pytest

# 运行Python脚本
uv run python script.py

# 更新依赖
uv sync

# 代码格式化
ruff format .

# 代码检查
ruff check .

# 安装 Git hooks（首次）
pre-commit install

# 手动运行所有检查
pre-commit run --all-files
```

## 项目结构

```
backend/
├── main.py                 # FastAPI 入口
├── pyproject.toml          # 项目配置和依赖
├── uv.lock                 # 锁定的依赖版本
├── .python-version         # 固定的 Python 版本
├── ruff.toml               # Ruff 配置
├── .pre-commit-config.yaml # Pre-commit hooks
├── models/                 # Pydantic 数据模型
├── nodes/                  # LangGraph 节点实现
├── services/               # 核心服务层
├── graph/                  # 工作流定义
├── routes/                 # API 路由
└── db/                     # 数据库层
```
