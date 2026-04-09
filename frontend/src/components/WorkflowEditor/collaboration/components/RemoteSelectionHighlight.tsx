'use client';

import { useEffect, useState } from 'react';
import { useReactFlow } from '@xyflow/react';
import { provider } from '../yjs/provider';
import { getRemoteSelections, type UserPresence } from '../yjs/awareness';
import styles from './CollaborationStyles.module.css';

/**
 * 远程选择高亮 / 软锁提示层
 * 获取所有远程客户端的选中态，并在对应的节点上方绘制带颜色的边框和昵称 tag
 */
export function RemoteSelectionHighlight() {
    const { getNodes } = useReactFlow();
    const [selections, setSelections] = useState<Map<string, UserPresence[]>>(new Map());

    useEffect(() => {
        if (!provider) return;

        const updateSelections = () => {
            if (!provider) return;
            const localClientId = provider.awareness.clientID;
            const newSelections = getRemoteSelections(localClientId);
            setSelections(newSelections);
        };

        updateSelections();
        provider.awareness.on('change', updateSelections);

        return () => {
            if (provider) {
                provider.awareness.off('change', updateSelections);
            }
        };
    }, []);

    if (selections.size === 0) {
        return null;
    }

    // 找到当前画布中的节点并获取坐标，画出遮罩
    // 其实更好的做法是通过 React Flow 的自定义 node 容器，或者在 Node 配置里接收 selectedBy。
    // 但是作为一个独立的 overlay 层，这样更解耦，不会入侵节点内部实现。
    const nodes = getNodes();

    return (
        <div className={styles.selectionOverlay}>
            {nodes.map(node => {
                const users = selections.get(node.id);
                if (!users || users.length === 0) return null;

                // 取第一个用户的颜色作为边框
                const mainUser = users[0];

                return (
                    <div
                        key={node.id}
                        className={styles.remoteSelectionBox}
                        style={{
                            transform: `translate(${node.position.x}px, ${node.position.y}px)`,
                            width: node.measured?.width || 250,
                            height: node.measured?.height || 100,
                            borderColor: mainUser.color,
                        }}
                    >
                        <div
                            className={styles.remoteSelectionTag}
                            style={{ backgroundColor: mainUser.color }}
                        >
                            {users.map(u => u.name).join(', ')} 正在编辑
                        </div>
                    </div>
                );
            })}
        </div>
    );
}
