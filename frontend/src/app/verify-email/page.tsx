'use client';

import React, { useEffect, useState, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import NextLink from 'next/link';
import { AuthShell } from '../../components/AuthShell/AuthShell';
import { verifyEmail } from '../../lib/auth';
import styles from '../login/login.module.css';

type VerificationStatus = 'loading' | 'success' | 'error' | 'missing_token';

// 使用模块级缓存，避免 Strict Mode 下重复验证同一令牌。
const promiseCache: { [token: string]: Promise<{ message: string }> | undefined } = {};
const terminalStateCache: { [token: string]: VerificationStatus } = {};

function getSessionStorageKey(token: string) {
  return `verification_status_${token}`;
}

function VerifyEmailComponent() {
  const searchParams = useSearchParams();
  const token = searchParams.get('token');
  const [status, setStatus] = useState<VerificationStatus>(() => {
    if (!token) return 'missing_token';
    // 刷新后优先读取会话缓存，减少重复请求。
    if (typeof window !== 'undefined' && sessionStorage.getItem(getSessionStorageKey(token)) === 'success') {
      return 'success';
    }
    // Strict Mode 重挂载时，复用内存中的终态缓存。
    return terminalStateCache[token] || 'loading';
  });

  useEffect(() => {
    let isActive = true;

    const performVerification = async () => {
      if (!token) {
        if (isActive) setStatus('missing_token');
        return;
      }

      // 命中终态缓存后直接返回，避免重复请求。
      if (typeof window !== 'undefined' && sessionStorage.getItem(getSessionStorageKey(token)) === 'success') {
        if (isActive) setStatus('success');
        return;
      }
      if (terminalStateCache[token]) {
        if (isActive) setStatus(terminalStateCache[token]);
        return;
      }

      // 若已有同令牌请求在飞行中，则复用该 Promise。
      const inFlightPromise = promiseCache[token];
      if (inFlightPromise) {
        if (isActive) setStatus('loading');
        try {
          await inFlightPromise;
          // 原始请求完成后，统一从缓存读取最终状态。
          if (isActive) setStatus(terminalStateCache[token] || 'success');
        } catch {
          if (isActive) setStatus(terminalStateCache[token] || 'error');
        }
        return;
      }

      // 第一个实例负责发起请求并写入缓存。
      if (isActive) setStatus('loading');

      const verificationPromise = verifyEmail(token);
      promiseCache[token] = verificationPromise;

      try {
        await verificationPromise;
        terminalStateCache[token] = 'success';
        if (typeof window !== 'undefined') {
          sessionStorage.setItem(getSessionStorageKey(token), 'success');
        }
        if (isActive) setStatus('success');
      } catch {
        // 若没有更早完成的成功态，则把当前结果记为失败。
        if (terminalStateCache[token] !== 'success') {
          terminalStateCache[token] = 'error';
        }
        if (isActive) {
          setStatus(terminalStateCache[token]!);
        }
      } finally {
        // 请求结束后清理飞行中缓存。
        delete promiseCache[token];
      }
    };

    performVerification();

    return () => {
      isActive = false;
    };
  }, [token]);

  const aside = {
    asideHeadline: '完成账户验证',
    asideBody: '验证成功后，您就可以进入 PromptChain 的工作流控制台。',
  };

  const renderStatus = () => {
    switch (status) {
      case 'loading':
        return <div className={styles.helperText}>正在验证您的电子邮件...</div>;
      case 'error':
        return (
          <div className={styles.errorBanner}>
            <strong>验证失败</strong>
            <span>令牌无效或已过期。请尝试重新登录或联系支持。</span>
          </div>
        );
      case 'missing_token':
        return (
          <div className={styles.errorBanner}>
            <strong>缺少验证令牌</strong>
            <span>请检查邮件链接是否完整，或重新发起验证流程。</span>
          </div>
        );
      case 'success':
        return (
          <div className={styles.successBox}>
            <h2>验证成功</h2>
            <p>您的电子邮件已成功验证。</p>
            <NextLink href="/login" className={styles.forgotLink}>
              返回登录
            </NextLink>
          </div>
        );
      default:
        return null;
    }
  };

  const isErrorState = status === 'error' || status === 'missing_token';

  return (
    <AuthShell
      title="电子邮件验证"
      description="我们正在确认您的邮箱验证状态。"
      eyebrow="邮箱验证"
      statusSlot={renderStatus()}
      asideHeadline={aside.asideHeadline}
      asideBody={aside.asideBody}
      footerPrompt={isErrorState ? '遇到问题？' : ''}
      footerLink={isErrorState ? '返回登录' : ''}
      footerHref={isErrorState ? '/login' : undefined}
    >
      {null}
    </AuthShell>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense
      fallback={
        <AuthShell
          title="电子邮件验证"
          description="正在准备验证页面。"
          eyebrow="邮箱验证"
          asideHeadline="完成账户验证"
          asideBody="验证成功后，您就可以进入 PromptChain 的工作流控制台。"
          statusSlot={<div className={styles.helperText}>正在加载验证状态...</div>}
        >
          {null}
        </AuthShell>
      }
    >
      <VerifyEmailComponent />
    </Suspense>
  );
}
