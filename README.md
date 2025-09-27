# Copilot Support

## Descripción

Copilot Support es un sistema inteligente de gestión de tickets diseñado para integrarse con monday.com. El sistema utiliza agentes de IA para analizar nuevos tickets, buscar tickets similares en una base de conocimiento y generar retroalimentación para ayudar a los usuarios a resolver problemas de manera más eficiente.

## Características

- **Integración con monday.com**: Se conecta a tableros de monday.com para recuperar y crear tickets.
- **Base de Conocimiento Vectorial**: Crea y mantiene una base de conocimiento vectorial para buscar tickets similares de manera semántica.
- **Procesamiento de Lenguaje Natural**: Utiliza modelos de lenguaje para destilar conocimiento de tickets existentes y generar retroalimentación.
- **Arquitectura Basada en Agentes**: Construido con LangGraph, el sistema orquesta una serie de agentes para manejar el flujo de trabajo de gestión de tickets.
- **Extracción de Datos**: Capaz de extraer texto de varios tipos de archivos, incluyendo PDFs, imágenes y documentos de Office.
- **API con FastAPI**: Expone la funcionalidad del agente a través de una API web robusta y fácil de usar.

## Cómo Funciona

El sistema está orquestado por un grafo de estados (`StateGraph`) de LangGraph que gestiona el flujo de trabajo entre diferentes agentes especializados. La interacción se realiza a través de una API creada con FastAPI.

1.  **Entrada del Usuario**: El usuario envía una consulta a través del endpoint `/invoke` de la API, especificando su pregunta y el historial de la conversación.
2.  **Supervisor (`supervisor_agent_node`)**: Este agente es el punto de entrada. Analiza la consulta del usuario y decide qué agente debe actuar a continuación.
    -   Si la consulta requiere una búsqueda, enruta al `SearchAgent`.
    -   Si ya se ha realizado una búsqueda y hay resultados, pasa el control al `ReportAgent`.
    -   Si la conversación parece haber terminado, finaliza el flujo.
3.  **Agente de Búsqueda (`search_agent_node`)**:
    -   Su objetivo es utilizar la herramienta `similarity_search` para encontrar ítems relevantes en monday.com.
    -   Si el usuario no ha especificado un tablero (`board_name`), primero utiliza la herramienta `list_boards` para obtener una lista de los tableros disponibles y se la presenta al usuario.
    -   Una vez que tiene el tablero y la consulta, realiza la búsqueda semántica y guarda los resultados en el estado del grafo.
4.  **Agente de Reporte (`report_agent_node`)**:
    -   Toma los resultados de la búsqueda (ítems de monday.com).
    -   Utiliza un modelo de lenguaje para generar un resumen estructurado y claro de cada ítem encontrado, en formato Markdown.
    -   Presenta un reporte final al usuario con los hallazgos.
5.  **Respuesta al Usuario**: El resultado final del `ReportAgent` se devuelve como respuesta de la API.

## Instalación

1.  Clona el repositorio:
    ```bash
    git clone https://github.com/tu_usuario/copilot_support.git
    cd copilot_support
    ```

2.  Crea un entorno virtual e instálalo:
    ```bash
    python -m venv .venv
    source .venv/bin/activate
    ```

3.  Instala las dependencias:
    ```bash
    pip install -r requirements.txt
    ```

4.  Crea un archivo `.env` en la raíz del proyecto y añade tus claves de API:
    ```
    MONDAY_API_KEY="tu_clave_api_de_monday"
    OPENAI_API_KEY="tu_clave_api_de_openai"
    ```

## Uso

La aplicación se ejecuta como un servidor web gracias a FastAPI. Para iniciarla, ejecuta el siguiente comando desde la raíz del proyecto:

```bash
uvicorn main:app --reload
```

El servidor estará disponible en `http://127.0.0.1:8000`. Puedes interactuar con la API a través de la documentación interactiva que se genera automáticamente en `http://127.0.0.1:8000/docs`.

## Estructura del Proyecto

```
/
├── .gitignore
├── main.py
├── README.md
├── requirements.txt
└── app/
    ├── __init__.py
    ├── main.py
    ├── agents/
    │   ├── __init__.py
    │   ├── report_agent_node.py
    │   ├── search_agent_node.py
    │   └── supervisor_agent_node.py
    ├── settings/
    │   ├── __init__.py
    │   └── settings.py
    ├── tools/
    │   ├── __init__.py
    │   ├── list_boards_tool.py
    │   └── similarity_search_tool.py
    └── utils/
        ├── __init__.py
        ├── extract_monday_data.py
        ├── model_provider.py
        ├── state.py
        └── text_cleaner.py
```

## Dependencias Principales

- **langgraph**: Para construir la arquitectura basada en agentes.
- **langchain-google-genai**: Para la integración con los modelos de IA generativa de Google.
- **fastapi**: Para crear la API web.
- **uvicorn**: Para ejecutar el servidor ASGI.
- **sentence-transformers**: Para la creación de embeddings de texto.
- **chromadb**: Para la base de datos vectorial.
- **pdfplumber**, **Pillow**, **pytesseract**, **openpyxl**, **python-docx**, **opencv-python**, **pdf2image**: Para la extracción de datos de varios formatos de archivo.
- **monday-tools**: Para la integración con monday.com.