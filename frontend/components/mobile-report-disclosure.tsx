"use client";

import { ChevronDown } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";

type MobileReportDisclosureProps = {
  title: string;
  summary?: string;
  children: ReactNode;
  className?: string;
  mobileOpen?: boolean;
};

const MOBILE_QUERY = "(max-width: 767px)";

export function MobileReportDisclosure({
  title,
  summary,
  children,
  className = "",
  mobileOpen = false,
}: MobileReportDisclosureProps) {
  const [open, setOpen] = useState(true);
  const initialized = useRef(false);

  useEffect(() => {
    const media = window.matchMedia(MOBILE_QUERY);
    const sync = () => setOpen(media.matches ? mobileOpen : true);
    sync();
    initialized.current = true;
    media.addEventListener("change", sync);
    return () => media.removeEventListener("change", sync);
  }, [mobileOpen]);

  return (
    <details
      className={`mobile-report-disclosure ${className}`.trim()}
      open={open}
      onToggle={(event) => {
        if (initialized.current) setOpen(event.currentTarget.open);
      }}
    >
      <summary>
        <span>
          <b>{title}</b>
          {summary ? <small>{summary}</small> : null}
        </span>
        <ChevronDown aria-hidden="true" />
      </summary>
      <div className="mobile-report-disclosure__content">{children}</div>
    </details>
  );
}
