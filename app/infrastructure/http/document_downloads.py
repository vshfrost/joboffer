"""HTTP одноразових посилань на PDF: `GET /documents/download/{token}` — БЕЗ сесії.

Доступом тут служить сам токен: його видає MCP-тул `get_document_download` власнику документа, він
живе 10 хвилин і спрацьовує один раз. Невідомий, використаний чи прострочений токен, а також
відсутній файл PDF — однаково 404, відповідь не розкриває, що з них сталося.
"""

from fastapi import APIRouter, Response

from application.documents.downloads import DocumentDownloads


def document_downloads_router(downloads: DocumentDownloads) -> APIRouter:
    router = APIRouter(tags=["documents"])

    @router.get("/documents/download/{token}", response_class=Response)
    async def download(token: str) -> Response:
        found = await downloads.redeem(token)
        return Response(
            found.data,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{found.file_name}"',
                "Cache-Control": "no-store",
                # Токен і є доступом (без cookies), тож сторінка в браузері користувача може
                # забрати PDF через fetch з іншого origin.
                "Access-Control-Allow-Origin": "*",
            },
        )

    return router
