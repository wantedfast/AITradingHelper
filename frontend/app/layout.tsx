import type { Metadata } from "next";
import "./globals.css";
import "./responsive.css";
import { EmailBindingReminder } from "@/components/email-binding-reminder";
import { UpdateNoticeGate } from "@/components/update-notice-gate";

export const metadata: Metadata = {
  title: "盈航",
  description: "AI 帮助你理解投资逻辑、建立交易计划，并持续优化交易决策。",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>
        {children}
        <UpdateNoticeGate />
        <EmailBindingReminder />
      </body>
    </html>
  );
}
