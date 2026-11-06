import { useState } from "react";

import { CODE_LENGTH } from "../../domain/signup";
import { Field } from "../components/field";
import { Input } from "../components/input";

export interface CodeFieldProps {
  /** Повідомлення під полем (невірний код тощо). */
  error?: string | undefined;
  disabled?: boolean | undefined;
  /** Викликається, щойно введено всі цифри коду. */
  onComplete(code: string): void;
}

/** Одне поле для коду з листа: браузер підставляє код сам, вставка очищується до цифр, повний код відправляється. */
export function CodeField({ error, disabled, onComplete }: CodeFieldProps) {
  const [value, setValue] = useState("");

  function change(raw: string) {
    const digits = raw.replace(/\D/g, "").slice(0, CODE_LENGTH);
    setValue(digits);
    if (digits.length === CODE_LENGTH) {
      onComplete(digits);
    }
  }

  return (
    <Field label="Код з листа" error={error}>
      {(control) => (
        <Input
          {...control}
          type="text"
          inputMode="numeric"
          autoComplete="one-time-code"
          // Вставка «123 456» довша за шість символів: обмеження робить change(), а не браузер.
          maxLength={CODE_LENGTH * 2}
          autoFocus
          disabled={disabled}
          value={value}
          className="text-center text-xl tracking-[0.4em]"
          onChange={(event) => {
            change(event.target.value);
          }}
        />
      )}
    </Field>
  );
}
