import httpx
import re
import json
import logging
import time
import random
from typing import Dict, List, Any, Optional

# Configuración de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
LOGGER = logging.getLogger(__name__)

# Token Bearer usado por Twitter web app (actualizar si deja de funcionar)
BEARER = "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"

# URL para activar token de invitado
GUEST_ACTIVATE = "https://api.twitter.com/1.1/guest/activate.json"

# IDs de operaciones comunes (estos hashes pueden cambiar con el tiempo)
OPERATIONS = {
    "TweetDetail": "v2sSj8yuQSX-K_YrDHWqBw",  # Para detalles del tweet
    "TweetResultByRestId": "3X4l8JgfNm4fgJqwdteLmQ",  # Para obtener un tweet por ID
    "UserByScreenName": "k4yvK5W8W4rUZmBnRJ4zsg",  # Para obtener un usuario por nombre
    "ConversationTimeline": "VMXOgXWqVW7okIe6hz5dDw",  # Para obtener comentarios
}

class TwitterGraphQLClient:
    """Cliente para acceder a la API GraphQL pública de Twitter/X sin necesidad de autenticación."""
    
    def __init__(self):
        """Inicializa el cliente GraphQL con un token de invitado."""
        self.client = httpx.Client(
            headers={
                "Authorization": f"Bearer {BEARER}",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
                "Accept": "*/*",
                "Accept-Language": "en-US,en;q=0.9",
                "Content-Type": "application/json",
                "X-Twitter-Active-User": "yes",
                "X-Twitter-Client-Language": "en",
            },
            timeout=30.0,
            follow_redirects=True,
        )
        self.last_refresh = 0
        self._refresh_guest_token()
        self.rate_limit_remaining = 100  # Contador estimado
    
    def _refresh_guest_token(self):
        """Obtiene un nuevo token de invitado."""
        try:
            LOGGER.info("Obteniendo nuevo guest token")
            r = self.client.post(GUEST_ACTIVATE)
            r.raise_for_status()
            token = r.json()["guest_token"]
            self.client.headers["x-guest-token"] = token
            self.last_refresh = time.time()
            self.rate_limit_remaining = 100  # Restablecer contador
            LOGGER.info(f"Guest token obtenido exitosamente: {token[:5]}...")
        except Exception as e:
            LOGGER.error(f"Error al refrescar guest token: {e}")
            raise

    def _ensure_token(self):
        """Asegura que el token de invitado esté vigente."""
        if time.time() - self.last_refresh > 600:  # 10 minutos
            self._refresh_guest_token()
        
        # Si estamos cerca del límite de velocidad, actualizar
        if self.rate_limit_remaining < 10:
            LOGGER.warning("Rate limit bajo, refrescando token")
            self._refresh_guest_token()
    
    def _handle_response(self, response):
        """Maneja la respuesta de la API, verificando errores y límites de velocidad."""
        if response.status_code == 429:
            LOGGER.warning("Rate limit alcanzado, esperando y refrescando token")
            time.sleep(10 + random.random() * 5)  # Esperar entre 10-15 segundos
            self._refresh_guest_token()
            return None
        
        # Actualizar contador de rate limit si hay headers
        if "x-rate-limit-remaining" in response.headers:
            self.rate_limit_remaining = int(response.headers["x-rate-limit-remaining"])
        
        try:
            response.raise_for_status()
            return response.json()
        except Exception as e:
            LOGGER.error(f"Error en respuesta ({response.status_code}): {e}")
            if response.status_code == 403:
                # Posible captcha o bloqueo, forzar refresh
                self._refresh_guest_token()
            return None
    
    def tweet_detail(self, tweet_id: str, reply_limit: int = 20) -> Dict[str, Any]:
        """
        Obtiene detalles de un tweet incluyendo métricas y comentarios.
        
        Args:
            tweet_id: ID del tweet
            reply_limit: Número máximo de comentarios a incluir
            
        Returns:
            Dict con métricas (likes, replies, reposts, views) y comentarios
        """
        self._ensure_token()
        
        # Variables para la consulta GraphQL
        variables = {
            "focalTweetId": tweet_id,
            "with_rux_injections": False,
            "includePromotedContent": False,
            "withCommunity": True,
            "withQuickPromoteEligibilityTweetFields": True,
            "withBirdwatchNotes": False,
            "withVoice": True,
            "withV2Timeline": True
        }
        
        features = {
            "responsive_web_graphql_exclude_directive_enabled": True,
            "verified_phone_label_enabled": False,
            "creator_subscriptions_tweet_preview_api_enabled": True,
            "responsive_web_graphql_timeline_navigation_enabled": True,
            "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
            "c9s_tweet_anatomy_moderator_badge_enabled": True,
            "tweetypie_unmention_optimization_enabled": True,
            "responsive_web_edit_tweet_api_enabled": True,
            "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
            "view_counts_everywhere_api_enabled": True,
            "longform_notetweets_consumption_enabled": True,
            "responsive_web_twitter_article_tweet_consumption_enabled": True,
            "tweet_awards_web_tipping_enabled": False,
            "freedom_of_speech_not_reach_fetch_enabled": True,
            "standardized_nudges_misinfo": True,
            "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
            "rweb_video_timestamps_enabled": True,
            "longform_notetweets_rich_text_read_enabled": True,
            "longform_notetweets_inline_media_enabled": True,
            "responsive_web_enhance_cards_enabled": False
        }
        
        # Construir URL de la consulta (usar TweetResultByRestId)
        operation = OPERATIONS["TweetResultByRestId"]
        url = (
            f"https://twitter.com/i/api/graphql/{operation}/TweetResultByRestId"
            f"?variables={json.dumps(variables, separators=(',', ':'))}"
            f"&features={json.dumps(features, separators=(',', ':'))}"
        )
        
        LOGGER.info(f"Consultando detalles para tweet {tweet_id}")
        response = self.client.get(url)
        data = self._handle_response(response)
        
        if not data:
            LOGGER.warning(f"No se pudieron obtener detalles para tweet {tweet_id}")
            return {
                "success": False,
                "likes": 0,
                "replies": 0,
                "reposts": 0,
                "views": 0,
                "comments": []
            }
        
        # Extraer métricas y comentarios del resultado
        try:
            result = self._extract_tweet_metrics_and_comments(data, reply_limit)
            result["success"] = True
            return result
        except Exception as e:
            LOGGER.error(f"Error procesando datos de tweet {tweet_id}: {e}")
            return {
                "success": False,
                "likes": 0,
                "replies": 0,
                "reposts": 0,
                "views": 0,
                "comments": []
            }
    
    def _extract_tweet_metrics_and_comments(self, data: Dict, reply_limit: int) -> Dict[str, Any]:
        """
        Extrae métricas y comentarios de la respuesta GraphQL.
        
        Args:
            data: Respuesta JSON de la API
            reply_limit: Límite de comentarios a extraer
            
        Returns:
            Dict con métricas y comentarios
        """
        likes = 0
        replies = 0
        reposts = 0
        views = 0
        comments = []
        
        # Navegar por la respuesta para extraer el tweet
        tweet_result = None
        
        # Buscar en result.data.tweetResult
        if "data" in data and "tweetResult" in data["data"]:
            if "result" in data["data"]["tweetResult"]:
                tweet_result = data["data"]["tweetResult"]["result"]
        
        # Si no se encuentra, buscar en el timeline
        if not tweet_result and "data" in data and "threaded_conversation_with_injections_v2" in data["data"]:
            instructions = data["data"]["threaded_conversation_with_injections_v2"]["instructions"]
            for instruction in instructions:
                if instruction["type"] == "TimelineAddEntries":
                    for entry in instruction["entries"]:
                        if "content" in entry and "itemContent" in entry["content"]:
                            content = entry["content"]["itemContent"]
                            if "tweet_results" in content:
                                tweet_result = content["tweet_results"]["result"]
                                break
        
        # Extraer métricas si encontramos el tweet
        if tweet_result:
            # Extraer legacy para las métricas
            if "legacy" in tweet_result:
                legacy = tweet_result["legacy"]
                likes = int(legacy.get("favorite_count", 0))
                replies = int(legacy.get("reply_count", 0))
                reposts = int(legacy.get("retweet_count", 0))
                
                # Views pueden estar en diferentes ubicaciones
                if "views" in legacy and "count" in legacy["views"]:
                    views = int(legacy["views"]["count"])
                elif "ext_views" in tweet_result and "count" in tweet_result["ext_views"]:
                    views = int(tweet_result["ext_views"]["count"])
            
            # Extraer comentarios
            comments = self._extract_comments(data, reply_limit)
        
        return {
            "likes": likes,
            "replies": replies,
            "reposts": reposts,
            "views": views,
            "comments": comments
        }
    
    def _extract_comments(self, data: Dict, limit: int) -> List[Dict[str, Any]]:
        """
        Extrae comentarios del resultado GraphQL.
        
        Args:
            data: Datos JSON de la respuesta
            limit: Número máximo de comentarios a extraer
            
        Returns:
            Lista de comentarios con usuario, texto y likes
        """
        comments = []
        
        # Buscar comentarios en las instrucciones del timeline
        if "data" in data and "threaded_conversation_with_injections_v2" in data["data"]:
            instructions = data["data"]["threaded_conversation_with_injections_v2"]["instructions"]
            for instruction in instructions:
                if instruction["type"] == "TimelineAddEntries":
                    for entry in instruction["entries"]:
                        # Saltar si ya tenemos suficientes comentarios
                        if len(comments) >= limit:
                            break
                            
                        # Ignorar el tweet principal y cursores
                        if "entryId" in entry and (
                            "cursor" in entry["entryId"] or 
                            "tweet" not in entry["entryId"] or
                            "conversationthread" in entry["entryId"].lower()
                        ):
                            continue
                        
                        # Extraer el comentario
                        comment = self._extract_single_comment(entry)
                        if comment:
                            comments.append(comment)
                            if len(comments) >= limit:
                                break
        
        return comments
    
    def _extract_single_comment(self, entry: Dict) -> Optional[Dict[str, Any]]:
        """
        Extrae un único comentario de una entrada del timeline.
        
        Args:
            entry: Entrada del timeline
            
        Returns:
            Dict con datos del comentario o None si no es válido
        """
        try:
            if "content" not in entry or "item" not in entry["content"]:
                if "content" in entry and "itemContent" in entry["content"]:
                    content = entry["content"]["itemContent"]
                else:
                    return None
            else:
                content = entry["content"]["item"]["itemContent"]
            
            # Obtener resultado del tweet (comentario)
            if "tweet_results" not in content:
                return None
                
            tweet_result = content["tweet_results"]["result"]
            
            # Ignorar tweets eliminados o restringidos
            if "tweet" in tweet_result:
                tweet_result = tweet_result["tweet"]
            elif "__typename" in tweet_result and tweet_result["__typename"] != "Tweet":
                return None
            
            # Extraer datos del comentario
            if "legacy" not in tweet_result or "core" not in tweet_result:
                return None
                
            legacy = tweet_result["legacy"]
            user_info = tweet_result["core"]["user_results"]["result"]
            
            # Extraer texto y limpiar
            full_text = legacy.get("full_text", "")
            
            # Construir objeto de comentario
            return {
                "user": user_info["legacy"].get("screen_name", "Usuario"),
                "text": full_text,
                "likes": int(legacy.get("favorite_count", 0))
            }
        except Exception as e:
            LOGGER.warning(f"Error extrayendo comentario: {e}")
            return None
    
    def fetch_more_comments(self, tweet_id: str, cursor: str, count: int = 20) -> Dict:
        """
        Obtiene más comentarios para un tweet usando un cursor de paginación.
        
        Args:
            tweet_id: ID del tweet
            cursor: Cursor de paginación
            count: Número de comentarios a obtener
            
        Returns:
            Dict con comentarios adicionales y nuevo cursor
        """
        self._ensure_token()
        
        # Variables para la consulta de conversación
        variables = {
            "focalTweetId": tweet_id,
            "cursor": cursor,
            "count": count,
            "includePromotedContent": False,
            "withCommunity": True,
            "withHighlightedLabel": False
        }
        
        # Usar operación ConversationTimeline
        operation = OPERATIONS["ConversationTimeline"]
        url = (
            f"https://twitter.com/i/api/graphql/{operation}/ConversationTimeline"
            f"?variables={json.dumps(variables, separators=(',', ':'))}"
        )
        
        LOGGER.info(f"Consultando más comentarios para tweet {tweet_id} con cursor {cursor[:10]}...")
        response = self.client.get(url)
        data = self._handle_response(response)
        
        if not data:
            return {"comments": [], "next_cursor": None}
        
        # Extraer comentarios y nuevo cursor
        comments = []
        next_cursor = None
        
        try:
            if "data" in data and "conversation_timeline" in data["data"]:
                timeline = data["data"]["conversation_timeline"]
                instructions = timeline["timeline"]["instructions"]
                
                # Extraer comentarios
                for instruction in instructions:
                    if instruction["type"] == "TimelineAddEntries":
                        for entry in instruction["entries"]:
                            # Buscar cursor para siguiente página
                            if "entryId" in entry and "cursor-bottom" in entry["entryId"]:
                                if "content" in entry and "value" in entry["content"]:
                                    next_cursor = entry["content"]["value"]
                                    continue
                            
                            # Extraer comentario
                            comment = self._extract_single_comment(entry)
                            if comment:
                                comments.append(comment)
                                
        except Exception as e:
            LOGGER.error(f"Error procesando más comentarios: {e}")
        
        return {
            "comments": comments,
            "next_cursor": next_cursor
        } 