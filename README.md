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
2.  **Supervisor de Equipos**: Este agente es el punto de entrada. Analiza la consulta del usuario y decide qué equipo debe actuar a continuación: `research_team` o `doc_writing_team`.
3.  **Equipo de Investigación (`research_team`)**:
    -   Este equipo tiene su propio supervisor que orquesta a dos agentes: `research_agent_node` y `report_agent_node`.
    -   **Agente de Búsqueda (`research_agent_node`)**: Su objetivo es utilizar herramientas para encontrar ítems relevantes en monday.com y otras fuentes de datos.
    -   **Agente de Reporte (`report_agent_node`)**: Toma los resultados de la búsqueda y genera un resumen estructurado en formato Markdown.
4.  **Equipo de Redacción de Documentos (`doc_writing_team`)**:
    -   Este equipo tiene su propio supervisor que orquesta a tres agentes: `doc_writer`, `note_taker` y `chart_generator`.
    -   **Agente Tomador de Notas (`note_taker`)**: Lee el informe de investigación y crea un esquema detallado.
    -   **Agente Generador de Gráficos (`chart_generator`)**: Puede generar gráficos a partir de los datos del informe.
    -   **Agente Escritor de Documentos (`doc_writer`)**: Escribe un documento completo basado en el esquema, pudiendo crear archivos de texto, Word, Excel o PowerPoint.
5.  **Respuesta al Usuario**: El resultado final se devuelve como respuesta de la API.

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
    GEMINI_API_KEY="tu_clave_api_de_gemini"
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
    ├── agents/
    │   ├── __init__.py
    │   ├── document_writer_team.py
    │   ├── hierarchy_team.py
    │   ├── make_supervisor_node.py
    │   └── research_team.py
    ├── auth/
    │   └── auth.py
    ├── database/
    │   └── connection.py
    ├── models/
    │   └── models.py
    ├── prompts/
    │   ├── action_prompt.md
    │   ├── report_prompt.md
    │   ├── search_prompt.md
    │   ├── supervisor_general_prompt.md
    │   └── supervisor_search_prompt.md
    ├── router/
    │   └── agent.py
    ├── settings/
    │   ├── __init__.py
    │   └── settings.py
    ├── tools/
    │   ├── __init__.py
    │   ├── doc_tools.py
    │   └── mcp_client.py
    └── utils/
        ├── __init__.py
        ├── files.py
        ├── monday_client.py
        └── state.py
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

1
 sudo apt install postgresql-16-pgvector
 2
 sudo -u postgres psql -d copilot
3
CREATE EXTENSION vector;
