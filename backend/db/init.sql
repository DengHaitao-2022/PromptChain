-- PromptChain 数据库初始化脚本
-- 创建所需的扩展

-- UUID 生成
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 向量检索
CREATE EXTENSION IF NOT EXISTS vector;

-- 用户授权
GRANT ALL PRIVILEGES ON DATABASE promptchain TO postgres;
