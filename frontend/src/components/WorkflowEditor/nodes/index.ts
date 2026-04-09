/**
 * 节点列表统一导出
 * 为什么这样分层：原先这里是硬编码的对象映射，现在改为基于 registry 动态导出。
 * 对外依然输出 nodeTypes 以兼容 ReactFlow 的 api。
 */

import { registerDefaultNodes } from '../registry/nodeFactories';
import { registry } from '../registry';

// 首次加载模块时注册所有默认节点
registerDefaultNodes();

// 导出生成的 nodeTypes 供给 ReactFlow 使用
export const nodeTypes = registry.getNodeTypes();

export type { InputNodeData } from './InputNode';
export type { ProcessNodeData } from './ProcessNode';
export type { GateNodeData } from './GateNode';
export type { CheckerNodeData } from './CheckerNode';
export type { OutputNodeData } from './OutputNode';
