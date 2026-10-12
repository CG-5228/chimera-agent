import { describe, expect, it } from "vitest";

import { automationTab } from "@/components/Automation";

describe("Automation's tabs have addresses", () => {
  it("reads the tab from the URL, and an unknown one as the schedule", () => {
    expect(automationTab("agents")).toBe("agents");
    expect(automationTab("tasks")).toBe("tasks");
    expect(automationTab("chat")).toBe("schedule");
    expect(automationTab(undefined)).toBe("schedule");
  });
});
