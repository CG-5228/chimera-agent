import { describe, expect, it } from "vitest";

import { describeCron } from "@/lib/cronText";
import { DICTS } from "@/lib/i18n";

/** The app's own `t`, for one language, without React. */
function tFor(lang: keyof typeof DICTS) {
  return (key: string, params?: Record<string, string | number>) => {
    let out = DICTS[lang][key] ?? DICTS.en[key] ?? key;
    for (const [k, v] of Object.entries(params ?? {})) out = out.replace(`{${k}}`, String(v));
    return out;
  };
}

describe("describeCron", () => {
  it("says the common shapes in Portuguese, where the server only ever said English", () => {
    const t = tFor("pt");
    expect(describeCron("0 7 * * *", t, "pt")).toBe("Todo dia às 07:00");
    expect(describeCron("30 9 * * 1-5", t, "pt")).toBe("De segunda a sexta às 09:30");
    expect(describeCron("0 8 * * 1", t, "pt")).toBe("Toda semana, segunda-feira, às 08:00");
    expect(describeCron("15 * * * *", t, "pt")).toBe("Toda hora, no minuto 15");
    expect(describeCron("*/10 * * * *", t, "pt")).toBe("A cada 10 minutos");
    expect(describeCron("0 */6 * * *", t, "pt")).toBe("A cada 6 horas");
  });

  it("reads Sunday as both 0 and 7, as cron does", () => {
    const t = tFor("en");
    expect(describeCron("0 9 * * 0", t, "en")).toBe("Every Sunday at 09:00");
    expect(describeCron("0 9 * * 7", t, "en")).toBe("Every Sunday at 09:00");
  });

  it("gives up on anything it cannot say exactly, so the caller falls back to the server", () => {
    const t = tFor("en");
    // A guess here would be worse than English: a wrong time is a missed job.
    for (const expr of ["0 7 1 * *", "0 7 * 6 *", "0 7,19 * * *", "0 7 * * 1,3", "@daily", "0 7 * *"]) {
      expect(describeCron(expr, t, "en"), expr).toBeNull();
    }
  });
});
