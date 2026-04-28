import type { CSSProperties } from "react";
import type { Metadata } from "next";
import { ThemeProvider } from "@/contexts/ThemeContext";
import { buildThemeInitScript } from "@/lib/theme";
import "./globals.css";

// 避免 next/font/google 在本地网络不可达时阻塞页面编译，直接提供离线安全的字体变量回退。
const fontVariableStyle = {
  "--font-inter": "Inter, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
  "--font-jetbrains-mono": "'JetBrains Mono', 'SFMono-Regular', 'SFMono', 'Fira Code', monospace",
  "--font-space-grotesk": "'Space Grotesk', Inter, system-ui, sans-serif",
} as CSSProperties;

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
    <html
      lang="zh-CN"
      suppressHydrationWarning
      data-theme="dark"
      data-theme-preference="system"
    >
      <body
        suppressHydrationWarning
        style={fontVariableStyle}
      >
        <script
          id="promptchain-theme-init"
          dangerouslySetInnerHTML={{ __html: buildThemeInitScript() }}
        />
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  );
}
