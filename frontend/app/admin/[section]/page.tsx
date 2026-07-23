import { notFound } from "next/navigation";
import { AdminConsole } from "@/components/admin/admin-console";
import { isAdminSection } from "@/components/admin/admin-navigation";

export default function AdminSectionPage({ params }: { params: { section: string } }) {
  if (!isAdminSection(params.section)) notFound();
  return <AdminConsole section={params.section} />;
}
