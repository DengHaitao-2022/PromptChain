'use client';

import React, { useEffect, useState, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import NextLink from 'next/link';
import { AuthShell } from '../../components/AuthShell/AuthShell';
import { verifyEmail } from '../../lib/auth';
import styles from '../login/login.module.css';

type VerificationStatus = 'loading' | 'success' | 'error' | 'missing_token';

// Module-level caches to survive React Strict Mode remounts
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
    // Check session storage first for refresh persistence
    if (typeof window !== 'undefined' && sessionStorage.getItem(getSessionStorageKey(token)) === 'success') {
      return 'success';
    }
    // Check module-level cache for remount persistence
    return terminalStateCache[token] || 'loading';
  });

  useEffect(() => {
    let isActive = true;

    const performVerification = async () => {
      if (!token) {
        if (isActive) setStatus('missing_token');
        return;
      }

      // Pre-flight checks. If any are true, we have a terminal state.
      if (typeof window !== 'undefined' && sessionStorage.getItem(getSessionStorageKey(token)) === 'success') {
        if (isActive) setStatus('success');
        return;
      }
      if (terminalStateCache[token]) {
        if (isActive) setStatus(terminalStateCache[token]);
        return;
      }

      // Check for an in-flight promise from another render/component
      const inFlightPromise = promiseCache[token];
      if (inFlightPromise) {
        if (isActive) setStatus('loading');
        try {
          await inFlightPromise;
          // After awaiting, the cache *should* be populated by the original caller.
          if (isActive) setStatus(terminalStateCache[token] || 'success');
        } catch {
          // The promise rejected. The cache should be populated.
          if (isActive) setStatus(terminalStateCache[token] || 'error');
        }
        return;
      }

      // This is the first component instance for this token.
      // It's responsible for making the API call and populating the caches.
      if (isActive) setStatus('loading');

      const verificationPromise = verifyEmail(token);
      promiseCache[token] = verificationPromise;

      try {
        await verificationPromise;
        // On success, we are the authority. Set the caches.
        terminalStateCache[token] = 'success';
        if (typeof window !== 'undefined') {
          sessionStorage.setItem(getSessionStorageKey(token), 'success');
        }
        if (isActive) setStatus('success');
      } catch {
        // On error, only set cache if a success state isn't already there from a race condition.
        if (terminalStateCache[token] !== 'success') {
          terminalStateCache[token] = 'error';
        }
        if (isActive) {
          // Read from cache to respect the authoritative state.
          setStatus(terminalStateCache[token]!);
        }
      } finally {
        // The promise is settled, remove it from the in-flight cache.
        delete promiseCache[token];
      }
    };

    performVerification();

    return () => {
      isActive = false;
    };
  }, [token]);

  const aside = {
    asideHeadline: '验证您的身份',
    asideBody: '完成最后一步以保护您的账户并解锁平台的全部功能。',
  };

  const renderStatus = () => {
    switch (status) {
      case 'loading':
        return <div className={styles.helperText}>正在验证您的电子邮件...</div>;
      case 'error':
        return <div className={styles.errorBanner}>令牌无效或已过期。请尝试重新登录或联系支持。</div>;
      case 'missing_token':
        return <div className={styles.errorBanner}>未提供验证令牌。请检查您的电子邮件链接。</div>;
      case 'success':
        return (
          <div className={styles.successBox}>
            <h2>✅ 验证成功</h2>
            <p>您的电子邮件已成功验证。</p>
            <NextLink href="/login" className={styles.forgotLink}>
              点击这里返回登录
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
      description="正在完成您的账户设置"
      statusSlot={renderStatus()}
      asideHeadline={aside.asideHeadline}
      asideBody={aside.asideBody}
      footerPrompt={isErrorState ? '遇到问题？' : ''}
      footerLink={isErrorState ? '返回登录' : ''}
      footerHref={isErrorState ? '/login' : undefined}
    >
      <div style={{ minHeight: '1px' }} />
    </AuthShell>
  );
}

export default function VerifyEmailPage() {
    return (
        <Suspense fallback={<div>正在加载...</div>}>
            <VerifyEmailComponent />
        </Suspense>
    )
}
