# 基于 Prompt Chain 的自动化内容生成系统 - 后端

## 技术栈
- **框架**: FastAPI
- **工作流引擎**: LangGraph
- **LLM**: 多Provider兼容 (OpenAI, Anthropic, Ollama)
- **数据存储**: SQLite (开发环境)

## 快速开始

```bash
# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # macOS/Linux
# 或 venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 文件，填入 API Keys

# 启动服务
uvicorn main:app --reload --port 8000
```

## 项目结构

```
backend/
├── main.py                 # FastAPI 入口
├── models/                 # Pydantic 数据模型
├── nodes/                  # LangGraph 节点实现
├── services/               # 核心服务层
├── graph/                  # 工作流定义
├── guardrails/             # 验证层
├── api/                    # API 路由
└── db/                     # 数据库层
```
