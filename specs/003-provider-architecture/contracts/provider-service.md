# Provider Service Contract

## 0. Current Baseline

- `backend/services/llm_provider.py` 当前已定义 `LLMProvider` 抽象、三个 provider 实现和 `LLMProviderFactory`。
- 当前统一调用入口已存在且被后端节点直接依赖。
- 当前错误消息主要依赖 `ValueError` 文本，不区分不支持 provider、缺少凭证、无效凭证。

## 1. Stable Public Surface

本轮之后，以下入口继续保持不变：

```python
get_llm(provider: Optional[str] = None, model: Optional[str] = None, **kwargs)
get_structured_llm(schema, provider: Optional[str] = None, model: Optional[str] = None, **kwargs)
get_current_model_info() -> dict
```

### Compatibility Rule

- 所有现有节点继续通过以上入口请求模型。
- 本轮不新增 provider 专属公共函数。
- 本轮不将 provider 选择改写为 `provider/model` 复合语法。

## 2. Registry Contract

### Canonical Registry Responsibilities

1. 声明当前支持的 provider 列表
2. 负责根据 provider 名称返回对应 provider 实现
3. 对已创建 provider 进行懒加载缓存
4. 不承担插件扫描、热加载、外部目录发现职责

### Registry Rules

- registry 中的 provider 名称必须唯一
- `google` 必须和 `openai / anthropic / ollama` 平级注册
- registry 变更应只影响 `backend/services/llm_provider.py` 内部，不扩散到调用方

## 3. Model Construction Contract

### Standard Model

- `get_llm()` 必须返回当前 provider 对应的 LangChain chat model 实例
- 返回类型保持与现有调用习惯兼容

### Structured Model

- `get_structured_llm()` 必须继续通过统一路径构造结构化模型
- `google` provider 必须与现有 provider 一样支持该调用路径

### Model Info

- `get_current_model_info()` 的返回结构保持：

```python
{
    "provider": "<provider-name>",
    "model": "<resolved-model-name>",
}
```

- 当 provider 初始化失败时，允许 `model` 回退到环境中的 `DEFAULT_MODEL_NAME`

## 4. Error Semantics

### A. Unsupported Provider

触发时机：

- provider 名称不在 registry 中

要求：

- 错误消息必须指出非法 provider 名称
- 错误消息必须列出当前支持列表

### B. Missing Credential

触发时机：

- 解析到受支持 provider，但其必需凭证不存在

要求：

- 错误消息必须指出缺少的凭证字段名
- 错误消息必须指出是哪个 provider 初始化失败

### C. Invalid Credential / Authentication Failure

触发时机：

- provider 已构造成功，但首次真实请求被上游服务拒绝

要求：

- 错误消息必须能区分“认证失败”与“配置缺失 / provider 不支持”
- 可以保留上游异常摘要，但必须附带 provider 上下文
- 本轮不要求在 `get_llm()` 构造阶段增加 eager 网络校验

## 5. Non-Goals Bound to This Contract

- 不引入完整插件接口
- 不引入模型别名系统
- 不引入密钥轮换或多 key 选择
- 不修改前端、路由或工作流节点的调用方式

## 6. Migration Notes

- 本契约是后端内部服务契约，不涉及外部 REST API 版本变更。
- 本轮主要回归风险集中在：
  - registry 选择逻辑
  - `get_current_model_info()` 的回退行为
  - 现有三类 provider 的构造路径
