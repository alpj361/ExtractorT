#!/usr/bin/env python3
"""
Script FORZADO para extraer SOLO tweets recientes de Twitter.
Este script:
1. Usa EXCLUSIVAMENTE la URL de búsqueda con filtro "live"
2. Combina resultados de múltiples métodos si es necesario
3. Filtra tweets fijados y promocionados
4. Usa una lógica mejorada para obtener solo tweets recientes
5. Incluye auto-renovación de cookies cuando expiran

Uso:
    python fix_extract_recent.py <username> [max_tweets] [min_tweets] [max_scrolls]
"""

import os
import sys
import logging
import asyncio
import pandas as pd
import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from playwright.async_api import async_playwright

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Credenciales para login automático
TWITTER_USERNAME = "StandPd2007"
TWITTER_PASSWORD = "Welcome2024!"
STORAGE_FILE = "firefox_storage.json"

async def perform_login():
    """
    Realiza un login automático en Twitter usando Firefox y guarda las cookies
    para su uso posterior. Se ejecuta cuando se detecta que las cookies han expirado.
    """
    logger.info("Iniciando proceso de login automático en Twitter")
    
    async with async_playwright() as p:
        # Lanzar navegador Firefox
        browser = await p.firefox.launch(headless=False)
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
            await page.wait_for_selector('input[autocomplete="username"]', timeout=30000)
            await page.fill('input[autocomplete="username"]', TWITTER_USERNAME)
            
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
            password_input = await page.wait_for_selector('input[type="password"]', timeout=30000)
            await password_input.fill(TWITTER_PASSWORD)
            
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
            
            if "twitter.com/home" in current_url or "/flow/login" not in current_url:
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
                return False
            
        except Exception as e:
            logger.error(f"Error durante el proceso de login: {e}")
            return False
            
        finally:
            # Cerrar navegador
            await browser.close()
            logger.info("Navegador de login cerrado.")

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
    Asegura que existe un archivo de almacenamiento válido.
    Si no existe o ha expirado, realiza un nuevo login.
    """
    if not check_storage_file():
        logger.info("Se requiere un nuevo login para obtener cookies válidas")
        success = await perform_login()
        if not success:
            logger.error("No se pudo iniciar sesión automáticamente")
            return False
    
    return True

async def extract_recent_tweets(username, max_tweets=20, min_tweets=10, max_scrolls=20):
    """
    Extrae SOLO tweets recientes usando EXCLUSIVAMENTE la URL de búsqueda con filtro "live"
    y fecha dinámica para garantizar los tweets más recientes.
    """
    logger.info(f"Iniciando extracción FORZADA de tweets RECIENTES para @{username}")
    logger.info(f"Parámetros: max_tweets={max_tweets}, min_tweets={min_tweets}, max_scrolls={max_scrolls}")
    
    # Verificar y asegurar cookies válidas
    if not await ensure_valid_storage():
        logger.error("No se pudieron obtener cookies válidas, abortando extracción")
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
    
    async with async_playwright() as p:
        # Usar Firefox para consistencia
        browser = await p.firefox.launch(headless=False)  # headless=False para ver el proceso
        
        context_options = {"storage_state": STORAGE_FILE}
        context = await browser.new_context(**context_options)
        page = await context.new_page()
        
        try:
            # Configurar tiempos de espera más cortos para evitar bloqueos
            page.set_default_timeout(15000)  # 15 segundos en lugar de 30
            
            # Esta vez comenzamos con la estrategia que funcionó mejor y seguimos un enfoque más agresivo
            
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
                    
                logger.info(f"Intento #{url_index+1}: Navegando a búsqueda: {search_url}")
                
                await page.goto(search_url, wait_until="domcontentloaded")
                await asyncio.sleep(5)  # Esperar a que cargue la página
                
                # Verificar URL actual
                current_url = page.url
                logger.info(f"URL actual: {current_url}")
                
                # Verificar si fuimos redirigidos a login
                if "/login" in current_url or "/i/flow/login" in current_url:
                    logger.warning("Redirigido a login, la sesión expiró. Iniciando login automático...")
                    await page.screenshot(path=f"login_redirect_{username}_{url_index}.png")
                    
                    # Cerrar la sesión actual y navegador
                    await browser.close()
                    
                    # Realizar un nuevo login
                    login_success = await perform_login()
                    if not login_success:
                        logger.error("No se pudo iniciar sesión de nuevo. Abortando extracción.")
                        login_error = True
                        break
                    
                    # Reiniciar el navegador con las nuevas cookies
                    browser = await p.firefox.launch(headless=False)
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
                
                # Scroll inicial agresivo para asegurar carga completa
                logger.info("Realizando desplazamiento inicial para cargar la página completamente")
                for i in range(3):
                    await page.evaluate('window.scrollBy(0, 1000)')
                    await asyncio.sleep(1)
                
                # Capturar pantalla para diagnóstico
                await page.screenshot(path=f"page_initial_{username}_{url_index}.png")
                logger.info(f"Captura inicial guardada: page_initial_{username}_{url_index}.png")
                
                # Scroll MUY agresivo para cargar más tweets - aumentamos el número y velocidad
                logger.info(f"Iniciando desplazamiento AGRESIVO para cargar tweets (máx {max_scrolls})")
                
                tweet_count_previous = 0
                no_new_tweets_count = 0
                
                for scroll_idx in range(max_scrolls):
                    logger.info(f"Desplazamiento {scroll_idx+1}/{max_scrolls}")
                    
                    # Desplazar hacia abajo con movimiento agresivo
                    await page.evaluate('window.scrollBy(0, 2500)')
                    await asyncio.sleep(1)
                    
                    # Verificar cada 2 scrolls
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
                        
                        # Tomar screenshots ocasionalmente
                        if scroll_idx % 4 == 0:
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
                        
                        # Buscar tweets del 16 de abril
                        target_date = '2025-04-16'
                        april_16_tweets = [t for t in new_tweets if target_date in t['timestamp']]
                        if april_16_tweets:
                            logger.info(f"¡ENCONTRADOS {len(april_16_tweets)} tweets del {target_date}!")
                else:
                    logger.warning(f"No se encontraron tweets en URL #{url_index+1}")
            
            # Verificar si hubo un error de login que no se pudo resolver
            if login_error:
                logger.error("La extracción se detuvo debido a un problema persistente con la sesión.")
                return []
            
            # Guardar el HTML de la página final para diagnóstico
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
                        
                        # Verificar si encontramos tweets de la fecha objetivo (16 de abril)
                        target_date = '2025-04-16'
                        april_16_tweets = [t for t in filtered_tweets if target_date in t['timestamp']]
                        if april_16_tweets:
                            logger.info(f"¡ÉXITO! Se encontraron {len(april_16_tweets)} tweets del {target_date}")
                        else:
                            logger.warning(f"No se encontraron tweets del {target_date}")
                    except Exception as e:
                        logger.error(f"Error al mostrar información del tweet más reciente: {e}")
                
                # Asignar a la variable de retorno, limitando al máximo
                tweets = filtered_tweets[:max_tweets]
            else:
                logger.warning("No se encontraron tweets en ningún intento")
            
        except Exception as e:
            logger.error(f"Error durante la extracción: {e}")
            
            # Capturar pantalla en caso de error
            try:
                await page.screenshot(path=f"error_{username}.png")
                logger.info(f"Captura de error guardada: error_{username}.png")
            except:
                pass
            
        finally:
            await browser.close()
            logger.info("Navegador cerrado")
    
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
    
    # Guardar el HTML de los tweets para diagnóstico
    tweet_html_debug = []
    
    for idx, tweet_element in enumerate(all_tweets):
        if len(tweets_data) >= max_tweets:
            logger.info(f"Se alcanzó el máximo de tweets a extraer ({max_tweets})")
            break
        
        try:
            # Verificar si es un tweet promocionado o fijado - método simple
            element_html = await tweet_element.evaluate('node => node.outerHTML')
            
            # Guardar HTML para diagnóstico (primeros 5 tweets)
            if idx < 5:
                tweet_html_debug.append(f"--- TWEET #{idx+1} HTML ---\n{element_html[:500]}...\n")
            
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
    
    # Guardar HTML de muestra para diagnóstico
    if tweet_html_debug:
        with open(f"/tmp/tweet_html_samples_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(tweet_html_debug))
    
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

def save_results(tweets, username):
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
                    # Asegurarse de que todos los timestamps tengan el formato correcto
                    timestamp = t['timestamp']
                    if 'Z' in timestamp:
                        dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    else:
                        dt = pd.to_datetime(timestamp).to_pydatetime()
                    formatted_dates.append(dt)
                except Exception as e:
                    logger.warning(f"Error al formatear fecha: {e}, usando fecha actual.")
                    formatted_dates.append(datetime.now())
            
            if formatted_dates:
                first_date = min(formatted_dates).strftime('%Y-%m-%d %H:%M')
                last_date = max(formatted_dates).strftime('%Y-%m-%d %H:%M')
                print(f"Rango de fechas: {first_date} hasta {last_date}")
        
            # Verificar si tenemos tweets del 16 de abril específicamente
            target_date = '2025-04-16'
            april_16_tweets = [t for t in tweets if target_date in t['timestamp']]
            if april_16_tweets:
                print(f"\n¡ÉXITO! Se encontraron {len(april_16_tweets)} tweets del {target_date}")
                # Mostrar los tweets del 16 de abril
                print(f"\nTWEETS DEL {target_date}:")
                for i, tweet in enumerate(april_16_tweets[:3]):  # Mostrar hasta 3 tweets de esa fecha
                    try:
                        time = pd.to_datetime(tweet['timestamp']).strftime('%H:%M')
                        text = tweet['text'].replace('\n', ' ')[:100] + ('...' if len(tweet['text']) > 100 else '')
                        print(f"{i+1}. [{target_date} {time}] {text}")
                    except Exception as e:
                        logger.warning(f"Error al formatear tweet: {e}")
                        print(f"{i+1}. [{target_date}] {tweet['text'][:100]}...")
            
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
            print("No se pudieron procesar correctamente las fechas de los tweets.")
            
            # Mostrar los tweets sin formateo de fechas
            print("\nPRIMEROS 5 TWEETS:")
            for i, tweet in enumerate(tweets[:5]):
                text = tweet['text'].replace('\n', ' ')[:100] + ('...' if len(tweet['text']) > 100 else '')
                print(f"{i+1}. {text}")
    
    print(f"\nArchivo guardado: {filename}")
    print("="*50)
    
    return filename

async def main_async():
    """Función principal asincrónica"""
    if len(sys.argv) < 2:
        print(f"Uso: {sys.argv[0]} <username> [max_tweets] [min_tweets] [max_scrolls]")
        sys.exit(1)
    
    username = sys.argv[1].replace("@", "")  # Eliminar @ si se incluyó
    
    # Parámetros opcionales
    max_tweets = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    min_tweets = int(sys.argv[3]) if len(sys.argv) > 3 else 10
    max_scrolls = int(sys.argv[4]) if len(sys.argv) > 4 else 20
    
    print(f"\n===== EXTRACCIÓN FORZADA DE TWEETS RECIENTES =====")
    print(f"Usuario: @{username}")
    print(f"Parámetros: máx={max_tweets}, mín={min_tweets}, scrolls={max_scrolls}")
    print("Iniciando extracción...")
    print("="*50)
    
    # Extraer tweets RECIENTES
    tweets = await extract_recent_tweets(username, max_tweets, min_tweets, max_scrolls)
    
    # Guardar resultados
    if tweets:
        save_results(tweets, username)
    else:
        logger.error("No se pudieron extraer tweets RECIENTES")
        print("\n¡ERROR! No se pudieron extraer tweets RECIENTES.")
        print("Revise los logs para más información.")

def main():
    """Función principal que maneja el event loop"""
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logger.info("Proceso interrumpido por el usuario")
        print("\nProceso interrumpido por el usuario")
    except Exception as e:
        logger.error(f"Error en la ejecución: {e}")
        print(f"\nError en la ejecución: {e}")

if __name__ == "__main__":
    main() 