/**
 * WebSocket Provider 管理
 * 为什么这样分层：隔离网络连接层。管理重连和断开，兼容无协作情况的回退。
 */

import { WebsocketProvider } from 'y-websocket';
import { ydoc } from './ydoc';

const WS_URL = process.env.NEXT_PUBLIC_YJS_WS_URL || 'ws://localhost:18080';

export let provider: WebsocketProvider | null = null;

export function initProvider(roomName: string, user: { id: string, name: string, color: string }) {
    if (provider) {
        provider.destroy();
    }

    // 连接到协作房间
    provider = new WebsocketProvider(WS_URL, roomName, ydoc, {
        connect: true,
    });

    // 设置自身的初始 presence (awareness)
    provider.awareness.setLocalStateField('user', user);
    provider.awareness.setLocalStateField('selection', []);
    provider.awareness.setLocalStateField('cursor', null);

    return provider;
}

export function destroyProvider() {
    if (provider) {
        provider.destroy();
        provider = null;
    }
}
