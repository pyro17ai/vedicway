import { afterEach, describe, expect, it, vi } from "vitest";

import { searchCities } from "./city-search";

describe("searchCities", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("не обращается к Open-Meteo для строки короче двух символов", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    await expect(searchCities(" М ")).resolves.toEqual([]);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("возвращает мировой результат Open-Meteo вместе с координатами и timezone", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(new Response(JSON.stringify({
      results: [{
        id: 2950159,
        name: "Берлин",
        country: "Германия",
        country_code: "DE",
        admin1: "Берлин",
        latitude: 52.52437,
        longitude: 13.41053,
        timezone: "Europe/Berlin",
      }],
    }), { status: 200 }));

    await expect(searchCities("Berlin")).resolves.toEqual([{
      id: "2950159",
      label: "Берлин, Берлин, Германия",
      name: "Берлин",
      country: "Германия",
      countryCode: "DE",
      admin1: "Берлин",
      latitude: 52.52437,
      longitude: 13.41053,
      timezone: "Europe/Berlin",
    }]);
  });

  it("возвращает понятную ошибку при недоступности Open-Meteo", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValueOnce(new Error("network down"));
    await expect(searchCities("Berlin")).rejects.toThrow("Не удалось загрузить варианты городов");
  });
});
