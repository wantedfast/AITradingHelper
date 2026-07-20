import BillingPage, { type CatalogPayload } from "./billing-client";

const internalApiBase = process.env.INTERNAL_API_BASE || "http://127.0.0.1:8600";

async function loadInitialCatalog(): Promise<CatalogPayload | null> {
  try {
    const response = await fetch(`${internalApiBase}/api/public/membership/plans`, {
      cache: "no-store",
    });
    if (!response.ok) return null;
    return (await response.json()) as CatalogPayload;
  } catch {
    return null;
  }
}

export default async function Page() {
  const initialCatalog = await loadInitialCatalog();
  return <BillingPage initialCatalog={initialCatalog} />;
}
