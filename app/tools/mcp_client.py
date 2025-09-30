from langchain_mcp_adapters.client import MultiServerMCPClient # type: ignore
from ..settings.settings import Settings
settings = Settings()

CLIENT = MultiServerMCPClient(
    {
        # Servidor de Monday.com añadido aquí
        "monday": {
            "command": "npx",
            "args": [
                "@mondaydotcomorg/monday-api-mcp",
                "-t",
                settings.MONDAY_API_KEY
            ],
            "transport": "stdio",
        }
    }
)