/**
 * 属性面板
 * 为什么这样分层：通过 registry 驱动表单渲染，完全摆脱原来 hardcode switch-case 的逻辑。
 * 如果选中未知节点，会优雅降级或提示不支持。
 */

'use client';

import { X } from 'lucide-react';
import type { Node } from '@xyflow/react';
import { registry } from '../registry';
import SchemaFormRenderer from '../renderers/SchemaFormRenderer';
import styles from './PanelStyles.module.css';

interface PropertiesPanelProps {
    node: Node;
    onClose: () => void;
    onChange: (nodeId: string, newData: Record<string, unknown>) => void;
}

export default function PropertiesPanel({ node, onClose, onChange }: PropertiesPanelProps) {
    const nodeDef = registry.get(node.type ?? '');

    // 通用的标题更新
    const handleLabelChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        onChange(node.id, { label: e.target.value });
    };

    // SchemaFormRenderer 回调，只需要更新 node.data.config
    const handleConfigChange = (config: Record<string, unknown>) => {
        // 这里需要保留 config 里的其它未在 schema 中的元数据吗？
        // 一般来说表单负责全部 config，或者合并
        onChange(node.id, {
            config: {
                ...(node.data.config as Record<string, unknown> || {}),
                ...config,
            }
        });
    };

    return (
        <div className={styles.configPanel}>
            <div className={styles.panelHeader}>
                <h3>{nodeDef?.title || '节点配置'}</h3>
                <button className={styles.closeButton} onClick={onClose}>
                    <X size={18} />
                </button>
            </div>

            <div className={styles.panelContent}>
                <div className={styles.configSection}>
                    <label className={styles.configLabel}>节点名称</label>
                    <input
                        type="text"
                        className={styles.configInput}
                        value={(node.data.label as string) || ''}
                        onChange={handleLabelChange}
                    />
                </div>

                {nodeDef?.formSchema ? (
                    <SchemaFormRenderer
                        key={`${node.id}:${node.type}`}
                        schema={nodeDef.formSchema}
                        defaultValues={(node.data.config as Record<string, unknown>) || {}}
                        onChange={handleConfigChange}
                    />
                ) : (
                    <div className={styles.emptyForm}>当前节点无更多配置项</div>
                )}
            </div>
        </div>
    );
}
