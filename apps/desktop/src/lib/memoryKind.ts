import type { TFunc } from "@/lib/i18n";

/**
 * A memory kind, in the reader's language.
 *
 * The kinds are identifiers on the wire ("working", "episodic", "semantic", "persona") and they were
 * printed as such — in a monospace font, in English, on every row of a screen otherwise translated
 * into ten languages. A kind this build does not know is shown as sent rather than hidden: a newer
 * server may add one, and a blank would say the fact has no kind.
 */
export function memoryKindLabel(t: TFunc, kind: string): string {
  // Written out in full, not assembled, so the i18n reachability test can see each key.
  switch (kind) {
    case "working":
      return t("memory.kind.working");
    case "episodic":
      return t("memory.kind.episodic");
    case "semantic":
      return t("memory.kind.semantic");
    case "persona":
      return t("memory.kind.persona");
    default:
      return kind;
  }
}
