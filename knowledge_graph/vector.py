import uuid
from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.http import models
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from core.settings import settings
from core.logging.logger import logger

class VectorDBManager:
    def __init__(self):
        self.collection_name = "kb_entities"
        self.vector_size = 3072  # Gemini gemini-embedding-001 default size
        
        # Initialize Embeddings model
        self.embeddings = None
        if settings.GEMINI_API_KEY:
            try:
                self.embeddings = GoogleGenerativeAIEmbeddings(
                    model="models/gemini-embedding-001",
                    google_api_key=settings.GEMINI_API_KEY
                )
            except Exception as e:
                logger.error(f"Failed to initialize Gemini Embeddings: {e}")
        
        # Initialize Qdrant Client
        if settings.VECTOR_PROVIDER == "qdrant" and settings.QDRANT_URL:
            try:
                logger.info(f"Connecting to Qdrant at {settings.QDRANT_URL}...")
                self.client = QdrantClient(url=settings.QDRANT_URL, timeout=10)
                # Test connection
                self.client.get_collections()
            except Exception as e:
                logger.warning(f"Failed to connect to Qdrant server: {e}. Falling back to in-memory Qdrant.")
                self.client = QdrantClient(":memory:")
        else:
            logger.info("Initializing Qdrant in-memory client...")
            self.client = QdrantClient(":memory:")
            
    async def initialize_collection(self):
        """Creates collection if it doesn't exist."""
        try:
            collections = self.client.get_collections().collections
            collection_names = [c.name for c in collections]
            
            if self.collection_name not in collection_names:
                logger.info(f"Creating Qdrant collection: {self.collection_name}...")
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=models.VectorParams(
                        size=self.vector_size,
                        distance=models.Distance.COSINE
                    )
                )
            else:
                logger.info(f"Qdrant collection {self.collection_name} already exists.")
        except Exception as e:
            logger.error(f"Failed to initialize collection: {e}")

    def _get_embedding(self, text: str) -> List[float]:
        """Generates embedding for a string. Falls back to dummy vector if Gemini fails/disabled."""
        if self.embeddings:
            try:
                return self.embeddings.embed_query(text)
            except Exception as e:
                logger.error(f"Gemini embedding generation failed: {e}. Generating dummy vector.")
        
        # Deterministic dummy embedding for fallback/offline mode
        import hashlib
        hash_bytes = hashlib.sha256(text.encode('utf-8')).digest()
        dummy_vec = []
        for i in range(self.vector_size):
            # Generate a pseudo-random float between -1.0 and 1.0 based on hash bytes
            val = ((hash_bytes[i % 32] * (i + 1)) % 1000) / 500.0 - 1.0
            dummy_vec.append(val)
        return dummy_vec

    async def upsert_entity(self, name: str, entity_type: str, description: str, trend_id: str):
        """Stores an entity in the vector database."""
        text_to_embed = f"Entity: {name} | Type: {entity_type} | Description: {description}"
        vector = self._get_embedding(text_to_embed)
        
        point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{trend_id}:{name}"))
        
        try:
            self.client.upsert(
                collection_name=self.collection_name,
                points=[
                    models.PointStruct(
                        id=point_id,
                        vector=vector,
                        payload={
                            "name": name,
                            "type": entity_type,
                            "description": description,
                            "trend_id": trend_id
                        }
                    )
                ]
            )
            logger.debug(f"Upserted entity '{name}' to vector store.")
        except Exception as e:
            logger.error(f"Failed to upsert entity to Qdrant: {e}")

    async def search_entities(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Searches for semantically similar entities."""
        vector = self._get_embedding(query)
        try:
            results = self.client.query_points(
                collection_name=self.collection_name,
                query=vector,
                limit=limit
            ).points
            entities = []
            for r in results:
                payload = r.payload or {}
                entities.append({
                    "name": payload.get("name"),
                    "type": payload.get("type"),
                    "description": payload.get("description"),
                    "trend_id": payload.get("trend_id"),
                    "score": r.score
                })
            return entities
        except Exception as e:
            logger.error(f"Failed to search Qdrant entities: {e}")
            return []

vector_db = VectorDBManager()
