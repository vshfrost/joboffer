/** Етап «Підключити агента»: вибір агента, інструкція саме для нього, адреса MCP, перевірка підключення. */
import { within } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import { CLAUDE } from "./agentsBackend";
import { ADDRESS, clipboardUser, openCard } from "./firstStepsHarness";
import { onboardingBackend, onboardingBody } from "./onboardingBackend";
import { json } from "./testClient";

const NAMES = ["Claude", "Claude Code", "ChatGPT", "Codex", "Інший агент"];

describe("ваш агент", () => {
  test("п'ять кнопок з видимими назвами; Claude обрано спочатку", async () => {
    const { card } = await openCard();

    for (const name of NAMES) {
      expect(within(card).getByRole("button", { name }).textContent).toContain(name);
    }
    expect(within(card).getByRole("button", { name: "Claude" }).getAttribute("aria-pressed")).toBe("true");
    expect(within(card).getByRole("button", { name: "Codex" }).getAttribute("aria-pressed")).toBe("false");
  });

  test("вибір агента міняє обраного: іншого знято", async () => {
    const { card, user } = await openCard();

    await user.click(within(card).getByRole("button", { name: "Codex" }));

    expect(within(card).getByRole("button", { name: "Codex" }).getAttribute("aria-pressed")).toBe("true");
    expect(within(card).getByRole("button", { name: "Claude" }).getAttribute("aria-pressed")).toBe("false");
  });

  test("чотири агенти з логотипом, «Інший агент» — з іконкою бота", async () => {
    const { card } = await openCard();

    const logos = ["Claude", "Claude Code", "ChatGPT", "Codex"].map((name) =>
      within(card).getByRole("button", { name }).querySelector<HTMLElement>("[data-agent-logo]")?.style.getPropertyValue("--agent-logo"),
    );
    expect(logos).toEqual(["url(/agents/claude.svg)", "url(/agents/claudecode.svg)", "url(/agents/openai.svg)", "url(/agents/codex.svg)"]);
    expect(within(card).getByRole("button", { name: "Інший агент" }).querySelector(".lucide-bot")).not.toBeNull();
  });
});

describe("як підключити", () => {
  test("спершу згорнуто: кнопка «Як підключити Claude» без кроків", async () => {
    const { card } = await openCard();

    const toggle = within(card).getByRole("button", { name: "Як підключити Claude" });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(within(card).queryByText(/Додати власний конектор/)).toBeNull();
    expect(within(card).queryByText("Кроки можуть відрізнятись")).toBeNull();
  });

  test("відкриті кроки — лише обраного агента, з приміткою «Кроки можуть відрізнятись»", async () => {
    const { card, user } = await openCard();

    await user.click(within(card).getByRole("button", { name: "Як підключити Claude" }));

    expect(within(card).getByText(/Додати власний конектор/)).toBeDefined();
    expect(within(card).getByText("Кроки можуть відрізнятись")).toBeDefined();
    expect(within(card).queryByText(`claude mcp add --transport http joboffer ${ADDRESS}`)).toBeNull();
    expect(within(card).queryByText(`codex mcp add joboffer --url ${ADDRESS}`)).toBeNull();
  });

  test("Claude: посилання на довідку відкривається в новій вкладці", async () => {
    const { card, user } = await openCard();
    await user.click(within(card).getByRole("button", { name: "Як підключити Claude" }));

    const help = within(card).getByRole("link", { name: /Довідка/ });
    expect(help.getAttribute("href")).toBe("https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp");
    expect(help.getAttribute("target")).toBe("_blank");
    expect(help.getAttribute("rel")).toBe("noopener noreferrer");
  });

  test("Claude Code: назва в кнопці, команда з адресою", async () => {
    const { card, user } = await openCard();

    await user.click(within(card).getByRole("button", { name: "Claude Code" }));
    await user.click(within(card).getByRole("button", { name: "Як підключити Claude Code" }));

    expect(within(card).getByText(`claude mcp add --transport http joboffer ${ADDRESS}`)).toBeDefined();
    expect(within(card).queryByText(/Додати власний конектор/)).toBeNull();
  });

  test("ChatGPT: шлях через Apps і режим розробника", async () => {
    const { card, user } = await openCard();

    await user.click(within(card).getByRole("button", { name: "ChatGPT" }));
    await user.click(within(card).getByRole("button", { name: "Як підключити ChatGPT" }));

    expect(within(card).getByText(/Налаштування → Apps/)).toBeDefined();
  });

  test("Codex: команди додавання й входу", async () => {
    const { card, user } = await openCard();

    await user.click(within(card).getByRole("button", { name: "Codex" }));
    await user.click(within(card).getByRole("button", { name: "Як підключити Codex" }));

    expect(within(card).getByText(`codex mcp add joboffer --url ${ADDRESS}`)).toBeDefined();
    expect(within(card).getByText("codex mcp login joboffer")).toBeDefined();
  });

  test("Інший агент: підпис «свого агента», довідки нема", async () => {
    const { card, user } = await openCard();

    await user.click(within(card).getByRole("button", { name: "Інший агент" }));
    await user.click(within(card).getByRole("button", { name: "Як підключити свого агента" }));

    expect(within(card).getByText(/Streamable HTTP/)).toBeDefined();
    expect(within(card).queryByRole("link", { name: /Довідка/ })).toBeNull();
  });

  test("зміна агента знову згортає інструкцію", async () => {
    const { card, user } = await openCard();
    await user.click(within(card).getByRole("button", { name: "Як підключити Claude" }));

    await user.click(within(card).getByRole("button", { name: "Codex" }));

    expect(within(card).getByRole("button", { name: "Як підключити Codex" }).getAttribute("aria-expanded")).toBe("false");
    expect(within(card).queryByText(`codex mcp add joboffer --url ${ADDRESS}`)).toBeNull();
  });
});

describe("адреса MCP", () => {
  test("показано адресу й кнопку копіювання; адреса одна на картку", async () => {
    const { card } = await openCard();

    expect(within(card).getAllByText(ADDRESS)).toHaveLength(1);
    expect(within(card).getByRole("button", { name: "Копіювати адресу MCP" })).toBeDefined();
  });

  test("кнопка кладе адресу в буфер обміну й повідомляє про це", async () => {
    const { card } = await openCard();
    const { user, writeText } = clipboardUser();

    await user.click(within(card).getByRole("button", { name: "Копіювати адресу MCP" }));

    expect(writeText).toHaveBeenCalledExactlyOnceWith(ADDRESS);
    expect(await within(card).findByText("Адресу скопійовано.")).toBeDefined();
  });

  test("буфер недоступний — підказує виділити адресу вручну", async () => {
    const { card } = await openCard();
    const { user, writeText } = clipboardUser();
    writeText.mockRejectedValueOnce(new Error("denied"));

    await user.click(within(card).getByRole("button", { name: "Копіювати адресу MCP" }));

    expect(await within(card).findByText("Не вдалося скопіювати — виділи адресу вручну.")).toBeDefined();
  });
});

describe("перевірити підключення", () => {
  test("перезавантажує онбординг і список агентів", async () => {
    const { card, user, backend, stub } = await openCard();
    const agentsBefore = stub.requests;

    await user.click(within(card).getByRole("button", { name: "Перевірити підключення" }));

    await within(card).findByText("Підключення ще не знайдено. Додай адресу в агенті й перевір ще раз.");
    expect(backend.calls).toEqual(["GET /api/onboarding", "GET /api/onboarding"]);
    expect(stub.requests).toBeGreaterThan(agentsBefore);
  });

  test("агента ще нема — лишається перший етап з повідомленням", async () => {
    const { card, user } = await openCard();

    await user.click(within(card).getByRole("button", { name: "Перевірити підключення" }));

    expect(await within(card).findByText("Підключення ще не знайдено. Додай адресу в агенті й перевір ще раз.")).toBeDefined();
    expect(within(card).getByText("Крок 1 із 3")).toBeDefined();
    expect(within(card).queryByText("Агента підключено")).toBeNull();
  });

  test("агент підключився — картка переходить на другий етап", async () => {
    const { card, user, backend } = await openCard({}, [CLAUDE]);
    backend.done.add("claude");

    await user.click(within(card).getByRole("button", { name: "Перевірити підключення" }));

    expect(await within(card).findByRole("heading", { level: 3, name: "Агента підключено" })).toBeDefined();
    expect(within(card).getByText("Крок 2 із 3")).toBeDefined();
  });

  test("сервер не відповів — повідомлення про помилку, етап не міняється", async () => {
    let calls = 0;
    const backend = onboardingBackend(
      {},
      {
        "GET /api/onboarding": () => {
          calls += 1;
          return calls === 1 ? json(200, onboardingBody({ done: new Set(), seen: new Set(), dismissed: new Set() })) : json(500, { code: "internal_error" });
        },
      },
    );
    const { card, user } = await openCard({}, [], backend);

    await user.click(within(card).getByRole("button", { name: "Перевірити підключення" }));

    expect(await within(card).findByText("Не вдалося перевірити підключення. Спробуй ще раз.")).toBeDefined();
    expect(within(card).getByText("Крок 1 із 3")).toBeDefined();
  });

  test("повторна перевірка прибирає старе повідомлення про помилку", async () => {
    let calls = 0;
    const backend = onboardingBackend(
      {},
      {
        "GET /api/onboarding": () => {
          calls += 1;
          return calls === 2 ? json(500, { code: "internal_error" }) : json(200, onboardingBody({ done: new Set(), seen: new Set(), dismissed: new Set() }));
        },
      },
    );
    const { card, user } = await openCard({}, [], backend);
    await user.click(within(card).getByRole("button", { name: "Перевірити підключення" }));
    await within(card).findByText("Не вдалося перевірити підключення. Спробуй ще раз.");

    await user.click(within(card).getByRole("button", { name: "Перевірити підключення" }));

    expect(await within(card).findByText("Підключення ще не знайдено. Додай адресу в агенті й перевір ще раз.")).toBeDefined();
    expect(within(card).queryByText("Не вдалося перевірити підключення. Спробуй ще раз.")).toBeNull();
  });
});
