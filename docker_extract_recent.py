#!/usr/bin/env python3
"""
Script para extraer tweets recientes de Twitter diseñado para entornos Docker y Railway.
Características:
1. Autenticación automática con renovación de sesión
2. Priorización de tweets recientes usando búsqueda con filtro "live"
3. Filtrado inteligente de tweets promocionados y fijados
4. API para integración con bots y servicios externos

Uso:
    En Docker/Railway: Se ejecuta como servicio API
    Localmente: python docker_extract_recent.py <username> [max_tweets] [min_tweets] [max_scrolls]
"""

import os
import sys
import json
import logging
import asyncio
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Any
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from playwright.async_api import async_playwright
import traceback
from pydantic import BaseModel
from fastapi import BackgroundTasks
import pytesseract
from PIL import Image, ImageDraw, ImageEnhance
import requests
from bs4 import BeautifulSoup
import unicodedata
import difflib
import re
import time

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Importar módulos para extracción de métricas y comentarios vía GraphQL
try:
    from twitter_graphql import TwitterGraphQLClient
    from tweet_metrics import fetch_via_graphql, parse_tweet_id_from_url
    GRAPHQL_AVAILABLE = True
    logger.info("Cliente GraphQL disponible para métricas y comentarios")
except ImportError:
    GRAPHQL_AVAILABLE = False
    logger.warning("Cliente GraphQL no disponible. Se usará el método de Playwright.")

# Nuevas importaciones para Selenium
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
    # Importar webdriver_manager condicionalmente (puede fallar en algunos entornos)
    try:
        from webdriver_manager.chrome import ChromeDriverManager
        WEBDRIVER_MANAGER_AVAILABLE = True
    except ImportError:
        WEBDRIVER_MANAGER_AVAILABLE = False
    
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    logger.warning("Selenium is not available. Some features will be disabled.")

# Credenciales para login automático (pueden ser sobreescritas por variables de entorno)
TWITTER_USERNAME = os.environ.get("TWITTER_USERNAME", "StandPd2007")
TWITTER_PASSWORD = os.environ.get("TWITTER_PASSWORD", "Welcome2024!")
STORAGE_FILE = os.environ.get("STORAGE_FILE", "firefox_storage.json")

# Detectar si estamos en entorno Docker/Railway
DOCKER_ENVIRONMENT = os.environ.get("DOCKER_ENVIRONMENT", "0") == "1" or os.path.exists('/.dockerenv')
RAILWAY_ENVIRONMENT = "RAILWAY_ENVIRONMENT" in os.environ or os.environ.get('RAILWAY_ENV', '0') == '1'

# Detectar si estamos en entorno local (no Docker ni Railway)
IS_LOCAL = not (DOCKER_ENVIRONMENT or RAILWAY_ENVIRONMENT) and not (os.environ.get("DOCKER") or os.environ.get("RAILWAY"))

# Configuración para modo headless
IS_HEADLESS = DOCKER_ENVIRONMENT or RAILWAY_ENVIRONMENT or os.environ.get("DOCKER") or os.environ.get("RAILWAY")
if IS_LOCAL:
    IS_HEADLESS = False  # En local, mostrar el navegador

# Permitir forzar el modo no headless con variable de entorno
if os.environ.get("HEADLESS") == "0":
    IS_HEADLESS = False
    logger.info("Modo headless desactivado mediante variable de entorno HEADLESS=0")

logger.info(f"Entorno - Docker: {DOCKER_ENVIRONMENT}, Railway: {RAILWAY_ENVIRONMENT}, Local: {IS_LOCAL}, Headless: {IS_HEADLESS}")

# Crear la app FastAPI
app = FastAPI(title="Twitter Recent Tweets Extractor", 
              description="API para extraer tweets recientes con auto-login y detección de tweets promocionados")

# Configurar CORS para permitir solicitudes de cualquier origen
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Variables globales para el estado
login_in_progress = False
extraction_in_progress = False
recent_extractions = {}  # Cache de extracciones recientes

# Modelos de datos para la API
class ExtractionRequest(BaseModel):
    username: str
    max_tweets: int = 20
    min_tweets: int = 10
    max_scrolls: int = 10

class ExtractionResponse(BaseModel):
    status: str
    message: str
    tweets: Optional[List[Dict[str, Any]]] = None
    count: int = 0
    date_range: Optional[Dict[str, str]] = None

# Punto de entrada API 
@app.get("/", response_class=JSONResponse)
async def root():
    """Punto de entrada principal. Muestra información básica sobre la API."""
    return {
        "status": "online",
        "service": "Twitter Recent Tweets Extractor",
        "endpoints": {
            "extract": "/extract/{username}?max_tweets=20&min_tweets=10&max_scrolls=10",
            "status": "/status"
        },
        "docker_environment": DOCKER_ENVIRONMENT,
        "railway_environment": RAILWAY_ENVIRONMENT
    }

@app.get("/status", response_class=JSONResponse)
async def status():
    """Muestra el estado actual del servicio y las extracciones recientes."""
    # Comprobar almacenamiento de sesión
    storage_valid = check_storage_file()
    
    return {
        "status": "online",
        "login_in_progress": login_in_progress,
        "extraction_in_progress": extraction_in_progress,
        "storage_valid": storage_valid,
        "recent_extractions": {k: {"count": len(v), "timestamp": v[0].get("timestamp", "N/A") if v else "N/A"} 
                              for k, v in recent_extractions.items()}
    }

@app.get("/extract/{username}", response_class=JSONResponse)
async def extract_endpoint(
    username: str,
    max_tweets: int = Query(20, ge=1, le=100, description="Máximo número de tweets a extraer"),
    min_tweets: int = Query(10, ge=1, le=50, description="Mínimo número de tweets a extraer"),
    max_scrolls: int = Query(10, ge=1, le=30, description="Máximo número de desplazamientos")
):
    """Extrae tweets recientes para un usuario específico."""
    global extraction_in_progress
    
    # Evitar múltiples extracciones simultáneas
    if extraction_in_progress:
        return {"status": "error", "message": "Ya hay una extracción en progreso. Intente más tarde."}
    
    extraction_in_progress = True
    try:
        # Intentar extraer tweets
        tweets = await extract_recent_tweets(username, max_tweets, min_tweets, max_scrolls)
        
        if not tweets:
            return {"status": "error", "message": "No se pudieron extraer tweets."}
        
        # Añadir al caché
        recent_extractions[username] = tweets
        
        # Devolver resultados
        return {
            "status": "success",
            "username": username,
            "tweet_count": len(tweets),
            "tweets": tweets
        }
    except Exception as e:
        logger.error(f"Error al extraer tweets: {e}")
        return {"status": "error", "message": f"Error al extraer tweets: {str(e)}"}
    finally:
        extraction_in_progress = False 

@app.post("/extract_recent", response_model=ExtractionResponse)
async def api_extract_recent(request: ExtractionRequest):
    try:
        # Extraer tweets recientes
        tweets = await extract_recent_tweets(
            request.username, 
            request.max_tweets, 
            request.min_tweets,
            request.max_scrolls
        )
        
        if not tweets:
            return {
                "status": "error",
                "message": "No se pudieron extraer tweets recientes",
                "tweets": [],
                "count": 0
            }
        
        # Calcular el rango de fechas
        date_range = {}
        try:
            formatted_dates = []
            for t in tweets:
                try:
                    timestamp = t['timestamp']
                    if 'Z' in timestamp:
                        dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    else:
                        dt = pd.to_datetime(timestamp).to_pydatetime()
                    formatted_dates.append(dt)
                except Exception as e:
                    logger.warning(f"Error al formatear fecha: {e}")
            
            if formatted_dates:
                first_date = min(formatted_dates).strftime('%Y-%m-%d %H:%M')
                last_date = max(formatted_dates).strftime('%Y-%m-%d %H:%M')
                date_range = {
                    "first_date": first_date,
                    "last_date": last_date
                }
        except Exception as e:
            logger.error(f"Error al procesar fechas: {e}")
        
        return {
            "status": "success",
            "message": f"Se extrajeron {len(tweets)} tweets recientes",
            "tweets": tweets,
            "count": len(tweets),
            "date_range": date_range
        }
        
    except Exception as e:
        logger.error(f"Error en API: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"Error al extraer tweets: {str(e)}"
        )

async def perform_login():
    """
    Realiza un login automático en Twitter usando Firefox y guarda las cookies
    para su uso posterior. Se ejecuta cuando se detecta que las cookies han expirado.
    """
    global login_in_progress
    
    if login_in_progress:
        logger.warning("Ya hay un proceso de login en curso")
        return False
        
    login_in_progress = True
    logger.info("Iniciando proceso de login automático en Twitter")
    
    try:
        async with async_playwright() as p:
            # Lanzar navegador Firefox con configuración específica para Docker
            firefox_args = []
            launch_options = {
                "headless": IS_HEADLESS,  # Headless solo en Docker/Railway, visible en local
            }
            
            if DOCKER_ENVIRONMENT or RAILWAY_ENVIRONMENT:
                # Configuraciones adicionales para entornos Docker/Railway
                firefox_args.extend([
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-setuid-sandbox",
                ])
                launch_options["firefox_user_prefs"] = {
                    "network.cookie.cookieBehavior": 0,
                    "privacy.trackingprotection.enabled": False
                }
            
            logger.info(f"Lanzando navegador con headless={IS_HEADLESS}")
                
            launch_options["args"] = firefox_args
            
            browser = await p.firefox.launch(**launch_options)
            context = await browser.new_context()
            page = await context.new_page()
            
            try:
                # Navegar a Twitter login
                logger.info("Navegando a Twitter login...")
                await page.goto("https://twitter.com/i/flow/login")
                
                # Esperar a que cargue la página
                await page.wait_for_load_state("networkidle")
                
                # Ingresar usuario
                logger.info(f"Ingresando usuario: {TWITTER_USERNAME}")
                try:
                    await page.wait_for_selector('input[autocomplete="username"]', timeout=30000)
                    await page.fill('input[autocomplete="username"]', TWITTER_USERNAME)
                except Exception as e:
                    logger.error(f"Error al encontrar campo de usuario: {e}")
                    if DOCKER_ENVIRONMENT:
                        await page.screenshot(path="/tmp/login_error_username.png")
                    return False
                
                # Hacer clic en Siguiente
                logger.info("Haciendo clic en Siguiente...")
                next_button = await page.query_selector('div[role="button"]:has-text("Next")')
                if next_button:
                    await next_button.click()
                else:
                    logger.info("Botón Next no encontrado, presionando Enter")
                    await page.press('input[autocomplete="username"]', 'Enter')
                
                # Esperar antes de ingresar contraseña
                await asyncio.sleep(3)
                
                # Ingresar contraseña
                logger.info("Ingresando contraseña...")
                try:
                    password_input = await page.wait_for_selector('input[type="password"]', timeout=30000)
                    await password_input.fill(TWITTER_PASSWORD)
                except Exception as e:
                    logger.error(f"Error al encontrar campo de contraseña: {e}")
                    if DOCKER_ENVIRONMENT:
                        await page.screenshot(path="/tmp/login_error_password.png")
                    return False
                
                # Hacer clic en Log in
                logger.info("Haciendo clic en Log in...")
                login_button = await page.query_selector('div[role="button"]:has-text("Log in")')
                if login_button:
                    await login_button.click()
                else:
                    logger.info("Botón Log in no encontrado, presionando Enter")
                    await page.press('input[type="password"]', 'Enter')
                
                # Esperar a que inicie sesión
                logger.info("Esperando inicio de sesión...")
                await asyncio.sleep(10)
                
                # Verificar si estamos en la página de inicio
                current_url = page.url
                logger.info(f"URL actual: {current_url}")
                
                if "twitter.com/home" in current_url or "x.com/home" in current_url or "/flow/login" not in current_url:
                    logger.info("¡Inicio de sesión exitoso!")
                    
                    # Guardar estado para uso posterior
                    logger.info(f"Guardando estado de la sesión en {STORAGE_FILE}...")
                    await context.storage_state(path=STORAGE_FILE)
                    logger.info(f"Estado guardado en {STORAGE_FILE}")
                    
                    # Navegar a una página de perfil para verificar
                    test_profile = "KarinHerreraVP"
                    logger.info(f"Verificando acceso a perfil de prueba: {test_profile}")
                    await page.goto(f"https://twitter.com/{test_profile}")
                    await asyncio.sleep(5)
                    
                    return True
                else:
                    logger.error("No se detectó inicio de sesión exitoso")
                    if DOCKER_ENVIRONMENT:
                        await page.screenshot(path="/tmp/login_error.png")
                    return False
                
            except Exception as e:
                logger.error(f"Error durante el proceso de login: {e}")
                if DOCKER_ENVIRONMENT:
                    try:
                        await page.screenshot(path="/tmp/login_exception.png")
                    except:
                        pass
                return False
                
            finally:
                # Cerrar navegador
                await browser.close()
                logger.info("Navegador de login cerrado.")
    except Exception as e:
        logger.error(f"Error general en el proceso de login: {e}")
        return False
    finally:
        login_in_progress = False

def check_storage_file():
    """
    Verifica si el archivo de almacenamiento de Firefox existe y es válido.
    También comprueba la fecha de modificación para ver si ha expirado.
    """
    storage_path = Path(STORAGE_FILE)
    
    # Verificar si existe
    if not storage_path.exists():
        logger.warning(f"Archivo de estado {STORAGE_FILE} no encontrado.")
        return False
    
    # Verificar si es un JSON válido
    try:
        with open(storage_path, 'r') as f:
            storage_data = json.load(f)
            
        # Verificar si tiene cookies
        if 'cookies' not in storage_data or not storage_data['cookies']:
            logger.warning(f"Archivo de estado {STORAGE_FILE} no contiene cookies válidas.")
            return False
            
        # Verificar fecha de modificación (más de 24 horas = expirado)
        mod_time = storage_path.stat().st_mtime
        mod_date = datetime.fromtimestamp(mod_time)
        if (datetime.now() - mod_date) > timedelta(hours=24):
            logger.warning(f"Archivo de estado {STORAGE_FILE} tiene más de 24 horas (creado el {mod_date.isoformat()})")
            return False
            
        return True
        
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"Error al leer archivo de estado {STORAGE_FILE}: {e}")
        return False

async def ensure_valid_storage():
    """
    Verifica si existe un archivo de sesión válido. Si no, intenta generarlo con login.
    """
    if os.path.exists(STORAGE_FILE):
        logger.info("Archivo de sesión encontrado, intentando usarlo.")
        return True

    logger.warning("Archivo de sesión no encontrado. Intentando iniciar sesión.")
    try:
        async with async_playwright() as p:
            browser = await p.firefox.launch(headless=IS_HEADLESS)
            context = await browser.new_context(
                locale="es-ES",
                timezone_id="America/Guatemala",
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            await page.goto("https://twitter.com/login", timeout=30000)

            # --- Aquí deberías automatizar tu login si es posible, o usar cookies cargadas manualmente ---
            logger.warning("Login manual requerido: por favor, inicia sesión en la ventana que se abre (si headless=False)")

            # Pausa para login manual (solo si no es headless)
            if not IS_HEADLESS:
                logger.info("Esperando 60 segundos para que completes el login...")
                await asyncio.sleep(60)

            # Guardar estado de sesión
            await context.storage_state(path=STORAGE_FILE)
            await browser.close()
            logger.info("Sesión guardada exitosamente.")
            return True
    except Exception as e:
        logger.error(f"No se pudo crear archivo de sesión: {e}")
        return False


MAX_RETRIES = 3  # Número máximo de reintentos para operaciones de navegador

async def extract_recent_tweets(username, max_tweets=20, min_tweets=10, max_scrolls=10):
    """
    Extrae SOLO tweets recientes usando EXCLUSIVAMENTE la URL de búsqueda con filtro "live"
    y fecha dinámica para garantizar los tweets más recientes.
    """
    logger.info(f"Iniciando extracción FORZADA de tweets RECIENTES para @{username}")
    logger.info(f"Parámetros: max_tweets={max_tweets}, min_tweets={min_tweets}, max_scrolls={max_scrolls}")
    
    # Verificar y asegurar cookies válidas
    for attempt in range(MAX_RETRIES):
        try:
            if not await ensure_valid_storage():
                logger.error("No se pudieron obtener cookies válidas, abortando extracción")
                return []
            break
        except Exception as e:
            if "Target page, context or browser has been closed" in str(e):
                if attempt < MAX_RETRIES - 1:
                    logger.warning(f"El navegador se cerró inesperadamente durante la validación de cookies (intento {attempt+1}/{MAX_RETRIES}). Reintentando...")
                    await asyncio.sleep(2)  # Esperar un poco antes de reintentar
                else:
                    logger.error(f"Error persistente al validar cookies después de {MAX_RETRIES} intentos: {e}")
                    return []
            else:
                logger.error(f"Error al validar cookies: {e}")
                return []
    
    # Obtener fechas para filtros dinámicos
    now = datetime.utcnow()
    today = now.strftime('%Y-%m-%d')
    yesterday = (now - timedelta(days=1)).strftime('%Y-%m-%d')
    last_week = (now - timedelta(days=7)).strftime('%Y-%m-%d')
    last_month = (now - timedelta(days=30)).strftime('%Y-%m-%d')
    
    logger.info(f"Fechas para filtros - Hora actual UTC: {now.isoformat()}, Hoy: {today}, Último mes: {last_month}")
    
    tweets = []
    pinned_tweet_ids = set()
    
    # Configurar opciones específicas para Docker/Railway
    firefox_args = []
    launch_options = {
        "headless": IS_HEADLESS,  # Usar variable global IS_HEADLESS
    }
    
    if DOCKER_ENVIRONMENT or RAILWAY_ENVIRONMENT:
        firefox_args.extend([
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-setuid-sandbox",
        ])
        launch_options["firefox_user_prefs"] = {
            "network.cookie.cookieBehavior": 0,
            "privacy.trackingprotection.enabled": False
        }
    
    logger.info(f"Lanzando navegador (extracción) con headless={IS_HEADLESS}")
        
    launch_options["args"] = firefox_args
    
    # Control de reintentos para problemas de navegador
    for browser_attempt in range(MAX_RETRIES):
        try:
            async with async_playwright() as p:
                # Usar Firefox para consistencia
                browser = await p.firefox.launch(**launch_options)
                
                try:
                    context_options = {"storage_state": STORAGE_FILE}
                    context = await browser.new_context(**context_options)
                    page = await context.new_page()
                    

                    # Aumentar los tiempos de espera por defecto para evitar errores de timeout
                    page.set_default_timeout(30000)  # 30 segundos en entornos Docker/Railway
                    
                    now = datetime.utcnow()
                    
                    # Lista de URLs a intentar, OPTIMIZADA para tweets recientes y con contenido
                    search_urls = [
                        # MÉTODO QUE FUNCIONÓ - Búsqueda directa con f=live (primer intento)
                        f"https://x.com/search?q=from%3A{username}&f=live",
                        
                        # Ir directamente al perfil para tweets más completos
                        f"https://x.com/{username}",
                        
                        # Búsqueda con rango amplio para asegurar volumen de tweets - última semana
                        f"https://x.com/search?q=from%3A{username}%20since%3A{last_week}&f=live",
                        
                        # Búsqueda con parámetro específico de fecha (último mes) para capturar más tweets
                        f"https://x.com/search?q=from%3A{username}%20since%3A{last_month}&f=live"
                    ]
                    
                    all_tweets = []
                    login_error = False
                    
                    for url_index, search_url in enumerate(search_urls):
                        if len(all_tweets) >= max_tweets * 1.5:  # Si ya tenemos 1.5x el número deseado, podemos parar
                            logger.info(f"Ya se recolectaron suficientes tweets ({len(all_tweets)}), deteniendo búsqueda")
                            break
                        
                        try:
                            logger.info(f"Intento #{url_index+1}: Navegando a búsqueda: {search_url}")
                            
                            # Manejar errores de navegación con reintentos
                            for nav_attempt in range(3):  # Máximo 3 intentos para navegar
                                try:
                                    await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                                    break
                                except Exception as nav_error:
                                    if "Target page, context or browser has been closed" in str(nav_error):
                                        raise nav_error  # Si el navegador está cerrado, salir del bucle principal
                                    if nav_attempt < 2:  # Si no es el último intento
                                        logger.warning(f"Error al navegar (intento {nav_attempt+1}/3): {nav_error}. Reintentando...")
                                        await asyncio.sleep(2)
                                    else:
                                        logger.error(f"Error persistente al navegar después de 3 intentos: {nav_error}")
                                        continue  # Intentar con la siguiente URL
                            
                            await asyncio.sleep(5)  # Esperar a que cargue la página
                            
                            # Verificar URL actual
                            current_url = page.url
                            logger.info(f"URL actual: {current_url}")
                            
                            # Verificar si fuimos redirigidos a login
                            if "/login" in current_url or "/i/flow/login" in current_url:
                                logger.warning("Redirigido a login, la sesión expiró. Iniciando login automático...")
                                
                                screenshot_path = "/tmp/login_redirect.png" if DOCKER_ENVIRONMENT else f"login_redirect_{username}_{url_index}.png"
                                await page.screenshot(path=screenshot_path)
                                
                                # Cerrar la sesión actual y navegador
                                await browser.close()
                                
                                # Realizar un nuevo login
                                login_success = await perform_login()
                                if not login_success:
                                    logger.error("No se pudo iniciar sesión de nuevo. Abortando extracción.")
                                    login_error = True
                                    break
                                
                                # Reiniciar el navegador con las nuevas cookies
                                browser = await p.firefox.launch(**launch_options)
                                context = await browser.new_context(storage_state=STORAGE_FILE)
                                page = await context.new_page()
                                page.set_default_timeout(15000)
                                
                                # Volver a intentar la URL actual
                                logger.info(f"Reintentando URL después de renovar sesión: {search_url}")
                                await page.goto(search_url, wait_until="domcontentloaded")
                                await asyncio.sleep(5)
                                
                                # Verificar URL de nuevo
                                current_url = page.url
                                if "/login" in current_url or "/i/flow/login" in current_url:
                                    logger.error("Seguimos siendo redirigidos a login a pesar del nuevo inicio de sesión.")
                                    login_error = True
                                    break
                            
                            # Forzar la pestaña "Latest" si hay pestañas disponibles y si estamos en una búsqueda
                            if "search" in current_url and "f=live" not in current_url:
                                latest_tab = await page.query_selector('a[href*="f=live"], a:has-text("Latest"), a:has-text("Recientes")')
                                if latest_tab:
                                    logger.info("Seleccionando pestaña 'Latest/Recientes'")
                                    await latest_tab.click()
                                    await asyncio.sleep(3)
                            
                            # Scroll inicial para asegurar carga completa
                            logger.info("Realizando desplazamiento inicial para cargar la página completamente")
                            for i in range(3):
                                await page.evaluate('window.scrollBy(0, 1000)')
                                await asyncio.sleep(1)
                            
                            # Capturar pantalla para diagnóstico (solo en entorno no Docker)
                            if not DOCKER_ENVIRONMENT:
                                screenshot_path = f"page_initial_{username}_{url_index}.png"
                                await page.screenshot(path=screenshot_path)
                                logger.info(f"Captura inicial guardada: {screenshot_path}")
                            
                            # Scroll AGRESIVO para cargar más tweets
                            logger.info(f"Iniciando desplazamiento AGRESIVO para cargar tweets (máx {max_scrolls})")
                            
                            tweet_count_previous = 0
                            no_new_tweets_count = 0
                            
                            for scroll_idx in range(max_scrolls):
                                logger.info(f"Desplazamiento {scroll_idx+1}/{max_scrolls}")
                                
                                # Desplazar hacia abajo con movimiento agresivo
                                await page.evaluate('window.scrollBy(0, 2500)')
                                await asyncio.sleep(1)
                                
                                # Verificar cada 2 scrolls o en el último
                                if scroll_idx % 2 == 0 or scroll_idx == max_scrolls - 1:
                                    # Contar tweets después de desplazar
                                    tweet_count = await _count_tweets(page)
                                    logger.info(f"Tweets encontrados tras desplazamiento {scroll_idx+1}: {tweet_count}")
                                    
                                    # Detectar si ya no aparecen nuevos tweets
                                    if tweet_count == tweet_count_previous:
                                        no_new_tweets_count += 1
                                        if no_new_tweets_count >= 3:  # Si 3 veces seguidas no hay nuevos tweets
                                            logger.info(f"No se detectan nuevos tweets después de {no_new_tweets_count} intentos, deteniendo scrolls")
                                            break
                                    else:
                                        no_new_tweets_count = 0
                                        tweet_count_previous = tweet_count
                                    
                                    # Tomar screenshots ocasionalmente (solo en entorno no Docker)
                                    if not DOCKER_ENVIRONMENT and scroll_idx % 4 == 0:
                                        screenshot_path = f"page_scroll_{username}_{url_index}_{scroll_idx}.png"
                                        await page.screenshot(path=screenshot_path)
                                        logger.info(f"Captura guardada: {screenshot_path}")
                                    
                                    # Si encontramos suficientes tweets, podemos parar
                                    if tweet_count >= max_tweets * 3:  # Extraer el triple para tener margen de filtrado
                                        logger.info(f"Se encontraron suficientes tweets ({tweet_count}), deteniendo desplazamiento")
                                        break
                            
                            # Extraer datos de tweets para esta URL
                            logger.info(f"Extrayendo datos de tweets desde URL #{url_index+1}...")
                            current_tweets = await _extract_tweets_data(page, max_tweets*2)  # Extraer el doble para tener margen
                            
                            if current_tweets and len(current_tweets) > 0:
                                logger.info(f"Se encontraron {len(current_tweets)} tweets en URL #{url_index+1}")
                                
                                # Agregar a la lista general, evitando duplicados
                                existing_ids = {t['tweet_id'] for t in all_tweets}
                                new_tweets = [t for t in current_tweets if t['tweet_id'] not in existing_ids]
                                
                                if new_tweets:
                                    logger.info(f"Añadiendo {len(new_tweets)} tweets no duplicados a la lista general")
                                    all_tweets.extend(new_tweets)
                            else:
                                logger.warning(f"No se encontraron tweets en URL #{url_index+1}")
                        
                        except Exception as url_error:
                            if "Target page, context or browser has been closed" in str(url_error):
                                raise url_error  # Propagar el error para reiniciar todo el proceso
                            logger.error(f"Error procesando URL #{url_index+1}: {url_error}")
                            continue  # Intentar con la siguiente URL
                    
                    # Verificar si hubo un error de login que no se pudo resolver
                    if login_error:
                        logger.error("La extracción se detuvo debido a un problema persistente con la sesión.")
                        return []
                    
                    # Guardar el HTML de la página final para diagnóstico en entorno Docker
                    if DOCKER_ENVIRONMENT:
                        html_content = await page.content()
                        with open(f"/tmp/final_page_content_{username}.html", "w", encoding="utf-8") as f:
                            f.write(html_content)
                        logger.info(f"HTML de la página final guardado en /tmp/final_page_content_{username}.html")
                    
                    # Ordenar tweets por timestamp (más recientes primero)
                    if all_tweets:
                        # Primero filtrar tweets sin contenido (eliminar analytics, photo, etc.)
                        filtered_tweets = [t for t in all_tweets if not (
                            "photo" in t['tweet_id'] or 
                            "analytics" in t['tweet_id'] or 
                            t['text'].startswith("[Contenido no disponible") or
                            len(t['text']) < 10  # Eliminar tweets demasiado cortos
                        )]
                        
                        logger.info(f"Filtrados {len(all_tweets) - len(filtered_tweets)} tweets sin contenido real")
                        
                        # Ordenar por fecha, más recientes primero
                        filtered_tweets.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
                        logger.info(f"Total de tweets extraídos, filtrados y ordenados: {len(filtered_tweets)}")
                        
                        # Mostrar info de los tweets más recientes para debug
                        if len(filtered_tweets) > 0:
                            try:
                                most_recent = filtered_tweets[0]
                                date_str = datetime.fromisoformat(most_recent['timestamp'].replace('Z', '+00:00')).strftime('%Y-%m-%d %H:%M')
                                logger.info(f"Tweet más reciente: {date_str} - {most_recent['text'][:50]}...")
                            except Exception as e:
                                logger.error(f"Error al mostrar información del tweet más reciente: {e}")
                        
                        # Asignar a la variable de retorno, limitando al máximo
                        tweets = filtered_tweets[:max_tweets]
                    else:
                        logger.warning("No se encontraron tweets en ningún intento")
                    
                except Exception as e:
                    if "Target page, context or browser has been closed" in str(e):
                        raise e  # Propagar el error para reiniciar todo el proceso
                    logger.error(f"Error durante la extracción: {e}")
                    logger.error(traceback.format_exc())
                    
                    # Capturar pantalla en caso de error
                    try:
                        screenshot_path = "/tmp/error.png" if DOCKER_ENVIRONMENT else f"error_{username}.png"
                        await page.screenshot(path=screenshot_path)
                        logger.info(f"Captura de error guardada: {screenshot_path}")
                    except Exception as screenshot_error:
                        logger.warning(f"No se pudo capturar pantalla de error: {screenshot_error}")
                
                finally:
                    try:
                        await browser.close()
                        logger.info("Navegador cerrado correctamente")
                    except Exception as close_error:
                        logger.warning(f"Error al cerrar el navegador: {close_error}")
            
            # Si llegamos aquí sin excepciones, salir del bucle de reintentos
            break
            
        except Exception as browser_error:
            if "Target page, context or browser has been closed" in str(browser_error):
                if browser_attempt < MAX_RETRIES - 1:
                    logger.warning(f"El navegador se cerró inesperadamente (intento {browser_attempt+1}/{MAX_RETRIES}). Reintentando...")
                    await asyncio.sleep(3)  # Esperar un poco más entre reintentos
                else:
                    logger.error(f"Error persistente con el navegador después de {MAX_RETRIES} intentos: {browser_error}")
            else:
                logger.error(f"Error fatal durante la extracción: {browser_error}")
                logger.error(traceback.format_exc())
                break
    
    total_tweets = len(tweets)
    logger.info(f"Total de tweets RECIENTES extraídos: {total_tweets}")
    
    if total_tweets < min_tweets:
        logger.warning(f"Se extrajeron menos tweets ({total_tweets}) que el mínimo requerido ({min_tweets})")
    
    return tweets 

async def _count_tweets(page):
    """Cuenta el número de tweets en la página actual de manera más eficiente y robusta"""
    # Selectors ordenados por prioridad (de más específico a menos específico)
    selectors = [
        'article[data-testid="tweet"]',
        'div[data-testid="cellInnerDiv"]',
        'div[data-testid="tweet"]',
        'article[role="article"]',
        'div[role="article"]',
        'div[data-testid="tweetText"]',  # Contenido de texto de tweets
        'a[href*="/status/"]'  # Buscar enlaces a tweets directamente
    ]
    
    # Intentar cada selector hasta encontrar uno que funcione
    total_count = 0
    best_selector = None
    
    for selector in selectors:
        try:
            # Usar evaluación JavaScript para contar elementos más rápido
            count = await page.evaluate(f'document.querySelectorAll("{selector}").length')
            
            if count > total_count:
                total_count = count
                best_selector = selector
                
                # Si encontramos suficientes, podemos detenernos para ahorrar tiempo
                if total_count > 10:
                    break
        except Exception as e:
            logger.debug(f"Error al contar con selector '{selector}': {e}")
    
    if total_count > 0:
        logger.info(f"Encontrados {total_count} tweets con selector '{best_selector}'")
    else:
        logger.warning("No se detectaron tweets con los selectores estándar")
        
        # Intentar detectar elementos que podrían ser tweets usando JavaScript más avanzado
        try:
            # Buscar cualquier elemento que pueda contener tweets
            count_js = await page.evaluate('''() => {
                // Buscar por atributos específicos de Twitter
                const tweetAttributes = [
                    'article[data-testid="tweet"]',
                    'div[data-testid="cellInnerDiv"]',
                    'div[data-testid="tweet"]',
                    'article[role="article"]',
                    'div[role="article"]',
                    'div[data-testid="tweetText"]',
                    'a[href*="/status/"]'
                ];
                
                let maxCount = 0;
                for (const attr of tweetAttributes) {
                    const count = document.querySelectorAll(attr).length;
                    maxCount = Math.max(maxCount, count);
                }
                
                // Si no encontramos nada, intentar buscar elementos que podrían ser tweets
                if (maxCount === 0) {
                    // Buscar elementos que contengan enlaces con /status/ en su URL
                    const links = Array.from(document.querySelectorAll('a[href*="/status/"]'));
                    const uniqueStatusIds = new Set();
                    
                    links.forEach(link => {
                        const href = link.getAttribute('href');
                        if (href.includes('/status/')) {
                            const statusId = href.split('/status/')[1].split('?')[0];
                            uniqueStatusIds.add(statusId);
                        }
                    });
                    
                    return uniqueStatusIds.size;
                }
                
                return maxCount;
            }''')
            
            if count_js > 0:
                logger.info(f"Detección JavaScript avanzada encontró {count_js} posibles tweets")
                total_count = max(total_count, count_js)
        except Exception as e:
            logger.error(f"Error en detección avanzada: {e}")
    
    return total_count

async def _extract_tweets_data(page, max_tweets=20):
    """
    Extrae datos de tweets de la página actual de forma más robusta y eficiente,
    asegurando que solo se extraigan tweets con contenido real
    """
    logger.info(f"Extrayendo datos de tweets (máx {max_tweets})")
    
    # Selectores para encontrar tweets, ordenados por prioridad
    tweet_selectors = [
        'article[data-testid="tweet"]',
        'div[data-testid="cellInnerDiv"]',
        'div[data-testid="tweet"]',
        'article[role="article"]',
        'div[role="article"]'
    ]
    
    # Encontrar el mejor selector para tweets
    all_tweets = []
    best_selector = None
    
    for selector in tweet_selectors:
        try:
            elements = await page.query_selector_all(selector)
            if len(elements) > len(all_tweets):
                all_tweets = elements
                best_selector = selector
                
                # Si encontramos suficientes, no necesitamos probar más selectores
                if len(all_tweets) >= max_tweets + 10:  # +10 para permitir filtrado más agresivo
                    break
        except Exception:
            pass
    
    if best_selector:
        logger.info(f"Usando selector '{best_selector}' con {len(all_tweets)} elementos")
    
    # Si no encontramos tweets con los selectores estándar
    if not all_tweets or len(all_tweets) == 0:
        # Último recurso: buscar enlaces a tweets y trabajar desde allí
        logger.info("Buscando enlaces a tweets como alternativa...")
        status_links = await page.query_selector_all('a[href*="/status/"]')
        
        # Convertir enlaces a tweet containers
        if status_links:
            logger.info(f"Encontrados {len(status_links)} enlaces a tweets, intentando extraer contenedores")
            temp_containers = []
            for link in status_links[:min(80, len(status_links))]:  # Aumentado a 80 enlaces para tener más opciones
                try:
                    # Verificar si este enlace tiene un tweet_id
                    href = await link.get_attribute('href')
                    if "/status/" in href and "/photo/" not in href and "/analytics" not in href:
                        # Encontrar el contenedor más cercano que podría ser un tweet
                        container = await link.evaluate('node => { const article = node.closest("article"); if (article) return article; const div = node.closest("div[role=\'article\']"); if (div) return div; return node.closest("div[data-testid]"); }')
                        if container:
                            temp_containers.append(container)
                except Exception:
                    pass
            
            # Filtrar elementos duplicados
            seen_ids = set()
            unique_containers = []
            for container in temp_containers:
                try:
                    # Usar una propiedad única para identificar el elemento
                    container_id = await container.evaluate('node => node.outerHTML.substring(0, 100)')
                    if container_id not in seen_ids:
                        seen_ids.add(container_id)
                        unique_containers.append(container)
                except Exception:
                    pass
            
            if unique_containers:
                logger.info(f"Encontrados {len(unique_containers)} contenedores de tweets únicos")
                all_tweets = unique_containers
    
    # Procesar los tweets encontrados
    tweets_data = []
    processed_ids = set()
    
    for idx, tweet_element in enumerate(all_tweets):
        if len(tweets_data) >= max_tweets:
            logger.info(f"Se alcanzó el máximo de tweets a extraer ({max_tweets})")
            break
        
        try:
            # Verificar si es un tweet promocionado o fijado - método simple
            element_html = await tweet_element.evaluate('node => node.outerHTML')
            
            if "Promoted" in element_html or "Pinned" in element_html or "Fijado" in element_html or "Promocionado" in element_html:
                logger.info(f"Saltando tweet #{idx+1} promocionado o fijado")
                continue
            
            # Extraer el ID del tweet
            tweet_id = None
            try:
                # Buscar enlaces con status/ en ellos (método más confiable)
                href = await tweet_element.evaluate('node => { const links = node.querySelectorAll("a[href*=\'/status/\']"); return links.length > 0 ? links[0].href : null; }')
                if href and "/status/" in href:
                    # Ignorar enlaces que contengan photo o analytics
                    if "/photo/" in href or "/analytics" in href:
                        logger.info(f"Saltando enlace que parece ser a una foto o analytics: {href}")
                        continue
                    
                    tweet_id = href.split("/status/")[1].split("?")[0].split("/")[0]  # Asegurarse de obtener solo el ID
            except Exception:
                pass
            
            if not tweet_id:
                logger.warning(f"No se pudo extraer ID del tweet #{idx+1}")
                continue
                
            if tweet_id in processed_ids:
                logger.info(f"Saltando tweet #{idx+1} duplicado")
                continue
            
            # Extraer el texto del tweet - método mejorado
            tweet_text = await tweet_element.evaluate('node => { const textElements = node.querySelectorAll("div[data-testid=\'tweetText\'], div[lang], div[dir=\'auto\']"); let text = ""; for (const el of textElements) { text += el.textContent + " "; } return text.replace(/\\s+/g, " ").trim(); }')
            
            # Verificar si el tweet tiene texto real y no es demasiado corto (como "Hola")
            if not tweet_text or len(tweet_text) < 5:
                logger.info(f"Saltando tweet #{idx+1} sin texto o muy corto: '{tweet_text}'")
                continue
                
            # Filtrar texto muy corto como "Hola" que probablemente no sea un tweet real
            if tweet_text.lower() in ["hola", "hello", "hi", "test", "prueba"]:
                logger.info(f"Saltando tweet #{idx+1} con texto genérico: '{tweet_text}'")
                continue
            
            # Filtrar tweets con muchos caracteres CJK (chino, japonés, coreano)
            if has_many_cjk(tweet_text, ratio=0.3):
                logger.info(f"Saltando tweet #{idx+1} con muchos caracteres CJK: '{tweet_text[:30]}...'")
                continue
                
            # Verificar contenido después de quitar URLs, menciones y hashtags
            cleaned_text = ' '.join([word for word in tweet_text.split() if not (word.startswith('http') or word.startswith('@') or word.startswith('#'))])
            if len(cleaned_text) < 10:
                logger.info(f"Saltando tweet #{idx+1} con contenido insuficiente después de quitar URLs/menciones: '{cleaned_text}'")
                continue
                
            # Extraer el nombre de usuario - método mejorado
            username = await tweet_element.evaluate('node => { const nameElements = node.querySelectorAll("div[data-testid=\'User-Name\'], a[role=\'link\'] div[dir=\'ltr\']"); return nameElements.length > 0 ? nameElements[0].textContent.replace(/\\s+/g, " ").trim() : "Desconocido"; }')
            
            # Verificar que el nombre de usuario contiene el username que estamos buscando
            if username == "Desconocido":
                logger.info(f"Saltando tweet #{idx+1} con usuario desconocido")
                continue
            
            # Extraer el timestamp
            timestamp = await tweet_element.evaluate('node => { const timeElement = node.querySelector("time"); return timeElement ? timeElement.getAttribute("datetime") : ""; }')
            if not timestamp:
                logger.info(f"Saltando tweet #{idx+1} sin timestamp")
                continue
            
            # Verificación adicional: Asegurarse de que el timestamp tenga formato ISO
            try:
                datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            except ValueError:
                logger.warning(f"Timestamp inválido en tweet #{idx+1}: {timestamp}. Saltando tweet.")
                continue
            
            # Añadir ID a procesados
            processed_ids.add(tweet_id)
            
            # Añadir a los resultados
            tweets_data.append({
                'tweet_id': tweet_id,
                'username': username,
                'text': tweet_text,
                'timestamp': timestamp
            })
            
            logger.info(f"Tweet {len(tweets_data)} extraído: ID {tweet_id}, fecha {timestamp}, texto: {tweet_text[:50]}...")
            
        except Exception as e:
            logger.error(f"Error al extraer datos del tweet {idx}: {e}")
    
    # Verificar que los tweets tengan suficiente contenido
    if len(tweets_data) > 0:
        # Ordenar por longitud de texto (privilegiar tweets con más contenido)
        tweets_data.sort(key=lambda x: len(x['text']), reverse=True)
        
        # Filtrar cualquier tweet que solo tenga URLs sin contexto
        filtered_tweets = []
        for tweet in tweets_data:
            # Verificar si el texto solo contiene URLs o menciones sin contexto adicional
            text = tweet['text']
            words = text.split()
            non_url_words = [w for w in words if not (w.startswith('http') or w.startswith('@') or w.startswith('#'))]
            
            if len(non_url_words) > 1:  # Al menos dos palabras que no sean URLs o menciones
                filtered_tweets.append(tweet)
            else:
                logger.info(f"Filtrando tweet con solo URLs o menciones: {text[:30]}...")
        
        # Actualizar tweets_data con los tweets filtrados
        tweets_data = filtered_tweets[:max_tweets]
    
    logger.info(f"Extracción completada: {len(tweets_data)} tweets con contenido real")
    return tweets_data 

# Función para salvar resultados a CSV (útil para ejecución local)
def save_results_to_csv(tweets, username):
    """
    Guarda los tweets extraídos en un archivo CSV
    """
    if not tweets:
        logger.warning("No hay tweets para guardar")
        return None
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"tweets_recientes_{username}_{timestamp}.csv"
    
    df = pd.DataFrame(tweets)
    
    # Añadir numeración
    df['tweet_num'] = range(1, len(df) + 1)
    
    # Reorganizar columnas
    columns = ['tweet_num', 'tweet_id', 'username', 'text', 'timestamp']
    df = df[columns]
    
    # Guardar a CSV
    df.to_csv(filename, index=False)
    logger.info(f"Tweets RECIENTES guardados en {filename}")
    
    return filename

# Ejecución como línea de comandos para entornos locales
async def main_async():
    """Función principal asincrónica para ejecución local"""
    if len(sys.argv) < 2:
        print(f"Uso: {sys.argv[0]} <username> [max_tweets] [min_tweets] [max_scrolls]")
        sys.exit(1)
    
    username = sys.argv[1].replace("@", "")  # Eliminar @ si se incluyó
    
    # Parámetros opcionales
    max_tweets = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    min_tweets = int(sys.argv[3]) if len(sys.argv) > 3 else 10
    max_scrolls = int(sys.argv[4]) if len(sys.argv) > 4 else 10
    
    print(f"\n===== EXTRACCIÓN FORZADA DE TWEETS RECIENTES =====")
    print(f"Usuario: @{username}")
    print(f"Parámetros: máx={max_tweets}, mín={min_tweets}, scrolls={max_scrolls}")
    print("Iniciando extracción...")
    print("="*50)
    
    # Extraer tweets RECIENTES
    tweets = await extract_recent_tweets(username, max_tweets, min_tweets, max_scrolls)
    
    # Guardar resultados
    if tweets:
        filename = save_results_to_csv(tweets, username)
        # Mostrar resumen
        print(f"\n===== RESUMEN DE EXTRACCIÓN DE TWEETS RECIENTES =====")
        print(f"Usuario: @{username}")
        print(f"Total de tweets extraídos: {len(tweets)}")
        
        if len(tweets) > 0:
            try:
                # Convertir timestamps a datetime de manera segura
                formatted_dates = []
                for t in tweets:
                    try:
                        timestamp = t['timestamp']
                        if 'Z' in timestamp:
                            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                        else:
                            dt = pd.to_datetime(timestamp).to_pydatetime()
                        formatted_dates.append(dt)
                    except Exception as e:
                        logger.warning(f"Error al formatear fecha: {e}")
                
                if formatted_dates:
                    first_date = min(formatted_dates).strftime('%Y-%m-%d %H:%M')
                    last_date = max(formatted_dates).strftime('%Y-%m-%d %H:%M')
                    print(f"Rango de fechas: {first_date} hasta {last_date}")
                
                # Mostrar los primeros tweets (los más recientes)
                print("\nPRIMEROS 5 TWEETS (MÁS RECIENTES):")
                for i, tweet in enumerate(tweets[:5]):
                    try:
                        timestamp = tweet['timestamp']
                        if 'Z' in timestamp:
                            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                        else:
                            dt = pd.to_datetime(timestamp).to_pydatetime()
                        date = dt.strftime('%Y-%m-%d %H:%M')
                        text = tweet['text'].replace('\n', ' ')[:100] + ('...' if len(tweet['text']) > 100 else '')
                        print(f"{i+1}. [{date}] {text}")
                    except Exception as e:
                        logger.warning(f"Error al formatear tweet: {e}")
                        print(f"{i+1}. [Fecha no disponible] {tweet['text'][:100]}...")
            except Exception as e:
                logger.error(f"Error al procesar fechas: {e}")
            
            print(f"\nArchivo guardado: {filename}")
        
        print("="*50)
    else:
        logger.error("No se pudieron extraer tweets RECIENTES")
        print("\n¡ERROR! No se pudieron extraer tweets RECIENTES.")
        print("Revise los logs para más información.")
        
def main():
    """Función principal que maneja el event loop"""
    # En modo local, ejecutar como script
    if not (DOCKER_ENVIRONMENT or RAILWAY_ENVIRONMENT):
        try:
            # Ejecutar como API local para pruebas
            port = int(os.environ.get("PORT", 8000))
            logger.info(f"Iniciando servidor API local en el puerto {port}")
            import uvicorn
            uvicorn.run(app, host="0.0.0.0", port=port)
        except KeyboardInterrupt:
            logger.info("Proceso interrumpido por el usuario")
            print("\nProceso interrumpido por el usuario")
        except Exception as e:
            logger.error(f"Error en la ejecución: {e}")
            print(f"\nError en la ejecución: {e}")
    # En modo Docker/Railway, ejecutar como API
    else:
        # Configure the health check endpoint
        @app.get("/health")
        async def health_check():
            return {"status": "healthy", "timestamp": datetime.now().isoformat()}
        
        # Run the FastAPI app with Uvicorn
        port = int(os.environ.get("PORT", 8000))
        import uvicorn
        logger.info(f"Iniciando servidor API en el puerto {port}")
        uvicorn.run(app, host="0.0.0.0", port=port)

@app.get("/extract_hashtag/{hashtag}", response_class=JSONResponse)
async def extract_hashtag_endpoint(
    hashtag: str,
    max_tweets: int = Query(20, ge=1, le=100, description="Máximo número de tweets a extraer"),
    min_tweets: int = Query(10, ge=1, le=50, description="Mínimo número de tweets a extraer"),
    max_scrolls: int = Query(10, ge=1, le=30, description="Máximo número de desplazamientos")
):
    """Extrae tweets recientes para un hashtag específico."""
    global extraction_in_progress
    
    # Normalizar el hashtag (eliminar # si se incluyó)
    hashtag = hashtag.strip().replace("#", "")
    
    # Evitar múltiples extracciones simultáneas
    if extraction_in_progress:
        return {"status": "error", "message": "Ya hay una extracción en progreso. Intente más tarde."}
    
    extraction_in_progress = True
    try:
        # Intentar extraer tweets
        tweets = await extract_hashtag_tweets(hashtag, max_tweets, min_tweets, max_scrolls)
        
        if not tweets:
            return {"status": "error", "message": "No se pudieron extraer tweets."}
        
        # Añadir al caché
        recent_extractions[f"hashtag_{hashtag}"] = tweets
        
        # Devolver resultados
        return {
            "status": "success",
            "hashtag": hashtag,
            "tweet_count": len(tweets),
            "tweets": tweets
        }
    except Exception as e:
        logger.error(f"Error al extraer tweets para hashtag: {e}")
        return {"status": "error", "message": f"Error al extraer tweets para hashtag: {str(e)}"}
    finally:
        extraction_in_progress = False

@app.post("/extract_hashtag_recent", response_model=ExtractionResponse)
async def api_extract_hashtag_recent(request: ExtractionRequest):
    try:
        # Normalizar el hashtag (eliminar # si se incluyó)
        hashtag = request.username.strip().replace("#", "")
        
        # Extraer tweets recientes por hashtag
        tweets = await extract_hashtag_tweets(
            hashtag, 
            request.max_tweets, 
            request.min_tweets,
            request.max_scrolls
        )
        
        if not tweets:
            return {
                "status": "error",
                "message": "No se pudieron extraer tweets recientes para el hashtag",
                "tweets": [],
                "count": 0
            }
        
        # Calcular el rango de fechas
        date_range = {}
        try:
            formatted_dates = []
            for t in tweets:
                try:
                    timestamp = t['timestamp']
                    if 'Z' in timestamp:
                        dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    else:
                        dt = pd.to_datetime(timestamp).to_pydatetime()
                    formatted_dates.append(dt)
                except Exception as e:
                    logger.warning(f"Error al formatear fecha: {e}")
            
            if formatted_dates:
                first_date = min(formatted_dates).strftime('%Y-%m-%d %H:%M')
                last_date = max(formatted_dates).strftime('%Y-%m-%d %H:%M')
                date_range = {
                    "first_date": first_date,
                    "last_date": last_date
                }
        except Exception as e:
            logger.error(f"Error al procesar fechas: {e}")
        
        return {
            "status": "success",
            "message": f"Se extrajeron {len(tweets)} tweets recientes para el hashtag #{hashtag}",
            "tweets": tweets,
            "count": len(tweets),
            "date_range": date_range
        }
        
    except Exception as e:
        logger.error(f"Error en API de hashtags: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"Error al extraer tweets para hashtag: {str(e)}"
        )

async def extract_hashtag_tweets(hashtag, max_tweets=20, min_tweets=10, max_scrolls=10, lang="es", search_mode="top"):
    """
    Extrae tweets con un hashtag específico usando la URL de búsqueda con filtro específico
    
    Args:
        hashtag (str): Hashtag a buscar (sin #)
        max_tweets (int): Número máximo de tweets a extraer
        min_tweets (int): Número mínimo de tweets a extraer
        max_scrolls (int): Número máximo de scrolls en la página
        lang (str): Idioma de los tweets ("es", "en", etc.)
        search_mode (str): Modo de búsqueda: 'top' para tweets populares, 'live' para tiempo real
    """
    logger.info(f"Iniciando extracción de tweets para el hashtag #{hashtag} en idioma {lang} (modo: {search_mode})")
    logger.info(f"Parámetros: max_tweets={max_tweets}, min_tweets={min_tweets}, max_scrolls={max_scrolls}")
    
    # Verificar y asegurar cookies válidas
    if not await ensure_valid_storage():
        logger.error("No se pudieron obtener cookies válidas, abortando extracción")
        return []
    
    # Preparación para entornos Docker/Railway
    firefox_args = []
    launch_options = {
        "headless": IS_HEADLESS,  # Usar variable global IS_HEADLESS
    }
    
    if DOCKER_ENVIRONMENT or RAILWAY_ENVIRONMENT:
        firefox_args.extend([
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-setuid-sandbox",
        ])
        launch_options["firefox_user_prefs"] = {
            "network.cookie.cookieBehavior": 0,
            "privacy.trackingprotection.enabled": False
        }
    
    logger.info(f"Lanzando navegador (hashtag) con headless={IS_HEADLESS}")
        
    launch_options["args"] = firefox_args
    
    # Preparación para entornos Docker/Railway
    now = datetime.utcnow()
    last_week = (now - timedelta(days=7)).strftime('%Y-%m-%d')
    last_month = (now - timedelta(days=30)).strftime('%Y-%m-%d')
    
    # Control de reintentos para problemas de navegador
    for browser_attempt in range(MAX_RETRIES):
        try:
            async with async_playwright() as p:
                # Usar Firefox para consistencia
                browser = await p.firefox.launch(**launch_options)
                
                try:
                    context_options = {"storage_state": STORAGE_FILE}
                    context = await browser.new_context(**context_options)
                    page = await context.new_page()
                    
                    # Aumentar los tiempos de espera por defecto para evitar errores de timeout
                    page.set_default_timeout(30000)  # 30 segundos en entornos Docker/Railway
                    
                    # Determinar el modo de búsqueda
                    filter_mode = "top" if search_mode == "top" else "live"
                    
                    # Construir parte del filtro de idioma si se especificó
                    lang_filter = f"%20lang%3A{lang}" if lang else ""
                    
                    # Lista de URLs a intentar, optimizada para tweets de hashtags, incluyendo filtro de idioma
                    # y modo de búsqueda (top o live)
                    search_urls = [
                        f"https://x.com/search?q=%23{hashtag}{lang_filter}&f={filter_mode}",
                        f"https://x.com/hashtag/{hashtag}?f={filter_mode}", 
                        f"https://x.com/search?q=%23{hashtag}{lang_filter}%20since%3A{last_week}&f={filter_mode}",
                        f"https://x.com/search?q=%23{hashtag}{lang_filter}%20since%3A{last_month}&f={filter_mode}"
                    ]
                    
                    all_tweets = []
                    login_error = False
                    
                    for url_index, search_url in enumerate(search_urls):
                        if len(all_tweets) >= max_tweets * 1.5:  # Si ya tenemos 1.5x el número deseado, podemos parar
                            logger.info(f"Ya se recolectaron suficientes tweets ({len(all_tweets)}), deteniendo búsqueda")
                            break
                        
                        try:
                            logger.info(f"Intento #{url_index+1}: Navegando a búsqueda de hashtag: {search_url}")
                            
                            # Manejar errores de navegación con reintentos
                            for nav_attempt in range(3):  # Máximo 3 intentos para navegar
                                try:
                                    await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                                    break
                                except Exception as nav_error:
                                    if "Target page, context or browser has been closed" in str(nav_error):
                                        raise nav_error  # Si el navegador está cerrado, salir del bucle principal
                                    if nav_attempt < 2:  # Si no es el último intento
                                        logger.warning(f"Error al navegar (intento {nav_attempt+1}/3): {nav_error}. Reintentando...")
                                        await asyncio.sleep(2)
                                    else:
                                        logger.error(f"Error persistente al navegar después de 3 intentos: {nav_error}")
                                        continue  # Intentar con la siguiente URL
                            
                            await asyncio.sleep(5)  # Esperar a que cargue la página
                            
                            # Verificar URL actual
                            current_url = page.url
                            logger.info(f"URL actual: {current_url}")
                            
                            # Verificar si fuimos redirigidos a login
                            if "/login" in current_url or "/i/flow/login" in current_url:
                                logger.warning("Redirigido a login, la sesión expiró. Iniciando login automático...")
                                
                                screenshot_path = "/tmp/login_redirect_hashtag.png" if DOCKER_ENVIRONMENT else f"login_redirect_hashtag_{hashtag}_{url_index}.png"
                                await page.screenshot(path=screenshot_path)
                                
                                # Cerrar la sesión actual y navegador
                                await browser.close()
                                
                                # Realizar un nuevo login
                                login_success = await perform_login()
                                if not login_success:
                                    logger.error("No se pudo iniciar sesión de nuevo. Abortando extracción.")
                                    login_error = True
                                    break
                                
                                # Reiniciar el navegador con las nuevas cookies
                                browser = await p.firefox.launch(**launch_options)
                                context = await browser.new_context(storage_state=STORAGE_FILE)
                                page = await context.new_page()
                                page.set_default_timeout(15000)
                                
                                # Volver a intentar la URL actual
                                logger.info(f"Reintentando URL después de renovar sesión: {search_url}")
                                await page.goto(search_url, wait_until="domcontentloaded")
                                await asyncio.sleep(5)
                                
                                # Verificar URL de nuevo
                                current_url = page.url
                                if "/login" in current_url or "/i/flow/login" in current_url:
                                    logger.error("Seguimos siendo redirigidos a login a pesar del nuevo inicio de sesión.")
                                    login_error = True
                                    break
                            
                            # Verificar si estamos en la pestaña correcta según el modo de búsqueda
                            if "search" in current_url:
                                # Si queremos "top" tweets pero la URL no tiene f=top, seleccionar pestaña Top
                                if search_mode == "top" and "f=top" not in current_url:
                                    top_tab = await page.query_selector('a[href*="f=top"], a:has-text("Top"), a:has-text("Destacado")')
                                    if top_tab:
                                        logger.info("Seleccionando pestaña 'Top/Destacado'")
                                        await top_tab.click()
                                        await asyncio.sleep(3)
                                # Si queremos "live" tweets pero la URL no tiene f=live, seleccionar pestaña Latest
                                elif search_mode == "live" and "f=live" not in current_url:
                                    latest_tab = await page.query_selector('a[href*="f=live"], a:has-text("Latest"), a:has-text("Recientes")')
                                    if latest_tab:
                                        logger.info("Seleccionando pestaña 'Latest/Recientes'")
                                        await latest_tab.click()
                                        await asyncio.sleep(3)
                            
                            # Scroll inicial para asegurar carga completa
                            logger.info("Realizando desplazamiento inicial para cargar la página completamente")
                            for i in range(3):
                                await page.evaluate('window.scrollBy(0, 1000)')
                                await asyncio.sleep(1)
                            
                            # Capturar pantalla para diagnóstico (solo en entorno no Docker)
                            if not DOCKER_ENVIRONMENT:
                                screenshot_path = f"page_initial_hashtag_{hashtag}_{url_index}.png"
                                await page.screenshot(path=screenshot_path)
                                logger.info(f"Captura inicial guardada: {screenshot_path}")
                            
                            # Scroll AGRESIVO para cargar más tweets
                            logger.info(f"Iniciando desplazamiento AGRESIVO para cargar tweets (máx {max_scrolls})")
                            
                            tweet_count_previous = 0
                            no_new_tweets_count = 0
                            
                            for scroll_idx in range(max_scrolls):
                                logger.info(f"Desplazamiento {scroll_idx+1}/{max_scrolls}")
                                
                                # Desplazar hacia abajo con movimiento agresivo
                                await page.evaluate('window.scrollBy(0, 2500)')
                                await asyncio.sleep(1)
                                
                                # Verificar cada 2 scrolls o en el último
                                if scroll_idx % 2 == 0 or scroll_idx == max_scrolls - 1:
                                    # Contar tweets después de desplazar
                                    tweet_count = await _count_tweets(page)
                                    logger.info(f"Tweets encontrados tras desplazamiento {scroll_idx+1}: {tweet_count}")
                                    
                                    # Detectar si ya no aparecen nuevos tweets
                                    if tweet_count == tweet_count_previous:
                                        no_new_tweets_count += 1
                                        if no_new_tweets_count >= 3:  # Si 3 veces seguidas no hay nuevos tweets
                                            logger.info(f"No se detectan nuevos tweets después de {no_new_tweets_count} intentos, deteniendo scrolls")
                                            break
                                    else:
                                        no_new_tweets_count = 0
                                        tweet_count_previous = tweet_count
                                    
                                    # Tomar screenshots ocasionalmente (solo en entorno no Docker)
                                    if not DOCKER_ENVIRONMENT and scroll_idx % 4 == 0:
                                        screenshot_path = f"page_scroll_hashtag_{hashtag}_{url_index}_{scroll_idx}.png"
                                        await page.screenshot(path=screenshot_path)
                                        logger.info(f"Captura guardada: {screenshot_path}")
                                    
                                    # Si encontramos suficientes tweets, podemos parar
                                    if tweet_count >= max_tweets * 3:  # Extraer el triple para tener margen de filtrado
                                        logger.info(f"Se encontraron suficientes tweets ({tweet_count}), deteniendo desplazamiento")
                                        break
                            
                            # Extraer datos de tweets para esta URL
                            logger.info(f"Extrayendo datos de tweets para hashtag desde URL #{url_index+1}...")
                            current_tweets = await _extract_tweets_data(page, max_tweets*2)  # Extraer el doble para tener margen
                            
                            if current_tweets and len(current_tweets) > 0:
                                logger.info(f"Se encontraron {len(current_tweets)} tweets para hashtag en URL #{url_index+1}")
                                
                                # Agregar a la lista general, evitando duplicados
                                existing_ids = {t['tweet_id'] for t in all_tweets}
                                new_tweets = [t for t in current_tweets if t['tweet_id'] not in existing_ids]
                                
                                if new_tweets:
                                    logger.info(f"Añadiendo {len(new_tweets)} tweets no duplicados a la lista general")
                                    all_tweets.extend(new_tweets)
                            else:
                                logger.warning(f"No se encontraron tweets para hashtag en URL #{url_index+1}")
                        
                        except Exception as url_error:
                            if "Target page, context or browser has been closed" in str(url_error):
                                raise url_error  # Propagar el error para reiniciar todo el proceso
                            logger.error(f"Error procesando URL #{url_index+1} para hashtag: {url_error}")
                            continue  # Intentar con la siguiente URL
                    
                    # Verificar si hubo un error de login que no se pudo resolver
                    if login_error:
                        logger.error("La extracción del hashtag se detuvo debido a un problema persistente con la sesión.")
                        return []
                    
                    # Guardar el HTML de la página final para diagnóstico en entorno Docker
                    if DOCKER_ENVIRONMENT:
                        html_content = await page.content()
                        with open(f"/tmp/final_page_content_hashtag_{hashtag}.html", "w", encoding="utf-8") as f:
                            f.write(html_content)
                        logger.info(f"HTML de la página final guardado en /tmp/final_page_content_hashtag_{hashtag}.html")
                    
                    # Ordenar tweets por timestamp (más recientes primero)
                    if all_tweets:
                        # Primero filtrar tweets sin contenido (eliminar analytics, photo, etc.)
                        filtered_tweets = [t for t in all_tweets if not (
                            "photo" in t['tweet_id'] or 
                            "analytics" in t['tweet_id'] or 
                            t['text'].startswith("[Contenido no disponible") or
                            len(t['text']) < 10  # Eliminar tweets demasiado cortos
                        )]
                        
                        logger.info(f"Filtrados {len(all_tweets) - len(filtered_tweets)} tweets sin contenido real")
                        
                        # Verificar que los tweets contengan el hashtag (caso insensitivo)
                        hashtag_tweets = []
                        for t in filtered_tweets:
                            text_lower = t['text'].lower()
                            if f"#{hashtag.lower()}" in text_lower or f" {hashtag.lower()} " in text_lower:
                                hashtag_tweets.append(t)
                            
                        logger.info(f"Encontrados {len(hashtag_tweets)} tweets con el hashtag #{hashtag}")
                        
                        # Ordenar por fecha, más recientes primero
                        hashtag_tweets.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
                        logger.info(f"Total de tweets extraídos para hashtag, filtrados y ordenados: {len(hashtag_tweets)}")
                        
                        # Mostrar info de los tweets más recientes para debug
                        if len(hashtag_tweets) > 0:
                            try:
                                most_recent = hashtag_tweets[0]
                                date_str = datetime.fromisoformat(most_recent['timestamp'].replace('Z', '+00:00')).strftime('%Y-%m-%d %H:%M')
                                logger.info(f"Tweet más reciente para #{hashtag}: {date_str} - {most_recent['text'][:50]}...")
                            except Exception as e:
                                logger.error(f"Error al mostrar información del tweet más reciente: {e}")
                        
                        # Asignar a la variable de retorno, limitando al máximo
                        tweets = hashtag_tweets[:max_tweets]
                    else:
                        logger.warning(f"No se encontraron tweets para el hashtag #{hashtag} en ningún intento")
                    
                except Exception as e:
                    if "Target page, context or browser has been closed" in str(e):
                        raise e  # Propagar el error para reiniciar todo el proceso
                    logger.error(f"Error durante la extracción del hashtag: {e}")
                    logger.error(traceback.format_exc())
                    
                    # Capturar pantalla en caso de error
                    try:
                        screenshot_path = "/tmp/error_hashtag.png" if DOCKER_ENVIRONMENT else f"error_hashtag_{hashtag}.png"
                        await page.screenshot(path=screenshot_path)
                        logger.info(f"Captura de error guardada: {screenshot_path}")
                    except Exception as screenshot_error:
                        logger.warning(f"No se pudo capturar pantalla de error: {screenshot_error}")
                
                finally:
                    try:
                        await browser.close()
                        logger.info("Navegador cerrado correctamente")
                    except Exception as close_error:
                        logger.warning(f"Error al cerrar el navegador: {close_error}")
            
            # Si llegamos aquí sin excepciones, salir del bucle de reintentos
            break
            
        except Exception as browser_error:
            if "Target page, context or browser has been closed" in str(browser_error):
                if browser_attempt < MAX_RETRIES - 1:
                    logger.warning(f"El navegador se cerró inesperadamente (intento {browser_attempt+1}/{MAX_RETRIES}). Reintentando...")
                    await asyncio.sleep(3)  # Esperar un poco más entre reintentos
                else:
                    logger.error(f"Error persistente con el navegador después de {MAX_RETRIES} intentos: {browser_error}")
            else:
                logger.error(f"Error fatal durante la extracción del hashtag: {browser_error}")
                logger.error(traceback.format_exc())
                break
    
    total_tweets = len(tweets)
    logger.info(f"Total de tweets extraídos para hashtag #{hashtag}: {total_tweets}")
    
    if total_tweets < min_tweets:
        logger.warning(f"Se extrajeron menos tweets ({total_tweets}) que el mínimo requerido ({min_tweets})")
    
    return tweets

# Función para salvar resultados de hashtag a CSV (útil para ejecución local)
def save_hashtag_results_to_csv(tweets, hashtag):
    """
    Guarda los tweets extraídos de un hashtag en un archivo CSV
    """
    if not tweets:
        logger.warning("No hay tweets para guardar")
        return None
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"tweets_hashtag_{hashtag}_{timestamp}.csv"
    
    df = pd.DataFrame(tweets)
    
    # Añadir numeración
    df['tweet_num'] = range(1, len(df) + 1)
    
    # Reorganizar columnas
    columns = ['tweet_num', 'tweet_id', 'username', 'text', 'timestamp']
    df = df[columns]
    
    # Guardar a CSV
    df.to_csv(filename, index=False)
    logger.info(f"Tweets del hashtag #{hashtag} guardados en {filename}")
    
    return filename

# --- Endpoint de tendencias ---
from fastapi import Query

# Mapa de WOEID para ubicaciones soportadas
WOEID_MAP = {
    "guatemala": 23424834,
    "mexico": 23424900,
    "us": 23424977,
    "estados_unidos": 23424977,
    "global": 1
}

# Mejorar función OCR para manejar mejor las tendencias
def ocr_trending_from_image(image_path, source='twitter'):
    """
    Extrae texto de una captura de pantalla de tendencias usando OCR.
    Optimizado para extraer tendencias de Twitter/X y Trends24.
    
    Args:
        image_path: Ruta de la imagen a procesar
        source: Origen de la imagen ('twitter' o 'trends24')
    """
    try:
        img = Image.open(image_path)
        
        # Configuración específica según la fuente
        if source == 'trends24':
            logger.info(f"Procesando OCR para Trends24 desde imagen: {image_path}")
            
            # Para Trends24, usamos configuración especial para tablas
            custom_config = r'--oem 3 --psm 6 -c preserve_interword_spaces=1'
            
            # Intentar mejorar la imagen para OCR
            try:
                # Convertir a escala de grises para mejorar contraste
                img_gray = img.convert('L')
                
                # Aumentar contraste
                enhancer = ImageEnhance.Contrast(img_gray)
                img_contrast = enhancer.enhance(1.5)
                
                # Guardar imagen preprocesada para debug
                preprocessed_path = f"{image_path}_preprocessed.png"
                img_contrast.save(preprocessed_path)
                logger.info(f"Imagen preprocesada guardada en: {preprocessed_path}")
                
                # Usar la imagen mejorada para OCR
                raw_text = pytesseract.image_to_string(img_contrast, lang='spa', config=custom_config)
            except Exception as e:
                logger.warning(f"Error en preprocesamiento de imagen: {e}")
                # Usar imagen original si falló el preprocesamiento
                raw_text = pytesseract.image_to_string(img, lang='spa', config=custom_config)
            
            # Procesamiento específico para Trends24
            trends = extract_trends24_trends(raw_text)
            logger.info(f"OCR Trends24 extrajo {len(trends)} tendencias")
            return trends
        else:
            logger.info(f"Procesando OCR para Twitter/X desde imagen: {image_path}")
            # Configuración para Twitter/X
            custom_config = r'--oem 3 --psm 6'
            raw_text = pytesseract.image_to_string(img, lang='spa', config=custom_config)
            
            # Procesar líneas
            lines = []
            for line in raw_text.split('\n'):
                line = line.strip()
                if not line:
                    continue
                    
                # Limpiar línea
                clean_line = re.sub(r'\s+', ' ', line).strip()
                
                # Filtrar líneas que parecen tendencias
                if (
                    len(clean_line) > 2 and 
                    len(clean_line) < 50 and  # Las tendencias generalmente no son muy largas
                    not clean_line.isdigit() and
                    not any(word.lower() in clean_line.lower() for word in UI_STOPWORDS)
                ):
                    lines.append(clean_line)
            
            # Filtrar tendencias duplicadas
            unique_trends = []
            seen = set()
            for line in lines:
                normalized = normalize_text(line)
                if normalized and normalized not in seen:
                    seen.add(normalized)
                    unique_trends.append(line)
            
            logger.info(f"OCR Twitter/X extrajo {len(unique_trends)} tendencias")
            return unique_trends
    except Exception as e:
        logger.error(f"Error en OCR: {e}")
        logger.error(traceback.format_exc())
        return []

def extract_trends24_trends(raw_text):
    """
    Extrae tendencias específicamente del formato de Trends24.
    Optimizado para detectar la estructura de tabla con rankings, tendencias y conteos.
    """
    trends = []
    lines = raw_text.split('\n')
    
    # Para debug
    logger.debug("===== TEXTO CRUDO DE TRENDS24 =====")
    for i, line in enumerate(lines):
        if line.strip():
            logger.debug(f"Línea {i+1}: {line}")
    
    # Patrones para detectar partes de la tendencia
    position_pattern = re.compile(r'^\s*(\d{1,2})\s*$')  # Números solos: 1, 2, 3...
    trend_number_pattern = re.compile(r'(\d+K|[0-9,.]+K)')  # 32K, 270K, 1.5K, etc.
    
    # Patrones para identificar la estructura de la tabla
    time_headers = ["minutes ago", "hour ago", "hours ago"]
    
    # Nueva estrategia: detectar bloques de tendencias por columna
    # 1. Identificar los encabezados de tiempo (33 minutes ago, 1 hour ago, etc.)
    time_header_indices = []
    for i, line in enumerate(lines):
        for header in time_headers:
            if header in line.lower():
                time_header_indices.append(i)
                break
    
    logger.debug(f"Encabezados de tiempo encontrados en líneas: {time_header_indices}")
    
    # 2. Procesar cada columna por separado
    if time_header_indices:
        # Por cada encabezado de tiempo, procesar las próximas líneas como una columna
        for start_idx in time_header_indices:
            column_trends = []
            i = start_idx + 1  # Comenzar después del encabezado
            
            # Determinar el límite de la columna (siguiente encabezado o final)
            next_idx = next((idx for idx in time_header_indices if idx > start_idx), len(lines))
            
            logger.debug(f"Procesando columna desde línea {start_idx+1} hasta {next_idx}")
            
            # Variables para rastrear la posición actual
            current_position = None
            position_count = 0
            
            while i < next_idx:
                line = lines[i].strip()
                
                # Ignorar líneas vacías
                if not line:
                    i += 1
                    continue
                
                # Verificar si es un número de posición (1-10)
                position_match = position_pattern.match(line)
                if position_match:
                    current_position = position_match.group(1)
                    position_count += 1
                    i += 1
                    
                    # Verificar si la siguiente línea es un nombre de tendencia
                    if i < next_idx and lines[i].strip() and not position_pattern.match(lines[i].strip()):
                        trend_name = lines[i].strip()
                        i += 1
                        
                        # Verificar si la siguiente línea es un conteo
                        trend_count = None
                        if i < next_idx and trend_number_pattern.fullmatch(lines[i].strip()):
                            trend_count = lines[i].strip()
                            i += 1
                        
                        # Añadir la tendencia con formato consistente
                        formatted_trend = f"{position_count}. {trend_name}"
                        if trend_count:
                            formatted_trend += f" ({trend_count})"
                        
                        column_trends.append(formatted_trend)
                        logger.debug(f"Tendencia encontrada: {formatted_trend}")
                elif line.startswith('#') and len(line) > 2:
                    # Es un hashtag, buscar si la siguiente línea es un conteo
                    trend_name = line
                    i += 1
                    
                    # Verificar si la siguiente línea es un conteo
                    trend_count = None
                    if i < next_idx and trend_number_pattern.fullmatch(lines[i].strip()):
                        trend_count = lines[i].strip()
                        i += 1
                    
                    # Si no encontramos posición, usar contador interno
                    if position_count == 0:
                        position_count = len(column_trends) + 1
                    
                    # Añadir la tendencia con formato consistente
                    formatted_trend = f"{position_count}. {trend_name}"
                    if trend_count:
                        formatted_trend += f" ({trend_count})"
                    
                    column_trends.append(formatted_trend)
                    logger.debug(f"Hashtag encontrado: {formatted_trend}")
                else:
                    # Verificar si es una tendencia seguida de un conteo
                    if i+1 < next_idx and trend_number_pattern.fullmatch(lines[i+1].strip()):
                        trend_name = line
                        trend_count = lines[i+1].strip()
                        
                        # Si no encontramos posición, usar contador interno
                        if position_count == 0:
                            position_count = len(column_trends) + 1
                        
                        formatted_trend = f"{position_count}. {trend_name} ({trend_count})"
                        column_trends.append(formatted_trend)
                        logger.debug(f"Tendencia con conteo: {formatted_trend}")
                        
                        i += 2  # Avanzar 2 líneas
                    else:
                        # Verificar si esta línea contiene un conteo al final
                        match = trend_number_pattern.search(line)
                        if match and match.end() == len(line):
                            # Separar tendencia y conteo
                            trend_name = line[:match.start()].strip()
                            trend_count = match.group(0)
                            
                            # Si no encontramos posición, usar contador interno
                            if position_count == 0:
                                position_count = len(column_trends) + 1
                            
                            formatted_trend = f"{position_count}. {trend_name} ({trend_count})"
                            column_trends.append(formatted_trend)
                            logger.debug(f"Tendencia con conteo en misma línea: {formatted_trend}")
                        
                        i += 1  # Avanzar 1 línea
            
            # Añadir tendencias de esta columna
            trends.extend(column_trends)
    
    # Si no se encontraron tendencias con el enfoque de columnas, usar enfoque directo
    if not trends:
        logger.debug("Usando enfoque directo para extraer tendencias")
        prev_number = None
        trend_count = 0
        
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            
            # Ignorar líneas que parecen UI
            if any(word.lower() in line.lower() for word in UI_STOPWORDS):
                continue
            
            # Verificar si es un número de posición (1-10)
            position_match = position_pattern.match(line)
            if position_match:
                prev_number = position_match.group(1)
                trend_count += 1
            elif line.startswith('#') or (len(line.split()) <= 3 and not line.isdigit()):
                # Parece ser un nombre de tendencia
                trend_name = line
                
                # Buscar conteo en la siguiente línea
                trend_count_value = None
                if i+1 < len(lines) and trend_number_pattern.fullmatch(lines[i+1].strip()):
                    trend_count_value = lines[i+1].strip()
                
                # Usar número previo o contador automático
                position = prev_number if prev_number else trend_count
                
                # Añadir la tendencia con formato consistente
                formatted_trend = f"{position}. {trend_name}"
                if trend_count_value:
                    formatted_trend += f" ({trend_count_value})"
                
                trends.append(formatted_trend)
                prev_number = None  # Reiniciar para el próximo ciclo
    
    # Procesar los resultados para eliminar duplicados y asegurar que sean tendencias reales
    unique_trends = []
    seen = set()
    
    for trend in trends:
        # Limpiar y normalizar
        clean_trend = re.sub(r'\s+', ' ', trend).strip()
        
        # Verificar que tenga un formato de ranking y nombre
        if '.' in clean_trend and clean_trend not in seen:
            parts = clean_trend.split('.')
            if len(parts) >= 2 and parts[0].strip().isdigit():
                # Verificar que el nombre no sea solo un número
                trend_text = parts[1].strip()
                if trend_text and not trend_text.isdigit():
                    seen.add(clean_trend)
                    unique_trends.append(clean_trend)
    
    # Si no se encontraron tendencias en formato ranking, devolver lo que se encontró
    if not unique_trends:
        # Filtrado básico para tendencias sin formato específico
        for trend in trends:
            clean_trend = re.sub(r'\s+', ' ', trend).strip()
            if clean_trend and clean_trend not in seen:
                seen.add(clean_trend)
                unique_trends.append(clean_trend)
    
    logger.info(f"Total de tendencias Trends24 extraídas: {len(unique_trends)}")
    return unique_trends

@app.get("/trending", response_class=JSONResponse)
async def trending_endpoint(
    location: str = Query("guatemala", description="Ubicación para obtener tendencias: guatemala, mexico, us"),
    force_refresh: bool = Query(False, description="Forzar actualización ignorando caché")
):
    """
    Devuelve las tendencias de Trends24 para la ubicación indicada.
    Usa métodos directos de extracción de HTML para mayor fiabilidad.
    """
    location_key = location.lower()
    if location_key not in WOEID_MAP:
        return {"status": "error", "message": f"Ubicación no soportada. Opciones: {', '.join(WOEID_MAP.keys())}"}
    
    # Timeout para toda la operación
    start_time = datetime.now()
    
    try:
        logger.info(f"===== INICIANDO EXTRACCIÓN DE TENDENCIAS PARA {location_key.upper()} =====")
        
        # Extraer tendencias de Trends24
        trends24_trends = await scrape_trends24_html(location_key, force_refresh)
            
        # Asegurar que las listas tengan datos válidos
        if not trends24_trends or not isinstance(trends24_trends, list):
            trends24_trends = get_fallback_trends(location_key)
        
        # Limitar las tendencias a 15
        trends24_trends = trends24_trends[:15]
        
        # Calcular tiempo total de ejecución
        execution_time = (datetime.now() - start_time).total_seconds()
        logger.info(f"===== EXTRACCIÓN DE TENDENCIAS COMPLETADA EN {execution_time:.1f} SEGUNDOS =====")
        
        # Devolver los resultados (copiando Trends24 en ambos campos para mantener compatibilidad)
        return {
            "status": "success",
            "location": location_key,
            "twitter_trends": trends24_trends,  # Mismo valor en ambos campos
            "trends24_trends": trends24_trends,
            "execution_time_seconds": execution_time
        }
    except Exception as e:
        # Calcular tiempo de ejecución incluso en caso de error
        execution_time = (datetime.now() - start_time).total_seconds()
        logger.error(f"Error extrayendo tendencias: {e}")
        logger.error(traceback.format_exc())
        logger.error(f"Tiempo hasta error: {execution_time:.1f} segundos")
        return {
            "status": "error", 
            "message": str(e),
            "execution_time_seconds": execution_time
        }

# Función para capturar screenshot de Trends24
async def capture_trends24_screenshot(location_key):
    """
    Navega a Trends24 y captura una screenshot para OCR.
    Optimizado para capturar la tabla de tendencias principales.
    """
    url_map = {
        "guatemala": "guatemala",
        "mexico": "mexico",
        "us": "united-states",
        "estados_unidos": "united-states",
        "global": ""
    }
    country = url_map.get(location_key, "guatemala")
    url = f"https://trends24.in/{country}/" if country else "https://trends24.in/"
    screenshot_path = f"trends24_screenshot_{location_key}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    # Ruta para captura procesada con solo las tablas de tendencias
    processed_screenshot_path = f"trends24_processed_{location_key}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    
    # Configurar opciones específicas para Docker/Railway
    browser_args = []
    launch_options = {
        "headless": IS_HEADLESS,
        "timeout": 60000  # Aumentar el timeout global del navegador a 60 segundos
    }
    
    if DOCKER_ENVIRONMENT or RAILWAY_ENVIRONMENT:
        browser_args.extend([
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-setuid-sandbox",
        ])
    
    # Agregar opciones adicionales para mejorar la conectividad
    browser_args.extend([
        "--disable-web-security",
        "--disable-features=IsolateOrigins,site-per-process",
        "--disable-features=BlockInsecurePrivateNetworkRequests",
        "--disable-blink-features=AutomationControlled",  # Evitar detección de bot
    ])
    
    launch_options["args"] = browser_args
    
    try:
        logger.info(f"Capturando screenshot de Trends24 para {location_key}...")
        async with async_playwright() as p:
            logger.info("Iniciando navegador para Trends24...")
            browser = await p.chromium.launch(**launch_options)
            logger.info("Navegador iniciado correctamente")
            
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},  # Pantalla más grande para mejor captura
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
                locale="es-ES",
                timezone_id="America/Guatemala",
                bypass_csp=True,
                ignore_https_errors=True
            )
            logger.info("Contexto de navegador creado")
            
            page = await context.new_page()
            logger.info("Nueva página creada")
            
            # Intento de navegación con reintentos
            for nav_attempt in range(3):
                try:
                    logger.info(f"Intento de navegación #{nav_attempt+1} a {url}")
                    # Reducir el timeout de navegación para evitar bloqueos
                    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    logger.info("Navegación a Trends24 exitosa")
                    
                    # Verificar si estamos en la pestaña "Timeline"
                    try:
                        # Intentar hacer clic en la pestaña "Timeline" si no está activa
                        timeline_tab = await page.query_selector("text=Timeline")
                        if timeline_tab:
                            logger.info("Haciendo clic en pestaña Timeline...")
                            await timeline_tab.click()
                            await asyncio.sleep(1)
                    except Exception as tab_err:
                        logger.warning(f"Error al seleccionar pestaña Timeline: {tab_err}")
                    
                    # Reducir el tiempo de espera inicial
                    logger.info("Esperando 2 segundos para carga inicial...")
                    await asyncio.sleep(2)
                    logger.info("Espera inicial completada")
                    
                    # Capturar pantalla completa con timeout
                    logger.info("Capturando screenshot...")
                    start_time = datetime.now()
                    await page.screenshot(path=screenshot_path, full_page=True, timeout=10000)
                    end_time = datetime.now()
                    duration = (end_time - start_time).total_seconds()
                    logger.info(f"Screenshot capturado en {duration} segundos")
                    
                    # Intentar recortar específicamente la región de las tablas de tendencias
                    try:
                        logger.info("Identificando regiones de tendencias...")
                        # Intentar encontrar las tablas/columnas de tendencias
                        trend_columns = await page.query_selector_all("div[class*='trend'] > ol, .trend-card, .trend-list, div[class*='trend-item'], div[class*='trend']")
                        
                        if not trend_columns:
                            logger.info("No se encontraron columnas de tendencias con selectores específicos")
                            trend_columns = await page.query_selector_all("ol, ul, .col")
                        
                        if trend_columns:
                            logger.info(f"Se encontraron {len(trend_columns)} columnas potenciales de tendencias")
                            
                            # Crear una imagen compuesta con todas las columnas
                            try:
                                from PIL import Image, ImageDraw
                                
                                # Crear una imagen base
                                base_img = Image.open(screenshot_path)
                                width, height = base_img.size
                                
                                # Crear una imagen en blanco para el resultado procesado
                                processed_img = Image.new('RGB', (width, height), color='white')
                                
                                # Copiar solo las regiones de tendencias
                                for i, column in enumerate(trend_columns):
                                    try:
                                        # Obtener dimensiones y posición del elemento
                                        bbox = await column.bounding_box()
                                        if bbox:
                                            x, y, w, h = bbox['x'], bbox['y'], bbox['width'], bbox['height']
                                            
                                            # Asegurarse de que sea una región válida
                                            if w > 50 and h > 100:  # Ignorar regiones muy pequeñas
                                                logger.info(f"Columna {i+1}: Posición ({x}, {y}), Tamaño {w}x{h}")
                                                
                                                # Recortar y pegar esta región
                                                region = base_img.crop((x, y, x+w, y+h))
                                                processed_img.paste(region, (x, y))
                                                
                                                # Añadir un borde para visualizar mejor
                                                draw = ImageDraw.Draw(processed_img)
                                                draw.rectangle((x, y, x+w, y+h), outline='blue', width=2)
                                    except Exception as col_err:
                                        logger.warning(f"Error procesando columna {i+1}: {col_err}")
                                
                                # Guardar la imagen procesada
                                processed_img.save(processed_screenshot_path)
                                logger.info(f"Imagen procesada guardada en {processed_screenshot_path}")
                                
                                # Usar la imagen procesada para el OCR
                                screenshot_path = processed_screenshot_path
                            except Exception as img_err:
                                logger.error(f"Error procesando imagen: {img_err}")
                        else:
                            logger.warning("No se encontraron columnas de tendencias")
                    except Exception as region_err:
                        logger.error(f"Error identificando regiones: {region_err}")
                    
                    logger.info(f"Screenshot de Trends24 guardado en {screenshot_path}")
                    break
                except Exception as nav_error:
                    logger.warning(f"Error al navegar a Trends24 (intento {nav_attempt+1}/3): {nav_error}")
                    if nav_attempt < 2:
                        await asyncio.sleep(1)  # Tiempo más corto entre reintentos
                    else:
                        # En el último intento, probar con URL alternativa
                        alt_url = "https://trends24.in/"
                        try:
                            logger.info(f"Intentando URL alternativa: {alt_url}")
                            await page.goto(alt_url, wait_until="domcontentloaded", timeout=20000)
                            await asyncio.sleep(2)
                            logger.info("Capturando screenshot de URL alternativa...")
                            await page.screenshot(path=screenshot_path, full_page=True, timeout=10000)
                            logger.info(f"Screenshot de Trends24 (URL alternativa) guardado en {screenshot_path}")
                        except Exception as alt_error:
                            logger.error(f"Error también con URL alternativa: {alt_error}")
                            # Crear una imagen en blanco para evitar errores
                            logger.info("Creando imagen en blanco como fallback")
                            img = Image.new('RGB', (1920, 1080), color='white')
                            img.save(screenshot_path)
                            logger.info("Imagen en blanco creada correctamente")
            
            logger.info("Cerrando navegador...")
            await browser.close()
            logger.info("Navegador cerrado correctamente")
            
    except Exception as e:
        logger.error(f"Error al capturar screenshot de Trends24: {e}")
        logger.error(traceback.format_exc())
        # Crear una imagen en blanco para evitar errores
        logger.info("Creando imagen en blanco debido a error")
        img = Image.new('RGB', (1920, 1080), color='white')
        img.save(screenshot_path)
        logger.info("Imagen en blanco creada correctamente")
    
    logger.info(f"Proceso de captura de Trends24 finalizado, retornando ruta: {screenshot_path}")
    return screenshot_path

# --- Normalización y comparación difusa ---

UI_STOPWORDS = set([
    "home", "explore", "notifications", "messages", "grok", "communities", "premium", "verified orgs", "profile", "more", "today's news", "who to follow", "show more", "arts", "business", "food", "travel", "entertainment", "posts for you", "search", "configuración", "ver más", "más", "inicio", "notificaciones", "mensajes", "comunidades", "perfil", "tendencias", "seguir", "mostrar más", "arte", "negocios", "comida", "viajes", "entretenimiento", "publicaciones para ti", "buscar", "trending in guatemala", "trending in mexico", "trending in united states", "trending in us", "trending", "en guatemala", "en mexico", "en united states", "en us", "global"
])

def normalize_text(text):
    # Minúsculas, quitar acentos, quitar caracteres especiales
    text = text.lower()
    text = ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')
    text = ''.join(c for c in text if c.isalnum() or c in ['#', ' '])
    text = text.strip()
    return text

def filter_ocr_trends(trends):
    filtered = []
    for t in trends:
        norm = normalize_text(t)
        if not norm or norm in UI_STOPWORDS:
            continue
        # Evitar líneas muy cortas o numéricas
        if len(norm) < 3 or norm.isdigit():
            continue
        filtered.append(t)
    return filtered

def fuzzy_match(trend, trend_list, threshold=0.8):
    norm_trend = normalize_text(trend)
    for candidate in trend_list:
        norm_candidate = normalize_text(candidate)
        ratio = difflib.SequenceMatcher(None, norm_trend, norm_candidate).ratio()
        if ratio >= threshold:
            return candidate
    return None

        # Función para hacer scroll en la página y cargar más contenido dinámico
async def auto_scroll(page, scrolls=5, delay=1):
    for _ in range(scrolls):
        await page.evaluate("window.scrollBy(0, window.innerHeight)")
        await asyncio.sleep(delay)

# Modificar get_trending_for_woeid para devolver también la ruta de la screenshot
async def get_trending_for_woeid_with_screenshot(woeid: int):
    logger.info(f"Obteniendo tendencias para WOEID: {woeid}")
    if not await ensure_valid_storage():
        logger.error("No se pudieron obtener cookies válidas, abortando extracción de tendencias")
        return [], None

    trends = []
    screenshot_path = f"trending_screenshot_{woeid}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"

    for browser_attempt in range(MAX_RETRIES):
        try:
            async with async_playwright() as p:
                browser = await p.firefox.launch(headless=IS_HEADLESS, args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-setuid-sandbox",
                ])
                try:
                    context = await browser.new_context(
                        storage_state=STORAGE_FILE,
                        locale="es-ES",
                        timezone_id="America/Guatemala",
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    )

                    page = await context.new_page()
                    url = f"https://twitter.com/i/trends?woeid={woeid}"
                    await page.goto(url, timeout=30000)
                    await asyncio.sleep(3)

                    # Simular actividad de usuario para evitar carga limitada
                    await page.mouse.move(100, 200)
                    await page.mouse.wheel(0, 1000)
                    await asyncio.sleep(1)

                    await page.screenshot(path=screenshot_path, full_page=True)

                    # Buscar tendencias
                    trend_blocks = await page.query_selector_all('[data-testid="trend"]')
                    for block in trend_blocks:
                        try:
                            name_el = await block.query_selector('[data-testid="trendName"], span')
                            name = await name_el.inner_text() if name_el else None
                            count_el = await block.query_selector('span:has-text("Tweets")')
                            count = await count_el.inner_text() if count_el else None
                            kw_els = await block.query_selector_all('span')
                            keywords = []
                            for kw in kw_els:
                                txt = await kw.inner_text()
                                if txt and txt != name and (not count or txt != count):
                                    keywords.append(txt)
                            trends.append({
                                "name": name,
                                "tweet_count": count,
                                "keywords": keywords
                            })
                        except Exception:
                            continue

                    await browser.close()
                    return trends, screenshot_path
                except Exception as e:
                    await browser.close()
                    raise e
        except Exception as browser_error:
            if "Target page, context or browser has been closed" in str(browser_error):
                if browser_attempt < MAX_RETRIES - 1:
                    logger.warning(f"El navegador se cerró inesperadamente (intento {browser_attempt+1}/{MAX_RETRIES}). Reintentando...")
                    await asyncio.sleep(3)
                else:
                    logger.error(f"Error persistente con el navegador después de {MAX_RETRIES} intentos: {browser_error}")
            else:
                logger.error(f"Error fatal durante la extracción de tendencias: {browser_error}")
                logger.error(traceback.format_exc())
                break

    return trends, screenshot_path

# Caché global para tendencias
trends_cache = {}

# Nueva función para extraer tendencias directamente del HTML de Trends24 (versión simplificada)
async def scrape_trends24_html(location_key, force_refresh=False):
    """
    Extrae tendencias directamente del HTML de Trends24 sin capturar screenshots.
    Versión simplificada que usa Playwright directamente.
    
    Args:
        location_key: Clave de ubicación (guatemala, mexico, us, etc)
        force_refresh: Forzar actualización del caché
        
    Returns:
        List[str]: Lista de tendencias encontradas
    """
    # Verificar caché primero
    cache_key = f"trends24_{location_key}"
    max_age_minutes = 30  # Caché de 30 minutos
    
    if not force_refresh and cache_key in trends_cache:
        timestamp, cached_trends = trends_cache[cache_key]
        # Verificar si el caché aún es válido
        if (datetime.now() - timestamp).total_seconds() < max_age_minutes * 60:
            logger.info(f"Usando tendencias en caché para {location_key} (edad: {(datetime.now() - timestamp).total_seconds() / 60:.1f} minutos)")
            return cached_trends
    
    # Mapeo de ubicaciones a URLs
    url_map = {
        "guatemala": "guatemala",
        "mexico": "mexico",
        "us": "united-states",
        "estados_unidos": "united-states",
        "global": ""
    }
    
    country = url_map.get(location_key, "guatemala")
    url = f"https://trends24.in/{country}/" if country else "https://trends24.in/"
    
    logger.info(f"Scrapeando tendencias HTML de Trends24 para {location_key} desde {url}")
    
    # Lista para almacenar tendencias
    all_trends = []
    
    # Intentar extraer con Playwright
    try:
        async with async_playwright() as p:
            # Configuración del navegador
            browser_args = ["--disable-web-security", "--disable-features=IsolateOrigins"]
            browser = await p.chromium.launch(headless=True, timeout=30000, args=browser_args)
            
            try:
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
                    locale="es-ES"
                )
                
                page = await context.new_page()
                
                # Navegar a la URL con timeout reducido
                await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                
                # Esperar brevemente para cargar el contenido dinámico
                await asyncio.sleep(2)
                
                # Extraer tendencias directamente del HTML usando JavaScript
                trends_data = await page.evaluate("""() => {
                    const trendsData = [];
                    // Buscar elementos de tendencia
                    const trendItems = document.querySelectorAll('.trend-card li, ol li, .trend-item, a.trend');
                    
                    // Si no encontramos elementos específicos, buscar más genéricamente
                    const items = trendItems.length > 0 ? trendItems : document.querySelectorAll('li');
                    
                    // Procesar cada elemento
                    items.forEach((item, index) => {
                        const text = item.textContent.trim();
                        // Filtrar elementos de UI o vacíos
                        if (text && text.length > 1 && text.length < 50) {
                            trendsData.push({
                                position: index + 1,
                                text: text
                            });
                        }
                    });
                    return trendsData;
                }""")
                
                # Procesar los datos obtenidos
                if trends_data:
                    for trend in trends_data:
                        formatted_trend = f"{trend['position']}. {trend['text']}"
                        all_trends.append(formatted_trend)
                    
                    logger.info(f"Se encontraron {len(all_trends)} tendencias mediante Playwright")
            except Exception as e:
                logger.error(f"Error al extraer tendencias: {e}")
            finally:
                await browser.close()
    except Exception as p_error:
        logger.error(f"Error con Playwright: {p_error}")
    
    # Si no se encontraron tendencias, usar tendencias de fallback
    if not all_trends:
        logger.warning(f"No se pudieron extraer tendencias de Trends24. Usando fallback.")
        all_trends = get_fallback_trends(location_key)
    
    # Eliminar duplicados y filtrar
    unique_trends = []
    seen = set()
    
    for trend in all_trends:
        # Normalizar y limpiar
        clean_trend = re.sub(r'\s+', ' ', trend).strip()
        
        # Verificar que no esté ya incluido y que no sea un elemento de UI
        normalized = normalize_text(clean_trend)
        if normalized and normalized not in seen and not any(word.lower() in normalized for word in UI_STOPWORDS):
            seen.add(normalized)
            unique_trends.append(clean_trend)
    
    # Guardar en caché
    trends_cache[cache_key] = (datetime.now(), unique_trends)
    
    logger.info(f"Total de tendencias únicas de Trends24: {len(unique_trends)}")
    return unique_trends

def get_fallback_trends(location_key="guatemala"):
    """
    Genera tendencias de fallback para cuando el scraping falla.
    Las tendencias son genéricas y típicas para cada ubicación.
    
    Args:
        location_key: Clave de ubicación
        
    Returns:
        List[str]: Lista de tendencias de fallback
    """
    logger.info(f"Generando tendencias de fallback para {location_key}")
    
    # Mapa de tendencias comunes por ubicación
    fallback_trends = {
        "guatemala": [
            "1. Guatemala",
            "2. #Guatemala",
            "3. Gobierno",
            "4. Congreso",
            "5. #FelizDomingo",
            "6. Presidente",
            "7. #BuenViernes",
            "8. COVID-19",
            "9. Municipalidad",
            "10. Zona 10"
        ],
        "mexico": [
            "1. México",
            "2. #México",
            "3. AMLO",
            "4. Gobierno de México",
            "5. #FelizDomingo",
            "6. Presidente",
            "7. CDMX",
            "8. #BuenViernes",
            "9. COVID-19",
            "10. Zócalo"
        ],
        "us": [
            "1. #USA",
            "2. Trump",
            "3. Biden",
            "4. COVID-19",
            "5. Election",
            "6. NFL",
            "7. Breaking News",
            "8. Congress",
            "9. White House",
            "10. NBA"
        ],
        "global": [
            "1. COVID-19",
            "2. #WorldNews",
            "3. Football",
            "4. Climate Change",
            "5. #Breaking",
            "6. #News",
            "7. Olympics",
            "8. Economy",
            "9. UEFA",
            "10. Technology"
        ]
    }
    
    # Obtener tendencias para la ubicación solicitada o usar las de Guatemala como default
    return fallback_trends.get(location_key, fallback_trends["guatemala"])

# Función para convertir texto de estadísticas (como "1.2K") a números enteros
def parse_count_text(count_text):
    """
    Convierte texto de estadísticas como "1.2K", "5,6K", "2M" a números enteros.
    """
    if not count_text:
        return 0
    
    # Eliminar espacios y caracteres no alfanuméricos excepto puntos y comas
    count_text = count_text.strip()
    # Si no hay texto, retornar 0
    if not count_text or count_text == "":
        return 0
        
    try:
        # Reemplazar comas por puntos para normalizar formato
        normalized = count_text.replace(',', '.').lower()
        
        if 'k' in normalized:
            # Ejemplo: "1.2K" -> 1200
            value = float(normalized.replace('k', ''))
            return int(value * 1000)
        elif 'm' in normalized:
            # Ejemplo: "3.4M" -> 3400000
            value = float(normalized.replace('m', ''))
            return int(value * 1000000)
        else:
            # Intentar convertir directamente a entero
            return int(float(normalized))
    except (ValueError, TypeError):
        logger.warning(f"No se pudo convertir '{count_text}' a número")
        return 0

def has_many_cjk(text, ratio=0.3):
    """
    Detecta si un texto tiene una alta proporción de caracteres CJK (chino, japonés, coreano).
    
    Args:
        text (str): Texto a analizar
        ratio (float): Proporción mínima de caracteres CJK para considerar que tiene muchos (0.0-1.0)
        
    Returns:
        bool: True si la proporción de caracteres CJK es mayor o igual a ratio
    """
    if not text:
        return False
        
    total = len(text)
    # Contar caracteres CJK (rangos Unicode para chino, japonés y coreano)
    cjk = sum(1 for ch in text if '\u4e00' <= ch <= '\u9fff' or  # CJK Unified Ideographs
                               '\u3040' <= ch <= '\u30ff' or      # Hiragana y Katakana
                               '\u3130' <= ch <= '\u318f' or      # Hangul Compatibility Jamo
                               '\uac00' <= ch <= '\ud7af')        # Hangul Syllables
    
    # Calcular proporción y comparar con el umbral
    return total > 0 and cjk / total >= ratio

class HashtagDetailExtractor:
    """
    Clase para extraer detalles avanzados de tweets con un hashtag específico, 
    incluyendo métricas (likes, replies, retweets, views) y comentarios.
    """
    
    def __init__(self, hashtag, max_tweets=20, min_tweets=10, max_scrolls=10, 
                include_comments=True, comment_limit=10, time_limit_seconds=250,
                lang="es", min_likes=10, search_mode="top"):
        """
        Inicializa el extractor con los parámetros necesarios.
        
        Args:
            hashtag (str): Hashtag a buscar (sin #)
            max_tweets (int): Número máximo de tweets a extraer
            min_tweets (int): Número mínimo de tweets a extraer
            max_scrolls (int): Número máximo de scrolls en la página
            include_comments (bool): Si se incluyen comentarios en los resultados
            comment_limit (int): Número máximo de comentarios por tweet
            time_limit_seconds (int): Límite de tiempo en segundos para la extracción completa
            lang (str): Idioma de los tweets a buscar (es, en, pt, etc.)
            min_likes (int): Número mínimo de likes que debe tener un tweet para ser incluido
            search_mode (str): Modo de búsqueda: 'top' para tweets populares, 'live' para tiempo real
        """
        self.hashtag = hashtag.strip().replace("#", "")
        self.max_tweets = max_tweets
        self.min_tweets = min_tweets
        self.max_scrolls = max_scrolls
        self.include_comments = include_comments
        self.comment_limit = comment_limit
        self.time_limit_seconds = time_limit_seconds
        self.lang = lang.lower() if lang else "es"
        self.min_likes = max(0, min_likes)  # Asegurar que no sea negativo
        self.search_mode = search_mode.lower() if search_mode in ["top", "live"] else "top"
        self.start_time = None
        self.logger = logging.getLogger(__name__)
        
        # Verificar si Selenium está disponible
        self.use_selenium = SELENIUM_AVAILABLE
        
    def _check_time_limit(self):
        """Verifica si se ha excedido el límite de tiempo"""
        if not self.start_time:
            return False
        
        elapsed = (datetime.now() - self.start_time).total_seconds()
        return elapsed >= self.time_limit_seconds
    
    def _create_empty_enriched_tweet(self, tweet):
        """Helper para crear un tweet enriquecido vacío"""
        enriched_tweet = tweet.copy()
        enriched_tweet.update({
            "likes": 0,
            "replies": 0,
            "reposts": 0,
            "views": 0,
            "comments": [],
            "should_exclude": True
        })
        return enriched_tweet

    async def _verify_page_loaded(self, page):
        """
        Verifica que la página ha cargado elementos claves
        """
        try:
            # Verificar si existe algún elemento clave en la página
            elements_exist = await page.evaluate("""() => {
                // Buscar elementos que indiquen que la página ha cargado
                const tweet = document.querySelector('article, [data-testid="tweet"]');
                const tweetText = document.querySelector('[data-testid="tweetText"]');
                const userSection = document.querySelector('[data-testid="User-Name"]');
                
                return {
                    tweetFound: !!tweet,
                    textFound: !!tweetText,
                    userFound: !!userSection
                };
            }""")
            
            # Determinar si la página está suficientemente cargada
            page_ready = elements_exist.get('tweetFound') or elements_exist.get('textFound')
            self.logger.info(f"Estado de carga: Tweet={elements_exist.get('tweetFound')}, Texto={elements_exist.get('textFound')}")
            return page_ready
        except Exception as e:
            self.logger.error(f"Error verificando carga de página: {e}")
            return False

    async def _extract_metrics_enhanced(self, page):
        """
        Extrae métricas con múltiples estrategias para mayor fiabilidad
        """
        counts = {
            "likes": 0, 
            "replies": 0,
            "reposts": 0,
            "views": 0
        }
        
        try:
            # Estrategia 1: Usar selectores modernos y alternativos
            metrics_modern = await page.evaluate("""() => {
                const getMetric = (selectors) => {
                    for (const selector of selectors) {
                        const elements = document.querySelectorAll(selector);
                        for (const el of elements) {
                            const text = el.textContent.trim();
                            if (/^[\\d,.]+[KkMm]?$/.test(text)) {
                                return text;
                            }
                        }
                    }
                    return "0";
                };
                
                return {
                    likes: getMetric([
                        '[data-testid="like"] span[data-testid="app-text-transition-container"]',
                        'div[role="button"] [aria-label*="Like"] span',
                        'div[data-testid="like"] span'
                    ]),
                    replies: getMetric([
                        '[data-testid="reply"] span[data-testid="app-text-transition-container"]', 
                        'div[role="button"] [aria-label*="repl"] span',
                        'div[data-testid="reply"] span'
                    ]),
                    reposts: getMetric([
                        '[data-testid="retweet"] span[data-testid="app-text-transition-container"]',
                        'div[role="button"] [aria-label*="Retweet"] span',
                        'div[data-testid="retweet"] span'
                    ]),
                    views: getMetric([
                        '[data-testid="analyticsButton"] span',
                        'a[href*="analytics"] span',
                        'div[data-testid="viewCount"] span'
                    ])
                };
            }""")
            
            # Estrategia 2: Analizar grupo de métricas (frecuentemente están juntas)
            if all(not metrics_modern.get(k) or metrics_modern.get(k) == "0" for k in metrics_modern):
                metrics_group = await page.evaluate("""() => {
                    // Buscar grupos de métricas (suelen estar en divs con role="group")
                    const groupElements = document.querySelectorAll('div[role="group"]');
                    for (const group of groupElements) {
                        const spans = group.querySelectorAll('span');
                        const numbers = Array.from(spans)
                            .map(s => s.textContent.trim())
                            .filter(t => /^[\\d,.]+[KkMm]?$/.test(t));
                        
                        if (numbers.length >= 3) {
                            return {
                                replies: numbers[0] || "0",
                                reposts: numbers[1] || "0", 
                                likes: numbers[2] || "0",
                                views: numbers.length >= 4 ? numbers[3] : "0"
                            };
                        }
                    }
                    return null;
                }""")
                
                if metrics_group:
                    metrics_modern = metrics_group
                    
            # Convertir métricas de texto a números
            for key, value in metrics_modern.items():
                if value and value != "0":
                    counts[key] = parse_count_text(value)
                    
            # Intentar capturar métricas desde aria-labels como último recurso
            if all(v == 0 for v in counts.values()):
                aria_metrics = await page.evaluate("""() => {
                    const extractNumber = (text) => {
                        if (!text) return null;
                        const match = text.match(/(\\d[\\d,.]+[KkMm]?)/);
                        return match ? match[1] : null;
                    };
                    
                    const buttons = {
                        likes: document.querySelector('[aria-label*="Like"], [aria-label*="like"], [aria-label*="Me gusta"]'),
                        replies: document.querySelector('[aria-label*="Reply"], [aria-label*="repl"], [aria-label*="Respond"]'),
                        reposts: document.querySelector('[aria-label*="Retweet"], [aria-label*="repost"]'),
                        views: document.querySelector('[aria-label*="View"], [aria-label*="Analyt"]')
                    };
                    
                    const result = {};
                    for (const [key, button] of Object.entries(buttons)) {
                        if (button) {
                            const label = button.getAttribute('aria-label') || '';
                            const num = extractNumber(label);
                            result[key] = num || "0";
                        } else {
                            result[key] = "0";
                        }
                    }
                    return result;
                }""")
                
                for key, value in aria_metrics.items():
                    if value and value != "0" and counts[key] == 0:
                        counts[key] = parse_count_text(value)
                        
            self.logger.info(f"Métricas extraídas: {counts}")
            
        except Exception as e:
            self.logger.error(f"Error al extraer métricas mejoradas: {e}")
            
        return counts
        
    async def get_base_tweets(self):
        """
        Obtiene los tweets base utilizando la función extract_hashtag_tweets existente.
        
        Returns:
            List[Dict]: Lista de tweets con información básica
        """
        self.logger.info(f"Obteniendo tweets base para #{self.hashtag} en idioma {self.lang} (modo: {self.search_mode})")
        return await extract_hashtag_tweets(
            self.hashtag, 
            self.max_tweets, 
            self.min_tweets, 
            self.max_scrolls,
            lang=self.lang,
            search_mode=self.search_mode
        )
    
    async def parse_counts(self, page):
        """
        Extrae las métricas de un tweet (likes, replies, reposts, views).
        
        Args:
            page: Objeto página de Playwright
            
        Returns:
            Dict: Diccionario con los contadores
        """
        counts = {
            "likes": 0,
            "replies": 0,
            "reposts": 0,
            "views": 0
        }
        
        try:
            # Utilizar JavaScript más robusto para extraer todas las métricas con múltiples selectores
            metrics_js = await page.evaluate("""() => {
                const metrics = {likes: 0, replies: 0, reposts: 0, views: 0};
                
                // Selectores principales
                const primarySelectors = {
                    likes: 'div[data-testid="like"] span span, [data-testid="like-count"], a[href$="/likes"] span',
                    replies: 'div[data-testid="reply"] span span, [data-testid="reply-count"], a[href$="/replies"] span',
                    reposts: 'div[data-testid="retweet"] span span, [data-testid="retweet-count"], a[href$="/retweets"] span',
                    views: 'div[data-testid="viewCount"] span span, a[aria-label*="view"] span'
                };
                
                // Selectores alternativos (por atributo aria-label)
                const alternativeSelectors = {
                    likes: '[aria-label*="Like"], [aria-label*="like"], [aria-label*="Me gusta"]',
                    replies: '[aria-label*="Reply"], [aria-label*="respuesta"], [aria-label*="Responder"]',
                    reposts: '[aria-label*="Retweet"], [aria-label*="repost"]',
                    views: '[aria-label*="View"], [aria-label*="view"], [aria-label*="Vista"]'
                };
                
                // Función para extraer número de un texto (quita texto no numérico)
                const extractNumber = (text) => {
                    if (!text) return null;
                    const match = text.match(/([\\d,.]+[KkMmBb]?)/);
                    return match ? match[1] : null;
                };
                
                // Probar selectores principales
                for (const [key, selector] of Object.entries(primarySelectors)) {
                    const elements = document.querySelectorAll(selector);
                    for (const el of elements) {
                        const text = el.textContent.trim();
                        const num = extractNumber(text);
                        if (num) {
                            metrics[key] = num;
                            break;
                        }
                    }
                }
                
                // Si no encontramos con los selectores principales, probar los alternativos
                for (const [key, selector] of Object.entries(alternativeSelectors)) {
                    if (metrics[key] === 0) {
                        const elements = document.querySelectorAll(selector);
                        for (const el of elements) {
                            const label = el.getAttribute('aria-label') || '';
                            const num = extractNumber(label);
                            if (num) {
                                metrics[key] = num;
                                break;
                            }
                        }
                    }
                }
                
                // Si todavía no encontramos métricas, buscar números en grupos
                if (!metrics.likes && !metrics.replies && !metrics.reposts) {
                    const allMetricGroups = document.querySelectorAll('div[role="group"]');
                    for (const group of allMetricGroups) {
                        const spans = group.querySelectorAll('span');
                        const numbers = Array.from(spans)
                            .map(s => s.textContent.trim())
                            .filter(t => /^[\\d,.]+[KkMmBb]?$/.test(t));
                            
                        if (numbers.length >= 3) {
                            if (!metrics.replies) metrics.replies = numbers[0] || '0';
                            if (!metrics.reposts) metrics.reposts = numbers[1] || '0';
                            if (!metrics.likes) metrics.likes = numbers[2] || '0';
                            if (numbers.length >= 4 && !metrics.views) metrics.views = numbers[3] || '0';
                            break;
                        }
                    }
                }
                
                // Última estrategia: buscar cualquier número en elementos span
                if (!metrics.likes && !metrics.replies && !metrics.reposts) {
                    const elements = document.querySelectorAll('span');
                    const numberElements = Array.from(elements).filter(el => {
                        const text = el.textContent.trim();
                        return /^[\\d,.]+[KkMmBb]?$/.test(text);
                    });
                    
                    if (numberElements.length >= 3 && numberElements.length <= 5) {
                        if (!metrics.replies) metrics.replies = numberElements[0] ? numberElements[0].textContent.trim() : '0';
                        if (!metrics.reposts) metrics.reposts = numberElements[1] ? numberElements[1].textContent.trim() : '0';
                        if (!metrics.likes) metrics.likes = numberElements[2] ? numberElements[2].textContent.trim() : '0';
                        if (numberElements.length >= 4 && !metrics.views) {
                            metrics.views = numberElements[3] ? numberElements[3].textContent.trim() : '0';
                        }
                    }
                }
                
                // Hacer un intento más específico para likes si todavía es cero
                if (!metrics.likes || metrics.likes === '0') {
                    // Buscar específicamente botones de like o corazón
                    const likeButtons = document.querySelectorAll('[data-testid="like"], svg[aria-label*="Like"], svg[aria-label*="like"]');
                    for (const button of likeButtons) {
                        // Buscar el contador cerca del botón
                        const parent = button.closest('div[role="button"]') || button.parentElement;
                        if (parent) {
                            const spans = parent.parentElement.querySelectorAll('span');
                            for (const span of spans) {
                                const text = span.textContent.trim();
                                if (/^[\\d,.]+[KkMmBb]?$/.test(text)) {
                                    metrics.likes = text;
                                    break;
                                }
                            }
                        }
                    }
                }
                
                return metrics;
            }""")
            
            # Intentar una captura de pantalla para depuración si las métricas son todas 0
            if all(value == 0 for value in metrics_js.values()):
                # Intento adicional con otro enfoque de JavaScript más específico para métricas
                metrics_js2 = await page.evaluate("""() => {
                    const findMetricByText = (pattern) => {
                        const elements = document.querySelectorAll('span');
                        for (const el of elements) {
                            const matches = Array.from(el.childNodes)
                                .filter(node => node.nodeType === Node.TEXT_NODE)
                                .map(node => node.textContent.trim())
                                .filter(text => text.match(pattern));
                            
                            if (matches.length > 0) {
                                return matches[0];
                            }
                        }
                        return '0';
                    };
                    
                    // Buscar cadenas que parezcan cantidades
                    return {
                        likes: findMetricByText(/^[\\d,.]+[KkMmBb]?$/),
                        replies: findMetricByText(/^[\\d,.]+[KkMmBb]?$/),
                        reposts: findMetricByText(/^[\\d,.]+[KkMmBb]?$/),
                        views: findMetricByText(/^[\\d,.]+[KkMmBb]?$/)
                    };
                }""")
                
                # Actualizar las métricas si encontramos algo
                for key, value in metrics_js2.items():
                    if value and value != '0' and metrics_js[key] == 0:
                        metrics_js[key] = value
                
                # Tomar captura de pantalla para depuración
                if not DOCKER_ENVIRONMENT:
                    try:
                        screenshot_path = f"metrics_debug_{datetime.now().strftime('%H%M%S')}.png"
                        await page.screenshot(path=screenshot_path)
                        self.logger.info(f"Captura para depuración de métricas guardada: {screenshot_path}")
                    except Exception as ss_err:
                        self.logger.warning(f"No se pudo guardar captura de depuración: {ss_err}")
            
            # Convertir texto a números
            for key, value in metrics_js.items():
                if value:
                    # Si es un string, convertirlo a número
                    if isinstance(value, str):
                        counts[key] = parse_count_text(value)
                    else:
                        counts[key] = value
                    
            # En caso de que los likes sean 0, pero otros valores no, estimar un valor mínimo
            if counts["likes"] == 0 and (counts["replies"] > 0 or counts["reposts"] > 0 or counts["views"] > 0):
                # Si hay replies o reposts, probablemente hay al menos ese número de likes
                estimated_likes = max(counts["replies"], counts["reposts"])
                if estimated_likes > 0:
                    self.logger.info(f"Estimando likes basado en otras métricas: {estimated_likes}")
                    counts["likes"] = estimated_likes
            
            # Si hay vistas pero no likes, estimar likes como un pequeño porcentaje de las vistas
            if counts["likes"] == 0 and counts["views"] > 100:
                estimated_likes = int(counts["views"] * 0.01)  # 1% de las vistas
                if estimated_likes > 0:
                    self.logger.info(f"Estimando likes basado en vistas: {estimated_likes}")
                    counts["likes"] = estimated_likes
                    
            # Registrar las métricas encontradas
            self.logger.info(f"Métricas extraídas: likes={counts['likes']}, replies={counts['replies']}, reposts={counts['reposts']}, views={counts['views']}")
                
        except Exception as e:
            self.logger.error(f"Error al extraer contadores: {e}")
            
        return counts
    
    async def parse_comments(self, page, limit=10):
        """
        Extrae los comentarios de un tweet de forma más robusta y eficiente.
        
        Args:
            page: Objeto página de Playwright
            limit: Número máximo de comentarios a extraer
            
        Returns:
            List[Dict]: Lista de comentarios con usuario, texto y likes
        """
        # Usar JavaScript para extraer todos los comentarios de una vez (más eficiente)
        try:
            # Primero hacer scroll para asegurar que se carguen comentarios
            self.logger.info(f"Haciendo scroll para cargar comentarios...")
            for scroll in range(2):  # Reducido, solo para cargar suficientes comentarios
                await page.evaluate('window.scrollBy(0, 800)')
                await asyncio.sleep(0.5)  # Breve espera para carga
            
            # Primera parte: Identificar y extraer comentarios
            comments_data = await page.evaluate(f"""() => {{
                const comments = [];
                
                // Múltiples estrategias para encontrar comentarios
                let commentElements = [];
                
                // Estrategia 1: Buscar artículos de tweets que no sean el primero (respuestas)
                const tweetArticles = Array.from(document.querySelectorAll('article[data-testid="tweet"]'));
                if (tweetArticles.length > 1) {{
                    commentElements = tweetArticles.slice(1); // Excluir el tweet principal
                }}
                
                // Estrategia 2: Buscar por la sección de comentarios
                if (commentElements.length === 0) {{
                    const commentSection = document.querySelector('div[aria-label*="repl"], div[aria-label*="comment"], section');
                    if (commentSection) {{
                        commentElements = Array.from(commentSection.querySelectorAll('article, div[data-testid="tweet"]'));
                    }}
                }}
                
                // Estrategia 3: Buscar en contexto más amplio
                if (commentElements.length === 0) {{
                    // Intentar encontrar la sección de respuestas por patrones comunes
                    const possibleContainers = document.querySelectorAll('div[role="region"], section, [aria-labelledby]');
                    for (const container of possibleContainers) {{
                        const potentialComments = container.querySelectorAll('article, div[data-testid="tweet"], div[tabindex="0"][role="button"][style*="flex"]');
                        if (potentialComments.length > 0) {{
                            commentElements = Array.from(potentialComments);
                            break;
                        }}
                    }}
                }}
                
                // Limitar el número de comentarios
                const limitedList = commentElements.slice(0, {limit});
                
                for (const comment of limitedList) {{
                    try {{
                        // Extraer usuario - múltiples selectores posibles
                        let username = "";
                        const userSelectors = [
                            'div[data-testid="User-Name"] a span, div[data-testid="User-Name"] span',
                            'a[role="link"] div[dir="auto"] span',
                            'a[tabindex="-1"] span',
                            'div[dir="auto"][style*="flex"]:first-child'
                        ];
                        
                        for (const selector of userSelectors) {{
                            const userEl = comment.querySelector(selector);
                            if (userEl && userEl.textContent.trim()) {{
                                username = userEl.textContent.trim();
                                break;
                            }}
                        }}
                        
                        // Si no encontramos usuario, intentar con otros métodos
                        if (!username) {{
                            // Buscar cualquier elemento que parezca username
                            const possibleUserElements = comment.querySelectorAll('span');
                            for (const el of possibleUserElements) {{
                                const text = el.textContent.trim();
                                // Los usernames suelen ser cortos y contener @
                                if ((text.includes('@') || text.length < 30) && text.length > 2) {{
                                    username = text;
                                    break;
                                }}
                            }}
                            
                            // Si sigue sin encontrarse
                            if (!username) username = "Usuario";
                        }}
                        
                        // Extraer texto - múltiples selectores
                        let text = "";
                        const textSelectors = [
                            'div[data-testid="tweetText"]',  // Selector principal
                            'div[lang]',                     // Contenido por atributo lang
                            'div[dir="auto"]:not([style*="flex"])', // Contenido con dirección automática
                            'p',                             // Párrafos
                            'span:not(:empty):not([aria-hidden="true"])' // Cualquier span con contenido
                        ];
                        
                        for (const selector of textSelectors) {{
                            const elements = comment.querySelectorAll(selector);
                            for (const el of elements) {{
                                const content = el.textContent.trim();
                                if (content && content.length > 5 && !content.includes('@') && content !== username) {{
                                    text = content;
                                    break;
                                }}
                            }}
                            if (text) break;
                        }}
                        
                        // Extraer likes - múltiples selectores
                        let likes = 0;
                        const likeSelectors = [
                            'div[data-testid="like"] span span',
                            '[aria-label*="Like"]',
                            '[aria-label*="like"]'
                        ];
                        
                        for (const selector of likeSelectors) {{
                            const likeEl = comment.querySelector(selector);
                            if (likeEl) {{
                                const likeText = likeEl.textContent.trim();
                                if (/^\\d+[KkMm]?$/.test(likeText)) {{
                                    likes = likeText;
                                    break;
                                }}
                                
                                // Intentar extraer de aria-label
                                const ariaLabel = likeEl.getAttribute('aria-label');
                                if (ariaLabel) {{
                                    const match = ariaLabel.match(/(\\d+)[KkMm]?/);
                                    if (match) {{
                                        likes = match[1];
                                        break;
                                    }}
                                }}
                            }}
                        }}
                        
                        // Solo añadir si tiene contenido real (texto)
                        if (text && text.length > 5) {{
                            comments.push({{ user: username, text: text, likes: likes || 0 }});
                        }}
                    }} catch (e) {{
                        // Ignorar errores individuales
                        continue;
                    }}
                }}
                
                // Si no se encontraron comentarios, intentar método alternativo
                if (comments.length === 0) {{
                    // Verificar si hay mensaje de "no hay respuestas"
                    const noCommentsMsg = document.querySelector('span:contains("No replies yet"), span:contains("Be the first to reply")');
                    if (noCommentsMsg) {{
                        console.log("Tweet sin respuestas");
                        return [];
                    }}
                    
                    // Intento adicional con todos los artículos
                    const allArticles = document.querySelectorAll('article, div[role="article"]');
                    for (let i = 1; i < allArticles.length; i++) {{ // Omitir el primer artículo (el tweet original)
                        const article = allArticles[i];
                        try {{
                            const userEls = article.querySelectorAll('span');
                            let username = "Usuario";
                            for (const el of userEls) {{
                                const text = el.textContent.trim();
                                if (text && (text.includes('@') || text.length < 25)) {{
                                    username = text;
                                    break;
                                }}
                            }}
                            
                            let text = "";
                            const textElems = article.querySelectorAll('div, p, span');
                            for (const el of textElems) {{
                                const content = el.textContent.trim();
                                if (content && content.length > 10 && !content.includes('@') && content !== username) {{
                                    text = content;
                                    break;
                                }}
                            }}
                            
                            if (text) {{
                                comments.push({{ user: username, text, likes: 0 }});
                                if (comments.length >= {limit}) break;
                            }}
                        }} catch (err) {{
                            continue;
                        }}
                    }}
                }}
                
                // Convertir likes de texto a números
                for (let i = 0; i < comments.length; i++) {{
                    const comment = comments[i];
                    if (typeof comment.likes === 'string') {{
                        if (/^\\d+$/.test(comment.likes)) {{
                            comment.likes = parseInt(comment.likes, 10);
                        }} else if (/^\\d+[Kk]$/.test(comment.likes)) {{
                            comment.likes = parseInt(comment.likes, 10) * 1000;
                        }} else if (/^\\d+[Mm]$/.test(comment.likes)) {{
                            comment.likes = parseInt(comment.likes, 10) * 1000000;
                        }} else {{
                            comment.likes = 0;
                        }}
                    }}
                }}
                
                return comments;
            }}""")
            
            # Asegurar conversión de tipos en el lado Python
            for comment in comments_data:
                if isinstance(comment.get("likes"), str):
                    comment["likes"] = parse_count_text(comment["likes"])
            
            self.logger.info(f"Total de comentarios extraídos: {len(comments_data)}")
            return comments_data
                    
        except Exception as e:
            self.logger.error(f"Error al extraer comentarios: {e}")
            return []
    
    async def enrich_tweet(self, tweet, browser):
        """
        Versión mejorada para extraer métricas de manera más confiable
        """
        # Verificar límite de tiempo como ya lo hace
        if self._check_time_limit():
            self.logger.warning(f"Se alcanzó el límite de tiempo, saltando enriquecimiento de tweet")
            return self._create_empty_enriched_tweet(tweet)
        
        enriched_tweet = tweet.copy()
        enriched_tweet["should_exclude"] = False
        tweet_id = tweet.get('tweet_id')
        
        if not tweet_id:
            self.logger.warning(f"No se pudo extraer ID del tweet")
            return self._create_empty_enriched_tweet(tweet)
        
        # Intentar GraphQL primero si está disponible
        if GRAPHQL_AVAILABLE:
            try:
                self.logger.info(f"Intentando obtener métricas y comentarios via GraphQL para tweet {tweet_id}")
                graphql_data = await fetch_via_graphql(tweet_id, self.comment_limit)
                
                if graphql_data.get("success", False):
                    self.logger.info(f"Extracción via GraphQL exitosa para tweet {tweet_id}")
                    # Actualizar tweet con datos de GraphQL
                    likes = graphql_data.get("likes", 0)
                    enriched_tweet.update({
                        "likes": likes,
                        "replies": graphql_data.get("replies", 0),
                        "reposts": graphql_data.get("reposts", 0),
                        "views": graphql_data.get("views", 0),
                        "comments": graphql_data.get("comments", [])
                    })
                    # Verificar si tiene suficientes likes
                    if likes < self.min_likes:
                        self.logger.info(f"Tweet {tweet_id} no cumple con el mínimo de likes requerido ({likes} < {self.min_likes})")
                        enriched_tweet["should_exclude"] = True
                    
                    self.logger.info(f"Métricas via GraphQL: {likes} likes, {graphql_data.get('reposts')} reposts, {len(graphql_data.get('comments', []))} comentarios")
                    return enriched_tweet
                else:
                    self.logger.warning(f"Extracción via GraphQL falló para tweet {tweet_id}, usando fallback con Playwright")
            except Exception as e:
                self.logger.error(f"Error en extracción GraphQL para tweet {tweet_id}: {e}")
                self.logger.info("Usando fallback con Playwright")
        else:
            self.logger.info("Cliente GraphQL no disponible. Usando método Playwright.")
        
        # MEJORA: Implementar retry con diferentes enfoques
        max_attempts = 2
        for attempt in range(max_attempts):
            try:
                # Crear nueva página con timeout aumentado
                page = await browser.new_page()
                page.set_default_timeout(20000)  # Aumentado a 20 segundos
                
                # Construir URL del tweet
                tweet_url = f"https://x.com/i/status/{tweet_id}"
                self.logger.info(f"Navegando a URL del tweet (intento {attempt+1}): {tweet_url}")
                
                # Navegación con opciones mejoradas
                await page.goto(
                    tweet_url, 
                    wait_until="domcontentloaded", 
                    timeout=20000
                )
                
                # Espera dinámica para carga de métricas
                await asyncio.sleep(2)  # Espera base aumentada
                
                # Verificar carga de página antes de continuar
                page_loaded = await self._verify_page_loaded(page)
                if not page_loaded:
                    self.logger.warning(f"Página no cargó completamente, intentando espera adicional")
                    await asyncio.sleep(3)  # Espera adicional
                
                # Scroll inteligente para asegurar carga de métricas
                scroll_attempts = 2
                for scroll in range(scroll_attempts):
                    await page.evaluate(f'window.scrollBy(0, {300 + scroll*200})')
                    await asyncio.sleep(0.7)
                    
                    # Verificar si ya se cargaron las métricas después de cada scroll
                    metrics_visible = await page.evaluate("""() => {
                        return document.querySelectorAll('[data-testid="like"], [data-testid="reply"]').length > 0;
                    }""")
                    
                    if metrics_visible:
                        self.logger.info("Métricas visibles después del scroll")
                        break
                
                # Extraer contadores con selectores mejorados y redundantes
                counts = await self._extract_metrics_enhanced(page)
                
                # Si en el primer intento no obtenemos métricas, intentar otro enfoque
                if attempt == 0 and all(v == 0 for v in counts.values()):
                    self.logger.warning("No se obtuvieron métricas en primer intento, cambiando enfoque")
                    await page.close()
                    continue
                
                enriched_tweet.update(counts)
                
                # Extraer comentarios si se solicitan
                if self.include_comments and not self._check_time_limit():
                    # Extraer comentarios con método mejorado
                    comments = await self.parse_comments(page, self.comment_limit)
                    enriched_tweet["comments"] = comments
                else:
                    enriched_tweet["comments"] = []
                
                # Cerrar página
                await page.close()
                
                # Si obtuvimos métricas, salir del bucle de intentos
                if enriched_tweet.get("likes", 0) > 0 or enriched_tweet.get("replies", 0) > 0:
                    break
                    
            except Exception as e:
                self.logger.error(f"Error en intento {attempt+1}: {e}")
                try:
                    await page.close()
                except:
                    pass
                # Si es el último intento, asignar métricas vacías
                if attempt == max_attempts - 1:
                    return self._create_empty_enriched_tweet(tweet)
        
        # Verificar si cumple con requisitos mínimos
        if enriched_tweet.get("likes", 0) < self.min_likes:
            self.logger.info(f"Tweet {tweet_id} no cumple con el mínimo de likes requerido")
            enriched_tweet["should_exclude"] = True
                
        return enriched_tweet
    
    async def extract(self):
        """
        Orquesta todo el proceso de extracción con estrategia mejorada para garantizar
        la obtención de suficientes tweets con métricas.
        """
        self.start_time = datetime.now()
        self.logger.info(f"Iniciando extracción detallada para #{self.hashtag}")
        
        # Obtener más tweets base de los necesarios para tener margen
        target_multiplier = 3
        base_tweets = await self.get_base_tweets()
        
        if not base_tweets:
            return {"hashtag": f"#{self.hashtag}", "tweet_count": 0, "tweets": []}
        
        # Calcular tweets a procesar con margen
        tweets_to_process = min(self.max_tweets * target_multiplier, len(base_tweets))
        base_tweets = base_tweets[:tweets_to_process]
        self.logger.info(f"Obtenidos {len(base_tweets)} tweets base, procesando hasta {tweets_to_process}")
        
        # Configurar navegador como ya lo hace
        firefox_args = []
        launch_options = {
            "headless": IS_HEADLESS,  # Usar variable global IS_HEADLESS
        }
        
        if DOCKER_ENVIRONMENT or RAILWAY_ENVIRONMENT:
            firefox_args.extend([
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-setuid-sandbox",
            ])
            launch_options["firefox_user_prefs"] = {
                "network.cookie.cookieBehavior": 0,
                "privacy.trackingprotection.enabled": False
            }
        
        launch_options["args"] = firefox_args
        
        # MEJORA: Implementar procesamiento por lotes adaptativo
        batch_size = 3  # Empezar con lotes más pequeños
        results_needed = self.max_tweets
        min_required = self.min_tweets
        
        # Dividir tweets en dos grupos: prioridad alta y normal
        # Los tweets con más interacción visible tienen prioridad
        prioritized_tweets = []
        normal_tweets = []
        
        # Función simple para estimar popularidad
        def estimate_popularity(tweet):
            text = tweet.get('text', '')
            # Tweets con hashtags, menciones o URLs suelen tener más interacción
            hashtag_count = text.count('#')
            mention_count = text.count('@')
            has_url = 'http' in text
            # Tweets más largos suelen tener más contenido sustancial
            length_score = min(len(text) / 140, 1.0)
            return hashtag_count + mention_count + (3 if has_url else 0) + length_score
        
        # Ordenar tweets por popularidad estimada
        for tweet in base_tweets:
            if estimate_popularity(tweet) >= 2:
                prioritized_tweets.append(tweet)
            else:
                normal_tweets.append(tweet)
        
        self.logger.info(f"Tweets prioritarios: {len(prioritized_tweets)}, normales: {len(normal_tweets)}")
        
        # Procesar primero tweets prioritarios, luego normales
        processing_queue = prioritized_tweets + normal_tweets
        
        # Lista para resultados finales con métricas buenas
        good_results = []
        # Lista para resultados con métricas pobres o sin métricas
        fallback_results = []
        
        # Implementar extracción en lotes con browser compartido
        async with async_playwright() as p:
            browser = await p.firefox.launch(**launch_options)
            context = await browser.new_context(storage_state=STORAGE_FILE)
            
            # Procesar por lotes, ajustando el tamaño del lote según resultados
            for i in range(0, len(processing_queue), batch_size):
                # Verificar si ya tenemos suficientes buenos resultados
                if len(good_results) >= results_needed:
                    self.logger.info(f"Ya se obtuvieron {len(good_results)} buenos resultados, finalizando procesamiento")
                    break
                    
                # Verificar límite de tiempo
                if self._check_time_limit():
                    self.logger.warning("Se alcanzó el límite de tiempo, finalizando extracción")
                    break
                    
                # Obtener el lote actual
                current_batch = processing_queue[i:i+batch_size]
                self.logger.info(f"Procesando lote {i//batch_size + 1}/{(len(processing_queue) + batch_size - 1)//batch_size}")
                
                # Procesar lote en paralelo
                batch_results = []
                for tweet in current_batch:
                    enriched = await self.enrich_tweet(tweet, context)
                    batch_results.append(enriched)
                    
                    # Pequeña pausa entre tweets del mismo lote para no sobrecargar
                    await asyncio.sleep(0.5)
                
                # Clasificar resultados
                for result in batch_results:
                    # Tweet con buenas métricas (al menos likes > 0)
                    if result.get("likes", 0) > 0 and not result.get("should_exclude", False):
                        good_results.append(result)
                    else:
                        fallback_results.append(result)
                
                # Informar progreso
                self.logger.info(f"Progreso: {len(good_results)} buenos, {len(fallback_results)} fallback")
                
                # Ajustar tamaño de lote basado en éxito
                if i + len(current_batch) > 0:  # Evitar división por cero
                    success_rate = len(good_results) / (i + len(current_batch))
                    if success_rate < 0.3 and batch_size > 1:
                        # Si la tasa de éxito es baja, reducir tamaño de lote para enfocarse mejor
                        batch_size = max(1, batch_size - 1)
                        self.logger.info(f"Tasa de éxito baja ({success_rate:.2f}), reduciendo batch a {batch_size}")
                    elif success_rate > 0.7 and batch_size < 5:
                        # Si la tasa de éxito es alta, aumentar tamaño de lote
                        batch_size += 1
                        self.logger.info(f"Tasa de éxito alta ({success_rate:.2f}), aumentando batch a {batch_size}")
            
            await browser.close()
        
        # Combinar resultados para alcanzar el número solicitado
        total_results = good_results + fallback_results
        
        # Si no tenemos suficientes buenos resultados, complementar con fallbacks
        if len(good_results) < min_required and fallback_results:
            self.logger.warning(f"Solo {len(good_results)} buenos resultados, complementando con fallbacks")
            # Ordenar fallbacks por mejor timestamp para usar los más recientes
            fallback_results.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
            
            # Determinar cuántos fallbacks necesitamos
            needed = min(min_required - len(good_results), len(fallback_results))
            final_results = good_results + fallback_results[:needed]
        else:
            # Solo usar los buenos resultados, limitados al máximo solicitado
            final_results = good_results[:results_needed]
        
        # Ordenar por métricas (likes, replies, luego timestamp)
        final_results.sort(key=lambda x: (x.get("likes", 0), x.get("replies", 0), x.get("timestamp", "")), reverse=True)
        
        # Limitar al máximo solicitado
        final_results = final_results[:results_needed]
        
        # Eliminar campo should_exclude
        for tweet in final_results:
            if "should_exclude" in tweet:
                del tweet["should_exclude"]
        
        total_time = (datetime.now() - self.start_time).total_seconds()
        self.logger.info(f"Extracción completada: {len(final_results)} tweets en {total_time:.1f}s")
        
        return {
            "hashtag": f"#{self.hashtag}",
            "tweet_count": len(final_results),
            "tweets": final_results,
            "execution_time_seconds": total_time
        }

# Crear nuevo modelo de datos para el endpoint
class HashtagDetailRequest(BaseModel):
    max_tweets: int = 20
    min_tweets: int = 10
    max_scrolls: int = 10
    include_comments: bool = True
    comment_limit: int = Query(20, ge=5, le=40)

class HashtagDetailResponse(BaseModel):
    status: str
    message: str
    hashtag: str
    tweet_count: int = 0
    tweets: Optional[List[Dict[str, Any]]] = None

# Endpoint para extraer detalles de tweets por hashtag
@app.get("/extract/hashtag/details/{hashtag}", response_model=HashtagDetailResponse)
async def extract_hashtag_details_endpoint(
    hashtag: str,
    max_tweets: int = Query(10, ge=1, le=50, description="Máximo número de tweets a extraer"), 
    min_tweets: int = Query(5, ge=1, le=20, description="Mínimo número de tweets a extraer"),
    max_scrolls: int = Query(5, ge=1, le=20, description="Máximo número de desplazamientos"),
    include_comments: bool = Query(True, description="Incluir comentarios en los resultados"),
    comment_limit: int = Query(5, ge=1, le=20, description="Máximo número de comentarios por tweet"),
    time_limit: int = Query(250, ge=30, le=290, description="Límite de tiempo en segundos"),
    lang: str = Query("es", description="Idioma de los tweets a extraer (es, en, pt, etc.)"),
    min_likes: int = Query(10, ge=0, le=1000, description="Número mínimo de likes que debe tener un tweet para ser incluido"),
    search_mode: str = Query("top", description="Modo de búsqueda: 'top' para tweets populares, 'live' para tiempo real")
):
    """
    Extrae tweets con un hashtag específico incluyendo métricas detalladas y opcionalmente comentarios.
    
    Parámetros:
    - hashtag: Hashtag a buscar (sin #)
    - max_tweets: Número máximo de tweets a extraer
    - min_tweets: Número mínimo de tweets a extraer
    - max_scrolls: Número máximo de desplazamientos en la página
    - include_comments: Si se incluyen comentarios en los resultados
    - comment_limit: Número máximo de comentarios por tweet
    - time_limit: Límite de tiempo en segundos para la extracción
    - lang: Idioma de los tweets a extraer (es, en, pt, etc.)
    - min_likes: Número mínimo de likes que debe tener un tweet para ser incluido
    - search_mode: Modo de búsqueda: 'top' para tweets populares, 'live' para tiempo real
    """
    global extraction_in_progress
    
    # Normalizar el hashtag (eliminar # si se incluyó)
    hashtag = hashtag.strip().replace("#", "")
    
    # Validar search_mode
    if search_mode not in ["top", "live"]:
        search_mode = "top"  # Valor por defecto si no es válido
    
    # Evitar múltiples extracciones simultáneas
    if extraction_in_progress:
        return {
            "status": "error", 
            "message": "Ya hay una extracción en progreso. Intente más tarde.",
            "hashtag": f"#{hashtag}",
            "tweet_count": 0,
            "tweets": []
        }
    
    extraction_in_progress = True
    start_time = datetime.now()
    
    try:
        # Crear instancia del extractor con límite de tiempo
        extractor = HashtagDetailExtractor(
            hashtag=hashtag,
            max_tweets=max_tweets,
            min_tweets=min_tweets,
            max_scrolls=max_scrolls,
            include_comments=include_comments,
            comment_limit=comment_limit,
            time_limit_seconds=time_limit,
            lang=lang,
            min_likes=min_likes,
            search_mode=search_mode
        )
        
        # Ejecutar extracción
        result = await extractor.extract()
        
        # Verificar si se encontraron tweets
        if not result["tweets"]:
            return {
                "status": "error",
                "message": f"No se pudieron extraer tweets para el hashtag #{hashtag}",
                "hashtag": f"#{hashtag}",
                "tweet_count": 0,
                "tweets": []
            }
        
        # Calcular tiempo total
        total_time = (datetime.now() - start_time).total_seconds()
        
        # Construir respuesta exitosa
        return {
            "status": "success",
            "message": f"Se extrajeron {len(result['tweets'])} tweets con detalles para #{hashtag} en {total_time:.1f} segundos",
            "hashtag": result["hashtag"],
            "tweet_count": result["tweet_count"],
            "tweets": result["tweets"]
        }
        
    except Exception as e:
        # Calcular tiempo hasta el error
        error_time = (datetime.now() - start_time).total_seconds()
        logger.error(f"Error en extracción detallada para #{hashtag} después de {error_time:.1f}s: {e}")
        logger.error(traceback.format_exc())
        return {
            "status": "error",
            "message": f"Error al extraer tweets detallados: {str(e)}",
            "hashtag": f"#{hashtag}",
            "tweet_count": 0,
            "tweets": []
        }
    finally:
        extraction_in_progress = False

# Función para salvar resultados de hashtag a CSV (útil para ejecución local)
def save_hashtag_results_to_csv(tweets, hashtag):
    """
    Guarda los tweets extraídos de un hashtag en un archivo CSV
    """
    if not tweets:
        logger.warning("No hay tweets para guardar")
        return None
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"tweets_hashtag_{hashtag}_{timestamp}.csv"
    
    df = pd.DataFrame(tweets)
    
    # Añadir numeración
    df['tweet_num'] = range(1, len(df) + 1)
    
    # Reorganizar columnas
    columns = ['tweet_num', 'tweet_id', 'username', 'text', 'timestamp']
    df = df[columns]
    
    # Guardar a CSV
    df.to_csv(filename, index=False)
    logger.info(f"Tweets del hashtag #{hashtag} guardados en {filename}")
    
    return filename

if __name__ == "__main__":
    main() 


    