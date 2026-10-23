import { describe, expect, it } from "vitest";

import { compactNumber, countdown, errorMessage, formatDuration, timeAgo, titleCase } from "@/lib/utils";

describe("compactNumber", () => {
  it("keeps small numbers exact", () => {
    expect(compactNumber(0)).toBe("0");
    expect(compactNumber(999)).toBe("999");
  });

  it("compacts thousands and millions", () => {
    expect(compactNumber(1_000)).toBe("1.0K");
    expect(compactNumber(15_000)).toBe("15K");
    expect(compactNumber(2_500_000)).toBe("2.5M");
  });

  it("treats missing values as zero", () => {
    expect(compactNumber(null)).toBe("0");
    expect(compactNumber(undefined)).toBe("0");
  });
});

describe("timeAgo", () => {
  it("returns a friendly fallback for empty dates", () => {
    expect(timeAgo(null)).toBe("just now");
    expect(timeAgo("")).toBe("just now");
  });

  it("formats recent timestamps", () => {
    expect(timeAgo(new Date(Date.now() - 5_000).toISOString())).toBe("5s ago");
    expect(timeAgo(new Date(Date.now() - 2 * 3_600_000).toISOString())).toBe("2h ago");
  });
});

describe("formatDuration", () => {
  it("shows a placeholder when there is no duration", () => {
    expect(formatDuration(null)).toBe("--:--");
    expect(formatDuration(0)).toBe("--:--");
  });

  it("formats minutes and seconds", () => {
    expect(formatDuration(65)).toBe("1:05");
    expect(formatDuration(600)).toBe("10:00");
  });
});

describe("countdown", () => {
  it("handles deadlines that are missing or passed", () => {
    expect(countdown(null, null)).toBe("No deadline");
    expect(countdown(null, 0)).toBe("Closed");
  });

  it("breaks the remaining time into days, hours and minutes", () => {
    expect(countdown(null, 90)).toBe("1m left");
    expect(countdown(null, 3_600)).toBe("1h 0m left");
    expect(countdown(null, 90_000)).toBe("1d 1h left");
  });
});

describe("titleCase", () => {
  it("turns snake_case into display text", () => {
    expect(titleCase("head_to_head")).toBe("Head To Head");
    expect(titleCase("open challenge")).toBe("Open Challenge");
  });

  it("returns an empty string for missing values", () => {
    expect(titleCase(null)).toBe("");
    expect(titleCase("")).toBe("");
  });
});

describe("errorMessage", () => {
  it("uses the error message when there is one", () => {
    expect(errorMessage(new Error("Network failed"))).toBe("Network failed");
  });

  it("falls back to a generic message", () => {
    expect(errorMessage("not an error")).toBe("Something went wrong. Please try again.");
    expect(errorMessage(new Error(""))).toBe("Something went wrong. Please try again.");
  });
});