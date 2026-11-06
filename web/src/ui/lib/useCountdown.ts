import { useCallback, useEffect, useState } from "react";

const TICK_MS = 1000;

/** Зворотний відлік у секундах до кінця; `remaining === 0`, коли відліку нема або він закінчився. */
export function useCountdown() {
  const [deadline, setDeadline] = useState<number | null>(null);
  const [remaining, setRemaining] = useState(0);

  useEffect(() => {
    if (deadline === null) {
      return;
    }
    const tick = () => {
      const left = Math.ceil((deadline - Date.now()) / TICK_MS);
      if (left <= 0) {
        setRemaining(0);
        setDeadline(null);
      } else {
        setRemaining(left);
      }
    };
    tick();
    const timer = setInterval(tick, TICK_MS);
    return () => {
      clearInterval(timer);
    };
  }, [deadline]);

  const start = useCallback((seconds: number) => {
    setDeadline(Date.now() + seconds * TICK_MS);
  }, []);

  return { remaining, start };
}
