'use client';

import React, { useEffect, useState, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import NextLink from 'next/link';
import { AuthShell } from '../../components/AuthShell/AuthShell';
import { verifyEmail } from '../../lib/auth';
import styles from '../login/login.module.css';

// Define a more comprehensive status type
type VerificationStatus = 'loading' | 'success' | 'error' | 'missing_token';

function VerifyEmailComponent() {
  const searchParams = useSearchParams();
  const token = searchParams.get('token');

  // Initialize state based on token presence, avoiding sync setState in useEffect
  const [status, setStatus] = useState<VerificationStatus>(
    token ? 'loading' : 'missing_token'
  );

  useEffect(() => {
    // The effect's responsibility is now only to perform the async operation
    if (token) {
      verifyEmail(token)
        .then(() => {
          setStatus('success');
        })
        .catch(() => {
          // API call failed, indicating an invalid or expired token
          setStatus('error');
        });
    }
    // No else block needed; the 'missing_token' case is handled by the initial state.
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
      footerHref={isErrorState ? '/login' : ''}
    >
      {/* AuthShell requires children. Provide a minimal placeholder. */}
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
