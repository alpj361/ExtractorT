#!/usr/bin/env python3
"""
Extractor de Tweets Ultra Minimalista para Railway
=================================================

Versión extremadamente ligera, diseñada para entornos con recursos muy limitados.
Características:
- No usa BeautifulSoup ni ninguna dependencia pesada
- Solo utiliza requests/urllib
- Parseo mínimo con regex
- Memoria y CPU mínimas requeridas
- Caché agresiva para reducir solicitudes
"""

import os
import sys
import re
import json
import time
import random
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
import gzip
from io import BytesIO
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import ssl
import urllib.parse

# Configuración
PORT = int(os.environ.get("PORT", 8000))
CACHE_DURATION = 900  # 15 minutos
CACHE_SIZE_LIMIT = 100  # Máximo número de usuarios en caché

# Configurar logging simplificado
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("minimal-extractor")

# Caché
cache = {}
last_cleanup = time.time()

# User agents minimalistas
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.159 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
]

def fetch_url(url: str, max_retries: int = 3) -> Optional[str]:
    """Obtiene el contenido de una URL con reintentos minimalistas."""
    user_agent = random.choice(USER_AGENTS)
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Encoding": "gzip, deflate",
        "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
        "Connection": "close",
    }
    
    for i in range(max_retries):
        try:
            req = Request(url, headers=headers)
            response = urlopen(req, timeout=10)
            
            # Manejar compresión gzip
            if response.info().get('Content-Encoding') == 'gzip':
                buffer = BytesIO(response.read())
                with gzip.GzipFile(fileobj=buffer) as f:
                    content = f.read().decode('utf-8')
            else:
                content = response.read().decode('utf-8')
                
            return content
        except (URLError, HTTPError) as e:
            logger.warning(f"Error fetching {url} (attempt {i+1}/{max_retries}): {e}")
            time.sleep(2 * (i + 1))  # Backoff exponencial simple
        except Exception as e:
            logger.error(f"Unexpected error fetching {url}: {e}")
            break
            
    return None

def extract_tweets_minimal(username: str, max_tweets: int = 20) -> List[Dict[str, Any]]:
    """
    Extrae tweets usando nitter.net con un parser extremadamente minimalista
    diseñado para usar la menor cantidad de recursos posible.
    """
    logger.info(f"Extracting tweets for @{username} (max: {max_tweets})")
    
    # Verificar caché
    cache_key = f"{username}_{max_tweets}"
    if cache_key in cache:
        timestamp, tweets = cache[cache_key]
        # Si está en caché y no ha expirado, usar la versión en caché
        if time.time() - timestamp < CACHE_DURATION:
            logger.info(f"Using cached data for @{username} ({len(tweets)} tweets)")
            return tweets
    
    # Lista de sitios Nitter para probar
    nitter_instances = [
        f"https://nitter.net/{username}",
        f"https://nitter.lacontrevoie.fr/{username}",
        f"https://nitter.fdn.fr/{username}",
    ]
    
    tweets = []
    html_content = None
    
    # Probar cada instancia de Nitter
    for instance in nitter_instances:
        logger.info(f"Trying {instance}")
        content = fetch_url(instance)
        if content and "<div class=\"timeline-item" in content:
            html_content = content
            logger.info(f"Successfully fetched data from {instance}")
            break
    
    if not html_content:
        logger.warning(f"Could not retrieve tweets for @{username} from any source")
        return []
    
    # Extraer tweets con regex minimalista
    timeline_items = re.findall(r'<div class="timeline-item[^>]*>(.*?)<\/div>\s*<\/div>\s*<\/div>', html_content, re.DOTALL)
    
    for item in timeline_items:
        if len(tweets) >= max_tweets:
            break
            
        try:
            # Saltar tweets pinned
            if "pinned-badge" in item:
                continue
                
            # Extraer ID de tweet
            tweet_id_match = re.search(r'href="[^"]*\/status\/([0-9]+)"', item)
            tweet_id = tweet_id_match.group(1) if tweet_id_match else ""
            
            # Extraer texto
            tweet_text_match = re.search(r'<div class="tweet-content[^>]*>(.*?)<\/div>', item, re.DOTALL)
            tweet_text = ""
            if tweet_text_match:
                # Limpieza básica de HTML
                tweet_text = re.sub(r'<[^>]+>', ' ', tweet_text_match.group(1))
                tweet_text = re.sub(r'\s+', ' ', tweet_text).strip()
            
            # Solo continuar si tenemos texto
            if not tweet_text or len(tweet_text) < 5:
                continue
                
            # Extraer fecha
            timestamp = ""
            date_match = re.search(r'<span class="tweet-date">.*?title="([^"]+)"', item)
            if date_match:
                timestamp = date_match.group(1)
            
            # Crear objeto tweet
            tweets.append({
                "tweet_id": tweet_id,
                "username": username,
                "text": tweet_text,
                "timestamp": timestamp
            })
            
        except Exception as e:
            logger.warning(f"Error parsing tweet: {e}")
    
    # Actualizar caché
    if tweets:
        logger.info(f"Extracted {len(tweets)} tweets for @{username}")
        cache[cache_key] = (time.time(), tweets)
        
        # Limpiar caché si es demasiado grande o si pasó mucho tiempo
        cleanup_cache()
    
    return tweets

def cleanup_cache():
    """Limpia la caché si es demasiado grande o si pasó mucho tiempo desde la última limpieza."""
    global last_cleanup
    
    if len(cache) > CACHE_SIZE_LIMIT or (time.time() - last_cleanup > 3600):  # 1 hora
        # Ordenar por timestamp, eliminar los más antiguos primero
        sorted_cache = sorted(cache.items(), key=lambda x: x[1][0])
        
        # Mantener solo la mitad más reciente
        keep_count = min(len(sorted_cache) // 2 + 1, CACHE_SIZE_LIMIT)
        new_cache = dict(sorted_cache[-keep_count:])
        
        # Actualizar caché
        cache.clear()
        cache.update(new_cache)
        
        last_cleanup = time.time()
        logger.info(f"Cache cleaned: {len(cache)}/{CACHE_SIZE_LIMIT} entries kept")

class RequestHandler(BaseHTTPRequestHandler):
    """Manejador de peticiones HTTP ultra ligero."""
    
    # Silenciar logs de peticiones para reducir ruido
    def log_message(self, format, *args):
        return
    
    def do_GET(self):
        """Maneja peticiones GET."""
        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path
        
        # Endpoint principal / información
        if path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            info = {
                "name": "Ultra Minimal Twitter Extractor",
                "version": "1.0.0",
                "description": "API minimalista para extraer tweets sin usar navegador",
                "endpoints": [
                    {"path": "/", "method": "GET", "description": "Información general"},
                    {"path": "/extract/{username}", "method": "GET", "description": "Extraer tweets"},
                    {"path": "/health", "method": "GET", "description": "Estado de la API"}
                ],
                "cache_size": len(cache)
            }
            
            self.wfile.write(json.dumps(info).encode())
            return
            
        # Health check
        elif path == '/health':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            health_info = {
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "cache_entries": len(cache)
            }
            
            self.wfile.write(json.dumps(health_info).encode())
            return
            
        # Extracción de tweets
        elif path.startswith('/extract/'):
            try:
                username = path.split('/extract/')[1]
                
                # Parámetros de consulta
                params = urllib.parse.parse_qs(parsed_path.query)
                max_tweets = int(params.get('max_tweets', ['20'])[0])
                
                # Limitar para evitar abusos
                max_tweets = min(max_tweets, 50)
                
                # Extraer tweets
                start_time = time.time()
                tweets = extract_tweets_minimal(username, max_tweets)
                process_time = time.time() - start_time
                
                # Preparar respuesta
                response = {
                    "status": "success" if tweets else "error",
                    "message": f"Extracted {len(tweets)} tweets" if tweets else "No tweets found",
                    "tweets": tweets,
                    "count": len(tweets),
                    "username": username,
                    "process_time_seconds": round(process_time, 3)
                }
                
                # Enviar respuesta
                self.send_response(200 if tweets else 404)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')  # CORS
                self.end_headers()
                self.wfile.write(json.dumps(response).encode())
                return
                
            except Exception as e:
                logger.error(f"Error processing request: {e}")
                
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                
                error_response = {
                    "status": "error",
                    "message": f"Internal server error: {str(e)}"
                }
                
                self.wfile.write(json.dumps(error_response).encode())
                return
        
        # Ruta no encontrada
        else:
            self.send_response(404)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            not_found = {
                "status": "error",
                "message": f"Endpoint not found: {path}"
            }
            
            self.wfile.write(json.dumps(not_found).encode())
            return

def run_server():
    """Ejecuta el servidor HTTP."""
    server_address = ('', PORT)
    httpd = HTTPServer(server_address, RequestHandler)
    
    # Imprimir información de inicio
    logger.info(f"Starting minimal Twitter extractor on port {PORT}")
    logger.info(f"Environment: {'Railway/Docker' if os.environ.get('RAILWAY_ENVIRONMENT') else 'Local'}")
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}")
    finally:
        httpd.server_close()
        logger.info("Server stopped")

if __name__ == "__main__":
    run_server() 