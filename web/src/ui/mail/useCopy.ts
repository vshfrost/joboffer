import { useCallback, useState } from "react";

/** Копіювання в буфер обміну: `message` — результат для читача екрана; без доступу до буфера — підказка. */
export function useCopy(): { message: string; copy(text: string, done: string, failed: string): Promise<void> } {
  const [message, setMessage] = useState("");
  const copy = useCallback(async (text: string, done: string, failed: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setMessage(done);
    } catch {
      setMessage(failed);
    }
  }, []);
  return { message, copy };
}
