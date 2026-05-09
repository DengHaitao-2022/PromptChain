/**
 * ELK 异步布局执行引擎
 * 为什么这样分层：将所有对 elkjs 的实例化和调用封装为一个纯异步过程。
 * elkjs 在浏览器端如果同步执行复杂图可能会阻塞渲染，后续还可无缝迁移至 Web Worker。
 */

import ELK from 'elkjs/lib/elk.bundled.js';
import type { Node, Edge } from '@xyflow/react';
import { type ElkLayoutOptions, defaultElkOptions, getElkLayoutConfig } from './config';
import { mapToElkGraph } from './graphMapper';
import { applyElkLayout } from './applyLayout';

const elk = new ELK();

export async function layoutGraph(
    nodes: Node[],
    edges: Edge[],
    options: Partial<ElkLayoutOptions> = {},
    filterIds?: string[] // 用于支持“选区重排”
): Promise<Node[]> {
    if (nodes.length === 0) return nodes;

    // TODO: 目前 elkjs 在重排局部选区时，由于必须考虑全局上下文才能算好相对位置，
    // 最简单的策略是：用完整的图算出一版全局布局，但在 apply 阶段只提取选区中节点的新坐标。
    // 这可能导致选区坐标跳跃。如果要在原位排列选区，可以提取子图进行独立布局再叠加偏移。
    // 作为初步阶段，我们直接在应用阶段过滤（详见 applyElkLayout）。

    const mergedOptions = { ...defaultElkOptions, ...options };
    const layoutOptions = getElkLayoutConfig(mergedOptions);

    const graph = mapToElkGraph(nodes, edges);
    graph.layoutOptions = {
        ...graph.layoutOptions,
        ...layoutOptions,
    };

    try {
        const layoutedGraph = await elk.layout(graph);
        return applyElkLayout(nodes, layoutedGraph, { filterIds });
    } catch (err) {
        console.error('ELK Layout Error:', err);
        return nodes; // 发生错误时优雅降级，返回原坐标
    }
}
