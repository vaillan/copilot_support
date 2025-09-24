# Copilot Support

## Descripción

Copilot Support es un sistema inteligente de gestión de tickets diseñado para integrarse con monday.com. El sistema utiliza agentes de IA para analizar nuevos tickets, buscar tickets similares en una base de conocimiento y generar retroalimentación para ayudar a los usuarios a resolver problemas de manera más eficiente.

## Características

- **Integración con monday.com**: Se conecta a tableros de monday.com para recuperar y crear tickets.
- **Base de Conocimiento Vectorial**: Crea y mantiene una base de conocimiento vectorial para buscar tickets similares de manera semántica.
- **Procesamiento de Lenguaje Natural**: Utiliza modelos de lenguaje para destilar conocimiento de tickets existentes y generar retroalimentación.
- **Arquitectura Basada en Agentes**: Construido con LangGraph, el sistema orquesta una serie de agentes para manejar el flujo de trabajo de gestión de tickets.
- **Extracción de Datos**: Capaz de extraer texto de varios tipos de archivos, incluyendo PDFs, imágenes y documentos de Office.

## Cómo Funciona

El sistema sigue un flujo de trabajo orquestado por el `UIOchestrationAgent`:

1.  **Entrada del Usuario**: El sistema solicita al usuario el nombre de un tablero de monday.com y la descripción de un nuevo ticket.
2.  **Recuperación de Datos**: Busca tickets similares en el tablero de monday.com especificado.
3.  **Destilación de Conocimiento**: Los tickets recuperados son procesados por un `KnowledgeDistillationAgent` para extraer información clave, que luego se almacena en un archivo CSV.
4.  **Búsqueda y Generación de Retroalimentación**: El sistema actualiza una base de conocimiento vectorial con la información destilada. Luego, busca tickets similares a la descripción del nuevo ticket del usuario en la base de conocimiento vectorial. Basado en los tickets similares encontrados, un `FinalFeedbackAgent` genera retroalimentación para el usuario.
5.  **Confirmación del Usuario**: Se presenta al usuario la retroalimentación generada y se le pregunta si desea crear un nuevo ticket en monday.com.
6.  **Creación de Ticket**: Si el usuario confirma, se crea un nuevo ticket en monday.com.

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

Para ejecutar la aplicación, ejecuta el siguiente comando desde la raíz del proyecto:

```bash
python -m src.main
```

El sistema te guiará a través del proceso de gestión de tickets.

## Estructura del Proyecto

```
/
├── .gitignore
├── README.md
├── requirements.txt
└── src/
    ├── __init__.py
    ├── main.py
    ├── agents/
    │   ├── __init__.py
    │   ├── data_preprocessing_agent.py
    │   ├── final_feedback_agent.py
    │   ├── knowledge_base_agent.py
    │   ├── knowledge_distillation_agent.py
    │   └── ui_orchestration_agent.py
    ├── knowledge_base/
    │   └── knowledge_base.csv
    ├── settings/
    │   ├── __init__.py
    │   └── settings.py
    ├── tools/
    │   ├── __init__.py
    │   ├── csv_knowledge_tools.py
    │   └── monday_tools.py
    └── utils/
        ├── extract_monday_data.py
        ├── llm_provider.py
        ├── state.py
        └── text_cleaner.py
```

## Dependencias Principales

- **langgraph**: Para construir la arquitectura basada en agentes.
- **langchain-google-genai**: Para la integración con los modelos de IA generativa de Google.
- **sentence-transformers**: Para la creación de embeddings de texto.
- **chromadb**: Para la base de datos vectorial.
- **pdfplumber**, **Pillow**, **pytesseract**, **openpyxl**, **python-docx**, **opencv-python**, **pdf2image**: Para la extracción de datos de varios formatos de archivo.
- **monday-tools**: Para la integración con monday.com.
