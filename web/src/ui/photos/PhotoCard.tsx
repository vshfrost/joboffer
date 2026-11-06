import { addedText, photoName, usedText, type Photo } from "../../domain/photos";
import { Badge } from "../components/badge";
import { Button } from "../components/button";
import { usePhotosServices } from "./PhotosServices";

/** Фото в галереї: мініатюра, підпис, коли додано й коли востаннє в CV, позначка пропозиції, видалення. */
export function PhotoCard({ photo, suggested, onDelete }: { photo: Photo; suggested: boolean; onDelete(photo: Photo): void }) {
  const services = usePhotosServices();
  const name = photoName(photo);
  return (
    <li className="flex min-w-0 flex-wrap items-start gap-4 rounded-xl border border-border bg-card p-4">
      <img
        src={services.imageUrl(photo.id)}
        alt={photo.label === "" ? name : `Фото «${photo.label}»`}
        width={90}
        height={101}
        loading="lazy"
        className="h-[6.3rem] w-[5.6rem] shrink-0 rounded-lg bg-muted object-cover"
      />
      <div className="flex min-w-0 flex-1 basis-40 flex-col gap-1">
        <p className="text-nav font-medium [overflow-wrap:anywhere]">{name}</p>
        <p className="text-caption text-muted-foreground">{addedText(photo)}</p>
        <p className="text-caption text-muted-foreground">{usedText(photo)}</p>
        {suggested ? (
          <Badge tone="info" className="whitespace-normal">
            Пропонується для CV
          </Badge>
        ) : null}
      </div>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="text-destructive"
        aria-label={`Видалити фото «${name}»`}
        onClick={() => onDelete(photo)}
      >
        Видалити
      </Button>
    </li>
  );
}
