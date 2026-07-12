import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function AiResearchReportRedirectPage({
  params,
}: {
  params: { id: string };
}) {
  const runId = decodeURIComponent(params.id);
  redirect(`/ai-research?report=${encodeURIComponent(runId)}`);
}
