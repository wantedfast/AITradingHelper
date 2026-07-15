import type { Metadata } from "next";
import "./globals.css";
import { EmailBindingReminder } from "@/components/email-binding-reminder";

export const metadata: Metadata = {
  title: "盈航",
  description: "AI 帮助你理解投资逻辑、建立交易计划、克服情绪波动，并持续优化决策。"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>{children}<EmailBindingReminder /></body>
    </html>
  );
}
