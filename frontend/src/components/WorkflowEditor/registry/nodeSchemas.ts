/**
 * 节点注册表 - 属性校验 Schema
 * 为什么这样分层：使用 Zod 定义节点的配置属性结构，作为唯一的契约数据源，
 * 既能提供静态的 TS 类型推导，又能用于运行时的 react-hook-form 校验和动态表单渲染。
 */

import { z } from 'zod';

export const processSchema = z.object({
    modelName: z.enum(['gpt-4o', 'gpt-4o-mini', 'claude-3.5-sonnet', 'gemini-2.0-flash'])
        .describe('模型')
        .default('gpt-4o'),
    maxTokens: z.number()
        .min(1, '不能小于1')
        .describe('最大Token')
        .default(2000),
});

export const gateSchema = z.object({
    gateType: z.enum(['approval', 'edit', 'input'])
        .describe('门控类型')
        .default('approval'),
    timeout: z.number()
        .min(0, '超时不能为负数')
        .describe('超时时间(秒)')
        .default(3600),
    autoApproveThreshold: z.number()
        .min(0).max(1)
        .describe('自动通过阈值')
        .default(0.95),
});

export const checkerSchema = z.object({
    confidenceThreshold: z.number()
        .min(0).max(1)
        .describe('置信度阈值')
        .default(0.8),
});

export const toolSchema = z.object({
    toolName: z.enum([
        'artifact.read',
        'artifact.write',
        'artifact.list_versions',
        'retrieval.query_workspace_knowledge',
        'document.load_text',
        'document.chunk_text',
        'validation.json_schema_validate',
        'content.outline_consistency_check',
        'content.style_check',
        'fact.check_claims',
    ])
        .describe('工具')
        .default('validation.json_schema_validate'),
    executionPhase: z.enum(['pre_outline', 'post_content', 'pre_finalize'])
        .describe('执行阶段')
        .default('pre_outline'),
    approvalMode: z.enum(['policy_default', 'auto', 'gate_required'])
        .describe('审批策略')
        .default('policy_default'),
    failureStrategy: z.enum(['terminate', 'skip', 'retry', 'enter_gate'])
        .describe('失败策略')
        .default('terminate'),
    maxAttempts: z.number()
        .min(1, '至少执行1次')
        .max(5, '最多重试5次')
        .describe('最大尝试次数')
        .default(2),
    input: z.record(z.string(), z.unknown())
        .describe('固定输入 JSON')
        .default({}),
    inputMapping: z.record(z.string(), z.unknown())
        .describe('输入映射 JSON')
        .default({}),
    outputMapping: z.record(z.string(), z.unknown())
        .describe('输出映射 JSON')
        .default({}),
});

export const outputSchema = z.object({
    outputFormat: z.enum(['text', 'markdown', 'json'])
        .describe('输出格式')
        .default('markdown'),
});

export const inputSchema = z.object({});
