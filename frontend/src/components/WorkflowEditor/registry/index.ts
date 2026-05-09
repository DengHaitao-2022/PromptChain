/**
 * 节点注册表 - 注册表实例
 * 为什么这样分层：实现一个单例注册表，替代原有的硬编码类型映射。
 * 支持动态注册（如后续增加新类型甚至插件扩展）。
 */

import type { NodeDefinition } from './types';

class NodeRegistry {
    private definitions = new Map<string, NodeDefinition>();

    register(definition: NodeDefinition) {
        this.definitions.set(definition.type, definition);
    }

    get(type: string): NodeDefinition | undefined {
        return this.definitions.get(type);
    }

    getAll(): NodeDefinition[] {
        return Array.from(this.definitions.values());
    }

    getNodeTypes() {
        const types: Record<string, React.ComponentType<any>> = {};
        for (const [type, def] of this.definitions.entries()) {
            types[type] = def.component;
        }
        return types;
    }
}

export const registry = new NodeRegistry();
