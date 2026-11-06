import { useCallback, useRef, useState } from "react";
import { useLocation } from "react-router";

import type { Photo } from "../../domain/photos";
import { Button } from "../components/button";
import { Skeleton } from "../components/skeleton";
import { EditorLayout } from "../profile/EditorLayout";
import { AddPhoto } from "./AddPhoto";
import { DeletePhotoDialog } from "./DeletePhotoDialog";
import { PhotoCard } from "./PhotoCard";
import { usePhotos } from "./PhotosProvider";

const ALERT = "flex flex-wrap items-center gap-3 rounded-xl border border-border bg-status-danger p-4 text-status-danger-foreground";

/** `/profile/photos`: галерея, додавання з кадруванням, видалення. Саму гру з кадром робить `AddPhoto`. */
export function PhotosEditor() {
  const { state, retry, refresh } = usePhotos();
  const [adding, setAdding] = useState(false);
  const [target, setTarget] = useState<Photo | null>(null);
  const [result, setResult] = useState("");
  const addRef = useRef<HTMLButtonElement | null>(null);
  // Розділ відкрито карткою огляду або форму закрито: фокус на «Додати фото», щойно кнопка зʼявиться.
  const wantFocus = useRef((useLocation().state as { focus?: boolean } | null)?.focus === true);
  const bindAdd = useCallback((node: HTMLButtonElement | null) => {
    addRef.current = node;
    if (node !== null && wantFocus.current) {
      wantFocus.current = false;
      node.focus();
    }
  }, []);

  function closeForm() {
    wantFocus.current = true;
    setAdding(false);
  }

  async function added() {
    await refresh();
    setResult("Фото додано.");
    closeForm();
  }

  return (
    <EditorLayout current="photos">
      <div className="flex flex-col gap-5">
        <header className="border-b border-border pb-4">
          <h2 className="text-xl font-semibold">Фото для CV</h2>
          <p className="mt-1 text-caption text-muted-foreground">Кілька фото для різних подач. CV можна створювати й без фото.</p>
        </header>
        <p role="status" aria-label="Результат" className="text-caption font-medium text-status-success-foreground empty:hidden">
          {result}
        </p>
        {adding ? (
          <AddPhoto
            onAdded={() => void added()}
            onCancel={() => {
              setResult("");
              closeForm();
            }}
            announce={setResult}
          />
        ) : (
          <div>
            <Button
              ref={bindAdd}
              type="button"
              onClick={() => {
                setResult("");
                setAdding(true);
              }}
            >
              Додати фото
            </Button>
          </div>
        )}
        {state.status === "idle" || state.status === "loading" ? (
          <div role="status" aria-label="Завантажуємо фото…" className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Skeleton className="h-28" />
            <Skeleton className="h-28" />
          </div>
        ) : state.status === "error" ? (
          <div role="alert" className={ALERT}>
            <p className="text-nav font-medium">
              {state.problem === "unauthorized" ? "Сесія завершилась. Увійди знову, щоб побачити фото." : "Не вдалося завантажити фото."}
            </p>
            {state.problem === "unauthorized" ? null : (
              <Button type="button" variant="secondary" onClick={retry}>
                Спробувати ще раз
              </Button>
            )}
          </div>
        ) : state.library.photos.length === 0 ? (
          <div className="flex flex-col gap-1">
            <h3 className="text-section font-semibold">Фото ще не додано</h3>
            <p className="text-caption text-muted-foreground">CV можна створювати й без фото.</p>
          </div>
        ) : (
          <ul aria-label="Збережені фото" className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {state.library.photos.map((photo) => (
              <PhotoCard key={photo.id} photo={photo} suggested={photo.id === state.library.suggestedId} onDelete={setTarget} />
            ))}
          </ul>
        )}
        <details className="rounded-lg border border-border p-4">
          <summary className="cursor-pointer text-nav font-medium">Як використовується фото</summary>
          <p className="mt-2 text-caption text-muted-foreground">
            Перед створенням CV Claude пропонує фото або варіант без нього. Зберігається лише обрана область, без EXIF і GPS. Дата останнього
            використання допомагає знайти актуальне фото.
          </p>
        </details>
      </div>
      <DeletePhotoDialog
        target={target}
        onClose={() => setTarget(null)}
        onDeleted={() => {
          setTarget(null);
          setResult("Фото видалено.");
          void refresh();
        }}
        focusAfterDelete={() => addRef.current?.focus()}
      />
    </EditorLayout>
  );
}
