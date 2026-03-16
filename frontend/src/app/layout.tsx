import type { Metadata } from "next";
import { Inter, JetBrains_Mono, Space_Grotesk } from "next/font/google";
import { ThemeProvider } from "@/contexts/ThemeContext";
import { buildThemeInitScript } from "@/lib/theme";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-inter",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-jetbrains-mono",
});

const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-space-grotesk",
});

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
      <head>
        <script
          id="promptchain-theme-init"
          dangerouslySetInnerHTML={{ __html: buildThemeInitScript() }}
        />
      </head>
      <body
        suppressHydrationWarning
        className={`${inter.variable} ${jetbrainsMono.variable} ${spaceGrotesk.variable}`}
      >
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  );
}
