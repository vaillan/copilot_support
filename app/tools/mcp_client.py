from langchain_mcp_adapters.client import MultiServerMCPClient # type: ignore
from app.settings.settings import Settings
settings = Settings()

CLIENT = MultiServerMCPClient(
    {
        # Servidor de Monday.com
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