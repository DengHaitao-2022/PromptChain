/**
 * ELK 布局引擎配置
 * 为什么这样分层：分离布局算法的纯计算参数，方便后续扩展更多布局算法或者在界面上暴露配置项给用户调整。
 */

export interface ElkLayoutOptions {
    direction: 'RIGHT' | 'DOWN' | 'TOP' | 'LEFT'; // RIGHT 对应 LR，DOWN 对应 TB
    nodeSpacing: number;
    edgeSpacing: number;
    layerSpacing: number;
    edgeRouting: 'ORTHOGONAL' | 'POLYLINE' | 'SPLINES';
}

export const defaultElkOptions: ElkLayoutOptions = {
    direction: 'RIGHT',
    nodeSpacing: 50,
    edgeSpacing: 30,
    layerSpacing: 100,
    edgeRouting: 'ORTHOGONAL',
};

export function getElkLayoutConfig(options: ElkLayoutOptions) {
    return {
        'elk.algorithm': 'layered',
        'elk.direction': options.direction,
        'elk.spacing.nodeNode': String(options.nodeSpacing),
        'elk.spacing.edgeNode': String(options.edgeSpacing),
        'elk.layered.spacing.nodeNodeBetweenLayers': String(options.layerSpacing),
        'elk.edgeRouting': options.edgeRouting,
        'elk.layered.nodePlacement.strategy': 'BRANDES_KOEPF',
    };
}
