import type { TFunc } from "@/lib/i18n";

/**
 * A cron schedule as a sentence in the reader's language, for the shapes people actually set.
 *
 * The server sends `schedule_description`, which is English whatever the app is set to — "every day
 * at 07:00" on a screen that otherwise says "Agenda". The common shapes (daily, weekdays, one day a
 * week, every hour, every N minutes or hours) are said here instead; anything else returns null and
 * the caller falls back to the server's text, so an unusual schedule is still described rather than
 * guessed at.
 */
const INT = /^\d+$/;

function hhmm(hour: number, minute: number): string {
  return `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
}

/** The weekday's name in `lang`. 2024-01-07 was a Sunday, cron's day 0 (and 7). */
function weekday(day: number, lang: string): string {
  const date = new Date(Date.UTC(2024, 0, 7 + (day % 7), 12));
  return new Intl.DateTimeFormat(lang, { weekday: "long", timeZone: "UTC" }).format(date);
}

export function describeCron(expr: string, t: TFunc, lang: string): string | null {
  const parts = expr.trim().split(/\s+/);
  if (parts.length !== 5) return null;
  const [min, hour, dom, mon, dow] = parts;
  if (dom !== "*" || mon !== "*") return null;

  const every = /^\*\/(\d+)$/;
  if (hour === "*" && dow === "*") {
    const n = every.exec(min);
    if (n) return t("cron.when.everyMinutes", { n: Number(n[1]) });
    if (INT.test(min)) return t("cron.when.hourly", { m: Number(min) });
    return null;
  }
  if (!INT.test(min)) return null;
  const m = Number(min);
  const nh = every.exec(hour);
  if (nh && dow === "*") return t("cron.when.everyHours", { n: Number(nh[1]) });
  if (!INT.test(hour)) return null;
  const time = hhmm(Number(hour), m);
  if (dow === "*") return t("cron.when.daily", { time });
  if (dow === "1-5") return t("cron.when.weekdays", { time });
  if (INT.test(dow) && Number(dow) <= 7) return t("cron.when.weekly", { day: weekday(Number(dow), lang), time });
  return null;
}
