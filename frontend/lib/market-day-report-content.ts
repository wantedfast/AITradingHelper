export type LabeledReportText = {
  label: string;
  value: string;
};

type EvidenceValue = string | { content?: string; type?: string };

type WatchPointValue = {
  object?: string;
  condition?: string;
  positiveSignal?: string;
  negativeSignal?: string;
  meaning?: string;
};

export function namedReportText(name?: string, value?: string): LabeledReportText[] {
  return [{ label: `${name?.trim() || "未命名"}：`, value: value?.trim() || "证据不足" }];
}

export function evidenceReportText(item: EvidenceValue): LabeledReportText[] {
  if (typeof item === "string") return item.trim() ? [{ label: "", value: item.trim() }] : [];
  const type = item?.type?.trim() || "";
  const content = item?.content?.trim() || "";
  if (content) return [{ label: type ? `${type}：` : "", value: content }];
  return type ? [{ label: "", value: type }] : [];
}

export function watchPointReportText(item: unknown): LabeledReportText[] {
  if (typeof item === "string") return item.trim() ? [{ label: "", value: item.trim() }] : [];
  if (!item || typeof item !== "object") return [];
  const point = item as WatchPointValue;
  return [
    { label: "", value: point.object?.trim() || "" },
    { label: "条件：", value: point.condition?.trim() || "" },
    { label: "正向：", value: point.positiveSignal?.trim() || "" },
    { label: "负向：", value: point.negativeSignal?.trim() || "" },
    { label: "含义：", value: point.meaning?.trim() || "" },
  ].filter((part) => part.value);
}
