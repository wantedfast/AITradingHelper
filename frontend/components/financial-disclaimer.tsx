"use client";

import Link from "next/link";
import { ChevronDown, MessageSquare, ShieldAlert } from "lucide-react";
import { useEffect, useState } from "react";

type FinancialDisclaimerProps = {
  compact?: boolean;
};

export function FinancialDisclaimer({ compact = false }: FinancialDisclaimerProps) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const media = window.matchMedia("(max-width: 767px)");
    const sync = () => setOpen(!media.matches);
    sync();
    media.addEventListener("change", sync);
    return () => media.removeEventListener("change", sync);
  }, []);

  return (
    <details
      className={`financial-disclaimer${compact ? " financial-disclaimer--compact" : ""}`}
      aria-label="金融风险免责声明"
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary className="financial-disclaimer__summary">
        <ShieldAlert aria-hidden="true" />
        <span>
          <strong>金融风险免责声明</strong>
          <small>内容仅供学习与研究，不构成投资建议</small>
        </span>
        <ChevronDown className="financial-disclaimer__chevron" aria-hidden="true" />
      </summary>
      <div className="financial-disclaimer__body">
        <p>
          本平台内容由 AI 基于公开信息生成，仅供学习、研究与信息参考，不构成任何投资建议、证券推荐或收益承诺。
          信息可能存在延迟、遗漏或错误，请独立核验并自主决策。投资有风险，入市需谨慎。
        </p>
        <div className="financial-disclaimer__feedback">
          <span>
            <MessageSquare aria-hidden="true" />
            发现问题或有改进建议？有效反馈被采纳后，可获赠 10 次使用次数。
          </span>
          <Link href="/#feedback">提交反馈</Link>
        </div>
      </div>
    </details>
  );
}
