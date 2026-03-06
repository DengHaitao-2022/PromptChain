import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PromptChain - AI驱动的内容生成平台",
  description: "基于 Prompt Chain 的自动化内容生成系统，支持意图解析、提纲生成、事实核查、内容创作的全流程 AI 协作",
  keywords: ["AI", "内容生成", "LangGraph", "Prompt Chain", "自动化写作"],
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap"
          rel="stylesheet"
        />
      </head>
      <body suppressHydrationWarning>
        {children}
      </body>
    </html>
  );
}
