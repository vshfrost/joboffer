import { Spinner } from "../components/spinner";

export function LoadingScreen() {
  return (
    <div role="status" className="flex min-h-dvh items-center justify-center gap-2 text-nav text-muted-foreground">
      <Spinner className="size-5" />
      Завантаження…
    </div>
  );
}
