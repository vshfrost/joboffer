import { useCallback, useEffect, useRef, useState } from "react";

export type Loaded<T, P extends string> = { ok: true; value: T } | { ok: false; kind: P };
export type LoadState<T, P extends string> = { status: "loading" } | { status: "error"; problem: P } | { status: "ready"; data: T };

/**
 * Дані сторінки: завантажуються при монтуванні (і коли змінився стабільний `load`), `reload` показує скелетон і вантажить знову,
 * `set` підміняє вже завантажене після дії. Застаріла відповідь відкидається.
 */
export function useLoaded<T, P extends string>(load: () => Promise<Loaded<T, P>>) {
  const [state, setState] = useState<LoadState<T, P>>({ status: "loading" });
  // Номер останнього запиту: відповідь на попередній уже нікому не потрібна.
  const latest = useRef(0);

  const run = useCallback(async () => {
    latest.current += 1;
    const ticket = latest.current;
    setState({ status: "loading" });
    const outcome = await load();
    if (ticket === latest.current) {
      setState(outcome.ok ? { status: "ready", data: outcome.value } : { status: "error", problem: outcome.kind });
    }
  }, [load]);

  useEffect(() => {
    void run();
    return () => {
      latest.current += 1;
    };
  }, [run]);

  const reload = useCallback(() => void run(), [run]);
  const set = useCallback((data: T) => setState({ status: "ready", data }), []);
  return { state, reload, set };
}
