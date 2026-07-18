export type CityOption = {
  id: string;
  label: string;
  name: string;
  country: string;
  countryCode: string;
  admin1: string;
  latitude: number;
  longitude: number;
  timezone: string;
};

export async function searchCities(query: string, signal?: AbortSignal): Promise<CityOption[]> {
  const normalizedQuery = query.trim();
  if (normalizedQuery.length < 2) {
    return [];
  }

  const url = new URL("https://geocoding-api.open-meteo.com/v1/search");
  url.searchParams.set("name", normalizedQuery);
  url.searchParams.set("count", "8");
  url.searchParams.set("language", "ru");
  url.searchParams.set("format", "json");

  try {
    const response = await fetch(url, { signal });
    if (!response.ok) throw new Error(`Open-Meteo returned ${response.status}`);
    const payload = (await response.json()) as {
      results?: Array<{
        id: number;
        name?: string;
        country?: string;
        country_code?: string;
        admin1?: string;
        latitude?: number;
        longitude?: number;
        timezone?: string;
      }>;
    };

    return (payload.results ?? []).map((result) => {
      const name = result.name?.trim() || "Без названия";
      const country = result.country?.trim() || "";
      const admin1 = result.admin1?.trim() || "";
      return {
        id: String(result.id),
        label: [name, admin1, country].filter(Boolean).join(", "),
        name,
        country,
        countryCode: result.country_code?.trim() || "",
        admin1,
        latitude: result.latitude ?? 0,
        longitude: result.longitude ?? 0,
        timezone: result.timezone?.trim() || "UTC",
      };
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new Error("Не удалось загрузить варианты городов");
  }
}
