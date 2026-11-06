import { ExternalLink } from "lucide-react";

import { KIND_LABELS, type JobDocument } from "../../domain/documents";
import { Button } from "../components/button";
import { useDocumentsServices } from "./DocumentsServices";

/** Нативне посилання на PDF саме цієї версії: нова вкладка, та сама сесія. Файлу нема — чесно, без іншої версії. */
export function PdfAccess({ document, compact = false }: { document: JobDocument; compact?: boolean }) {
  const services = useDocumentsServices();
  if (!document.pdfAvailable) {
    return compact ? (
      <span className="text-caption text-status-warning-foreground">PDF недоступний</span>
    ) : (
      <p className="w-fit rounded-lg bg-status-warning px-3 py-2 text-caption text-status-warning-foreground">Файл PDF цієї версії недоступний. Іншу версію не підставляємо.</p>
    );
  }
  const label = `${KIND_LABELS[document.kind]}, версія ${document.version}: відкрити PDF у новій вкладці`;
  return (
    <Button asChild variant={compact ? "ghost" : "default"} size={compact ? "sm" : "default"}>
      <a href={services.pdfUrl(document.id)} target="_blank" rel="noopener noreferrer" aria-label={label}>
        {compact ? "PDF" : "Відкрити PDF"}
        <ExternalLink aria-hidden="true" />
      </a>
    </Button>
  );
}
