# Feature Specification: PromptChain Provider Architecture Upgrade

**Feature ID**: `003-provider-architecture`
**Created**: 2026-03-13
**Status**: Draft
**Input**: User description: "基于当前 PromptChain 的 LLM provider 实现现状，并参考 OpenClaw 的 provider 设计思想，产出一个“最小可落地”的 Provider 架构设计 spec。目标是新增 google provider、保持统一调用入口不变，并消除 quickstart 因 provider 不支持导致的阻塞。"

## Overview

PromptChain 当前已经具备统一的模型访问入口，但受支持的模型提供方仍不完整，导致仅持有 Google 凭证的开发者无法直接完成本地启动与最小验收。该能力缺口不仅阻塞 quickstart，也让 provider 支持范围、配置方式和错误反馈不够一致。

本特性聚焦于一次最小而完整的 provider 能力补齐：把 Google 纳入受支持 provider，保持既有统一调用入口稳定，收敛 provider 支持列表与路由规则，并让常见配置错误能够被快速识别。目标不是引入完整插件平台，而是让当前系统具备稳定、清晰、可继续扩展的 provider 基线。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 开发者启用 Google 作为默认 Provider (Priority: P1)

作为本地开发者或后端维护者，我希望在只持有 Google 凭证的情况下也能完成 Provider 配置并触发首次模型请求，这样 quickstart 不会因为“代码不支持该 provider”而中断。

**Why this priority**: 这是本轮改动的直接业务价值，也是当前 quickstart 阻塞点的最小修复闭环。

**Independent Test**: 使用仅包含 Google 凭证的环境完成本地配置，并在不改既有调用方式的前提下成功触发一次标准模型请求或结构化模型请求。

**Acceptance Scenarios**:

1. **Given** 系统已提供有效的 Google 凭证并将 Google 设为默认 provider，**When** 维护者触发一次模型请求，**Then** 系统能够成功解析并使用 Google provider
2. **Given** Google 已被设为当前 provider，**When** 现有工作流节点按既有统一入口请求标准模型或结构化模型，**Then** 调用方无需改动即可继续工作

---

### User Story 2 - 维护者继续使用现有 Provider (Priority: P2)

作为维护者，我希望在补充 Google 支持后，现有 OpenAI、Anthropic 和 Ollama 的使用方式保持兼容，这样本轮升级不会造成回归或额外迁移成本。

**Why this priority**: 本轮是补齐能力，不是替换现有能力；若既有 provider 回归，改动价值会被抵消。

**Independent Test**: 分别选择现有三个 provider 进行最小模型初始化验证，确认它们仍可通过相同的统一入口被解析和使用。

**Acceptance Scenarios**:

1. **Given** 维护者选择 OpenAI、Anthropic 或 Ollama 作为当前 provider，**When** 系统解析 provider 并创建模型访问上下文，**Then** 现有 provider 仍能被正常使用
2. **Given** 系统切换不同受支持 provider，**When** 维护者查看当前运行信息，**Then** 系统仍能返回一致的 provider 与模型标识

---

### User Story 3 - 维护者快速定位 Provider 配置问题 (Priority: P2)

作为维护者，我希望系统在 provider 不支持、凭证缺失或凭证无效时给出清晰且可区分的错误反馈，这样我可以直接定位问题，而不是被笼统报错卡住。

**Why this priority**: 这决定了 quickstart 与后续运维排障的成本，也是最容易被忽视但影响实际可用性的部分。

**Independent Test**: 人为构造“不支持的 provider”“缺少凭证”“无效凭证”三类错误，验证系统返回的信息可直接区分错误类型与处理方向。

**Acceptance Scenarios**:

1. **Given** 维护者配置了系统不支持的 provider 名称，**When** 系统解析 provider，**Then** 错误信息会指出非法值并列出当前支持列表
2. **Given** 维护者选择了受支持 provider 但未提供必需凭证，**When** 系统初始化该 provider，**Then** 错误信息会明确指出缺失的凭证类型
3. **Given** 维护者提供了无效凭证，**When** 系统首次尝试使用该 provider，**Then** 错误信息会明确表明这是认证失败而不是 provider 不支持或配置缺失

### Edge Cases

- 当维护者把 Google 设为当前 provider，但没有提供对应凭证时，系统必须在初始化阶段阻止继续执行
- 当维护者提供了受支持 provider 之外的名称时，系统必须拒绝继续并返回支持列表
- 当凭证存在但无效时，系统必须把认证失败与配置缺失区分开
- 当未显式指定默认模型时，系统仍应能为当前 provider 解析出可用的默认模型标识
- 当调用方请求结构化模型输出时，新增 provider 不应改变现有统一调用路径

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 系统必须将 Google 纳入受支持的 LLM provider 列表，与现有受支持 provider 并列可选
- **FR-002**: 系统必须在选择 Google 时接受并消费专属的 Google 凭证
- **FR-003**: 系统必须保持现有统一模型访问入口的调用方式不变，使既有工作流节点和服务无需改动调用面即可继续工作
- **FR-004**: 系统必须通过集中定义的 provider registry 管理受支持 provider 列表与 provider 路由规则
- **FR-005**: 系统必须允许所有受支持 provider 通过同一套统一入口提供标准模型访问能力
- **FR-006**: 系统必须允许当前声明为受支持的 provider 通过同一套统一入口提供结构化模型访问能力
- **FR-007**: 系统必须在新增 Google 后继续保持 OpenAI、Anthropic 和 Ollama 的兼容可用
- **FR-008**: 系统必须将 provider 选择保持为配置驱动行为，而不是依赖运行时插件扫描或热加载
- **FR-009**: 系统必须在遇到不受支持的 provider 名称时返回可读错误，并明确给出当前支持列表
- **FR-010**: 系统必须在缺少必需凭证时返回可读错误，并明确指出缺失的是哪类凭证
- **FR-011**: 系统必须在凭证无效时返回可读错误，并明确区分认证失败与配置缺失或 provider 不支持
- **FR-012**: 系统必须继续提供一致的当前 provider 与模型信息，供运行记录、日志或调用方读取
- **FR-013**: 系统必须让仅持有 Google 凭证的 quickstart 使用者无需修改业务调用代码即可完成最小 provider 配置

### Key Entities *(include if feature involves data)*

- **Provider Configuration**: 描述当前启用的 provider、默认模型以及与 provider 相关的凭证输入
- **Provider Registration**: 描述系统声明支持的 provider 列表以及每个 provider 对应的访问能力
- **Model Access Context**: 描述一次模型访问所使用的 provider 与模型标识，供调用方和运行记录读取
- **Provider Error State**: 描述 provider 不支持、凭证缺失、认证失败等可区分的错误状态

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 仅持有 Google 凭证的开发者能够在 15 分钟内完成本地 provider 配置并成功触发首次模型请求
- **SC-002**: 现有统一模型访问入口在接入 Google 后仍保持零调用面迁移，既有工作流节点无需修改即可继续请求模型
- **SC-003**: 在验收中构造的“不支持 provider”“缺少凭证”“无效凭证”三类场景里，100% 都能得到可区分、可读的错误反馈
- **SC-004**: Google、OpenAI、Anthropic、Ollama 四类受支持 provider 都能通过配置被正确解析并进入可用状态
- **SC-005**: quickstart 不再因为“代码尚未支持 Google provider”而阻塞；剩余失败原因仅限于环境配置或凭证有效性问题

## Assumptions & Dependencies

- 当前系统会继续保留统一的模型访问入口，而不是让调用方直接依赖某个特定 provider
- 维护者能够提供至少一种受支持 provider 所需的有效凭证或本地访问条件
- 本轮范围内仍以补齐 provider 基线能力为主，不扩展为完整 provider 平台治理能力

## Out of Scope

- 完整插件包扫描、动态加载、热插拔机制
- 模型别名系统、provider/model 复合路由扩展
- 密钥轮换、多凭证故障转移、集中密钥治理
- 前端页面、交互或配置入口改动
