// 节点组件统一导入
import InputNode from './InputNode';
import ProcessNode from './ProcessNode';
import GateNode from './GateNode';
import CheckerNode from './CheckerNode';
import OutputNode from './OutputNode';

// 节点组件统一导出
export { InputNode, ProcessNode, GateNode, CheckerNode, OutputNode };

// 节点数据类型导出
export type { InputNodeData } from './InputNode';
export type { ProcessNodeData } from './ProcessNode';
export type { GateNodeData } from './GateNode';
export type { CheckerNodeData } from './CheckerNode';
export type { OutputNodeData } from './OutputNode';

/**
 * 节点类型映射 - 用于 ReactFlow nodeTypes
 *
 * 映射规则:
 * - input:  用户意图解析 (Blue)
 * - process: 内容生成 / 任务执行 (Green)
 * - gate:    人工审批 / 逻辑分流 (Orange)
 * - checker: 事实核查 / 质量自检 (Purple)
 * - output:  最终成果交付 (Gray)
 */
export const nodeTypes = {
  input: InputNode,
  process: ProcessNode,
  gate: GateNode,
  checker: CheckerNode,
  output: OutputNode,
} as const;
