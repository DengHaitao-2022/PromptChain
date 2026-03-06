'use client';

import WorkflowEditor from '@/components/WorkflowEditor';

/**
 * 工作流编辑器页面
 */
export default function WorkflowEditPage() {
    const handleSave = (nodes: unknown[], edges: unknown[]) => {
        console.log('保存工作流:', { nodes, edges });
        // TODO: 调用后端API保存
    };

    return (
        <main>
            <WorkflowEditor onSave={handleSave} />
        </main>
    );
}
