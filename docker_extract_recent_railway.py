#!/usr/bin/env python3
"""
Twitter Extractor API - Railway Edition

Una versión ligera del extractor de tweets optimizada para Railway.
Esta versión utiliza httpx y BeautifulSoup en lugar de Playwright
para reducir el consumo de recursos y evitar problemas de cierre del navegador.

Features:
- Extrae tweets recientes de perfiles de Twitter
- API FastAPI para acceso a través de HTTP
- Optimizado para entornos con recursos limitados (Railway)
- No utiliza navegador, solo solicitudes HTTP
- Caché de resultados para minimizar solicitudes repetidas
"""

import os
import time
import json
import random
import logging
import asyncio
import httpx
from typing import List, Dict, Any, Optional, Union
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import pandas as pd
from fastapi import FastAPI, BackgroundTasks, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("twitter-extractor-railway")

# Detectar entorno
IS_DOCKER = os.environ.get("DOCKER_ENVIRONMENT", "0") == "1"
IS_RAILWAY = os.environ.get("RAILWAY_ENVIRONMENT", "0") == "1"
PORT = int(os.environ.get("PORT", 8000))

# Configuración de la aplicación FastAPI
app = FastAPI(
    title="Twitter Extractor API - Railway Edition",
    description="API para extraer tweets recientes de perfiles de Twitter, optimizada para Railway",
    version="1.0.0"
)

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Caché para resultados
results_cache = {}
cache_duration = 300  # 5 minutos

# User-Agents para evitar bloqueos
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:90.0) Gecko/20100101 Firefox/90.0",
]

# Modelos de datos
class ExtractionRequest(BaseModel):
    username: str
    max_tweets: int = Field(default=50, ge=1, le=200)
    min_tweets: int = Field(default=5, ge=1, le=100)
    max_scrolls: int = Field(default=10, ge=1, le=50)

class ExtractionResponse(BaseModel):
    status: str
    message: str
    tweets: List[Dict[str, Any]]
    count: int
    date_range: Optional[str] = None
    username: str

async def fetch_with_retry(url: str, max_retries: int = 3, timeout: int = 30) -> httpx.Response:
    """Realiza solicitudes HTTP con reintentos."""
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Connection": "keep-alive",
    }
    
    retries = 0
    while retries < max_retries:
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(url, headers=headers, follow_redirects=True)
                response.raise_for_status()
                return response
        except httpx.HTTPStatusError as e:
            logger.warning(f"HTTP error: {e} (attempt {retries+1}/{max_retries})")
        except httpx.RequestError as e:
            logger.warning(f"Request error: {e} (attempt {retries+1}/{max_retries})")
        except Exception as e:
            logger.warning(f"Unexpected error: {e} (attempt {retries+1}/{max_retries})")
        
        retries += 1
        await asyncio.sleep(2 * retries)  # Backoff exponencial
    
    raise HTTPException(status_code=503, detail="Failed to fetch data after multiple retries")

def parse_tweet_text(tweet_element) -> str:
    """Extrae el texto del tweet de un elemento HTML."""
    text_parts = []
    
    # Buscar el contenido principal del tweet
    tweet_content = tweet_element.select_one(".tweet-content")
    if tweet_content:
        text_parts.append(tweet_content.get_text(strip=True))
    
    # Buscar citas o contenido adicional
    quote_content = tweet_element.select_one(".quote-text")
    if quote_content:
        text_parts.append("Quoted: " + quote_content.get_text(strip=True))
    
    return " ".join(text_parts)

def parse_tweet_timestamp(tweet_element) -> Optional[str]:
    """Extrae la marca de tiempo del tweet de un elemento HTML."""
    timestamp_elem = tweet_element.select_one(".tweet-date a")
    if timestamp_elem and timestamp_elem.get("title"):
        return timestamp_elem.get("title")
    return None

def extract_tweet_id(tweet_element) -> Optional[str]:
    """Extrae el ID del tweet de un elemento HTML."""
    permalink = tweet_element.select_one(".tweet-link")
    if permalink and permalink.get("href"):
        # El formato es generalmente /username/status/ID
        parts = permalink.get("href").split("/")
        if len(parts) >= 3 and parts[-2] == "status":
            return parts[-1]
    return None

async def extract_tweets_from_nitter(username: str, max_tweets: int = 50) -> List[Dict[str, Any]]:
    """Extrae tweets de un usuario utilizando una instancia Nitter."""
    logger.info(f"Intentando extraer tweets de {username} usando Nitter")
    
    # Lista de instancias Nitter (se intentarán en orden)
    nitter_instances = [
        f"https://nitter.net/{username}",
        f"https://nitter.poast.org/{username}",
        f"https://nitter.privacydev.net/{username}",
        f"https://nitter.1d4.us/{username}",
    ]
    
    tweets = []
    
    # Intentar cada instancia Nitter
    for instance_url in nitter_instances:
        if len(tweets) >= max_tweets:
            break
            
        try:
            logger.info(f"Intentando con instancia: {instance_url}")
            response = await fetch_with_retry(instance_url)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Encontrar elementos de tweet
            tweet_elements = soup.select(".timeline-item")
            
            if not tweet_elements:
                logger.warning(f"No se encontraron tweets en {instance_url}")
                continue
                
            logger.info(f"Se encontraron {len(tweet_elements)} tweets en {instance_url}")
            
            # Procesar cada tweet
            for tweet_elem in tweet_elements:
                # Saltar tweets promocionados o fijados
                if tweet_elem.select_one(".pinned"):
                    continue
                
                tweet_id = extract_tweet_id(tweet_elem)
                tweet_text = parse_tweet_text(tweet_elem)
                timestamp = parse_tweet_timestamp(tweet_elem)
                
                # Verificar contenido mínimo
                if not tweet_text or len(tweet_text.strip()) < 5:
                    continue
                
                tweets.append({
                    "tweet_id": tweet_id or "",
                    "username": username,
                    "text": tweet_text,
                    "timestamp": timestamp or datetime.now().isoformat(),
                })
                
                if len(tweets) >= max_tweets:
                    break
            
            # Si encontramos tweets, no seguir intentando con otras instancias
            if tweets:
                break
                
        except Exception as e:
            logger.error(f"Error al extraer tweets de {instance_url}: {str(e)}")
    
    return tweets

async def extract_tweets_railway(username: str, max_tweets: int = 50, min_tweets: int = 5) -> List[Dict[str, Any]]:
    """Función principal de extracción de tweets optimizada para Railway."""
    # Verificar caché
    cache_key = f"{username}_{max_tweets}"
    if cache_key in results_cache:
        cache_time, cached_tweets = results_cache[cache_key]
        if time.time() - cache_time < cache_duration:
            logger.info(f"Usando resultados en caché para {username} ({len(cached_tweets)} tweets)")
            return cached_tweets
    
    # Intentar extraer los tweets de Nitter
    tweets = await extract_tweets_from_nitter(username, max_tweets)
    
    # Si no hay suficientes tweets, intentar extraer directamente de Twitter
    if len(tweets) < min_tweets:
        logger.warning(f"No se obtuvieron suficientes tweets de Nitter. Intentando directamente con Twitter")
        # Aquí se podría implementar un extractor directo de Twitter como alternativa
        # Por ahora, simplemente retornamos lo que tenemos
    
    # Ordenar tweets por fecha (más recientes primero)
    try:
        tweets = sorted(tweets, key=lambda x: x.get("timestamp", ""), reverse=True)
    except Exception as e:
        logger.warning(f"Error al ordenar tweets: {str(e)}")
    
    # Guardar en caché
    results_cache[cache_key] = (time.time(), tweets)
    
    return tweets

def format_date_range(tweets: List[Dict[str, Any]]) -> str:
    """Formatea un rango de fechas basado en los tweets extraídos."""
    if not tweets:
        return "No hay tweets disponibles"
    
    dates = []
    for tweet in tweets:
        try:
            timestamp = tweet.get("timestamp", "")
            if timestamp:
                # Intentar varios formatos de fecha comunes
                for fmt in ["%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%S%z", "%a %b %d %H:%M:%S %z %Y"]:
                    try:
                        date = datetime.strptime(timestamp, fmt)
                        dates.append(date)
                        break
                    except ValueError:
                        continue
        except Exception as e:
            logger.warning(f"Error al parsear fecha: {str(e)}")
    
    if not dates:
        return "Fechas no disponibles"
    
    oldest = min(dates).strftime("%d/%m/%Y")
    newest = max(dates).strftime("%d/%m/%Y")
    
    if oldest == newest:
        return f"{oldest}"
    return f"{oldest} - {newest}"

@app.get("/")
async def root():
    """Información general sobre la API."""
    return {
        "name": "Twitter Extractor API - Railway Edition",
        "version": "1.0.0",
        "description": "API para extraer tweets recientes de perfiles de Twitter, optimizada para Railway",
        "endpoints": [
            {"path": "/", "method": "GET", "description": "Información general sobre la API"},
            {"path": "/status", "method": "GET", "description": "Estado actual del servicio"},
            {"path": "/extract/{username}", "method": "GET", "description": "Extraer tweets de un usuario"},
            {"path": "/extract_recent", "method": "POST", "description": "Extraer tweets usando una solicitud POST"},
            {"path": "/health", "method": "GET", "description": "Verificar estado de salud del servicio"}
        ],
        "environment": {
            "docker": IS_DOCKER,
            "railway": IS_RAILWAY
        }
    }

@app.get("/status")
async def status():
    """Estado actual del servicio."""
    return {
        "status": "active",
        "timestamp": datetime.now().isoformat(),
        "cache_size": len(results_cache),
        "environment": {
            "docker": IS_DOCKER,
            "railway": IS_RAILWAY
        }
    }

@app.get("/health")
async def health():
    """Verificar estado de salud del servicio."""
    return {"status": "healthy"}

@app.get("/extract/{username}")
async def extract_tweets_endpoint(
    username: str, 
    max_tweets: int = 50,
    min_tweets: int = 5,
    max_scrolls: int = 10
):
    """Extraer tweets de un usuario usando una solicitud GET."""
    try:
        tweets = await extract_tweets_railway(username, max_tweets, min_tweets)
        
        if not tweets:
            return JSONResponse(
                status_code=404,
                content={
                    "status": "error",
                    "message": f"No se encontraron tweets para el usuario {username}",
                    "tweets": [],
                    "count": 0,
                    "username": username
                }
            )
        
        return {
            "status": "success",
            "message": f"Se extrajeron {len(tweets)} tweets para el usuario {username}",
            "tweets": tweets,
            "count": len(tweets),
            "date_range": format_date_range(tweets),
            "username": username
        }
    
    except Exception as e:
        logger.error(f"Error al extraer tweets para {username}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error al extraer tweets: {str(e)}"
        )

@app.post("/extract_recent")
async def extract_recent_endpoint(request: ExtractionRequest):
    """Extraer tweets usando una solicitud POST."""
    try:
        tweets = await extract_tweets_railway(
            request.username, 
            request.max_tweets, 
            request.min_tweets
        )
        
        if not tweets:
            return JSONResponse(
                status_code=404,
                content={
                    "status": "error",
                    "message": f"No se encontraron tweets para el usuario {request.username}",
                    "tweets": [],
                    "count": 0,
                    "username": request.username
                }
            )
        
        return {
            "status": "success",
            "message": f"Se extrajeron {len(tweets)} tweets para el usuario {request.username}",
            "tweets": tweets,
            "count": len(tweets),
            "date_range": format_date_range(tweets),
            "username": request.username
        }
    
    except Exception as e:
        logger.error(f"Error al extraer tweets para {request.username}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error al extraer tweets: {str(e)}"
        )

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Middleware para registrar solicitudes."""
    start_time = time.time()
    
    response = await call_next(request)
    
    process_time = time.time() - start_time
    logger.info(f"Request: {request.method} {request.url.path} - Completed in {process_time:.4f}s")
    
    return response

def save_to_csv(tweets: List[Dict[str, Any]], username: str) -> str:
    """Guarda los tweets en un archivo CSV."""
    if not tweets:
        return ""
    
    try:
        df = pd.DataFrame(tweets)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"tweets_recientes_{username}_{timestamp}.csv"
        
        # Asegurar que el directorio existe
        os.makedirs("data", exist_ok=True)
        filepath = os.path.join("data", filename)
        
        df.to_csv(filepath, index=False)
        logger.info(f"Tweets guardados en {filepath}")
        return filepath
    
    except Exception as e:
        logger.error(f"Error al guardar tweets en CSV: {str(e)}")
        return ""

if __name__ == "__main__":
    import uvicorn
    
    logger.info(f"Iniciando API en modo {'Docker/Railway' if IS_DOCKER or IS_RAILWAY else 'local'}")
    logger.info(f"Escuchando en el puerto {PORT}")
    
    uvicorn.run(app, host="0.0.0.0", port=PORT) 