/**
 * 节点注册表 - 类型定义
 * 为什么这样分层：规范化节点定义，将节点行为、UI和数据结构集中声明。
 * 以便后续扩展新的节点类型时，不需要去多个组件中改 switch-case。
 */

import type { ZodTypeAny } from 'zod';
import type { ComponentType } from 'react';
import type { NodeProps } from '@xyflow/react';

export interface NodeDefinition {
    type: string;
    title: string;
    category: string;
    description: string;
    icon: ComponentType<{ size?: number; className?: string }>;
    color: string;
    ports?: string[];
    defaultData?: Record<string, unknown>;
    formSchema?: ZodTypeAny;
    component: ComponentType<NodeProps>;
}
