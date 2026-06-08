/**
 * 节点注册表 - 默认节点注册
 * 为什么这样分层：把默认的 5 类节点统一通过 registry 进行声明，分离具体的 UI 组件与其配置元数据。
 */

import { Cpu, FileInput, FileOutput, ShieldCheck, UserCheck, Wrench } from 'lucide-react';
import { registry } from './index';

// 节点组件
import InputNode from '../nodes/InputNode';
import ProcessNode from '../nodes/ProcessNode';
import GateNode from '../nodes/GateNode';
import CheckerNode from '../nodes/CheckerNode';
import OutputNode from '../nodes/OutputNode';
import ToolNode from '../nodes/ToolNode';

// 配置 Schema
import {
    inputSchema,
    processSchema,
    gateSchema,
    checkerSchema,
    outputSchema,
    toolSchema,
} from './nodeSchemas';

export function registerDefaultNodes() {
    registry.register({
        type: 'input',
        title: '输入节点',
        category: '基础',
        description: '工作流起点，解析用户意图',
        icon: FileInput,
        color: '#3b82f6', // blue-500
        component: InputNode,
        formSchema: inputSchema,
        defaultData: {},
    });

    registry.register({
        type: 'process',
        title: '处理节点',
        category: '处理',
        description: 'LLM内容生成与处理',
        icon: Cpu,
        color: '#22c55e', // green-500
        component: ProcessNode,
        formSchema: processSchema,
        defaultData: { config: { modelName: 'gpt-4o', maxTokens: 2000 } },
    });

    registry.register({
        type: 'gate',
        title: '门控节点',
        category: '控制',
        description: '人机交互审批与编辑',
        icon: UserCheck,
        color: '#eab308', // yellow-500
        component: GateNode,
        formSchema: gateSchema,
        defaultData: { config: { gateType: 'approval', timeout: 3600, autoApproveThreshold: 0.95 } },
    });

    registry.register({
        type: 'tool',
        title: '工具节点',
        category: '工具',
        description: '调用 Tool Registry 中的受控工具',
        icon: Wrench,
        color: '#14b8a6', // teal-500
        component: ToolNode,
        formSchema: toolSchema,
        defaultData: {
            config: {
                toolName: 'validation.json_schema_validate',
                executionPhase: 'pre_outline',
                approvalMode: 'policy_default',
                failureStrategy: 'terminate',
                maxAttempts: 2,
                input: {
                    schema: { type: 'object' },
                    instance: {},
                },
                inputMapping: {},
                outputMapping: {
                    stateKey: 'tool_result',
                    persistArtifact: false,
                    artifactType: 'tool_result',
                },
            },
        },
    });

    registry.register({
        type: 'checker',
        title: '核查节点',
        category: '核查',
        description: '事实核查与置信度检测',
        icon: ShieldCheck,
        color: '#f97316', // orange-500
        component: CheckerNode,
        formSchema: checkerSchema,
        defaultData: { config: { confidenceThreshold: 0.8 } },
    });

    registry.register({
        type: 'output',
        title: '输出节点',
        category: '基础',
        description: '工作流终点，输出结果',
        icon: FileOutput,
        color: '#a855f7', // purple-500
        component: OutputNode,
        formSchema: outputSchema,
        defaultData: { config: { outputFormat: 'markdown' } },
    });
}
