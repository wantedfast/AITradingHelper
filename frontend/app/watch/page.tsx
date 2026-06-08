import { Suspense } from "react";
import WatchClient from "./watch-client";


export default function WatchPage() {
  return (
    <Suspense
      fallback={
        <main className="review-workbench-page watch-terminal-page">
          <div className="watch-page-fallback">
            <span>AI WATCH AGENT</span>
            <strong>AI 盯盘加载中</strong>
          </div>
        </main>
      }
    >
      <WatchClient mode="entry" />
    </Suspense>
  );
}
