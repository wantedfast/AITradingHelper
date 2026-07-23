import { redirect } from "next/navigation";
import { adminSectionPath, isAdminSection } from "@/components/admin/admin-navigation";

function firstValue(value: string | string[] | undefined) {
  return Array.isArray(value) ? value[0] || "" : value || "";
}

export default function AdminRootPage({
  searchParams,
}: {
  searchParams?: Record<string, string | string[] | undefined>;
}) {
  const section = firstValue(searchParams?.section);
  const targetSection = isAdminSection(section) ? section : "overview";
  const params = new URLSearchParams();
  Object.entries(searchParams || {}).forEach(([key, rawValue]) => {
    if (key === "section") return;
    const value = firstValue(rawValue);
    if (value) params.set(key, value);
  });
  const query = params.toString();
  redirect(query ? `${adminSectionPath(targetSection)}?${query}` : adminSectionPath(targetSection));
}
