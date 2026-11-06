/** Сесія клієнта: хто увійшов і куди вести після входу. */

export interface User {
  id: string;
  email: string;
  displayName: string;
}

/** Які способи входу ввімкнено на сервері. */
export interface AuthProviders {
  google: boolean;
}

export interface Session {
  user: User;
}

const HOME_PATH = "/";
const LOGIN_PATH = "/login";
const SECONDS_PER_MINUTE = 60;

function hasControlOrBackslash(value: string): boolean {
  return [...value].some((char) => char.charCodeAt(0) <= 0x1f || char === "\u007f" || char === "\\");
}

/**
 * Внутрішній шлях після входу з параметра `next`; будь-що інше веде на головну.
 * Браузер прибирає з адреси табуляції й переноси та читає `\` як `/`, тож `/\t/evil` — це `//evil`:
 * такі рядки відкидаються цілком. Сам екран входу не може бути метою — вхід зациклився б.
 */
export function safeNextPath(raw: string | null | undefined): string {
  if (raw == null || !raw.startsWith("/") || raw.startsWith("//") || hasControlOrBackslash(raw)) {
    return HOME_PATH;
  }
  const { pathname } = new URL(raw, "http://internal.invalid");
  if (pathname === LOGIN_PATH || pathname.startsWith(`${LOGIN_PATH}/`)) {
    return HOME_PATH;
  }
  return raw;
}

/** Скільки хвилин показати для «спробуй за ~N хв»: округлення вгору, щонайменше 1. */
export function retryMinutes(seconds: number): number {
  return Math.max(1, Math.ceil(seconds / SECONDS_PER_MINUTE));
}
