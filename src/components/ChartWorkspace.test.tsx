import { useState } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { DomainCard } from "../lib/chart-api";
import { currentDashaIndex, DomainDetail, downloadReportFile } from "./ChartWorkspace";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("currentDashaIndex", () => {
  const periods = [
    { lord: "Кету", start: "2020-01-01T00:00:00Z", end: "2027-01-01T00:00:00Z" },
    { lord: "Венера", start: "2027-01-01T00:00:00Z", end: "2047-01-01T00:00:00Z" },
  ];

  it("находит текущий период по дате браузера", () => {
    expect(currentDashaIndex(periods, new Date("2026-07-31T12:00:00Z"))).toBe(0);
  });

  it("на границе выбирает начинающийся период", () => {
    expect(currentDashaIndex(periods, new Date("2027-01-01T00:00:00Z"))).toBe(1);
  });
});

describe("downloadReportFile", () => {
  it("создаёт локальную ссылку с именем PDF и запускает скачивание", async () => {
    const blob = new Blob(["pdf"], { type: "application/pdf" });
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, blob: vi.fn().mockResolvedValue(blob) });
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:report");
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function capture(this: HTMLAnchorElement) {
      expect(this.download).toBe("vedicway-chart_123.pdf");
      expect(this.href).toBe("blob:report");
    });

    await downloadReportFile("/api/report", "vedicway-chart_123.pdf");

    expect(fetchMock).toHaveBeenCalledWith("/api/report", { credentials: "same-origin" });
    expect(click).toHaveBeenCalledTimes(1);
    expect(document.querySelector('a[href="blob:report"]')).not.toBeInTheDocument();
  });
});

describe("DomainDetail", () => {
  const domains: DomainCard[] = [
    {
      slug: "character",
      section_label: "Характер",
      title: "Первый раздел",
      summary: "Первое резюме",
      evidence_ids: [],
      coverage: "multiple_factors",
      limitations: [],
      paragraphs: ["Длинный текст первого раздела"],
      manifestations: [],
      reflection_prompts: [],
    },
    {
      slug: "work",
      section_label: "Работа",
      title: "Второй раздел",
      summary: "Второе резюме",
      evidence_ids: [],
      coverage: "multiple_factors",
      limitations: [],
      paragraphs: ["Длинный текст второго раздела"],
      manifestations: [],
      reflection_prompts: [],
    },
  ];

  function DetailHarness() {
    const [index, setIndex] = useState(0);
    return (
      <DomainDetail
        domain={domains[index]}
        facts={new Map()}
        index={index}
        total={domains.length}
        onClose={() => undefined}
        onPrevious={() => setIndex((value) => (value + domains.length - 1) % domains.length)}
        onNext={() => setIndex((value) => (value + 1) % domains.length)}
      />
    );
  }

  it("returns the reading body to the top and focuses its heading when paging", async () => {
    const user = userEvent.setup();
    render(<DetailHarness />);

    await waitFor(() => expect(screen.getByRole("heading", { name: "Первый раздел" })).toHaveFocus());
    const body = screen.getByText("Длинный текст первого раздела").closest(".domain-detail__body") as HTMLDivElement;
    body.scrollTop = 240;

    await user.click(screen.getByRole("button", { name: /следующая/i }));
    expect(body.scrollTop).toBe(0);
    await waitFor(() => expect(screen.getByRole("heading", { name: "Второй раздел" })).toHaveFocus());

    body.scrollTop = 180;
    await user.click(screen.getByRole("button", { name: /предыдущая/i }));
    expect(body.scrollTop).toBe(0);
    await waitFor(() => expect(screen.getByRole("heading", { name: "Первый раздел" })).toHaveFocus());
  });
});
