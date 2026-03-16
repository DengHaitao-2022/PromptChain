'use client';

import React from 'react';
import NextLink from 'next/link';
import type { LucideIcon } from 'lucide-react';
import {
  GitBranch,
  Radar,
  ShieldCheck,
  Waypoints,
} from 'lucide-react';
import styles from './AuthShell.module.css';

interface AuthShellProps {
  title: string;
  description?: string;
  eyebrow?: string;
  asideHeadline: string;
  asideBody: string;
  statusSlot?: React.ReactNode;
  footerPrompt?: string;
  footerLink?: string;
  footerHref?: string;
  children: React.ReactNode;
}

interface TrustItem {
  icon: LucideIcon;
  title: string;
  description: string;
}

const trustItems: TrustItem[] = [
  {
    icon: ShieldCheck,
    title: '审批式安全入口',
    description: '账号、权限和关键操作保持可确认与可审计。',
  },
  {
    icon: GitBranch,
    title: '版本化工作流资产',
    description: '生成记录、提纲与产物都保留历史，不做黑盒覆盖。',
  },
  {
    icon: Radar,
    title: '节点级运行感知',
    description: '从入口登录到运行详情，都围绕可追踪的工程链路展开。',
  },
];

export const AuthShell: React.FC<AuthShellProps> = ({
  title,
  description,
  eyebrow,
  asideHeadline,
  asideBody,
  statusSlot,
  footerPrompt,
  footerLink,
  footerHref,
  children,
}) => {
  return (
    <div className={styles.container}>
      <div className={styles.backgroundMotion} aria-hidden="true">
        <span className={styles.backgroundOrbPrimary} />
        <span className={styles.backgroundOrbSecondary} />
        <span className={styles.backgroundBeam} />
      </div>

      <aside className={styles.aside}>
        <div className={styles.asidePanel}>
          <header className={styles.asideHeader}>
            <NextLink href="/" className={styles.logo}>
              <span className={styles.logoIcon}>
                <Waypoints size={18} aria-hidden="true" />
              </span>
              <span className={styles.logoText}>PromptChain</span>
            </NextLink>

            {eyebrow ? <span className={styles.eyebrow}>{eyebrow}</span> : null}
          </header>

          <div className={styles.asideContent}>
            <h1 className={styles.headline}>{asideHeadline}</h1>
            <p className={styles.body}>{asideBody}</p>

            <div className={styles.trustGroup}>
              {trustItems.map((item) => {
                const Icon = item.icon;

                return (
                  <div key={item.title} className={styles.chip}>
                    <span className={styles.chipIcon} aria-hidden="true">
                      <Icon size={18} />
                    </span>
                    <span className={styles.chipCopy}>
                      <strong>{item.title}</strong>
                      <span>{item.description}</span>
                    </span>
                  </div>
                );
              })}
            </div>
          </div>

          <footer className={styles.asideFooter}>
            <span className={styles.asideFooterLabel}>认证入口</span>
            <p>进入可追踪、可审批、可重跑的 AI 内容工作流控制台。</p>
          </footer>
        </div>
      </aside>

      <main className={styles.main}>
        <div className={styles.mobileBrand}>
          <NextLink href="/" className={styles.logo}>
            <span className={styles.logoIcon}>
              <Waypoints size={18} aria-hidden="true" />
            </span>
            <span className={styles.logoText}>PromptChain</span>
          </NextLink>
          {eyebrow ? <span className={styles.mobileEyebrow}>{eyebrow}</span> : null}
        </div>

        <div className={styles.cardContainer}>
          <div className={styles.cardShell}>
            <span className={styles.cardBorder} aria-hidden="true" />

            <div className={styles.card}>
              <header className={styles.header}>
                <span className={styles.cardBadge}>认证入口</span>
                <h2 className={styles.title}>{title}</h2>
                {description ? <p className={styles.description}>{description}</p> : null}
              </header>

              {statusSlot ? <div className={styles.statusArea}>{statusSlot}</div> : null}

              <div className={styles.formArea}>{children}</div>

              {footerPrompt || footerLink ? (
                <footer className={styles.formFooter}>
                  {footerPrompt ? <span className={styles.prompt}>{footerPrompt}</span> : null}
                  {footerLink && footerHref ? (
                    <NextLink href={footerHref} className={styles.link}>
                      {footerLink}
                    </NextLink>
                  ) : null}
                </footer>
              ) : null}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
};
