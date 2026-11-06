/** Тема Pine: токени збігаються з design-system-pine (brain: projects/joboffer/design-system-pine). */
import { describe, expect, test } from "vitest";

import css from "./theme.css?raw";

function declarations(source: string): Map<string, string> {
  const found = new Map<string, string>();
  for (const [, name, value] of source.matchAll(/(--[a-z0-9-]+)\s*:\s*([^;]+);/g)) {
    // @theme пише `--color-x: var(--x)`; сирі значення беремо з першого оголошення без префікса --color-.
    if (name !== undefined && value !== undefined && !found.has(name)) found.set(name, value.trim());
  }
  return found;
}

const tokens = declarations(css);

function resolve(name: string): string {
  const value = tokens.get(name);
  if (value === undefined) throw new Error(`токен ${name} не оголошено в theme.css`);
  const reference = /^var\((--[a-z0-9-]+)\)$/.exec(value);
  return reference?.[1] === undefined ? value.toLowerCase() : resolve(reference[1]);
}

const PALETTE: Record<string, string> = {
  "--background": "#F7F8F7",
  "--card": "#FFFFFF",
  "--popover": "#FFFFFF",
  "--foreground": "#202624",
  "--card-foreground": "#202624",
  "--popover-foreground": "#202624",
  "--muted": "#EEF1EF",
  "--secondary": "#EEF1EF",
  "--muted-foreground": "#626B66",
  "--secondary-foreground": "#202624",
  "--border": "#DCE2DE",
  "--input": "#849089",
  "--primary": "#356859",
  "--ring": "#356859",
  "--primary-foreground": "#FFFFFF",
  "--jo-primary-hover": "#2C584B",
  "--jo-metric": "#2C584B",
  "--accent": "#EDF2EF",
  "--accent-foreground": "#202624",
  "--jo-selected": "#E7F0EB",
  "--jo-selected-foreground": "#2C584B",
  "--jo-disabled": "#EEF1EF",
  "--jo-disabled-foreground": "#626B66",
  "--sidebar": "#F1F4F2",
  "--jo-counter": "#B8EF70",
  "--jo-counter-foreground": "#21462E",
  "--destructive": "#A23D3D",
  "--destructive-foreground": "#FFFFFF",
  "--jo-status-neutral-foreground": "#626B66",
  "--jo-status-neutral-background": "#EEF1EF",
  "--jo-status-info-foreground": "#405D86",
  "--jo-status-info-background": "#EEF2F8",
  "--jo-status-warning-foreground": "#805B20",
  "--jo-status-warning-background": "#FBF4E7",
  "--jo-status-success-foreground": "#286044",
  "--jo-status-success-background": "#EDF5EF",
  "--jo-status-danger-foreground": "#A23D3D",
  "--jo-status-danger-background": "#FAEEEE",
  "--jo-agent-claude": "#A84E32",
  "--jo-agent-claude-surface": "#FBF2ED",
  "--jo-agent-claude-border": "#EADBD2",
  "--jo-agent-chatgpt": "#286044",
  "--jo-agent-chatgpt-surface": "#EDF5EF",
  "--jo-agent-chatgpt-border": "#D7E6DC",
  "--jo-agent-codex": "#35434A",
  "--jo-agent-codex-surface": "#EEF1F2",
  "--jo-agent-codex-border": "#DCE2E4",
};

describe("токени Pine", () => {
  test.each(Object.entries(PALETTE))("%s = %s", (name, hex) => {
    expect(resolve(name)).toBe(hex.toLowerCase());
  });

  test.each([
    ["--sidebar-foreground", "--foreground"],
    ["--sidebar-accent", "--jo-selected"],
    ["--sidebar-accent-foreground", "--jo-selected-foreground"],
    ["--sidebar-primary", "--primary"],
    ["--sidebar-ring", "--ring"],
    ["--sidebar-border", "--border"],
  ])("%s повторює %s", (name, source) => {
    expect(resolve(name)).toBe(resolve(source));
  });

  test("базовий радіус — 8 px", () => {
    expect(resolve("--radius")).toBe("0.5rem");
  });

  test("у темі нема кольорів поза палітрою", () => {
    const allowed = new Set(Object.values(PALETTE).map((hex) => hex.toLowerCase()));
    const used = [...css.matchAll(/#[0-9a-fA-F]{6}\b/g)].map((match) => match[0].toLowerCase());
    expect(used.filter((hex) => !allowed.has(hex))).toEqual([]);
  });

  test("агент без власного бренду («Інший агент») — шавлія: --primary на --jo-selected", () => {
    expect(resolve("--jo-agent-other")).toBe(resolve("--primary"));
    expect(resolve("--jo-agent-other-surface")).toBe(resolve("--jo-selected"));
    expect(resolve("--jo-agent-other-border")).toBe(resolve("--border"));
  });

  test("шрифт — Inter з системним запасним", () => {
    expect(tokens.get("--font-sans")).toMatch(/^"Inter Variable",.*system-ui.*sans-serif$/);
  });
});

function luminance(hex: string): number {
  const channels = [1, 3, 5].map((start) => parseInt(hex.slice(start, start + 2), 16) / 255);
  const [r = 0, g = 0, b = 0] = channels.map((c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(foreground: string, background: string): number {
  const [light, dark] = [luminance(foreground), luminance(background)].sort((a, b) => b - a);
  return ((light ?? 0) + 0.05) / ((dark ?? 0) + 0.05);
}

describe("контраст пар (за формулою з документа)", () => {
  test.each([
    ["--foreground", "--background", 14.46],
    ["--muted-foreground", "--background", 5.17],
    ["--muted-foreground", "--jo-selected", 4.74],
    ["--primary-foreground", "--primary", 6.41],
    ["--primary-foreground", "--jo-primary-hover", 8.06],
    ["--jo-metric", "--card", 8.06],
    ["--jo-metric", "--background", 7.57],
    ["--jo-counter-foreground", "--jo-counter", 7.89],
    ["--jo-status-neutral-foreground", "--jo-status-neutral-background", 4.84],
    ["--jo-status-info-foreground", "--jo-status-info-background", 5.98],
    ["--jo-status-warning-foreground", "--jo-status-warning-background", 5.59],
    ["--jo-status-success-foreground", "--jo-status-success-background", 6.64],
    ["--jo-status-danger-foreground", "--jo-status-danger-background", 5.66],
  ])("%s на %s ≈ %s", (foreground, background, expected) => {
    const ratio = contrast(resolve(foreground), resolve(background));
    expect(Math.abs(ratio - expected)).toBeLessThan(0.01);
    expect(ratio).toBeGreaterThanOrEqual(4.5);
  });
});

describe("кольори агентів: текст на своїй поверхні читається (≥ 4.5)", () => {
  test.each(["claude", "chatgpt", "codex", "other"])("%s", (agent) => {
    expect(contrast(resolve(`--jo-agent-${agent}`), resolve(`--jo-agent-${agent}-surface`))).toBeGreaterThanOrEqual(4.5);
  });
});

describe("лічильники джерел (K47)", () => {
  /** Оголошення правила, що стоїть на всі перелічені селектори разом. */
  function ruleFor(selectors: string): Map<string, string> {
    const escaped = selectors.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/,\s*/g, "\\s*,\\s*");
    const found = new RegExp(`${escaped}\\s*\\{([^}]*)\\}`).exec(css);
    if (found?.[1] === undefined) throw new Error(`правила ${selectors} нема в theme.css`);
    return new Map([...found[1].matchAll(/([a-z-]+)\s*:\s*([^;]+);/g)].map(([, name, value]) => [name ?? "", (value ?? "").trim()]));
  }

  test(".sr-count і .sr-stats dd: колір з --jo-metric, вага 600, цифри однієї ширини", () => {
    const declared = ruleFor(".sr-count, .sr-stats dd");

    expect(declared.get("color")).toBe("var(--jo-metric)");
    expect(declared.get("font-weight")).toBe("600");
    expect(declared.get("font-variant-numeric")).toBe("tabular-nums");
  });
});
