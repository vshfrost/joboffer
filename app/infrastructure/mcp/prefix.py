"""Прибирає префікс `/mcp` зі шляху: OAuth-маршрути агента лежать у корені процесу.

Edge веде `/mcp*` на агента без зміни шляху, а метадані оголошують endpoint-и як
`<public_url>/authorize` тощо, тож вони мають працювати з префіксом.
Сам MCP-ендпоінт — це рівно `prefix`, його не чіпаємо.
"""

from starlette.types import ASGIApp, Receive, Scope, Send


class StripPrefix:
    def __init__(self, app: ASGIApp, prefix: str) -> None:
        self.app = app
        self.prefix = prefix

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["path"].startswith(f"{self.prefix}/"):
            stripped = scope["path"].removeprefix(self.prefix)
            scope = {**scope, "path": stripped, "raw_path": stripped.encode()}
        await self.app(scope, receive, send)
