'use client';

import { FileInput, Cpu, UserCheck, ShieldCheck, FileOutput } from 'lucide-react';
import styles from './PanelStyles.module.css';

// 节点模板定义
const nodeTemplates = [
    {
        type: 'input',
        label: '输入节点',
        description: '工作流起点，解析用户意图',
        icon: FileInput,
        color: '#3b82f6',
    },
    {
        type: 'process',
        label: '处理节点',
        description: 'LLM内容生成与处理',
        icon: Cpu,
        color: '#22c55e',
    },
    {
        type: 'gate',
        label: '门控节点',
        description: '人机交互审批与编辑',
        icon: UserCheck,
        color: '#eab308',
    },
    {
        type: 'checker',
        label: '核查节点',
        description: '事实核查与置信度检测',
        icon: ShieldCheck,
        color: '#f97316',
    },
    {
        type: 'output',
        label: '输出节点',
        description: '工作流终点，输出结果',
        icon: FileOutput,
        color: '#a855f7',
    },
];

/**
 * 节点模板库 - 左侧面板
 * 支持拖拽节点到画布
 */
export default function NodeLibrary() {
    // 开始拖拽
    const onDragStart = (event: React.DragEvent, nodeType: string) => {
        event.dataTransfer.setData('application/reactflow', nodeType);
        event.dataTransfer.effectAllowed = 'move';
    };

    return (
        <div className={styles.nodeLibrary}>
            <div className={styles.libraryHeader}>
                <h3>节点库</h3>
                <span className={styles.hint}>拖拽到画布添加</span>
            </div>

            <div className={styles.nodeList}>
                {nodeTemplates.map((template) => {
                    const Icon = template.icon;
                    return (
                        <div
                            key={template.type}
                            className={styles.nodeTemplate}
                            draggable
                            onDragStart={(e) => onDragStart(e, template.type)}
                            style={{ borderLeftColor: template.color }}
                        >
                            <div className={styles.templateIcon} style={{ color: template.color }}>
                                <Icon size={20} />
                            </div>
                            <div className={styles.templateInfo}>
                                <div className={styles.templateLabel}>{template.label}</div>
                                <div className={styles.templateDesc}>{template.description}</div>
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}
