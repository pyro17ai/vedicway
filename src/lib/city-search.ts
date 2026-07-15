export type CityOption = {
  id: number;
  label: string;
  name: string;
  country: string;
  admin1: string;
  latitude: number;
  longitude: number;
  timezone: string;
};

type GeocodingResult = {
  id: number;
  name?: string;
  country?: string;
  admin1?: string;
  latitude?: number;
  longitude?: number;
  timezone?: string;
};

type GeocodingResponse = {
  results?: GeocodingResult[];
};

const GEOCODING_ENDPOINT = "https://geocoding-api.open-meteo.com/v1/search";

export async function searchCities(
  query: string,
  signal?: AbortSignal,
): Promise<CityOption[]> {
  const normalizedQuery = query.trim();

  if (normalizedQuery.length < 2) {
    return [];
  }

  const url = new URL(GEOCODING_ENDPOINT);
  url.searchParams.set("name", normalizedQuery);
  url.searchParams.set("count", "6");
  url.searchParams.set("language", "ru");
  url.searchParams.set("format", "json");

  const response = await fetch(url, { signal });

  if (!response.ok) {
    throw new Error("Не удалось загрузить варианты городов");
  }

  const payload = (await response.json()) as GeocodingResponse;

  return (payload.results ?? []).map((result) => {
    const name = result.name?.trim() || "Без названия";
    const admin1 = result.admin1?.trim() || "";
    const country = result.country?.trim() || "";

    return {
      id: result.id,
      label: [name, admin1, country].filter(Boolean).join(", "),
      name,
      country,
      admin1,
      latitude: result.latitude ?? 0,
      longitude: result.longitude ?? 0,
      timezone: result.timezone ?? "UTC",
    };
  });
}
