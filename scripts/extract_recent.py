#!/usr/bin/env python3
"""
Script optimizado para extraer tweets recientes de Twitter con Firefox.
Este script:
1. Prioriza tweets recientes usando un enfoque de búsqueda
2. Filtra tweets fijados y promocionados
3. Utiliza el estado guardado de Firefox para autenticación
4. Guarda los resultados en CSV

Uso:
    python extract_recent.py <username> [max_tweets] [min_tweets] [max_scrolls]
"""

import os
import sys
import json
import logging
import asyncio
import pandas as pd
from datetime import datetime
from playwright.async_api import async_playwright

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def extract_tweets(username, max_tweets=20, min_tweets=10, max_scrolls=10):
    """
    Extrae tweets recientes de un perfil de Twitter usando Firefox
    
    Args:
        username: Nombre de usuario de Twitter (sin @)
        max_tweets: Número máximo de tweets a extraer
        min_tweets: Número mínimo de tweets a extraer
        max_scrolls: Número máximo de veces a desplazar para cargar más tweets
    
    Returns:
        Lista de diccionarios con tweets extraídos
    """
    logger.info(f"Iniciando extracción de tweets para @{username}")
    logger.info(f"Parámetros: max_tweets={max_tweets}, min_tweets={min_tweets}, max_scrolls={max_scrolls}")
    
    storage_file = "firefox_storage.json"
    if not os.path.exists(storage_file):
        logger.warning(f"Archivo de estado {storage_file} no encontrado. Se recomienda ejecutar login_firefox.py primero.")
    
    tweets = []
    pinned_tweet_ids = set()
    
    async with async_playwright() as p:
        browser_type = p.firefox
        browser = await browser_type.launch(headless=True)
        
        context_options = {}
        if os.path.exists(storage_file):
            logger.info(f"Usando estado guardado de {storage_file}")
            context_options["storage_state"] = storage_file
        
        context = await browser.new_context(**context_options)
        page = await context.new_page()
        
        try:
            # Lista de URLs a intentar en orden de prioridad
            urls_to_try = [
                f"https://twitter.com/search?q=from%3A{username}&f=live", # Búsqueda con filtro "latest"
                f"https://twitter.com/{username}",                         # Perfil directo
                f"https://twitter.com/search?q={username}&f=user"          # Búsqueda de usuario
            ]
            
            successful_url = None
            
            for url_index, url in enumerate(urls_to_try):
                logger.info(f"Intentando acceder a URL {url_index+1}/{len(urls_to_try)}: {url}")
                
                # Navegar a la URL
                await page.goto(url)
                await page.wait_for_load_state("networkidle")
                
                # Verificar si redirigió a login
                current_url = page.url
                logger.info(f"URL actual: {current_url}")
                
                if "/login" in current_url:
                    logger.warning(f"Redirigido a página de login. Autenticación no válida.")
                    await page.screenshot(path=f"/tmp/login_redirect_{username}.png")
                    continue
                    
                # Comprobar si hay contenido
                await asyncio.sleep(3)  # Dar tiempo para que cargue
                
                # Capturar pantalla para diagnóstico
                screenshot_path = f"/tmp/page_initial_{username}_{url_index}.png"
                await page.screenshot(path=screenshot_path)
                logger.info(f"Captura guardada: {screenshot_path}")
                
                # Guardar HTML para diagnóstico
                html_content = await page.content()
                with open(f"/tmp/page_content_{username}_{url_index}.html", "w", encoding="utf-8") as f:
                    f.write(html_content)
                
                # Buscar tweets
                tweet_count = await _count_tweets(page)
                logger.info(f"Tweets encontrados inicialmente: {tweet_count}")
                
                if tweet_count > 0:
                    successful_url = url
                    break
            
            if not successful_url:
                logger.error("No se pudo acceder a ninguna URL con tweets")
                return []
                
            logger.info(f"URL exitosa: {successful_url}")
            
            # Detectar tweets fijados
            pinned_tweets = await page.query_selector_all('div[data-testid="socialContext"][role="presentation"]')
            for pinned in pinned_tweets:
                text = await pinned.text_content()
                if "Pinned" in text or "Fijado" in text:
                    logger.info(f"Tweet fijado detectado: {text}")
                    
                    # Obtener el ID del tweet fijado
                    parent_article = await pinned.evaluate('node => node.closest("article")')
                    if parent_article:
                        links = await page.evaluate('''
                            article => {
                                const links = article.querySelectorAll('a[href*="/status/"]');
                                return Array.from(links).map(a => a.href);
                            }
                        ''', parent_article)
                        
                        for link in links:
                            if "/status/" in link:
                                tweet_id = link.split("/status/")[1].split("?")[0]
                                logger.info(f"ID de tweet fijado: {tweet_id}")
                                pinned_tweet_ids.add(tweet_id)
            
            # Desplazar para cargar más tweets
            logger.info(f"Iniciando desplazamiento para cargar más tweets (máx {max_scrolls})")
            
            for scroll_idx in range(max_scrolls):
                logger.info(f"Desplazamiento {scroll_idx+1}/{max_scrolls}")
                
                # Desplazar hacia abajo
                await page.evaluate('window.scrollBy(0, 2000)')
                await asyncio.sleep(2)  # Esperar a que carguen nuevos tweets
                
                # Contar tweets después de desplazar
                tweet_count = await _count_tweets(page)
                logger.info(f"Tweets encontrados tras desplazamiento {scroll_idx+1}: {tweet_count}")
                
                # Capturar pantalla ocasionalmente
                if scroll_idx % 3 == 0:
                    screenshot_path = f"/tmp/page_scroll_{username}_{scroll_idx}.png"
                    await page.screenshot(path=screenshot_path)
                    logger.info(f"Captura guardada: {screenshot_path}")
                
                # Si ya tenemos suficientes tweets, salir del bucle
                if tweet_count >= max_tweets:
                    logger.info(f"Se alcanzó el máximo de tweets ({max_tweets})")
                    break
            
            # Extraer datos de tweets
            tweets = await _extract_tweets_data(page, pinned_tweet_ids, max_tweets)
            
            # Ordenar tweets por timestamp (más recientes primero)
            tweets.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            
            # Tomar captura final
            await page.screenshot(path=f"/tmp/page_final_{username}.png")
            logger.info(f"Captura final guardada: /tmp/page_final_{username}.png")
            
        except Exception as e:
            logger.error(f"Error durante la extracción: {e}")
            
            # Capturar pantalla en caso de error
            try:
                await page.screenshot(path=f"/tmp/error_{username}.png")
                logger.info(f"Captura de error guardada: /tmp/error_{username}.png")
            except:
                pass
            
        finally:
            await browser.close()
            logger.info("Navegador cerrado")
    
    total_tweets = len(tweets)
    logger.info(f"Total de tweets extraídos: {total_tweets}")
    
    if total_tweets < min_tweets:
        logger.warning(f"Se extrajeron menos tweets ({total_tweets}) que el mínimo requerido ({min_tweets})")
    
    return tweets

async def _count_tweets(page):
    """Cuenta el número de tweets en la página actual"""
    selectors = [
        'article[data-testid="tweet"]',
        'div[data-testid="tweet"]',
        'div[role="article"]',
        'article[role="article"]'
    ]
    
    count = 0
    for selector in selectors:
        elements = await page.query_selector_all(selector)
        count += len(elements)
    
    return count

async def _extract_tweets_data(page, pinned_tweet_ids=None, max_tweets=20):
    """
    Extrae datos de tweets de la página actual
    
    Args:
        page: Objeto página de Playwright
        pinned_tweet_ids: Conjunto de IDs de tweets fijados a filtrar
        max_tweets: Número máximo de tweets a extraer
    
    Returns:
        Lista de diccionarios con datos de tweets
    """
    if pinned_tweet_ids is None:
        pinned_tweet_ids = set()
    
    logger.info(f"Extrayendo datos de tweets (máx {max_tweets}, filtrando {len(pinned_tweet_ids)} IDs de tweets fijados)")
    
    # Selectors para diferentes elementos de tweets
    tweet_selectors = [
        'article[data-testid="tweet"]',
        'div[data-testid="tweet"]',
        'div[role="article"]',
        'article[role="article"]'
    ]
    
    # Recolectar todos los elementos de tweets
    all_tweets = []
    for selector in tweet_selectors:
        elements = await page.query_selector_all(selector)
        all_tweets.extend(elements)
    
    logger.info(f"Total de elementos de tweets encontrados: {len(all_tweets)}")
    
    # Extraer datos
    tweets_data = []
    processed_ids = set()
    
    for idx, tweet_element in enumerate(all_tweets):
        if len(tweets_data) >= max_tweets:
            logger.info(f"Se alcanzó el máximo de tweets a extraer ({max_tweets})")
            break
        
        try:
            # Verificar si es un tweet especial (fijado, promocionado, etc.)
            special_indicators = await tweet_element.query_selector_all('span:has-text("Promoted"), span:has-text("Pinned"), span:has-text("Fijado"), span:has-text("Promocionado")')
            if special_indicators:
                special_text = await special_indicators[0].text_content()
                logger.info(f"Saltando tweet especial: {special_text}")
                continue
            
            # Extraer ID del tweet desde su URL
            tweet_id = None
            links = await tweet_element.query_selector_all('a[href*="/status/"]')
            for link in links:
                href = await link.get_attribute('href')
                if href and "/status/" in href:
                    tweet_id = href.split("/status/")[1].split("?")[0]
                    break
            
            if tweet_id in pinned_tweet_ids:
                logger.info(f"Saltando tweet fijado con ID: {tweet_id}")
                continue
                
            if tweet_id in processed_ids:
                logger.info(f"Saltando tweet duplicado con ID: {tweet_id}")
                continue
            
            # Extraer texto del tweet
            text_element = await tweet_element.query_selector('div[data-testid="tweetText"]')
            if not text_element:
                # Intentar selectores alternativos para el texto
                text_element = await tweet_element.query_selector('div[lang]')
            
            tweet_text = await text_element.text_content() if text_element else "[Sin texto]"
            
            # Extraer nombre de usuario
            username_element = await tweet_element.query_selector('div[data-testid="User-Name"]')
            if not username_element:
                username_element = await tweet_element.query_selector('a[role="link"] div[dir="ltr"]')
            
            username = await username_element.text_content() if username_element else "Unknown User"
            
            # Extraer timestamp
            time_element = await tweet_element.query_selector('time')
            timestamp = await time_element.get_attribute('datetime') if time_element else ""
            
            if tweet_id:
                processed_ids.add(tweet_id)
            
            # Añadir a los resultados
            tweets_data.append({
                'tweet_id': tweet_id,
                'username': username,
                'text': tweet_text,
                'timestamp': timestamp
            })
            
            logger.debug(f"Tweet {len(tweets_data)} extraído: {tweet_text[:30]}...")
            
        except Exception as e:
            logger.error(f"Error al extraer datos del tweet {idx}: {e}")
    
    logger.info(f"Extracción completada: {len(tweets_data)} tweets")
    return tweets_data

def save_results(tweets, username):
    """
    Guarda los tweets extraídos en un archivo CSV
    
    Args:
        tweets: Lista de diccionarios con tweets
        username: Nombre de usuario para el nombre del archivo
    
    Returns:
        Ruta del archivo guardado
    """
    if not tweets:
        logger.warning("No hay tweets para guardar")
        return None
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"tweets_{username}_{timestamp}.csv"
    
    df = pd.DataFrame(tweets)
    
    # Añadir numeración
    df['tweet_num'] = range(1, len(df) + 1)
    
    # Reorganizar columnas
    columns = ['tweet_num', 'tweet_id', 'username', 'text', 'timestamp']
    df = df[columns]
    
    # Guardar a CSV
    df.to_csv(filename, index=False)
    logger.info(f"Tweets guardados en {filename}")
    
    # Mostrar resumen
    print(f"\nResumen de extracción para @{username}:")
    print(f"- Total de tweets extraídos: {len(tweets)}")
    
    if len(tweets) > 0:
        first_date = pd.to_datetime(tweets[0]['timestamp']).strftime('%Y-%m-%d %H:%M')
        last_date = pd.to_datetime(tweets[-1]['timestamp']).strftime('%Y-%m-%d %H:%M')
        print(f"- Rango de fechas: {first_date} hasta {last_date}")
    
    print(f"- Archivo guardado: {filename}")
    
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
    max_scrolls = int(sys.argv[4]) if len(sys.argv) > 4 else 10
    
    # Extraer tweets
    tweets = await extract_tweets(username, max_tweets, min_tweets, max_scrolls)
    
    # Guardar resultados
    if tweets:
        save_results(tweets, username)
    else:
        logger.error("No se pudieron extraer tweets")

def main():
    """Función principal que maneja el event loop"""
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logger.info("Proceso interrumpido por el usuario")
    except Exception as e:
        logger.error(f"Error en la ejecución: {e}")

if __name__ == "__main__":
    main() 