from ..utils.extract_monday_data import ExtractData
from langchain_core.tools import tool

extractData = ExtractData()

@tool
def similarity_search(board_name: str, query: str):
    """Utiliza esta herramienta para buscar ítems por similitud DENTRO de un tablero específico."""
    initial_gql_query = """
        query($board_id: [ID!], $text_search: CompareValue!) {
            boards(ids:$board_id) {
                name
                state
                permissions
                items_page(limit: 10, query_params: {rules: [
                            {column_id: "name", compare_value: $text_search, operator:contains_text}
                        ]
                }) {
                    cursor
                    items {
                        id
                        name
                        column_values {
                            id
                            value
                            text
                            column {
                                id
                                title
                                archived
                            }
                        }
                        subitems {
                            id
                            name
                            column_values {
                                id
                                value
                                text
                                column {
                                    id
                                    title
                                    archived
                                }
                            }
                            updates {
                                body
                                id
                                created_at
                                creator {
                                    name
                                    id
                                }
                            }
                        }
                        updates {
                            body
                            id
                            created_at
                            creator {
                                name
                                id
                            }
                        }
                    }
                }
                views {
                    id
                    type
                    name
                }      
            }
        }
    """
    
    next_page_gql_query = """
        query($board_id: [ID!], $cursor: String!) {
            boards(ids:$board_id) {
                items_page(limit: 50, cursor: $cursor) {
                    cursor
                    items {
                        id
                        name
                        column_values {
                            id
                            value
                            text
                            column {
                                id
                                title
                                archived
                            }
                        }
                        subitems {
                            id
                            name
                            column_values {
                                id
                                value
                                text
                                column {
                                    id
                                    title
                                    archived
                                }
                            }
                            updates {
                                body
                                id
                                created_at
                                creator {
                                    name
                                    id
                                }
                            }
                        }
                        updates {
                            body
                            id
                            created_at
                            creator {
                                name
                                id
                            }
                        }
                    }
                }
            }
        }
    """

    all_boards = extractData._extract_all_boards()
    boarsd = extractData._get_board_id(boards=all_boards, board_name=board_name)
    print('search_similar_items_in_board: ', f"Board: {board_name}", f"Query: {query}")
    # boarsd = next((b for b in all_boards if b['name'].lower() == board_name.lower()), None)
    if not boarsd:
        board_names = ", ".join([f"'{b['name']}'" for b in all_boards])
        return f"Error: No se encontraron tableros similares a '{board_name}'. Los tableros disponibles son: {board_names}."

    data = extractData.pre_processor_cleaner_data(datos=extractData._process_board_items(
            board_ids=boarsd,
            text_search=query,
            initial_gql_query=initial_gql_query,
            next_page_gql_query=next_page_gql_query
        ))
    return data