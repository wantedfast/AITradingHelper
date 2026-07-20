import CreditsPage, { type CreditCatalogPayload } from "./credits-client";

const internalApiBase = process.env.INTERNAL_API_BASE || "http://127.0.0.1:8600";

async function loadInitialCatalog(): Promise<CreditCatalogPayload | null> {
  try {
    const response = await fetch(`${internalApiBase}/api/public/credits/catalog`, {
      cache: "no-store",
    });
    if (!response.ok) return null;
    return (await response.json()) as CreditCatalogPayload;
  } catch {
    return null;
  }
}

export default async function Page() {
  const initialCatalog = await loadInitialCatalog();
  return <CreditsPage initialCatalog={initialCatalog} />;
}
