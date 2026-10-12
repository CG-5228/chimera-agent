import { useEffect, useRef, useState, type KeyboardEvent } from "react";

import { focusRing } from "@/components/ui/focus";
import { Tooltip } from "@/components/ui/tooltip";
import { useAppearance } from "@/lib/appearance";
import { anyInstalled, bundledFontLoads, fontInstalled } from "@/lib/fonts";
import { useT } from "@/lib/i18n";
import { useLayout } from "@/lib/layout/context";
import type { TranscriptWidth } from "@/lib/layout/model";
import { ACCENTS, type Accent, type CodeFont, type Contrast, type Motion, type TextSize, type Theme, type Tint, type UiFont } from "@/lib/theme";
import { cn } from "@/lib/utils";

/**
 * The controls of Settings › Appearance, beside the language picker.
 *
 * Each is a plain select over a small closed set, named by the row it sits in (the caller passes the
 * row's label, the way `LanguageSelect` takes it from the row). The keys are written out in full rather
 * than assembled, so the i18n reachability test can see every one of them.
 */

const selectCls = "field h-8 w-56 px-2.5 text-sm";

interface Option<T extends string> {
  value: T;
  label: string;
  /**
   * Shown but not choosable, and why. The two reasons read differently on purpose: a code font is the
   * computer's own, so "not on this computer" is true and actionable; a font the app ships is not the
   * computer's business, and blaming the computer for a file the build lacks would send someone off
   * installing a font that would change nothing.
   */
  unavailable?: "missing" | "notInBuild";
}

function optionLabel(t: ReturnType<typeof useT>, o: Option<string>): string {
  if (o.unavailable === "missing") return t("settings.font.missing", { name: o.label });
  if (o.unavailable === "notInBuild") return t("settings.font.notInBuild", { name: o.label });
  return o.label;
}

function Choice<T extends string>({
  name,
  value,
  options,
  onChange,
}: {
  name: string;
  value: T;
  options: Option<T>[];
  onChange: (value: T) => void;
}) {
  const t = useT();
  return (
    <select
      className={selectCls}
      aria-label={name}
      value={value}
      onChange={(e) => onChange(e.target.value as T)}
    >
      {options.map((o) => (
        // The current choice stays choosable even when its font went missing: disabling the selected
        // option would leave the select showing a value it claims cannot be picked.
        <option key={o.value} value={o.value} disabled={o.unavailable !== undefined && o.value !== value}>
          {optionLabel(t, o)}
        </option>
      ))}
    </select>
  );
}

export function ThemeSelect({ name }: { name: string }) {
  const t = useT();
  const { theme, setTheme } = useAppearance();
  const options: Option<Theme>[] = [
    { value: "system", label: t("settings.theme.system") },
    { value: "light", label: t("settings.theme.light") },
    { value: "dark", label: t("settings.theme.dark") },
  ];
  return <Choice name={name} value={theme} options={options} onChange={setTheme} />;
}

/**
 * The accent, as swatches rather than a list of colour names: a colour is chosen by looking at it.
 *
 * A radio group, so it behaves like one — one tab stop, arrows move the choice — and each swatch is
 * named, because a circle of colour says nothing to a screen reader.
 */
export function AccentPicker({ name }: { name: string }) {
  const t = useT();
  const { accent, setAccent } = useAppearance();
  const refs = useRef<Partial<Record<Accent, HTMLButtonElement | null>>>({});
  const label: Record<Accent, string> = {
    blue: t("settings.accent.blue"),
    cyan: t("settings.accent.cyan"),
    green: t("settings.accent.green"),
    amber: t("settings.accent.amber"),
    rose: t("settings.accent.rose"),
    graphite: t("settings.accent.graphite"),
  };
  const move = (event: KeyboardEvent<HTMLDivElement>) => {
    const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[event.key];
    if (step === undefined) return;
    event.preventDefault();
    const next = ACCENTS[(ACCENTS.indexOf(accent) + step + ACCENTS.length) % ACCENTS.length];
    setAccent(next);
    refs.current[next]?.focus();
  };
  return (
    <div role="radiogroup" aria-label={name} className="flex items-center gap-2.5" onKeyDown={move}>
      {ACCENTS.map((a) => (
        <Tooltip key={a} label={label[a]}>
          <button
            ref={(el) => {
              refs.current[a] = el;
            }}
            type="button"
            role="radio"
            aria-checked={accent === a}
            aria-label={label[a]}
            tabIndex={accent === a ? 0 : -1}
            data-swatch={a}
            onClick={() => setAccent(a)}
            className={cn(
              "accent-swatch h-6 w-6 shrink-0 rounded-full transition-transform duration-1 ease-out",
              focusRing,
              // The chosen one is marked by a ring in the TEXT colour, not by its own colour: the
              // mark has to read the same on every swatch, including the one that matches it.
              accent === a ? "ring-2 ring-foreground ring-offset-2 ring-offset-card" : "hover:scale-110",
            )}
          />
        </Tooltip>
      ))}
    </div>
  );
}

export function TintSelect({ name }: { name: string }) {
  const t = useT();
  const { tint, setTint } = useAppearance();
  const options: Option<Tint>[] = [
    { value: "navy", label: t("settings.tint.navy") },
    { value: "neutral", label: t("settings.tint.neutral") },
    { value: "warm", label: t("settings.tint.warm") },
  ];
  return <Choice name={name} value={tint} options={options} onChange={setTint} />;
}

export function ContrastSelect({ name }: { name: string }) {
  const t = useT();
  const { contrast, setContrast } = useAppearance();
  const options: Option<Contrast>[] = [
    { value: "standard", label: t("settings.contrast.standard") },
    { value: "high", label: t("settings.contrast.high") },
  ];
  return <Choice name={name} value={contrast} options={options} onChange={setContrast} />;
}

export function MotionSelect({ name }: { name: string }) {
  const t = useT();
  const { motion, setMotion } = useAppearance();
  const options: Option<Motion>[] = [
    { value: "system", label: t("settings.motion.system") },
    { value: "full", label: t("settings.motion.full") },
    { value: "reduced", label: t("settings.motion.reduced") },
  ];
  return <Choice name={name} value={motion} options={options} onChange={setMotion} />;
}

export function TextSizeSelect({ name }: { name: string }) {
  const t = useT();
  const { textSize, setTextSize } = useAppearance();
  const options: Option<TextSize>[] = [
    { value: "small", label: t("settings.textSize.small") },
    { value: "medium", label: t("settings.textSize.medium") },
    { value: "large", label: t("settings.textSize.large") },
  ];
  return <Choice name={name} value={textSize} options={options} onChange={setTextSize} />;
}

/** Kept in the layout rather than beside the others: it is a property of the conversation screen, and
 *  the layout is what already travels to the server and back. */
export function TranscriptWidthSelect({ name }: { name: string }) {
  const t = useT();
  const { layout, dispatch } = useLayout();
  const options: Option<TranscriptWidth>[] = [
    { value: "narrow", label: t("settings.transcriptWidth.narrow") },
    { value: "medium", label: t("settings.transcriptWidth.medium") },
    { value: "wide", label: t("settings.transcriptWidth.wide") },
  ];
  return (
    <Choice
      name={name}
      value={layout.transcriptWidth}
      options={options}
      onChange={(width) => void dispatch({ type: "transcript-width", width })}
    />
  );
}

export function UiFontSelect({ name }: { name: string }) {
  const t = useT();
  const { uiFont, setUiFont } = useAppearance();
  // Declared by the app's own @font-face (public/fonts), so the question is whether the file loads,
  // not whether the computer has it. "pending" until the check answers: an option that appears and
  // then vanishes would be worse than one that appears a moment late.
  const [dyslexic, setDyslexic] = useState<boolean | null | "pending">("pending");
  useEffect(() => {
    let live = true;
    void bundledFontLoads("OpenDyslexic").then((ok) => {
      if (live) setDyslexic(ok);
    });
    return () => {
      live = false;
    };
  }, []);
  const options: Option<UiFont>[] = [
    { value: "system", label: t("settings.uiFont.system") },
    { value: "serif", label: t("settings.uiFont.serif") },
  ];
  // Offered only once the file is known to load (or the webview cannot tell, which fonts.ts treats as
  // available). A build without the file shows no OpenDyslexic at all, rather than an option that is
  // permanently disabled. The one exception is someone whose stored choice IS OpenDyslexic: the
  // select must be able to show its own value, so it stays, saying the build lacks it.
  const loads = dyslexic === true || dyslexic === null;
  if (loads || uiFont === "dyslexic") {
    options.push({
      value: "dyslexic",
      label: "OpenDyslexic",
      unavailable: dyslexic === false ? "notInBuild" : undefined,
    });
  }
  return <Choice name={name} value={uiFont} options={options} onChange={setUiFont} />;
}

export function CodeFontSelect({ name }: { name: string }) {
  const t = useT();
  const { codeFont, setCodeFont } = useAppearance();
  // Measured once per mount: fonts are not installed while a settings screen is open often enough to
  // be worth watching for.
  const [installed] = useState(() => ({
    // Either name will do: the stack in index.css lists both, and Windows ships them as a pair.
    cascadia: anyInstalled("Cascadia Code", "Cascadia Mono"),
    jetbrains: fontInstalled("JetBrains Mono"),
  }));
  const options: Option<CodeFont>[] = [
    { value: "default", label: t("settings.codeFont.default") },
    {
      value: "cascadia",
      label: "Cascadia Code",
      unavailable: installed.cascadia === false ? "missing" : undefined,
    },
    {
      value: "jetbrains",
      label: "JetBrains Mono",
      unavailable: installed.jetbrains === false ? "missing" : undefined,
    },
  ];
  return <Choice name={name} value={codeFont} options={options} onChange={setCodeFont} />;
}
