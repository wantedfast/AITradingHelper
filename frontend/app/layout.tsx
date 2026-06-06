import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Trading for Beginners",
  description: "AI trade review and watchlist assistant for new traders."
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
