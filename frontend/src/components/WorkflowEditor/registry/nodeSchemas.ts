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

export const outputSchema = z.object({
    outputFormat: z.enum(['text', 'markdown', 'json'])
        .describe('输出格式')
        .default('markdown'),
});

export const inputSchema = z.object({});
