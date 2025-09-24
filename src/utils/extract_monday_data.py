from typing import Any
from .text_cleaner import AdvancedFileCleaner
from src.settings.settings import Settings
import requests
import json
from bs4 import BeautifulSoup, Comment # type: ignore # Importar BeautifulSoup para limpiar HTML
import os
import re # Para expresiones regulares

class ExtractData(Settings):

    def _clean_html(self, html_content):
        """
        Limpia contenido HTML, eliminando etiquetas y extrayendo texto de manera más efectiva.

        Mejoras:
        - Elimina una gama más amplia de etiquetas no deseadas (scripts, estilos, navegación, etc.).
        - Maneja explícitamente las etiquetas <br> para asegurar saltos de línea.
        - Mejora el manejo de enlaces, eliminando aquellos sin texto descriptivo.
        - Elimina comentarios HTML.
        - Normaliza los espacios en blanco y los saltos de línea para un texto más limpio y consistente.
        """
        if not html_content:
            return ""

        soup = BeautifulSoup(html_content, 'html.parser')

        tags_to_remove = [
            'script', 'style', 'header', 'footer', 'nav', 'form', 'iframe', 'svg', 'img',
            'meta', 'link', 'noscript', 'button', 'input', 'select', 'textarea',
            'aside', 'figcaption', 'figure', 'canvas', 'audio', 'video', 'embed', 'object',
            'param', 'source', 'track', 'map', 'area', 'applet', 'base', 'bdo', 'datalist',
            'fieldset', 'keygen', 'label', 'legend', 'meter', 'optgroup', 'option', 'output',
            'progress', 'command', 'details', 'dialog', 'menu', 'menuitem', 'summary',
            'rp', 'rt', 'ruby', 'time', 'wbr'
        ]
        for tag_name in tags_to_remove:
            for tag in soup.find_all(tag_name):
                tag.decompose()

        for br in soup.find_all('br'):
            br.replace_with('\n')

        for a in soup.find_all('a'):
            link_text = a.get_text(strip=True)
            if link_text:
                a.replace_with(link_text)
            else:
                a.decompose()

        for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()

        text = soup.get_text(separator='\n').strip()

        cleaned_lines = []
        for line in text.splitlines():
            # Reemplazar múltiples espacios/tabulaciones por uno solo y eliminar espacios al inicio/final de la línea.
            line = re.sub(r'[ \t]+', ' ', line).strip()
            if line: # Solo añadir líneas que no estén vacías
                cleaned_lines.append(line)

        text = os.linesep.join(cleaned_lines)
        text = re.sub(r'\n+', '\n', text)

        return text
    
    def _extract_all_boards(self):
        gql_query = """
        query {
            boards(limit: 500) {
                id
                name
            }
        }
        """
        headers = {"Authorization" : self.MONDAY_API_KEY, "API-Version" : "2023-04"}
        data = {'query' : gql_query}
        response = requests.post(url=self.MONDAY_API_URL, json=data, headers=headers)
        boards = None
        if 'data' in response.json():
            boards = response.json()['data']['boards']
        return boards
    
    def _get_board_id(self, boards: list, board_name: str):
        for board in boards:
            if board['name'].lower() == board_name.lower():
                return board['id']
        return None

    def _get_file_content_as_text(self, public_url: str, file_name: str) -> str:
        """
        Descarga un archivo desde su URL pública e intenta extraer su contenido como texto.
        Soporta PDF, XML, imágenes (usando OCR), XLSX, DOCX, TXT.
        Devuelve una cadena vacía si no se puede extraer contenido significativo.
        Filtra sellos digitales y cadenas de certificación.
        """
        if not public_url:
            return ""

        try:
            cleaner = AdvancedFileCleaner()
            return cleaner.get_file_content_as_text(public_url=public_url, file_name=file_name)
        except requests.exceptions.RequestException as e:
            print(f"Error al descargar o acceder al archivo {public_url}: {e}")
            return "" # Retornar vacío
        except Exception as e:
            print(f"Error inesperado al procesar el archivo {file_name}: {e}")
            return "" # Retornar vacío
        
    def extract_board_data(self, board_name: str, text_search: str):
        boards = self._extract_all_boards()
        
        initial_gql_query = """
        query($board_id: [ID!], $text_search: CompareValue!) {
            boards(ids:$board_id) {
                name
                state
                permissions
                items_page(limit: 10, query_params: {rules: [
                            {column_id: "name", compare_value: $text_search, operator:contains_text}
                            {column_id: "estatius", compare_value: [11]}
                        ]operator:and
                }) {
                    cursor
                    items {
                        id
                        name
                        assets {
                            id
                            name
                            public_url
                        }
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
                            assets {
                                name
                                public_url
                            }
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
                                assets {
                                    id
                                    name
                                    public_url
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
                            assets {
                                id
                                name
                                public_url
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
                        assets {
                            id
                            name
                            public_url
                        }
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
                            assets {
                                name
                                public_url
                            }
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
                                assets {
                                    id
                                    name
                                    public_url
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
                            assets {
                                id
                                name
                                public_url
                            }
                        }
                    }
                }
            }
        }
        """

        if boards is not None:
            board_id = self._get_board_id(boards=boards, board_name=board_name)
            if board_id is not None:
                return self.pre_processor_cleaner_data(self._process_board_items(
                    board_id=board_id,
                    text_search=text_search,
                    initial_gql_query=initial_gql_query,
                    next_page_gql_query=next_page_gql_query
                ))
        return None
    
    def clean_value(self, valor):
        """
        Limpia un valor individual si es una cadena de texto.
        """
        if isinstance(valor, str):
            # Eliminar caracteres no deseados
            valor_limpio = valor.replace('\ufeff', '').replace('\xa0', ' ')
            
            # Eliminar el texto extraído de archivos adjuntos
            if '--- ARCHIVOS ADJUNTOS (TEXTO EXTRAÍDO) ---' in valor_limpio:
                valor_limpio = valor_limpio.split('--- ARCHIVOS ADJUNTOS (TEXTO EXTRAÍDO) ---')[0]
                
            # Quitar espacios en blanco al inicio y al final
            return valor_limpio.strip()
        return valor
    
    def pre_processor_cleaner_data(self, datos):
        """
        Recorre la lista de diccionarios y limpia cada uno de sus valores.
        Mantiene la estructura original de los datos.
        """
        datos_limpios = []
        for item in datos:
            item_limpio = {}
            for clave, valor in item.items():
                if isinstance(valor, list):
                    # Si el valor es una lista (como 'item_updates_details'),
                    # se itera sobre sus elementos para limpiarlos también.
                    lista_limpia = []
                    for sub_item in valor:
                        if isinstance(sub_item, dict):
                            sub_item_limpio = {k: self.clean_value(v) for k, v in sub_item.items()}
                            lista_limpia.append(sub_item_limpio)
                        else:
                            lista_limpia.append(self.clean_value(sub_item))
                    item_limpio[clave] = lista_limpia
                else:
                    item_limpio[clave] = self.clean_value(valor)
            datos_limpios.append(item_limpio)
        return datos_limpios

    def _process_board_items(self, board_id: str, text_search: Any, initial_gql_query: str, next_page_gql_query: str):
        all_items = []
        current_cursor = None
        current_board_name = ""
        
        headers = {"Authorization" : self.MONDAY_API_KEY, "API-Version" : "2023-04"}

        # --- Primera consulta ---
        variables = {"board_id": [board_id]}
        if text_search is not None:
            variables['text_search']=text_search
        data = {'query' : initial_gql_query, "variables": variables}
        response = requests.post(url=self.MONDAY_API_URL, json=data, headers=headers)
        response_data = response.json()
        # print(response_data)

        if 'data' in response_data and response_data['data']['boards']:
            board_info = response_data['data']['boards'][0]
            current_board_name = board_info['name']
            
            if board_info['items_page']['items']:
                all_items.extend(board_info['items_page']['items'])
            current_cursor = board_info['items_page']['cursor']
        
        # --- Consultas de paginación ---
        while current_cursor:
            variables = {"board_id": [board_id], "cursor": current_cursor}
            data = {'query' : next_page_gql_query, "variables": variables}
            response = requests.post(url=self.MONDAY_API_URL, json=data, headers=headers)
            response_data = response.json()
            
            if 'data' in response_data and response_data['data']['boards']:
                next_items_page = response_data['data']['boards'][0]['items_page']
                if next_items_page['items']:
                    all_items.extend(next_items_page['items'])
                current_cursor = next_items_page['cursor'] # Actualiza el cursor para la siguiente iteración
            else:
                current_cursor = None # No hay más datos o error, termina el bucle

        # --- Transformación de los datos completos ---
        transformed_items = []
        for item in all_items:
            transformed_item = {
                "board_name": current_board_name,
                "item_id": item['id'],
                "item_name": item['name']
            }

            # Procesar column_values
            for col_value in item['column_values']:
                col_title = col_value['column']['title']
                cleaned_col_key = col_title.lower().replace(' ', '_').replace('-', '_')
                
                value_to_use = col_value['text']
                
                if not value_to_use and col_value['value']:
                    try:
                        parsed_value = json.loads(col_value['value'])
                        if isinstance(parsed_value, dict):
                            if not parsed_value: # Si es un diccionario vacío {}
                                value_to_use = ""
                            elif 'date' in parsed_value:
                                value_to_use = parsed_value['date']
                            elif 'personsAndTeams' in parsed_value:
                                value_to_use = col_value['text'] 
                                if not value_to_use:
                                    value_to_use = "" 
                            elif 'item_id' in parsed_value:
                                value_to_use = parsed_value['item_id']
                            elif 'index' in parsed_value and 'text' in col_value:
                                value_to_use = col_value['text']
                            else:
                                value_to_use = str(parsed_value)
                        elif isinstance(parsed_value, list) and not parsed_value: # Si es una lista vacía []
                            value_to_use = ""
                        elif isinstance(parsed_value, str):
                            value_to_use = parsed_value.strip('"')
                        else:
                            value_to_use = str(parsed_value)
                    except json.JSONDecodeError:
                        value_to_use = col_value['value'].strip('"')
                
                if value_to_use is not None and str(value_to_use).strip() != "":
                    transformed_item[cleaned_col_key] = value_to_use
            
            item_updates_details = []
            full_description_parts = []
            item_attached_files_summary_text = []

            # Procesar assets adjuntos directamente al item principal
            item_assets_details = []
            if item.get('assets'):
                for asset in item['assets']:
                    file_text = self._get_file_content_as_text(asset.get('public_url'), asset.get('name'))
                    if file_text.strip():
                        item_attached_files_summary_text.append(f"--- Contenido de archivo '{asset.get('name')}' (Item principal):\n{file_text}\n---")
                    
                    item_assets_details.append({
                        "asset_id": asset.get('id'),
                        "extracted_text_content": file_text
                    })
            transformed_item['item_assets'] = item_assets_details

            # Procesar actualizaciones del item principal
            if item.get('updates'):
                for update in item['updates']:
                    cleaned_body = self._clean_html(update['body'])
                    creator_name = update['creator']['name'] if update.get('creator') and update['creator'].get('name') else 'Desconocido'
                    created_at_date = update['created_at'].split('T')[0] if update.get('created_at') else ''
                    
                    if cleaned_body.strip():
                        full_description_parts.append(f"[{created_at_date} - {creator_name}]:\n{cleaned_body}")

                    update_assets_details = []
                    if update.get('assets'):
                        for asset in update['assets']:
                            file_text = self._get_file_content_as_text(asset.get('public_url'), asset.get('name'))
                            if file_text.strip():
                                item_attached_files_summary_text.append(f"--- Contenido de archivo adjunto '{asset.get('name')}' (Actualización {update['id']}):\n{file_text}\n---")
                            
                            update_assets_details.append({
                                "asset_id": asset.get('id'),
                                "extracted_text_content": file_text
                            })

                    if cleaned_body.strip() or update_assets_details:
                        item_updates_details.append({
                            "update_id": update['id'],
                            "created_at": created_at_date,
                            "creator_name": creator_name,
                            "body_cleaned": cleaned_body,
                            "assets": update_assets_details
                        })
            
            # Procesar subitems
            subitems_details = []
            if item.get('subitems'):
                for subitem in item['subitems']:
                    subitem_transformed = {
                        "subitem_id": subitem['id'],
                        "subitem_name": subitem['name']
                    }

                    subitem_column_values = {}
                    for col_value in subitem['column_values']:
                        col_title = col_value['column']['title']
                        cleaned_col_key = col_title.lower().replace(' ', '_').replace('-', '_')
                        value_to_use = col_value['text'] if col_value['text'] is not None else ""
                        if str(value_to_use).strip() != "":
                            subitem_column_values[cleaned_col_key] = value_to_use
                    if subitem_column_values:
                        subitem_transformed['column_values'] = subitem_column_values

                    subitem_assets_details = []
                    if subitem.get('assets'):
                        for asset in subitem['assets']:
                            file_text = self._get_file_content_as_text(asset.get('public_url'), asset.get('name'))
                            if file_text.strip():
                                item_attached_files_summary_text.append(f"--- Contenido de archivo '{asset.get('name')}' (Subitem '{subitem['name']}'):\n{file_text}\n---")
                            
                            subitem_assets_details.append({
                                # "asset_id": asset.get('id'), # Monday.com subitem assets don't always have ID
                                "extracted_text_content": file_text
                            })
                    if subitem_assets_details:
                        subitem_transformed['assets'] = subitem_assets_details

                    subitem_updates_details = []
                    if subitem.get('updates'):
                        for update in subitem['updates']:
                            cleaned_body = self._clean_html(update['body'])
                            creator_name = update['creator']['name'] if update.get('creator') and update['creator'].get('name') else 'Desconocido'
                            created_at_date = update['created_at'].split('T')[0] if update.get('created_at') else ''
                            
                            if cleaned_body.strip():
                                full_description_parts.append(f"[{created_at_date} - {creator_name} - Subitem {subitem['name']}]:\n{cleaned_body}")

                            subitem_update_assets_details = []
                            if update.get('assets'):
                                for asset in update['assets']:
                                    file_text = self._get_file_content_as_text(asset.get('public_url'), asset.get('name'))
                                    if file_text.strip():
                                        item_attached_files_summary_text.append(f"--- Contenido de archivo adjunto '{asset.get('name')}' (Actualización de Subitem '{subitem['name']}'):\n{file_text}\n---")
                                    
                                    subitem_update_assets_details.append({
                                        "asset_id": asset.get('id'),
                                        "extracted_text_content": file_text
                                    })
                            if cleaned_body.strip() or subitem_update_assets_details:
                                subitem_updates_details.append({
                                    "update_id": update['id'],
                                    "created_at": created_at_date,
                                    "creator_name": creator_name,
                                    "body_cleaned": cleaned_body,
                                    "assets": subitem_update_assets_details
                                })
                    if subitem_updates_details:
                        subitem_transformed['updates'] = subitem_updates_details
                    
                    if subitem_transformed['column_values'] or subitem_transformed['assets'] or subitem_transformed['updates']:
                        subitems_details.append(subitem_transformed)
            transformed_item['subitems_details'] = subitems_details


            # Añadir el texto resumido de todos los archivos adjuntos a la descripción completa
            if item_attached_files_summary_text:
                full_description_parts.append("\n\n--- ARCHIVOS ADJUNTOS (TEXTO EXTRAÍDO) ---\\n" + "\n\n".join(item_attached_files_summary_text))

            transformed_item['descripcion_completa'] = "\n\n".join([p for p in full_description_parts if p.strip()]).strip()
            if not transformed_item['descripcion_completa']:
                transformed_item.pop('descripcion_completa', None)

            if item_updates_details:
                transformed_item['item_updates_details'] = item_updates_details
            
            if item_attached_files_summary_text:
                transformed_item['all_attached_files_extracted_text_summary'] = "\n\n".join([t for t in item_attached_files_summary_text if t.strip()])
                if not transformed_item['all_attached_files_extracted_text_summary']:
                    transformed_item.pop('all_attached_files_extracted_text_summary', None)


            transformed_items.append(transformed_item)
                
        return transformed_items

    def extract_board_data_by_timeline(self, board_name: str, timeline: Any | None):
        boards = self._extract_all_boards()
        initial_gql_query = """
        query($board_id: [ID!], $text_search: CompareValue!) {
            boards(ids:$board_id) {
                name
                state
                permissions
                items_page(limit: 10, query_params: {
                            rules: [
                                {column_id: "fecha", compare_value: $text_search, operator: between}
                                {column_id: "estatius", compare_value: [11]}
                            ]operator:and
                        }
                    ) {
                    cursor
                    items {
                        id
                        name
                        assets {
                            id
                            name
                            public_url
                        }
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
                            assets {
                                name
                                public_url
                            }
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
                                assets {
                                    id
                                    name
                                    public_url
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
                            assets {
                                id
                                name
                                public_url
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
                        assets {
                            id
                            name
                            public_url
                        }
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
                            assets {
                                name
                                public_url
                            }
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
                                assets {
                                    id
                                    name
                                    public_url
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
                            assets {
                                id
                                name
                                public_url
                            }
                        }
                    }
                }
            }
        }
        """

        if boards is not None:
            board_id = self._get_board_id(boards=boards, board_name=board_name)
            if board_id is not None:
                return self.pre_processor_cleaner_data(self._process_board_items(
                    board_id=board_id,
                    text_search=timeline,
                    initial_gql_query=initial_gql_query,
                    next_page_gql_query=next_page_gql_query
                ))
        return None