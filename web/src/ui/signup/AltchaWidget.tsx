// Збірка без вбудованих воркера й стилів (CSP без CDN): воркер і CSS віддаємо з власного origin.
import "altcha/external";
import "altcha/altcha.css";
import "altcha/i18n/uk";
import workerUrl from "altcha/worker?url";
import { useEffect, useRef } from "react";

/** Віджет ALTCHA (proof-of-work): сам бере задачу з `challengeUrl` і віддає розв'язок. */
export interface AltchaWidgetProps {
  /** Адреса задачі на тому ж origin (`GET /auth/challenge`). */
  challengeUrl: string;
  /** Розв'язок (base64-JSON віджета), який іде в `altcha` запиту реєстрації. */
  onSolved(payload: string): void;
  /** Розв'язок втрачено: прострочився, збій або перевірку почато заново. */
  onReset(): void;
}

const THEME = {
  "--altcha-max-width": "100%",
  "--altcha-border-radius": "0.5rem",
  "--altcha-color-base": "var(--color-card)",
  "--altcha-color-border": "var(--color-input)",
  "--altcha-color-text": "var(--color-foreground)",
  "--altcha-color-border-focus": "var(--color-primary)",
  "--altcha-color-error-text": "var(--color-destructive)",
};

export function AltchaWidget({ challengeUrl, onSolved, onReset }: AltchaWidgetProps) {
  const host = useRef<HTMLDivElement>(null);
  // Слухач читає останні колбеки, а не ті, що були при монтуванні.
  const handlers = useRef({ onSolved, onReset });
  handlers.current = { onSolved, onReset };

  // Елемент створюємо вручну: React 19 віддає custom element'у пропси властивостями, а віджет має отримати
  // атрибути до підключення до DOM, інакше `auto="onload"` стартує без адреси задачі.
  useEffect(() => {
    const widget = document.createElement("altcha-widget");
    widget.setAttribute("challengeurl", challengeUrl);
    widget.setAttribute("workerurl", workerUrl);
    widget.setAttribute("credentials", "same-origin");
    widget.setAttribute("auto", "onload");
    widget.setAttribute("language", "uk");
    for (const [name, value] of Object.entries(THEME)) {
      widget.style.setProperty(name, value);
    }
    widget.addEventListener("statechange", (event) => {
      const { state, payload } = (event as AltchaStateChangeEvent).detail;
      if (state === "verified" && payload !== undefined) {
        handlers.current.onSolved(payload);
      } else {
        handlers.current.onReset();
      }
    });
    (host.current as HTMLDivElement).append(widget);
    return () => {
      widget.remove();
    };
  }, [challengeUrl]);

  return <div ref={host} />;
}
