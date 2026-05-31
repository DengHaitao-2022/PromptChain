'use client';

import React, { Suspense, useEffect, useState } from 'react';
import NextLink from 'next/link';
import { useSearchParams } from 'next/navigation';
import { AuthShell } from '@/components/AuthShell/AuthShell';
import { acceptWorkspaceInvite } from '@/lib/auth';
import styles from '../login/login.module.css';

type InviteStatus = 'loading' | 'success' | 'error' | 'missing_token' | 'login_required';

interface InviteState {
  status: InviteStatus;
  message?: string;
}

// 使用模块级缓存，避免 Strict Mode 下重复接受同一邀请。
const promiseCache: { [token: string]: Promise<{ message: string }> | undefined } = {};
const terminalStateCache: { [token: string]: InviteState | undefined } = {};

function getSessionStorageKey(token: string) {
  return `workspace_invite_status_${token}`;
}

function getSessionMessageKey(token: string) {
  return `workspace_invite_message_${token}`;
}

function getInviteErrorState(error: unknown): InviteState {
  const message = error instanceof Error ? error.message : '邀请链接无效或已过期';
  if (message.includes('未登录') || message.includes('登录已过期')) {
    return {
      status: 'login_required',
      message: '请先登录账号，再重新打开邀请链接。',
    };
  }
  if (message.includes('已经是该工作空间的成员')) {
    return {
      status: 'success',
      message: '您已经是该工作空间的成员。',
    };
  }
  return { status: 'error', message };
}

function InviteComponent() {
  const searchParams = useSearchParams();
  const token = searchParams.get('token');
  const [inviteState, setInviteState] = useState<InviteState>(() => {
    if (!token) return { status: 'missing_token' };
    if (
      typeof window !== 'undefined' &&
      sessionStorage.getItem(getSessionStorageKey(token)) === 'success'
    ) {
      return {
        status: 'success',
        message: sessionStorage.getItem(getSessionMessageKey(token)) || '您已成功加入工作空间。',
      };
    }
    return terminalStateCache[token] || { status: 'loading' };
  });

  useEffect(() => {
    let isActive = true;

    const acceptInvite = async () => {
      if (!token) {
        if (isActive) setInviteState({ status: 'missing_token' });
        return;
      }

      if (
        typeof window !== 'undefined' &&
        sessionStorage.getItem(getSessionStorageKey(token)) === 'success'
      ) {
        if (isActive) {
          setInviteState({
            status: 'success',
            message: sessionStorage.getItem(getSessionMessageKey(token)) || '您已成功加入工作空间。',
          });
        }
        return;
      }

      if (terminalStateCache[token]) {
        if (isActive) setInviteState(terminalStateCache[token]!);
        return;
      }

      const inFlightPromise = promiseCache[token];
      if (inFlightPromise) {
        if (isActive) setInviteState({ status: 'loading' });
        try {
          const result = await inFlightPromise;
          const nextState = { status: 'success', message: result.message } as InviteState;
          terminalStateCache[token] = nextState;
          if (isActive) setInviteState(nextState);
        } catch (error) {
          const nextState = getInviteErrorState(error);
          if (nextState.status === 'success') {
            terminalStateCache[token] = nextState;
          }
          if (isActive) setInviteState(nextState);
        }
        return;
      }

      if (isActive) setInviteState({ status: 'loading' });

      const invitePromise = acceptWorkspaceInvite(token);
      promiseCache[token] = invitePromise;

      try {
        const result = await invitePromise;
        const nextState = { status: 'success', message: result.message } as InviteState;
        terminalStateCache[token] = nextState;
        if (typeof window !== 'undefined') {
          sessionStorage.setItem(getSessionStorageKey(token), 'success');
          sessionStorage.setItem(getSessionMessageKey(token), result.message);
        }
        if (isActive) setInviteState(nextState);
      } catch (error) {
        const nextState = getInviteErrorState(error);
        if (nextState.status === 'success' && typeof window !== 'undefined') {
          terminalStateCache[token] = nextState;
          sessionStorage.setItem(getSessionStorageKey(token), 'success');
          sessionStorage.setItem(getSessionMessageKey(token), nextState.message || '');
        }
        if (isActive) setInviteState(nextState);
      } finally {
        delete promiseCache[token];
      }
    };

    acceptInvite();

    return () => {
      isActive = false;
    };
  }, [token]);

  const loginHref = token ? `/login?next=${encodeURIComponent(`/invite?token=${token}`)}` : '/login';

  const renderStatus = () => {
    switch (inviteState.status) {
      case 'loading':
        return <div className={styles.helperText}>正在接受工作空间邀请...</div>;
      case 'success':
        return (
          <div className={styles.successBox}>
            <h2>已加入工作空间</h2>
            <p>{inviteState.message || '您已成功加入工作空间。'}</p>
            <NextLink href="/console" className={styles.forgotLink}>
              进入控制台
            </NextLink>
          </div>
        );
      case 'login_required':
        return (
          <div className={styles.errorBanner}>
            <strong>请先登录</strong>
            <span>{inviteState.message}</span>
            <NextLink href={loginHref} className={styles.forgotLink}>
              前往登录
            </NextLink>
          </div>
        );
      case 'missing_token':
        return (
          <div className={styles.errorBanner}>
            <strong>缺少邀请令牌</strong>
            <span>请检查邮件链接是否完整，或联系工作空间管理员重新发送邀请。</span>
          </div>
        );
      case 'error':
        return (
          <div className={styles.errorBanner}>
            <strong>接受邀请失败</strong>
            <span>{inviteState.message || '邀请链接无效或已过期。'}</span>
          </div>
        );
      default:
        return null;
    }
  };

  const isErrorState =
    inviteState.status === 'error' ||
    inviteState.status === 'missing_token' ||
    inviteState.status === 'login_required';

  return (
    <AuthShell
      title="工作空间邀请"
      description="我们正在处理您的工作空间邀请。"
      eyebrow="成员邀请"
      statusSlot={renderStatus()}
      asideHeadline={'加入协作空间'}
      asideBody="接受邀请后，您可以和团队一起管理 PromptChain 工作流、运行记录与内容产物。"
      footerPrompt={isErrorState ? '需要帮助？' : ''}
      footerLink={isErrorState ? '返回登录' : ''}
      footerHref={isErrorState ? loginHref : undefined}
    >
      {null}
    </AuthShell>
  );
}

export default function InvitePage() {
  return (
    <Suspense
      fallback={
        <AuthShell
          title="工作空间邀请"
          description="正在准备邀请页面。"
          eyebrow="成员邀请"
          asideHeadline="加入协作空间"
          asideBody="接受邀请后，您可以和团队一起管理 PromptChain 工作流、运行记录与内容产物。"
          statusSlot={<div className={styles.helperText}>正在加载邀请状态...</div>}
        >
          {null}
        </AuthShell>
      }
    >
      <InviteComponent />
    </Suspense>
  );
}
