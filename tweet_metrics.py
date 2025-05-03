import logging
import asyncio
from typing import Dict, Any, Optional

from twitter_graphql import TwitterGraphQLClient

# Configuración de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
LOGGER = logging.getLogger(__name__)

# Cliente GraphQL compartido
graph_client = TwitterGraphQLClient()

async def fetch_via_graphql(tweet_id: str, comment_limit: int = 20) -> Dict[str, Any]:
    """
    Obtiene métricas y comentarios de un tweet usando la API GraphQL de Twitter.
    
    Args:
        tweet_id: ID del tweet
        comment_limit: Número máximo de comentarios a obtener
        
    Returns:
        Dict con indicador de éxito, métricas y comentarios
    """
    try:
        # Ejecutar en un thread separado para no bloquear asyncio
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(
            None, 
            lambda: graph_client.tweet_detail(tweet_id, comment_limit)
        )
        
        # Si tuvo éxito, asegurarse de que el flag de éxito esté presente
        if "success" not in data:
            data["success"] = True
        
        return data
    except Exception as e:
        LOGGER.warning(f"GraphQL falló para tweet {tweet_id}: {e}")
        return {
            "success": False,
            "likes": 0,
            "replies": 0,
            "reposts": 0,
            "views": 0,
            "comments": []
        }

async def fetch_more_comments_via_graphql(tweet_id: str, cursor: str, count: int = 20) -> Dict[str, Any]:
    """
    Obtiene más comentarios para un tweet usando paginación.
    
    Args:
        tweet_id: ID del tweet
        cursor: Cursor de paginación
        count: Número de comentarios a obtener
        
    Returns:
        Dict con comentarios adicionales y nuevo cursor
    """
    try:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: graph_client.fetch_more_comments(tweet_id, cursor, count)
        )
    except Exception as e:
        LOGGER.warning(f"Error obteniendo más comentarios para {tweet_id}: {e}")
        return {"comments": [], "next_cursor": None}

async def parse_tweet_id_from_url(url: str) -> Optional[str]:
    """
    Extrae el ID del tweet de una URL de Twitter.
    
    Args:
        url: URL del tweet (https://twitter.com/usuario/status/ID)
        
    Returns:
        ID del tweet o None si no se pudo extraer
    """
    import re
    
    # Patrón para extraer IDs de tweets
    pattern = r'twitter\.com/[^/]+/status/(\d+)'
    match = re.search(pattern, url)
    
    if match:
        return match.group(1)
    
    # Patrón alternativo para URLs de X
    pattern = r'x\.com/[^/]+/status/(\d+)'
    match = re.search(pattern, url)
    
    if match:
        return match.group(1)
    
    return None 