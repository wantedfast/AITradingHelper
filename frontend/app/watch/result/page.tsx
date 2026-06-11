import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function WatchResultPage({
  searchParams,
}: {
  searchParams?: { planId?: string | string[] };
}) {
  const rawPlanId = searchParams?.planId;
  const planId = Array.isArray(rawPlanId) ? rawPlanId[0] : rawPlanId;
  redirect(planId ? `/watch?planId=${encodeURIComponent(planId)}` : "/watch");
}
