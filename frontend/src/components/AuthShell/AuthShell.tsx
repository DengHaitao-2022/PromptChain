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
import { ThemeSwitcher } from '@/components/ThemeSwitcher/ThemeSwitcher';
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
    title: '审批与权限控制',
    description: '关键操作需确认，敏感节点支持审计。',
  },
  {
    icon: GitBranch,
    title: '版本记录与变更追溯',
    description: '提示词、输出结果与历史版本统一留存。',
  },
  {
    icon: Radar,
    title: '节点状态可视化',
    description: '从入口到执行链路，实时掌握流程状态。',
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
      <div className={styles.backgroundCanvas} aria-hidden="true">
        <svg className={styles.backgroundSvg} viewBox="0 0 1440 900" preserveAspectRatio="xMidYMid slice">
          <defs>
            <linearGradient id="auth-fluid-a" x1="102" y1="792" x2="1028" y2="126" gradientUnits="userSpaceOnUse">
              <stop offset="0" stopColor="var(--auth-fluid-a-deep)" />
              <stop offset="0.46" stopColor="var(--auth-fluid-a-mid)" />
              <stop offset="1" stopColor="var(--auth-fluid-a-light)" />
            </linearGradient>
            <linearGradient id="auth-fluid-b" x1="598" y1="18" x2="1402" y2="618" gradientUnits="userSpaceOnUse">
              <stop offset="0" stopColor="var(--auth-fluid-b-light)" />
              <stop offset="0.44" stopColor="var(--auth-fluid-b-mid)" />
              <stop offset="1" stopColor="var(--auth-fluid-b-deep)" />
            </linearGradient>
            <radialGradient id="auth-fluid-c" cx="0" cy="0" r="1" gradientUnits="userSpaceOnUse" gradientTransform="translate(1088 264) rotate(137.58) scale(466.844 342.592)">
              <stop offset="0" stopColor="var(--auth-fluid-c-core)" />
              <stop offset="0.56" stopColor="var(--auth-fluid-c-mid)" />
              <stop offset="1" stopColor="var(--auth-fluid-c-fade)" />
            </radialGradient>
            <linearGradient id="auth-rim-primary" x1="346" y1="386" x2="954" y2="286" gradientUnits="userSpaceOnUse">
              <stop offset="0" stopColor="transparent" />
              <stop offset="0.5" stopColor="var(--auth-fluid-rim)" />
              <stop offset="1" stopColor="transparent" />
            </linearGradient>
            <linearGradient id="auth-rim-secondary" x1="846" y1="258" x2="1308" y2="404" gradientUnits="userSpaceOnUse">
              <stop offset="0" stopColor="transparent" />
              <stop offset="0.48" stopColor="var(--auth-fluid-rim-alt)" />
              <stop offset="1" stopColor="transparent" />
            </linearGradient>
            <linearGradient id="auth-shadow-plane" x1="188" y1="734" x2="1268" y2="534" gradientUnits="userSpaceOnUse">
              <stop offset="0" stopColor="var(--auth-fluid-shadow)" stopOpacity="0.66" />
              <stop offset="0.54" stopColor="var(--auth-fluid-shadow)" stopOpacity="0.18" />
              <stop offset="1" stopColor="transparent" />
            </linearGradient>
            <filter id="auth-depth-shadow" x="-12%" y="-12%" width="124%" height="124%">
              <feDropShadow dx="0" dy="34" stdDeviation="30" floodColor="var(--auth-fluid-shadow)" floodOpacity="0.34" />
            </filter>
            <filter id="auth-soft-shadow" x="-10%" y="-10%" width="120%" height="120%">
              <feDropShadow dx="0" dy="18" stdDeviation="20" floodColor="var(--auth-fluid-shadow)" floodOpacity="0.22" />
            </filter>
          </defs>

          <path
            d="M-172 782C18 682 198 614 350 562C528 500 650 462 786 448C944 430 1118 456 1460 564V934H-172V782Z"
            fill="url(#auth-shadow-plane)"
            filter="url(#auth-depth-shadow)"
            opacity="0.72"
          />
          <path
            d="M-172 756C-16 606 136 520 298 472C480 416 646 460 820 394C988 332 1168 186 1460 72V624C1298 700 1148 740 992 752C786 768 604 710 432 700C232 688 56 722 -172 840V756Z"
            fill="url(#auth-fluid-a)"
            filter="url(#auth-soft-shadow)"
          />
          <path
            d="M454 -102C616 -52 738 24 846 126C944 220 1048 282 1176 326C1284 362 1374 386 1460 452V-102H454Z"
            fill="url(#auth-fluid-b)"
            filter="url(#auth-soft-shadow)"
            opacity="0.94"
          />
          <path
            d="M738 108C872 156 980 220 1076 308C1142 368 1234 436 1460 552V120C1368 134 1286 158 1192 212C1072 282 958 290 874 256C820 232 780 184 738 108Z"
            fill="url(#auth-fluid-c)"
            opacity="0.92"
          />
          <path
            d="M332 406C470 346 618 336 748 320C862 304 960 256 1084 190"
            fill="none"
            stroke="url(#auth-rim-primary)"
            strokeWidth="4"
            strokeLinecap="round"
          />
          <path
            d="M848 254C976 278 1072 324 1180 356C1262 382 1342 400 1460 438"
            fill="none"
            stroke="url(#auth-rim-secondary)"
            strokeWidth="3"
            strokeLinecap="round"
          />
        </svg>
      </div>

      <div className={styles.backgroundMotion} aria-hidden="true">
        <span className={styles.backgroundOrbPrimary} />
        <span className={styles.backgroundOrbSecondary} />
        <span className={styles.backgroundBeam} />
      </div>

      <header className={styles.topBar}>
        <div className={styles.topBarInner}>
          <NextLink href="/" className={styles.logo}>
            <span className={styles.logoIcon}>
              <Waypoints size={18} aria-hidden="true" />
            </span>
            <span className={styles.logoText}>PromptChain</span>
          </NextLink>

          <ThemeSwitcher className={styles.topBarTheme} showStatus={false} compact />
        </div>
      </header>

      <div className={styles.shell}>
        <div className={styles.contentGrid}>
          <aside className={styles.aside}>
            <div className={styles.asidePanel}>
              <header className={styles.asideHeader}>
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
                <p>进入可追踪、可审计、可重跑的 AI 内容工作流。</p>
              </footer>
            </div>
          </aside>

          <main className={styles.main}>
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
      </div>
    </div>
  );
};
