'use client';

import { registry } from '../registry';
import styles from './PanelStyles.module.css';

/**
 * 节点模板库 - 左侧面板
 * 支持拖拽节点到画布
 */
interface NodeLibraryProps {
    readOnly?: boolean;
}

export default function NodeLibrary({ readOnly = false }: NodeLibraryProps) {
    // 开始拖拽
    const onDragStart = (event: React.DragEvent, nodeType: string) => {
        if (readOnly) {
            event.preventDefault();
            return;
        }

        event.dataTransfer.setData('application/reactflow', nodeType);
        event.dataTransfer.effectAllowed = 'move';
    };

    const nodeTemplates = registry.getAll();

    return (
        <div className={styles.nodeLibrary}>
            <div className={styles.libraryHeader}>
                <h3>节点库</h3>
                <span className={styles.hint}>
                    {readOnly ? '只读模式不可编辑' : '拖拽到画布添加'}
                </span>
            </div>

            <div className={styles.nodeList}>
                {nodeTemplates.map((template) => {
                    const Icon = template.icon;
                    return (
                        <div
                            key={template.type}
                            className={styles.nodeTemplate}
                            draggable={!readOnly}
                            aria-disabled={readOnly}
                            onDragStart={(e) => onDragStart(e, template.type)}
                            style={{
                                borderLeftColor: template.color,
                                cursor: readOnly ? 'not-allowed' : undefined,
                            }}
                        >
                            <div className={styles.templateIcon} style={{ color: template.color }}>
                                <Icon size={20} />
                            </div>
                            <div className={styles.templateInfo}>
                                <div className={styles.templateLabel}>{template.title}</div>
                                <div className={styles.templateDesc}>{template.description}</div>
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}
