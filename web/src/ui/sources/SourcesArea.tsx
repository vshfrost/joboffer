import { Route, Routes } from "react-router";

import { NotFoundPage } from "../pages/NotFoundPage";
import { AddSourcePage } from "./AddSourcePage";
import { FilteredPage } from "./FilteredPage";
import { SourcesListPage } from "./SourcesListPage";

/** `/sources`: реєстр джерел, форма `/sources/new` і перегляд `/sources/filtered`. */
export function SourcesArea() {
  return (
    <Routes>
      <Route index element={<SourcesListPage />} />
      <Route path="new" element={<AddSourcePage />} />
      <Route path="filtered" element={<FilteredPage />} />
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
