'use client';

import { X } from 'lucide-react';
import type { Node } from '@xyflow/react';
import styles from './PanelStyles.module.css';

interface NodeConfigPanelProps {
    node: Node;
    onClose: () => void;
    onChange: (nodeId: string, newData: Record<string, unknown>) => void;
}

/**
 * 节点配置面板 - 右侧面板
 * 根据节点类型显示不同的配置选项
 */
export default function NodeConfigPanel({
    node,
    onClose,
    onChange,
}: NodeConfigPanelProps) {
    // 更新标签
    const handleLabelChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        onChange(node.id, { label: e.target.value });
    };

    // 渲染通用配置
    const renderCommonConfig = () => (
        <div className={styles.configSection}>
            <label className={styles.configLabel}>节点名称</label>
            <input
                type="text"
                className={styles.configInput}
                value={node.data.label as string || ''}
                onChange={handleLabelChange}
            />
        </div>
    );

    // 渲染处理节点配置
    const renderProcessConfig = () => (
        <>
            <div className={styles.configSection}>
                <label className={styles.configLabel}>模型</label>
                <select
                    className={styles.configSelect}
                    value={(node.data.config as { modelName?: string })?.modelName || 'gpt-4o'}
                    onChange={(e) =>
                        onChange(node.id, {
                            config: { ...(node.data.config || {}), modelName: e.target.value },
                        })
                    }
                >
                    <option value="gpt-4o">GPT-4o</option>
                    <option value="gpt-4o-mini">GPT-4o Mini</option>
                    <option value="claude-3.5-sonnet">Claude 3.5 Sonnet</option>
                    <option value="gemini-2.0-flash">Gemini 2.0 Flash</option>
                </select>
            </div>
            <div className={styles.configSection}>
                <label className={styles.configLabel}>最大Token</label>
                <input
                    type="number"
                    className={styles.configInput}
                    value={(node.data.config as { maxTokens?: number })?.maxTokens || 2000}
                    onChange={(e) =>
                        onChange(node.id, {
                            config: { ...(node.data.config || {}), maxTokens: parseInt(e.target.value) },
                        })
                    }
                />
            </div>
        </>
    );

    // 渲染门控节点配置
    const renderGateConfig = () => (
        <>
            <div className={styles.configSection}>
                <label className={styles.configLabel}>门控类型</label>
                <select
                    className={styles.configSelect}
                    value={(node.data.config as { gateType?: string })?.gateType || 'approval'}
                    onChange={(e) =>
                        onChange(node.id, {
                            config: { ...(node.data.config || {}), gateType: e.target.value },
                        })
                    }
                >
                    <option value="approval">审批</option>
                    <option value="edit">编辑</option>
                    <option value="input">输入</option>
                </select>
            </div>
            <div className={styles.configSection}>
                <label className={styles.configLabel}>超时时间(秒)</label>
                <input
                    type="number"
                    className={styles.configInput}
                    value={(node.data.config as { timeout?: number })?.timeout || 3600}
                    onChange={(e) =>
                        onChange(node.id, {
                            config: { ...(node.data.config || {}), timeout: parseInt(e.target.value) },
                        })
                    }
                />
            </div>
            <div className={styles.configSection}>
                <label className={styles.configLabel}>自动通过阈值</label>
                <input
                    type="number"
                    step="0.05"
                    min="0"
                    max="1"
                    className={styles.configInput}
                    value={(node.data.config as { autoApproveThreshold?: number })?.autoApproveThreshold || 0.95}
                    onChange={(e) =>
                        onChange(node.id, {
                            config: { ...(node.data.config || {}), autoApproveThreshold: parseFloat(e.target.value) },
                        })
                    }
                />
            </div>
        </>
    );

    // 渲染核查节点配置
    const renderCheckerConfig = () => (
        <div className={styles.configSection}>
            <label className={styles.configLabel}>置信度阈值</label>
            <input
                type="number"
                step="0.05"
                min="0"
                max="1"
                className={styles.configInput}
                value={(node.data.config as { confidenceThreshold?: number })?.confidenceThreshold || 0.8}
                onChange={(e) =>
                    onChange(node.id, {
                        config: { ...(node.data.config || {}), confidenceThreshold: parseFloat(e.target.value) },
                    })
                }
            />
        </div>
    );

    // 渲染输出节点配置
    const renderOutputConfig = () => (
        <div className={styles.configSection}>
            <label className={styles.configLabel}>输出格式</label>
            <select
                className={styles.configSelect}
                value={(node.data.config as { outputFormat?: string })?.outputFormat || 'markdown'}
                onChange={(e) =>
                    onChange(node.id, {
                        config: { ...(node.data.config || {}), outputFormat: e.target.value },
                    })
                }
            >
                <option value="text">纯文本</option>
                <option value="markdown">Markdown</option>
                <option value="json">JSON</option>
            </select>
        </div>
    );

    // 根据节点类型渲染配置
    const renderTypeConfig = () => {
        switch (node.type) {
            case 'process':
                return renderProcessConfig();
            case 'gate':
                return renderGateConfig();
            case 'checker':
                return renderCheckerConfig();
            case 'output':
                return renderOutputConfig();
            default:
                return null;
        }
    };

    return (
        <div className={styles.configPanel}>
            <div className={styles.panelHeader}>
                <h3>节点配置</h3>
                <button className={styles.closeButton} onClick={onClose}>
                    <X size={18} />
                </button>
            </div>

            <div className={styles.panelContent}>
                {renderCommonConfig()}
                {renderTypeConfig()}
            </div>
        </div>
    );
}
