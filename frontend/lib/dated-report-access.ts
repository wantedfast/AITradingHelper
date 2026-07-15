export type BillingStatus = "no_data" | "pending_view" | "charged" | "free_history";

export function canReadDatedReport(status: BillingStatus) {
  return status === "charged" || status === "free_history";
}

export function shouldShowDatedReportPayment(status: BillingStatus, hasReport: boolean) {
  return hasReport && status === "pending_view";
}
