from typing import Any, Optional, Union
from monday_sdk import MondayClient
import requests
from langchain_core.tools import tool # type: ignore
from ..settings.settings import Settings

settings = Settings()

mondayClient = MondayClient(token=settings.MONDAY_API_KEY)

def _extract_all_boards() -> list[dict]:
    gql_query = """
    query {
        boards(limit: 500) {
            id
            name
        }
    }
    """
    headers = {"Authorization" : settings.MONDAY_API_KEY, "API-Version" : "2023-04"}
    data = {'query' : gql_query}
    response = requests.post(url=settings.MONDAY_API_URL, json=data, headers=headers)
    boards = []
    if 'data' in response.json():
        boards = response.json()['data']['boards']
    return boards

@tool
def find_boards_like_name(board_name: str) -> list[dict]:
    """
    Encuentra y devuelve tableros de monday.com por nombre como {board_name}.
    Utiliza esta herramienta cuando necesites encontrar un tableros como {board_name}.
    """
    boards = _extract_all_boards()
    extracted_boards = []
    search_terms = board_name.lower().split()
    for board in boards:
        board_name_lower = board['name'].lower()
        if all(term in board_name_lower for term in search_terms):
            extracted_boards.append(board)
    return extracted_boards

@tool
def fetch_all_items_by_board_id(board_id: Union[int, str], query_params: Optional[Any] = None):
    """
    Fetches all items from a board by board ID, includes paginating
    todo: add support for multiple board IDs
    """
    return mondayClient.boards.fetch_all_items_by_board_id(board_id=board_id, query_params=query_params)

@tool
def fetch_item_by_board_id_by_update_date(board_id: Union[int, str], updated_after: str, updated_before: str,):
    """
    Fetches items from a board by board ID by update date, useful for incremental fetching
    todo: add type hints for updated_after and updated_before and validate them
    """
    return mondayClient.boards.fetch_item_by_board_id_by_update_date(board_id=board_id, updated_after=updated_after, updated_before=updated_before)

@tool
def fetch_columns_by_board_id(board_id: Union[int, str]):
    """Fetch columns from a board by the board's id."""
    return mondayClient.boards.fetch_columns_by_board_id(board_id=board_id)

@tool
def fetch_items_by_column_value(board_id: Union[str, int], column_id: str, value: str, limit: int | None = None, cursor: str | None = None):
    """Fetch items from a board by a specific column value."""
    return mondayClient.items.fetch_items_by_column_value(board_id=board_id, column_id=column_id, value=value, limit=limit, cursor=cursor) # type: ignore
