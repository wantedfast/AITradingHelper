import type { ReactNode } from "react";

type MobileActionDockProps = {
  children: ReactNode;
  hint?: ReactNode;
  className?: string;
};

/**
 * Keeps the current task's only primary action reachable on a phone while
 * remaining an ordinary inline action row on tablet and desktop.
 */
export function MobileActionDock({ children, hint, className = "" }: MobileActionDockProps) {
  return (
    <div className={`mobile-action-dock ${className}`.trim()}>
      <div className="mobile-action-dock__action">{children}</div>
      {hint ? <div className="mobile-action-dock__hint">{hint}</div> : null}
    </div>
  );
}
