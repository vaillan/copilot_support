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

El flujo de trabajo se puede resumir en los siguientes pasos:

1.  **Entrada del Usuario**: El usuario envía una consulta a través del endpoint `/invoke` de la API.
2.  **Supervisor de Equipos**: Un agente supervisor analiza la consulta y la dirige al equipo apropiado: `research_team` o `doc_writing_team`.
3.  **Equipo de Investigación (`research_team`)**: Busca información relevante en monday.com y otras fuentes de datos, y genera un resumen.
4.  **Equipo de Redacción de Documentos (`doc_writing_team`)**: Crea documentos detallados, notas o gráficos basados en el informe de investigación.
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
5. Configura la base de datos PostgreSQL con la extensión `pgvector`:
    ```bash
    sudo apt install postgresql-16-pgvector
    sudo -u postgres psql -d copilot
    CREATE EXTENSION vector;
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
├── media/
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
    │   ├── connection.py
    │   └── tables.py
    ├── models/
    │   └── models.py
    ├── prompts/
    │   ├── action_prompt.md
    │   ├── report_prompt.md
    │   ├── search_prompt.md
    │   └── supervisor_general_prompt.md
    ├── router/
    │   ├── agent.py
    │   └── auth.py
    ├── settings/
    │   ├── __init__.py
    │   └── settings.py
    ├── tools/
    │   ├── __init__.py
    │   ├── doc_tools.py
    │   └── mcp_client.py
    └── utils/
        ├── checkpointer.py
        ├── files.py
        ├── monday_client.py
        ├── state.py
        └── vector_store.py
```

## Dependencias Principales

- **langchain**, **langgraph**, **langchain-core**, **langchain-community**, **langchain-google-genai**: Para construir la arquitectura basada en agentes y la integración con los modelos de IA generativa de Google.
- **fastapi**, **uvicorn**: Para crear la API web y ejecutar el servidor ASGI.
- **python-dotenv**, **pydantic**: Para la gestión de variables de entorno y la validación de datos.
- **pdfplumber**, **Pillow**, **pytesseract**, **openpyxl**, **python-docx**, **python-pptx**, **defusedxml**, **opencv-python**, **pdf2image**, **beautifulsoup4**: Para la extracción de datos de varios formatos de archivo.
- **monday-api-python-sdk**: Para la integración con monday.com.
- **sqlmodel**, **psycopg2-binary**, **pgvector**, **langgraph-checkpoint-postgres**: Para la conexión, ORM y base de datos PostgreSQL con capacidades vectoriales.
- **pyppeteer**, **nest-asyncio**, **httpx**: Para la navegación y solicitudes web asíncronas.
- **pyjwt**, **pwdlib**: Para la autenticación y gestión de contraseñas.