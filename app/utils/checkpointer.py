import psycopg
from langgraph.checkpoint.postgres import PostgresSaver
from app.settings.settings import Settings

def get_checkpointer() -> PostgresSaver:
    """
    Crea y retorna una instancia del Checkpointer PostgresSaver.

    La conexión a la base de datos se configura utilizando las variables de entorno
    a través de la clase Settings.

    Returns:
        Una instancia de PostgresSaver lista para ser usada.
    """
    settings = Settings()
    db_config = settings.DB_CONFIG

    # Crea la cadena de conexión para psycopg
    conn_string = f"postgresql://{db_config.user}:{db_config.password}@{db_config.host}:{db_config.port}/{db_config.database}"
    
    # Crea la conexión a la base de datos
    conn = psycopg.connect(conn_string)
    
    # Instancia el PostgresSaver con la conexión
    memory = PostgresSaver(conn=conn) # type: ignore
    
    return memory
