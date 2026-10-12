import { useQuery } from "@tanstack/react-query";

import { ErrorState } from "@/components/ui/async";
import { EmptyState, Panel, Spinner } from "@/components/ui/panel";
import { getMemoryProfile } from "@/lib/api";
import { Badge } from "@/components/ui/panel";
import { useT, type TFunc } from "@/lib/i18n";

/** Where a persona fact came from, in words. The store's source ids ("chat", "extracted") were
 *  printed raw, in English, under every fact; an unknown one is still shown as sent. */
function sourceLabel(t: TFunc, source: string): string {
  switch (source) {
    case "chat":
      return t("profile.source.chat");
    case "extracted":
      return t("profile.source.extracted");
    case "chimera":
      return t("profile.source.chimera");
    default:
      return source;
  }
}

/**
 * What the agent has learned about you.
 *
 * `GET /api/memory/profile` existed and no screen read it, while Memory happily wrote persona facts
 * into the same store — so you could feed a picture of yourself that you were never shown. For a
 * feature whose entire premise is "it remembers you", not being able to see what it remembers is
 * the part that matters most.
 *
 * Read-only by design: the profile is derived by the agent from persona facts, so the honest place
 * to change it is the facts themselves, in Memory.
 */
export function Profile({ onOpenMemory }: { onOpenMemory?: () => void } = {}) {
  const t = useT();
  const profile = useQuery({ queryKey: ["memory-profile"], queryFn: getMemoryProfile });

  if (profile.isLoading) return <Spinner />;
  if (profile.isError)
    return <ErrorState error={profile.error} onRetry={() => profile.refetch()} />;

  const text = profile.data?.profile?.trim() ?? "";
  const persona = profile.data?.persona ?? [];

  return (
    <div className="space-y-6">
      <Panel title={t("profile.summary")}>
        <div className="px-4 py-3">
          {text ? (
            <p className="whitespace-pre-wrap text-sm leading-relaxed">{text}</p>
          ) : (
            <p className="text-sm text-muted-foreground">{t("profile.empty")}</p>
          )}
        </div>
      </Panel>

      <Panel
        title={t("profile.facts")}
        // Read-only here on purpose (see above), so the way to change a fact is one click away
        // rather than a tab the reader has to know about.
        action={
          onOpenMemory ? (
            <button type="button" onClick={onOpenMemory} className="text-xs text-accent-ink hover:underline">
              {t("profile.manage")}
            </button>
          ) : undefined
        }
      >
        {persona.length === 0 ? (
          <EmptyState text={t("profile.noFacts")} />
        ) : (
          persona.map((item) => (
            <div key={item.id} className="px-4 py-2.5">
              <p className="text-sm">{item.content}</p>
              {/* Where the fact came from. A persona fact the agent inferred and one you typed
                  yourself carry different weight, and you should be able to tell them apart. */}
              <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                <span>{sourceLabel(t, item.source)}</span>
                {/* The same word and colour Memory uses for it, instead of the raw "tainted". */}
                {item.provenance === "tainted" ? <Badge tone="warn">{t("memory.unverified")}</Badge> : null}
              </div>
            </div>
          ))
        )}
      </Panel>
    </div>
  );
}
