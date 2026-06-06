import { Suspense } from "react";
import WatchClient from "./watch-client";


export default function WatchPage() {
  return (
    <Suspense fallback={null}>
      <WatchClient mode="entry" />
    </Suspense>
  );
}
