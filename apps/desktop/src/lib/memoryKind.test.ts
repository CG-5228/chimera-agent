import { describe, expect, it } from "vitest";

import { DICTS } from "@/lib/i18n";
import { memoryKindLabel } from "@/lib/memoryKind";

describe("memoryKindLabel", () => {
  const pt = (key: string) => DICTS.pt[key] ?? key;

  it("names each kind in the reader's language instead of printing the identifier", () => {
    expect(["working", "episodic", "semantic", "persona"].map((k) => memoryKindLabel(pt, k))).toEqual([
      "Trabalho",
      "Episódica",
      "Semântica",
      "Persona",
    ]);
  });

  it("shows a kind it does not know as sent, never as a blank", () => {
    expect(memoryKindLabel(pt, "procedural")).toBe("procedural");
  });
});
