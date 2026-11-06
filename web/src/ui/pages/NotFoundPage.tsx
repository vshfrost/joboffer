import { Link } from "react-router";

import { Button } from "../components/button";
import { usePageTitle } from "../lib/usePageTitle";
import { HOME } from "../navigation";
import { PageHeading } from "./PageHeading";

export function NotFoundPage() {
  usePageTitle("Не знайдено");
  return (
    <>
      <PageHeading title="Сторінку не знайдено" subtitle="Такої адреси нема або її вже прибрано." />
      <Button asChild>
        <Link to={HOME}>До вакансій</Link>
      </Button>
    </>
  );
}
