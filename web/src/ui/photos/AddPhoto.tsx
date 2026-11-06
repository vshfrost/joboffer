import { useEffect, useId, useRef, useState, type FormEvent, type KeyboardEvent } from "react";

import { cropProblem, FRAME, fileProblem, MAX_LABEL_LENGTH, type CropArea } from "../../domain/photos";
import type { CropSession } from "../../ports/cropper";
import { Button } from "../components/button";
import { Field } from "../components/field";
import { Input } from "../components/input";
import { useCropper, usePhotosServices } from "./PhotosServices";

/** Крок зсуву фото з клавіатури й кнопок (екранні пікселі); із Shift — більший. */
const MOVE_STEP = 10;
const MOVE_STEP_FAST = 50;
const ACCEPT = "image/jpeg,image/png,image/webp";
const ALERT = "rounded-lg bg-status-danger px-3 py-2 text-caption font-medium text-status-danger-foreground";

interface AddPhotoProps {
  /** Кадр збережено: список оновлено. */
  onAdded(): void;
  onCancel(): void;
  /** Повідомлення для живого регіону сторінки («Зберігаємо…»); порожнє — прибрати. */
  announce(message: string): void;
}

/** Додавання: файл → кадрування під нерухомою рамкою → підпис → «Зберегти фото». Чернетка живе, доки не збережено чи скасовано. */
export function AddPhoto({ onAdded, onCancel, announce }: AddPhotoProps) {
  const services = usePhotosServices();
  const cropper = useCropper();
  const [file, setFile] = useState<File | null>(null);
  const [sourceUrl, setSourceUrl] = useState<string | null>(null);
  const [area, setArea] = useState<CropArea | null>(null);
  const [session, setSession] = useState<CropSession | null>(null);
  const [label, setLabel] = useState("");
  const [saving, setSaving] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const imageRef = useRef<HTMLImageElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const hintId = useId();
  // Подвійне надсилання в межах одного кадру: стан ще старий, тож ворота — у ref.
  const inFlight = useRef(false);

  // Форма щойно відкрилась: кнопка «Додати фото» зникла, тож фокус — на вибір файлу.
  useEffect(() => inputRef.current?.focus(), []);

  // Адреса для перегляду обраного файлу живе стільки, скільки файл у чернетці.
  useEffect(() => {
    if (file === null) {
      return;
    }
    const url = URL.createObjectURL(file);
    setSourceUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  // Редактор кадрування над `<img>` цього файлу; змінився файл чи закрили форму — старий знищено.
  useEffect(() => {
    const image = imageRef.current;
    if (sourceUrl === null || image === null) {
      return;
    }
    let cancelled = false;
    let opened: CropSession | null = null;
    setArea(null);
    void cropper.mount(image, setArea).then((mounted) => {
      if (cancelled) {
        mounted.destroy();
        return;
      }
      opened = mounted;
      setSession(mounted);
      stageRef.current?.focus();
    });
    return () => {
      cancelled = true;
      opened?.destroy();
      setSession(null);
    };
  }, [sourceUrl, cropper]);

  function choose(event: FormEvent<HTMLInputElement>) {
    const chosen = event.currentTarget.files?.[0];
    // Поле лишаємо порожнім: той самий файл можна обрати ще раз.
    event.currentTarget.value = "";
    if (chosen === undefined) {
      return;
    }
    const problem = fileProblem(chosen);
    if (problem !== null) {
      setFailure(problem);
      return;
    }
    setFailure(null);
    setFile(chosen);
  }

  function key(event: KeyboardEvent<HTMLElement>) {
    if (session === null) {
      return;
    }
    const step = event.shiftKey ? MOVE_STEP_FAST : MOVE_STEP;
    const moves: Record<string, [number, number]> = {
      ArrowLeft: [-step, 0],
      ArrowRight: [step, 0],
      ArrowUp: [0, -step],
      ArrowDown: [0, step],
    };
    const move = moves[event.key];
    if (move !== undefined) {
      session.move(move[0], move[1]);
    } else if (event.key === "+" || event.key === "=") {
      session.zoom(1);
    } else if (event.key === "-" || event.key === "−") {
      session.zoom(-1);
    } else {
      return;
    }
    event.preventDefault();
  }

  const problem = area === null ? null : cropProblem(area.width);
  const canSave = session !== null && area !== null && problem === null && !saving;

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!canSave || session === null || inFlight.current) {
      return;
    }
    inFlight.current = true;
    setSaving(true);
    setFailure(null);
    announce("Зберігаємо…");
    let frame: Blob;
    try {
      frame = await session.frame();
    } catch {
      announce("");
      setFailure("Не вдалося підготувати кадр. Спробуй ще раз.");
      inFlight.current = false;
      setSaving(false);
      return;
    }
    const outcome = await services.upload(frame, label);
    if (outcome.ok) {
      onAdded();
      return;
    }
    announce("");
    inFlight.current = false;
    setSaving(false);
    setFailure(
      outcome.kind === "rejected"
        ? outcome.message
        : outcome.kind === "unauthorized"
          ? "Сесія завершилась. Увійди знову, щоб зберегти фото."
          : "Не вдалося зберегти фото. Спробуй ще раз.",
    );
  }

  return (
    <form
      aria-label="Нове фото"
      noValidate
      onSubmit={(event) => void save(event)}
      onKeyDown={(event) => event.key === "Escape" && onCancel()}
      className="flex flex-col gap-4 rounded-xl border border-border bg-card p-5 max-sm:p-4"
    >
      <Field label="Файл фото" hint="JPEG, PNG або WebP, до 15 МБ. Зберігається лише обрана область, без EXIF і GPS-метаданих.">
        {(props) => <Input {...props} ref={inputRef} type="file" accept={ACCEPT} onChange={choose} className="h-auto py-2" />}
      </Field>
      {failure === null ? null : (
        <p role="alert" className={ALERT}>
          {failure}
        </p>
      )}
      {sourceUrl === null ? null : (
        <>
          <div
            ref={stageRef}
            role="group"
            aria-label="Кадрування фото"
            tabIndex={0}
            onKeyDown={key}
            className="mx-auto w-full max-w-sm rounded-lg"
          >
            <div data-testid="crop-frame" style={{ aspectRatio: `${FRAME.width} / ${FRAME.height}` }} className="w-full overflow-hidden rounded-lg bg-muted">
              <img ref={imageRef} src={sourceUrl} alt="Фото, з якого обираєш область" className="block max-w-full" />
            </div>
          </div>
          <p className="text-caption text-muted-foreground">
            Рамка — пропорції фото в шапці CV. Тягни фото під рамкою; + і − чи кнопки змінюють масштаб, стрілки зсувають фото (Shift — швидше).
          </p>
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="secondary" aria-label="Збільшити" onClick={() => session?.zoom(1)}>
              +
            </Button>
            <Button type="button" variant="secondary" aria-label="Зменшити" onClick={() => session?.zoom(-1)}>
              −
            </Button>
            <Button type="button" variant="secondary" aria-label="Зсунути фото ліворуч" onClick={() => session?.move(-MOVE_STEP, 0)}>
              ←
            </Button>
            <Button type="button" variant="secondary" aria-label="Зсунути фото праворуч" onClick={() => session?.move(MOVE_STEP, 0)}>
              →
            </Button>
            <Button type="button" variant="secondary" aria-label="Зсунути фото вгору" onClick={() => session?.move(0, -MOVE_STEP)}>
              ↑
            </Button>
            <Button type="button" variant="secondary" aria-label="Зсунути фото вниз" onClick={() => session?.move(0, MOVE_STEP)}>
              ↓
            </Button>
          </div>
          <Field label="Підпис фото">
            {(props) => <Input {...props} value={label} maxLength={MAX_LABEL_LENGTH} onChange={(event) => setLabel(event.target.value)} />}
          </Field>
        </>
      )}
      {problem === null ? null : (
        <p id={hintId} className="rounded-lg bg-status-warning px-3 py-2 text-caption text-status-warning-foreground">
          {problem}
        </p>
      )}
      <div className="flex flex-wrap items-center gap-3 border-t border-border pt-4">
        <Button type="button" variant="secondary" onClick={onCancel}>
          Скасувати
        </Button>
        <Button type="submit" disabled={!canSave} aria-describedby={problem === null ? undefined : hintId}>
          Зберегти фото
        </Button>
      </div>
    </form>
  );
}

