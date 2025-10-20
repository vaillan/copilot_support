from langchain_community.vectorstores.pgvector import PGVector
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from app.settings.settings import Settings

# --- Configuración Centralizada del VectorStore ---

# Carga la configuración de la base de datos desde las variables de entorno
settings = Settings()
DB_CONFIG = settings.DB_CONFIG

# Crea la cadena de conexión para PostgreSQL de forma segura
CONNECTION_STRING = PGVector.connection_string_from_db_params(
    driver="psycopg2",
    user=DB_CONFIG.user,
    password=DB_CONFIG.password,
    host=DB_CONFIG.host,
    port=DB_CONFIG.port,
    database=DB_CONFIG.database,
)

# Elige el modelo de embeddings.
# Asegúrate de tener GOOGLE_API_KEY en tu entorno.
embeddings = GoogleGenerativeAIEmbeddings(model="models/text-embedding-004", google_api_key=settings.GEMINI_API_KEY) # type: ignore

# Nombre de la colección (corresponde al nombre de la tabla en la BD)
COLLECTION_NAME = "messages"

def get_vector_store() -> PGVector:
    """
    Crea y retorna una instancia del VectorStore PGVector.
    
    Esta instancia está conectada a la base de datos PostgreSQL y configurada
    para usar el modelo de embeddings de Google.
    
    Returns:
        Una instancia de PGVector lista para ser usada.
    """
    store = PGVector(
        connection_string=CONNECTION_STRING,
        embedding_function=embeddings,
        collection_name=COLLECTION_NAME,
    )
    return store
