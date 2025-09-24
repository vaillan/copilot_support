import os
from typing import List, Dict, Any, Optional
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings # Solo importamos HuggingFaceEmbeddings
from langchain_core.documents import Document
from dotenv import load_dotenv

load_dotenv() # Cargar variables de entorno

# --- Configuración de Embeddings y Vector Store para ejecución local ---
# Utilizaremos un modelo de HuggingFace que se descarga y ejecuta localmente.
# Asegúrate de instalar 'sentence-transformers': pip install sentence-transformers
EMBEDDING_MODEL = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

# Directorio para la base de datos vectorial persistente
PERSIST_DIRECTORY = os.path.join(os.getcwd(), 'src', 'knowledge_base', 'vector_store')

class KnowledgeBaseAgent:
    """
    Agente encargado de gestionar la base de conocimiento vectorial.
    Crea, actualiza y busca en la base de datos vectorial utilizando un modelo de embeddings local.
    """
    def __init__(self):
        self.embedding_model = EMBEDDING_MODEL
        self.persist_directory = PERSIST_DIRECTORY
        self.vectorstore = self._initialize_vectorstore()
        print(f"KnowledgeBaseAgent inicializado con modelo de embeddings: {EMBEDDING_MODEL.model_name}")

    def _initialize_vectorstore(self) -> Chroma:
        """
        Inicializa o carga la base de datos vectorial Chroma.
        """
        if not os.path.exists(self.persist_directory):
            os.makedirs(self.persist_directory)
            print(f"Directorio de base de conocimiento vectorial creado: {self.persist_directory}")
            # Si el directorio es nuevo, inicializamos una Chroma vacía
            return Chroma(embedding_function=self.embedding_model, persist_directory=self.persist_directory)
        else:
            # Si el directorio ya existe, cargamos la base de datos existente
            print(f"Cargando base de conocimiento vectorial desde: {self.persist_directory}")
            return Chroma(persist_directory=self.persist_directory, embedding_function=self.embedding_model)

    def update_knowledge_base(self, processed_tickets: List[Dict[str, Any]]):
        """
        Añade o actualiza tickets en la base de conocimiento vectorial.
        Cada ticket se convierte en un Documento de LangChain.
        """
        if not processed_tickets:
            print("No hay tickets procesados para actualizar la base de conocimiento vectorial.")
            return

        documents = []
        for ticket in processed_tickets:
            # Combinamos problem_summary y solution_applied para el contenido del documento
            # Estos campos vienen del LLM de destilación y son de alta calidad.
            content = f"Resumen del problema: {ticket['problem_summary']}\nSolución aplicada: {ticket['solution_applied']}"
            metadata = {
                "item_id": ticket["item_id"],
                "board_name": ticket["board_name"],
                "item_name": ticket["item_name"],
                "problem_summary": ticket["problem_summary"],
                "root_cause": ticket["root_cause"],
                "solution_applied": ticket["solution_applied"],
                "keywords": ticket["keywords"],
                "source_date": ticket["source_date"]
            }
            documents.append(Document(page_content=content, metadata=metadata))
        
        print(f"Añadiendo {len(documents)} documentos a la base de conocimiento vectorial...")
        # Añadir documentos a la base de datos vectorial
        # Chroma maneja la deduplicación si se usa un ID, pero aquí simplemente añadimos.
        # Para una actualización más robusta, se podría borrar y re-añadir o usar IDs específicos.
        self.vectorstore.add_documents(documents)
        self.vectorstore.persist() # Guardar los cambios en disco
        print("Base de conocimiento vectorial actualizada y persistida.")

    def retrieve_similar_tickets(self, query_text: str, k: int = 3) -> List[Dict[str, Any]]:
        """
        Busca los 'k' tickets más similares en la base de conocimiento vectorial
        basándose en el texto de la consulta.
        """
        if not query_text:
            return []

        print(f"Buscando {k} tickets similares en la base vectorial para la consulta: '{query_text}'...")
        # El retriever devuelve una lista de Documentos de LangChain
        similar_docs = self.vectorstore.similarity_search(query_text, k=k)
        
        similar_tickets = []
        for doc in similar_docs:
            # Convertimos el Documento de nuevo a nuestro formato de diccionario de ticket
            # Los metadatos ya contienen la información destilada
            ticket_data = {
                "item_id": doc.metadata.get("item_id"),
                "board_name": doc.metadata.get("board_name"),
                "item_name": doc.metadata.get("item_name"),
                "problem_summary": doc.metadata.get("problem_summary"),
                "root_cause": doc.metadata.get("root_cause"),
                "solution_applied": doc.metadata.get("solution_applied"),
                "keywords": doc.metadata.get("keywords"),
                "source_date": doc.metadata.get("source_date"),
                # 'score' no se incluye por defecto con similarity_search,
                # si se necesita, usar similarity_search_with_score y extraerlo.
            }
            similar_tickets.append(ticket_data)
        
        print(f"Encontrados {len(similar_tickets)} tickets similares en la base vectorial.")
        return similar_tickets
