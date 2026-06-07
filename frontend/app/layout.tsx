import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "盈航",
  description: "研究、预案、盯盘、复盘与重要消息提醒，帮助你持续做出更有依据的投资决策。",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
