type FinancialDisclaimerProps = {
  compact?: boolean;
};

export function FinancialDisclaimer({ compact = false }: FinancialDisclaimerProps) {
  return (
    <aside
      className={`financial-disclaimer${compact ? " financial-disclaimer--compact" : ""}`}
      aria-label="金融风险免责声明"
    >
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M12 3 3.8 6.5v5.3c0 4.8 3.5 8.2 8.2 9.2 4.7-1 8.2-4.4 8.2-9.2V6.5L12 3Z" />
        <path d="M12 8v5M12 16.5v.1" />
      </svg>
      <div>
        <strong>金融风险免责声明</strong>
        <p>
          本平台内容由 AI 基于公开信息生成，仅供学习、研究与信息参考，不构成任何投资建议、证券推荐或收益承诺。
          信息可能存在延迟、遗漏或错误，请独立核验并自主决策。投资有风险，入市需谨慎。
        </p>
      </div>
    </aside>
  );
}
