/**
 * 画布控制工具栏
 * 为什么这样分层：将所有影响视图布局和节点的画布全局操作，收敛在一处组件。
 * 组件内部消费 useReactFlow() 提供的视图方法和 store 里提供的 ELK 自动布局。
 */

'use client';

import { useReactFlow, getNodesBounds } from '@xyflow/react';
import { Network, SplitSquareHorizontal, SplitSquareVertical, Expand, Focus, Pin, PinOff } from 'lucide-react';
import { useWorkflowActions } from './store/actions';
import { useWorkflowContext } from './provider/WorkflowProvider';
import { selectIsLayouting, selectLayoutDirection, selectSelectedNode } from './store/selectors';
import styles from './ToolbarStyles.module.css';

export default function CanvasToolbar() {
    const { fitView, fitBounds, getNodes } = useReactFlow();
    const actions = useWorkflowActions();

    const isLayouting = useWorkflowContext(selectIsLayouting);
    const layoutDirection = useWorkflowContext(selectLayoutDirection);
    const selectedNode = useWorkflowContext(selectSelectedNode);

    // 全图自动布局
    const handleLayoutAll = () => {
        actions.autoLayout();
    };

    // 选区重排
    const handleLayoutSelection = () => {
        const selectedIds = getNodes().filter(n => n.selected).map(n => n.id);
        if (selectedIds.length > 0) {
            actions.autoLayout({}, selectedIds);
        }
    };

    // 自适应视图
    const handleFitView = () => {
        fitView({ padding: 0.2, duration: 800 });
    };

    // 居中选区
    const handleCenterSelection = () => {
        const selectedNodes = getNodes().filter(n => n.selected);
        if (selectedNodes.length > 0) {
            const rect = getNodesBounds(selectedNodes);
            fitBounds(rect, { padding: 0.2, duration: 800 });
        }
    };

    // 切换布局方向
    const handleToggleDirection = () => {
        const nextDirection = layoutDirection === 'RIGHT' ? 'DOWN' : 'RIGHT';
        actions.setLayoutDirection(nextDirection);
        actions.autoLayout({ direction: nextDirection });
    };

    // 锁定/解锁当前选中节点
    const handleTogglePin = () => {
        if (selectedNode) {
            actions.togglePinNode(selectedNode.id);
        }
    };

    const hasSelection = !!selectedNode;
    const isSelectedPinned = selectedNode?.data?.isPinned;

    return (
        <div className={styles.canvasToolbar}>
            <button
                className={styles.toolButton}
                onClick={handleLayoutAll}
                disabled={isLayouting}
                title="全图自动布局"
            >
                <Network size={18} />
            </button>

            <button
                className={styles.toolButton}
                onClick={handleLayoutSelection}
                disabled={isLayouting || !hasSelection}
                title="选区重排"
            >
                <Network size={18} className={styles.selectionIcon} />
            </button>

            <div className={styles.divider} />

            <button
                className={styles.toolButton}
                onClick={handleFitView}
                title="自适应缩放 (Fit View)"
            >
                <Expand size={18} />
            </button>

            <button
                className={styles.toolButton}
                onClick={handleCenterSelection}
                disabled={!hasSelection}
                title="居中选区"
            >
                <Focus size={18} />
            </button>

            <div className={styles.divider} />

            <button
                className={styles.toolButton}
                onClick={handleToggleDirection}
                disabled={isLayouting}
                title={layoutDirection === 'RIGHT' ? "当前横向，点击切换纵向" : "当前纵向，点击切换横向"}
            >
                {layoutDirection === 'RIGHT' ? <SplitSquareHorizontal size={18} /> : <SplitSquareVertical size={18} />}
            </button>

            <button
                className={`${styles.toolButton} ${isSelectedPinned ? styles.pinnedActive : ''}`}
                onClick={handleTogglePin}
                disabled={!hasSelection}
                title={isSelectedPinned ? "解锁节点位置" : "锁定节点（不受自动布局影响）"}
            >
                {isSelectedPinned ? <PinOff size={18} /> : <Pin size={18} />}
            </button>
        </div>
    );
}
