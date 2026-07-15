import { afterEach, describe, expect, it, vi } from "vitest";

import { searchCities } from "./city-search";

describe("searchCities", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("не отправляет запрос для строки короче двух символов", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    await expect(searchCities(" М ")).resolves.toEqual([]);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("запрашивает мировые города и нормализует ответ", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        results: [
          {
            id: 524901,
            name: "Москва",
            country: "Россия",
            admin1: "Москва",
            latitude: 55.75222,
            longitude: 37.61556,
            timezone: "Europe/Moscow",
          },
        ],
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(searchCities("Москва")).resolves.toEqual([
      {
        id: 524901,
        label: "Москва, Москва, Россия",
        name: "Москва",
        country: "Россия",
        admin1: "Москва",
        latitude: 55.75222,
        longitude: 37.61556,
        timezone: "Europe/Moscow",
      },
    ]);

    const requestedUrl = new URL(fetchMock.mock.calls[0][0]);
    expect(requestedUrl.origin + requestedUrl.pathname).toBe(
      "https://geocoding-api.open-meteo.com/v1/search",
    );
    expect(requestedUrl.searchParams.get("name")).toBe("Москва");
    expect(requestedUrl.searchParams.get("count")).toBe("6");
    expect(requestedUrl.searchParams.get("language")).toBe("ru");
    expect(requestedUrl.searchParams.get("format")).toBe("json");
  });

  it("возвращает понятную ошибку при недоступности сервиса", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 503 }),
    );

    await expect(searchCities("Berlin")).rejects.toThrow(
      "Не удалось загрузить варианты городов",
    );
  });
});
