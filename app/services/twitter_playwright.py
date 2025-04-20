"""
Servicio para scraping de Twitter usando Playwright, más resistente a la detección que Selenium.
"""
import logging
import pandas as pd
import io
import time
import os
import json
import random
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError, Browser, BrowserContext, Page
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

class TwitterPlaywrightScraper:
    """Servicio para scraping de tweets de Twitter usando Playwright."""
    
    def __init__(self, username=None, password=None, bypass_login=False):
        """
        Inicializar scraper con credenciales opcionales.
        
        Args:
            username (str, optional): Usuario o email de Twitter
            password (str, optional): Contraseña de Twitter
            bypass_login (bool): Si se debe omitir el login e intentar acceso directo
        """
        self.username = username or os.environ.get('TWITTER_USERNAME')
        self.password = password or os.environ.get('TWITTER_PASSWORD')
        self.bypass_login = bypass_login
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        
        # Paths para cookies y storage
        self.cookie_paths = [
            "/app/cookies/twitter_cookies.json",  # Docker path
            "playwright_data/twitter_cookies.json",  # Local development path
            "twitter_cookies.json"                # Alternative local path
        ]
        
        self.storage_paths = [
            "/app/storage/twitter_state.json",  # Docker path
            "playwright_data/twitter_state.json",  # Local development path
        ]
    
    async def __aenter__(self):
        """Configurar el navegador al ingresar al contexto."""
        try:
            logger.info("Inicializando navegador para Twitter scraping con Playwright")
            self.playwright = await async_playwright().start()
            
            # Configurar opciones del navegador
            browser_args = [
                '--no-sandbox',
                '--disable-blink-features=AutomationControlled',
                '--disable-features=IsolateOrigins,site-per-process',
            ]
            
            # Añadir headless solo en entorno Docker/Railway
            if os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("DOCKER_ENVIRONMENT"):
                browser_args.append('--headless=new')
            
            # Iniciar Chrome/Chromium
            self.browser = await self.playwright.chromium.launch(
                headless=bool(os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("DOCKER_ENVIRONMENT")),
                args=browser_args
            )
            
            # User-Agent móvil para evadir detección
            mobile_user_agent = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1"
            
            # Crear contexto con UA móvil y viewport de dispositivo móvil
            self.context = await self.browser.new_context(
                viewport={"width": 375, "height": 812},  # iPhone X viewport
                user_agent=mobile_user_agent,
                device_scale_factor=2.0,  # Retina display
                is_mobile=True,
            )
            
            # Inyectar scripts anti-detección
            await self.context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'languages', { get: () => ['es-ES', 'es', 'en-US', 'en'] });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            window.chrome = { runtime: {} };
            // Sobrescribir geolocalización con valores aleatorios
            navigator.geolocation.getCurrentPosition = function(success) {
                success({
                    coords: {
                        latitude: 40 + Math.random(),
                        longitude: -3 + Math.random(),
                        accuracy: 100,
                        altitude: null,
                        altitudeAccuracy: null,
                        heading: null,
                        speed: null
                    },
                    timestamp: Date.now()
                });
            };
            """)
            
            # Crear página
            self.page = await self.context.new_page()
            self.page.set_default_timeout(30000)  # 30 segundos de timeout por defecto
            
            # Intentar cargar cookies o estado guardado
            await self.load_stored_auth()
            
            logger.info("Configuración del navegador exitosa")
            return self
        except Exception as e:
            logger.error(f"Error en la configuración del navegador: {str(e)}")
            await self.cleanup()
            raise
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Limpiar recursos al salir del contexto."""
        await self.cleanup()
    
    async def cleanup(self):
        """Cerrar y limpiar recursos de Playwright."""
        try:
            if self.page:
                await self.page.close()
                self.page = None
            
            if self.context:
                await self.context.close()
                self.context = None
            
            if self.browser:
                await self.browser.close()
                self.browser = None
            
            if self.playwright:
                await self.playwright.stop()
                self.playwright = None
            
            logger.info("Recursos de Playwright liberados")
        except Exception as e:
            logger.error(f"Error al limpiar recursos: {str(e)}")
    
    async def load_stored_auth(self):
        """
        Cargar autenticación almacenada (cookies o estado completo).
        
        Returns:
            bool: True si la autenticación se cargó correctamente
        """
        # Primero intentar cargar el estado completo si existe
        for storage_path in self.storage_paths:
            if os.path.exists(storage_path):
                try:
                    logger.info(f"Cargando estado de navegador desde {storage_path}")
                    await self.context.storage_state(path=storage_path)
                    logger.info("Estado del navegador cargado correctamente")
                    return await self.verify_auth()
                except Exception as e:
                    logger.warning(f"Error al cargar estado: {str(e)}")
        
        # Si no hay estado, intentar con las cookies
        for cookie_path in self.cookie_paths:
            if os.path.exists(cookie_path):
                try:
                    logger.info(f"Cargando cookies desde {cookie_path}")
                    with open(cookie_path, 'r') as f:
                        cookies = json.load(f)
                    
                    # Verificar si hay cookies críticas para autenticación
                    auth_cookies = ["auth_token", "ct0", "twid"]
                    critical_cookies = [c for c in cookies if c.get('name') in auth_cookies]
                    
                    if not critical_cookies:
                        logger.warning("No se encontraron cookies críticas para autenticación")
                        continue
                    
                    # Navegar primero a Twitter para poder establecer las cookies
                    await self.page.goto("https://twitter.com")
                    await self.page.wait_for_load_state("networkidle")
                    
                    # Añadir las cookies al contexto
                    await self.context.add_cookies(cookies)
                    logger.info(f"Se añadieron {len(cookies)} cookies")
                    
                    # Verificar autenticación
                    return await self.verify_auth()
                    
                except Exception as e:
                    logger.warning(f"Error al cargar cookies desde {cookie_path}: {str(e)}")
        
        logger.warning("No se encontró autenticación almacenada válida")
        return False
    
    async def verify_auth(self, retries=3):
        """
        Verificar si la autenticación está activa, con reintentos en caso de fallo.
        
        Args:
            retries (int): Número de reintentos permitidos en caso de fallo
        
        Returns:
            bool: True si el usuario está autenticado
        """
        attempt = 0
        while attempt < retries:
            try:
                logger.info("Verificando autenticación")
                
                # Navegar a la página principal
                await self.page.goto("https://twitter.com/home")
                await self.page.wait_for_load_state("networkidle")
                
                # Guardar captura para diagnóstico
                await self.page.screenshot(path="/tmp/auth_verification.png")
                
                # Comprobar si estamos en la página de inicio o en login
                current_url = self.page.url
                if "login" in current_url or "flow" in current_url:
                    logger.warning(f"Redirección a login detectada: {current_url}")
                    attempt += 1
                    continue
                
                # Buscar elementos que indiquen sesión iniciada
                selectors = [
                    "a[data-testid='SideNav_NewTweet_Button']",
                    "a[aria-label='Post']",
                    "a[data-testid='AppTabBar_Home_Link']",
                    "svg[data-testid='tweetButtonInline']",
                    "div[aria-label='Timeline: Your Home Timeline']"
                ]
                
                for selector in selectors:
                    try:
                        element = await self.page.wait_for_selector(selector, timeout=5000)
                        if element:
                            logger.info(f"Autenticación verificada (selector encontrado: {selector})")
                            return True
                    except:
                        pass
                
                logger.warning("No se pudo verificar la autenticación")
                attempt += 1
                
            except Exception as e:
                logger.error(f"Error al verificar autenticación: {str(e)}")
                attempt += 1
        
        return False
    
    async def extract_by_hashtag(self, hashtag, max_tweets=30, min_tweets=10, max_scrolls=10):
        """
        Extract tweets containing a specific hashtag.
        
        Args:
            hashtag (str): Hashtag to search for (with or without the # symbol)
            max_tweets (int): Maximum number of tweets to extract
            min_tweets (int): Minimum number of tweets to extract before stopping
            max_scrolls (int): Maximum number of page scrolls
            
        Returns:
            pandas.DataFrame: DataFrame containing extracted tweets
        """
        logger.info(f"Extracting tweets for hashtag: #{hashtag}")
        
        # Clean hashtag (remove # if present)
        clean_hashtag = hashtag.strip()
        if clean_hashtag.startswith("#"):
            clean_hashtag = clean_hashtag[1:]
        
        # URLs of search to try (in order)
        search_urls = [
            f"https://twitter.com/search?q=%23{clean_hashtag}&src=typed_query&f=top",
            f"https://x.com/search?q=%23{clean_hashtag}&src=typed_query&f=top",
            f"https://twitter.com/hashtag/{clean_hashtag}?src=hashtag_click",
            f"https://x.com/hashtag/{clean_hashtag}?src=hashtag_click"
        ]
        
        tweets_data = []
        
        # Try each URL until one works
        for url_index, url in enumerate(search_urls):
            try:
                logger.info(f"Attempting URL {url_index+1}/{len(search_urls)}: {url}")
                
                # Navigate to search URL
                await self.page.goto(url)
                await self.page.wait_for_load_state("domcontentloaded")
                
                # Wait a bit for dynamic content to load
                await asyncio.sleep(random.uniform(2, 4))
                
                # Capture screen for diagnostic
                screenshot_path = f"/tmp/search_initial_{clean_hashtag}_{url_index}.png"
                await self.page.screenshot(path=screenshot_path)
                logger.info(f"Initial capture saved to {screenshot_path}")
                
                # Check if we're on login page (redirection)
                current_url = self.page.url
                logger.info(f"Current URL after navigation: {current_url}")
                
                if "login" in current_url or "flow/login" in current_url:
                    logger.warning(f"Login redirection detected, skipping URL: {url}")
                    continue  # Try next URL
                
                # Wait for tweets to load
                logger.info("Waiting for tweets to load")
                
                # Tweet selectors used by Twitter
                tweet_selectors = [
                    "article[data-testid='tweet']",
                    "div[data-testid='cellInnerDiv']",
                    "div[data-testid='tweet']"
                ]
                
                tweet_selector = None
                for selector in tweet_selectors:
                    try:
                        logger.info(f"Searching for tweets with selector: {selector}")
                        await self.page.wait_for_selector(selector, timeout=10000)
                        tweet_selector = selector
                        logger.info(f"Tweets found using selector: {selector}")
                        break
                    except:
                        logger.warning(f"Selector not found: {selector}")
                
                if not tweet_selector:
                    logger.warning(f"No tweets found with URL {url}")
                    continue  # Try next URL
                
                # Scroll to load more tweets
                logger.info(f"Scrolling {max_scrolls} times to load more tweets")
                
                for i in range(max_scrolls):
                    await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    # Wait between scrolls with random time
                    await asyncio.sleep(random.uniform(1, 3))
                    logger.info(f"Scroll {i+1}/{max_scrolls} completed")
                
                # Capture after scrolling
                await self.page.screenshot(path=f"/tmp/after_scroll_{clean_hashtag}_{url_index}.png")
                
                # Extract data from tweets
                logger.info(f"Extracting tweet data using selector: {tweet_selector}")
                
                # Get all tweet elements
                tweet_elements = await self.page.query_selector_all(tweet_selector)
                logger.info(f"Found {len(tweet_elements)} potential tweet elements")
                
                # Limit to max_tweets
                tweet_elements = tweet_elements[:max_tweets]
                
                # Process each tweet
                for i, tweet_el in enumerate(tweet_elements):
                    try:
                        # Try to extract text
                        tweet_text = ""
                        text_selectors = [
                            "div[data-testid='tweetText']",
                            "div.css-901oao"
                        ]
                        
                        for text_selector in text_selectors:
                            text_el = await tweet_el.query_selector(text_selector)
                            if text_el:
                                tweet_text = await text_el.inner_text()
                                if tweet_text:
                                    break
                        
                        # Extract username if available
                        username = "Unknown"
                        try:
                            username_el = await tweet_el.query_selector("div[data-testid='User-Name']")
                            if username_el:
                                username = await username_el.inner_text()
                        except:
                            pass
                        
                        # Extract timestamp if available
                        timestamp = ""
                        try:
                            time_el = await tweet_el.query_selector("time")
                            if time_el:
                                timestamp = await time_el.get_attribute("datetime")
                        except:
                            pass
                        
                        # Add tweet if it has text
                        if tweet_text and len(tweet_text.strip()) > 0:
                            tweets_data.append({
                                'texto': tweet_text,
                                'usuario': username,
                                'timestamp': timestamp,
                                'numero': i+1
                            })
                            logger.debug(f"Tweet {i+1} processed: {tweet_text[:30]}...")
                        
                        # Stop if we have enough tweets
                        if len(tweets_data) >= min_tweets:
                            logger.info(f"Minimum of {min_tweets} tweets reached, stopping extraction")
                            break
                        
                    except Exception as e:
                        logger.error(f"Error processing tweet {i+1}: {str(e)}")
                
                # If tweets found, return DataFrame
                if tweets_data:
                    logger.info(f"Extraction successful: {len(tweets_data)} tweets for #{clean_hashtag}")
                    break  # Exit loop over URLs
                
            except PlaywrightTimeoutError:
                logger.error(f"Timeout waiting for page load: {url}")
                # Continue with next URL
            except Exception as e:
                logger.error(f"Error with URL {url}: {str(e)}")
                # Continue with next URL
        
        # Create DataFrame with extracted data
        if tweets_data:
            df = pd.DataFrame(tweets_data)
            logger.info(f"Created DataFrame with {len(df)} tweets")
            return df
        else:
            logger.warning(f"No tweets extracted for #{clean_hashtag}")
            return pd.DataFrame(columns=["texto", "usuario", "timestamp", "numero"])
    
    async def extract_by_user(self, username, max_tweets=30, min_tweets=10, max_scrolls=10):
        """
        Extract tweets from a specific user's timeline.
        
        Args:
            username (str): Twitter username (without the @ symbol)
            max_tweets (int): Maximum number of tweets to extract
            min_tweets (int): Minimum number of tweets to extract before stopping
            max_scrolls (int): Maximum number of page scrolls
            
        Returns:
            pandas.DataFrame: DataFrame containing extracted tweets
        """
        logger.info(f"Extracting tweets for user: @{username}")
        
        # Clean username (remove @ if present)
        clean_username = username.strip()
        if clean_username.startswith("@"):
            clean_username = clean_username[1:]
        
        # URLs en orden de prioridad para forzar tweets recientes
        urls_to_try = [
            # Enfoque 1: Búsqueda con "Latest" como primera opción (esto debería mostrar tweets recientes)
            f"https://twitter.com/search?q=from%3A{clean_username}%20since%3A2024-01-01&src=typed_query&f=live",
            
            # Enfoque 2: URL de perfil con "Media" y luego buscar "Tweets" (puede evadir la caché)
            f"https://twitter.com/{clean_username}/media",
            
            # Enfoque 3: Perfil de usuario con el parámetro ?f=tweets" (filtrado explícito por tweets)
            f"https://twitter.com/{clean_username}?f=tweets",
            
            # Enfoque 4: Perfil con replies (a veces muestra contenido diferente)
            f"https://twitter.com/{clean_username}/with_replies",
            
            # Enfoque 5: Perfil básico como último recurso
            f"https://twitter.com/{clean_username}"
        ]
        
        logger.info(f"Intentando múltiples estrategias para forzar la carga de tweets recientes")
        
        try:
            # Variables para rastrear el estado y los datos
            tweets_data = []
            current_url = None
            successful_url = None
            pinned_tweet_ids = set()  # Para rastrear y filtrar tweets fijados
            
            # Intentar cada URL en orden hasta encontrar tweets suficientes
            for url_index, url in enumerate(urls_to_try):
                try:
                    logger.info(f"Estrategia {url_index+1}: Accediendo a {url}")
                    
                    # Limpiar caché de página para evitar contenido almacenado
                    await self.page.context.clear_cookies()
                    
                    # Navegar a la URL directamente 
                    await self.page.goto(url, wait_until="domcontentloaded", timeout=20000)
                    current_url = self.page.url
                    logger.info(f"URL actual: {current_url}")
                    
                    # Verificar redirección a login
                    if "login" in current_url or "flow/login" in current_url:
                        logger.warning(f"Redirección a login detectada para {url}, intentando siguiente URL")
                        continue
                    
                    # Simular comportamiento humano - mover el ratón, hacer clic aleatorio
                    await self.page.mouse.move(random.randint(100, 300), random.randint(100, 300))
                    
                    # Esperar a que cargue el contenido con tiempo extra
                    await asyncio.sleep(5)
                    
                    # Tomar captura y guardar HTML
                    await self.page.screenshot(path=f"/tmp/profile_{clean_username}_url{url_index+1}.png")
                    page_content = await self.page.content()
                    with open(f"/tmp/page_content_{clean_username}_url{url_index+1}.html", "w", encoding="utf-8") as f:
                        f.write(page_content)
                    
                    # Si es la estrategia de "Media", hacer clic en "Tweets" para cambiar la vista
                    if "media" in url:
                        try:
                            logger.info("En vista de Media, intentando cambiar a vista de Tweets")
                            await self.page.click('a[href$="/tweets"]')
                            await self.page.wait_for_load_state("networkidle")
                            await asyncio.sleep(3)
                            await self.page.screenshot(path=f"/tmp/profile_{clean_username}_after_tab_switch.png")
                        except Exception as e:
                            logger.warning(f"No se pudo cambiar a la pestaña de Tweets: {str(e)}")
                    
                    # Detectar tweets fijados antes de scrolling para filtrarlos
                    try:
                        logger.info("Buscando tweets fijados antes de scroll")
                        
                        # Múltiples selectores para tweets fijados
                        pinned_selectors = [
                            "div[data-testid='socialContext']",
                            "div:has-text('Pinned Tweet')",
                            "div:has-text('Tweet fijado')",
                            "span:has-text('Pinned')",
                            "span:has-text('Fijado')"
                        ]
                        
                        for selector in pinned_selectors:
                            pinned_elements = await self.page.query_selector_all(selector)
                            for element in pinned_elements:
                                element_text = await element.inner_text()
                                if "Pinned" in element_text or "Fijado" in element_text:
                                    # Intentar obtener el tweet contenedor
                                    parent = await element.evaluate("""
                                    (el) => {
                                        // Navegar hacia arriba buscando artículo o div de tweet
                                        let node = el;
                                        for (let i = 0; i < 6; i++) {
                                            if (!node.parentElement) break;
                                            node = node.parentElement;
                                            if (node.tagName === 'ARTICLE' || 
                                                node.getAttribute('data-testid') === 'tweet' ||
                                                node.getAttribute('role') === 'article') {
                                                return node;
                                            }
                                        }
                                        return null;
                                    }
                                    """)
                                    
                                    if parent:
                                        # Intentar obtener ID o texto del tweet fijado
                                        try:
                                            links = await self.page.query_selector_all("a[href*='/status/']")
                                            for link in links:
                                                href = await link.get_attribute("href")
                                                if href and '/status/' in href:
                                                    parts = href.split('/status/')
                                                    if len(parts) > 1:
                                                        tweet_id = parts[1].split('?')[0].split('/')[0]
                                                        pinned_tweet_ids.add(tweet_id)
                                                        logger.info(f"Identified pinned tweet ID: {tweet_id}")
                                        except Exception as e:
                                            logger.warning(f"Error extracting pinned tweet ID: {str(e)}")
                    except Exception as e:
                        logger.warning(f"Error checking pinned tweets: {str(e)}")
                    
                    # Iniciar scrolling para cargar más tweets
                    logger.info(f"Iniciando scroll para URL {url_index+1}")
                    scrolls = 0
                    last_tweets_count = 0
                    
                    while scrolls < max_scrolls and len(tweets_data) < max_tweets:
                        logger.info(f"Scroll {scrolls+1}/{max_scrolls}")
                        
                        # Obtener tweets visibles actualmente
                        new_tweets = await self._extract_tweets_data(pinned_tweet_ids=pinned_tweet_ids)
                        
                        # Añadir nuevos tweets únicos
                        initial_count = len(tweets_data)
                        for tweet in new_tweets:
                            if tweet not in tweets_data:
                                tweets_data.append(tweet)
                        
                        current_count = len(tweets_data)
                        logger.info(f"Encontrados {len(new_tweets)} tweets nuevos, {current_count - initial_count} únicos. Total: {current_count}")
                        
                        # Si no obtuvimos nuevos tweets y ya tenemos algunos, intentar hacer scroll diferente
                        if current_count == last_tweets_count and current_count > 0:
                            # Probar un scroll más agresivo
                            logger.info("No se encontraron nuevos tweets, intentando scroll más agresivo")
                            await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        else:
                            # Scroll normal
                            await self.page.evaluate("window.scrollBy(0, window.innerHeight)")
                        
                        # Simular comportamiento humano con pausas variables
                        await asyncio.sleep(random.uniform(2, 4))
                        
                        # Tomar capturas periódicas
                        if scrolls % 2 == 0:
                            await self.page.screenshot(path=f"/tmp/scroll_{clean_username}_url{url_index+1}_{scrolls}.png")
                        
                        last_tweets_count = current_count
                        scrolls += 1
                        
                        # Si tenemos suficientes tweets, parar
                        if len(tweets_data) >= min_tweets:
                            logger.info(f"Se encontraron {len(tweets_data)} tweets, suficientes para el mínimo de {min_tweets}")
                            successful_url = url
                            break
                    
                    # Si esta URL funcionó bien (obtuvimos suficientes tweets), salir del loop
                    if len(tweets_data) >= min_tweets:
                        logger.info(f"Extracción exitosa con URL: {url}")
                        successful_url = url
                        break
                    
                except Exception as e:
                    logger.warning(f"Error con URL {url}: {str(e)}")
                    # Continuar con la siguiente URL
            
            # Verificar si obtuvimos tweets suficientes
            if len(tweets_data) < min_tweets:
                logger.warning(f"No se pudieron extraer suficientes tweets para @{clean_username} tras probar todas las URLs")
            elif successful_url:
                logger.info(f"Extracción exitosa usando URL: {successful_url}")
            
            # Crear DataFrame con los tweets obtenidos
            if tweets_data:
                df = pd.DataFrame(tweets_data)
                
                # Añadir numeración secuencial
                df['numero'] = range(1, len(df) + 1)
                
                # CRÍTICO: Ordenar por timestamp para asegurar que los más recientes estén primero
                if 'timestamp' in df.columns and not df['timestamp'].isna().all():
                    try:
                        df['timestamp_parsed'] = pd.to_datetime(df['timestamp'])
                        df = df.sort_values(by='timestamp_parsed', ascending=False)  # Los más recientes primero
                        df = df.drop('timestamp_parsed', axis=1)
                        logger.info("Tweets ordenados por fecha (más recientes primero)")
                        
                        # Mostrar información de los primeros 3 tweets para diagnosticar
                        if len(df) > 0:
                            logger.info("Primeros tweets después de ordenar:")
                            for i, (_, row) in enumerate(df.head(3).iterrows()):
                                logger.info(f"Tweet {i+1}: {row.get('timestamp', 'Sin fecha')} - {row.get('texto', '')[:50]}...")
                    except Exception as e:
                        logger.error(f"No se pudieron ordenar los tweets por fecha: {str(e)}")
                
                # Eliminar columna tweet_id si está presente
                if 'tweet_id' in df.columns:
                    df = df.drop('tweet_id', axis=1)
                
                logger.info(f"Extracción y procesamiento exitoso de {len(df)} tweets para @{clean_username}")
                return df
            else:
                logger.warning(f"No se encontraron tweets para @{clean_username}")
                return pd.DataFrame(columns=["texto", "usuario", "timestamp", "numero"])
                
        except Exception as e:
            logger.error(f"Error extrayendo tweets: {str(e)}")
            # Guardar captura de pantalla para diagnóstico
            await self.page.screenshot(path=f"/tmp/error_{clean_username}.png")
            logger.info(f"Captura de pantalla de error guardada en /tmp/error_{clean_username}.png")
            raise Exception(f"Error en la extracción de tweets: {str(e)}")
    
    async def _extract_tweets_data(self, hashtag=None, pinned_tweet_ids=None):
        """
        Extract data from tweets currently visible on the page.
        
        Args:
            hashtag (str): Hashtag to filter by (None for no filtering)
            pinned_tweet_ids (set): Set of tweet IDs to filter out (None to include all tweets)
            
        Returns:
            list: List of dictionaries containing tweet data
        """
        tweets_data = []
        if pinned_tweet_ids is None:
            pinned_tweet_ids = set()
        
        # Tweet selectors used by Twitter
        tweet_selectors = [
            "article[data-testid='tweet']",
            "div[data-testid='tweet']",
            "div[data-testid='cellInnerDiv']",
            "div.tweet",
            "div.js-stream-tweet",
            "div[role='article']", # Newer Twitter layout
            "article[role='article']" # Alt Twitter layout
        ]
        
        tweet_selector = None
        for selector in tweet_selectors:
            try:
                tweet_elements = await self.page.query_selector_all(selector)
                if tweet_elements and len(tweet_elements) > 0:
                    tweet_selector = selector
                    logger.info(f"Found {len(tweet_elements)} tweets using selector: {selector}")
                    break
            except Exception as e:
                logger.warning(f"Error with selector {selector}: {str(e)}")
        
        if not tweet_selector:
            logger.warning("No tweets found on page")
            return tweets_data
        
        # Get all tweet elements
        tweet_elements = await self.page.query_selector_all(tweet_selector)
        logger.info(f"Found {len(tweet_elements)} potential tweet elements")
        
        # Detect all pinned or promoted tweets first
        for i, tweet_el in enumerate(tweet_elements):
            try:
                # Detectar si es un tweet fijado o promocionado
                special_indicators = [
                    "div[data-testid='socialContext']", # Pinned tweet
                    "span:has-text('Pinned')",
                    "span:has-text('Fijado')",
                    "div:has-text('Promoted')",
                    "div:has-text('Promocionado')",
                    "span:has-text('Promoted')",
                    "span:has-text('Promocionado')"
                ]
                
                for indicator_selector in special_indicators:
                    try:
                        indicator = await tweet_el.query_selector(indicator_selector)
                        if indicator:
                            indicator_text = await indicator.inner_text()
                            if any(text in indicator_text for text in ["Pinned", "Fijado", "Promoted", "Promocionado"]):
                                # Es un tweet fijado o promocionado, extraer su ID para filtrarlo
                                try:
                                    # Intentar obtener ID desde URL de status
                                    link_el = await tweet_el.query_selector("a[href*='/status/']")
                                    if link_el:
                                        href = await link_el.get_attribute("href")
                                        if href and '/status/' in href:
                                            parts = href.split('/status/')
                                            if len(parts) > 1:
                                                tweet_id = parts[1].split('?')[0].split('/')[0]
                                                pinned_tweet_ids.add(tweet_id)
                                                logger.info(f"Adding special tweet to filter list: {tweet_id[:15]}... ({indicator_text})")
                                    
                                    # Como fallback, usar texto o ID del elemento
                                    if not tweet_id:
                                        tweet_text = await tweet_el.inner_text()
                                        pinned_tweet_ids.add(tweet_text[:50])  # Usar primeros 50 caracteres como ID
                                except Exception as e:
                                    logger.debug(f"Error extracting special tweet ID: {str(e)}")
                    except Exception as e:
                        continue
            except Exception as e:
                logger.debug(f"Error checking tweet {i+1} for special status: {str(e)}")

        # Process each tweet
        for i, tweet_el in enumerate(tweet_elements):
            try:
                tweet_data = {}
                
                # Verificar si es un tweet especial (fijado/promocionado)
                is_special_tweet = False
                special_indicators = [
                    "div[data-testid='socialContext']", # Pinned tweet
                    "span:has-text('Pinned')",
                    "span:has-text('Fijado')",
                    "div:has-text('Promoted')",
                    "div:has-text('Promocionado')",
                    "span:has-text('Promoted')",
                    "span:has-text('Promocionado')"
                ]
                
                for indicator_selector in special_indicators:
                    try:
                        indicator = await tweet_el.query_selector(indicator_selector)
                        if indicator:
                            indicator_text = await indicator.inner_text()
                            if any(text in indicator_text for text in ["Pinned", "Fijado", "Promoted", "Promocionado"]):
                                is_special_tweet = True
                                logger.info(f"Tweet {i+1} is a special tweet ({indicator_text}), will be filtered out")
                                break
                    except:
                        continue
                
                # Skip this tweet if it's pinned or promoted
                if is_special_tweet:
                    continue
                
                # Try to extract text
                tweet_text = ""
                text_selectors = [
                    "div[data-testid='tweetText']",
                    "div[lang]",  # Often used for tweet text with language attribute
                    "div.css-901oao.r-18jsvk2.r-37j5jr.r-a023e6",  # Common Twitter class
                    "div.css-901oao",  # Broader Twitter class for text
                    "div.tweet-text",
                    "p.tweet-text",
                    "div[dir='auto']"  # Another common pattern for tweet text
                ]
                
                for text_selector in text_selectors:
                    try:
                        text_element = await tweet_el.query_selector(text_selector)
                        if text_element:
                            tweet_text = await text_element.inner_text()
                            if tweet_text and tweet_text.strip():
                                break
                    except:
                        continue
                
                # If no text found using selectors, try getting all text from tweet
                if not tweet_text or not tweet_text.strip():
                    try:
                        tweet_text = await tweet_el.inner_text()
                        # Try to clean up the text - remove common UI elements text
                        for remove_text in ["Follow", "Reply", "Retweet", "Like", "Share", "View", "More", 
                                           "Seguir", "Responder", "Retweetear", "Me gusta", "Compartir", "Ver"]:
                            tweet_text = tweet_text.replace(remove_text, "")
                    except:
                        pass
                
                # Skip this tweet if we still don't have text
                if not tweet_text or not tweet_text.strip():
                    logger.debug(f"Skipping tweet {i+1} - no text content found")
                    continue
                
                tweet_data['texto'] = tweet_text.strip()
                
                # Extract username
                username = "Unknown"
                try:
                    user_selectors = [
                        "div[data-testid='User-Name'] span",
                        "div[data-testid='User-Name'] a",
                        "span.username",
                        "a[data-testid='Tweet-Username']",
                        "a.user-link",
                        "a.username",
                        "a[role='link']:has-text('@')", # Username links often contain @ symbol
                        "span:has-text('@')"  # Plain text username
                    ]
                    
                    for user_selector in user_selectors:
                        try:
                            user_elements = await tweet_el.query_selector_all(user_selector)
                            for user_element in user_elements:
                                user_text = await user_element.inner_text()
                                if '@' in user_text:  # Verify it looks like a username
                                    username = user_text
                                    # Clean username
                                    username = username.strip()
                                    if username.startswith('@'):
                                        username = username[1:]
                                    break
                            if username != "Unknown":
                                break
                        except:
                            continue
                except Exception as e:
                    logger.warning(f"Error extracting username: {str(e)}")
                
                tweet_data['usuario'] = username
                
                # Extract timestamp
                timestamp = ""
                try:
                    time_selectors = [
                        "time",
                        "a[href*='/status/'] time",
                        "span.tweet-timestamp",
                        "a.tweet-timestamp",
                        "a[href*='/status/'] span", # In newer Twitter UI
                        "span:has-text(/\\d{1,2}[A-Za-z]{3}/)",  # Date patterns like "25 Apr"
                        "span:has-text(/\\d{1,2}\\s+[A-Za-z]{3}/)"  # Date with spaces
                    ]
                    
                    for time_selector in time_selectors:
                        try:
                            time_elements = await tweet_el.query_selector_all(time_selector)
                            for time_element in time_elements:
                                # First try to get datetime attribute (most reliable)
                                datetime_attr = await time_element.get_attribute("datetime")
                                if datetime_attr:
                                    timestamp = datetime_attr
                                    break
                                    
                                # Otherwise get the text and see if it looks like a date
                                element_text = await time_element.inner_text()
                                if element_text:
                                    # Check if text contains date-like patterns
                                    if any(month in element_text for month in ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]):
                                        timestamp = element_text
                                        logger.debug(f"Found timestamp text: {timestamp}")
                                        break
                            
                            if timestamp:
                                break
                        except:
                            continue
                except Exception as e:
                    logger.warning(f"Error extracting timestamp: {str(e)}")
                
                tweet_data['timestamp'] = timestamp
                
                # Try to extract tweet ID
                tweet_id = ""
                is_in_thread = False
                try:
                    # Tweet ID is usually in the href of links to the tweet status
                    link_selectors = ["a[href*='/status/']"]
                    for link_selector in link_selectors:
                        link_elements = await tweet_el.query_selector_all(link_selector)
                        for link_el in link_elements:
                            href = await link_el.get_attribute("href")
                            if href and '/status/' in href:
                                parts = href.split('/status/')
                                if len(parts) > 1:
                                    tweet_id = parts[1].split('?')[0].split('/')[0]
                                    # Check if this tweet is already in our filter list
                                    if tweet_id in pinned_tweet_ids:
                                        is_in_thread = True
                                        logger.info(f"Tweet {i+1} matches a filtered tweet ID, will be skipped")
                                    break
                        if tweet_id:
                            break
                except Exception as e:
                    logger.debug(f"Error extracting tweet ID: {str(e)}")
                
                tweet_data['tweet_id'] = tweet_id
                
                # Skip if this is a known filtered tweet
                if is_in_thread or (tweet_id and tweet_id in pinned_tweet_ids):
                    logger.info(f"Skipping filtered tweet: {tweet_id}")
                    continue
                
                # Also check tweet content for text-based filtering
                # This helps when the tweet ID can't be determined
                for filter_text in pinned_tweet_ids:
                    if isinstance(filter_text, str) and len(filter_text) > 20 and filter_text in tweet_text:
                        logger.info(f"Skipping tweet that matches filtered content: {filter_text[:20]}...")
                        is_in_thread = True
                        break
                
                if is_in_thread:
                    continue
                
                # Filter by hashtag if specified
                if hashtag:
                    hashtag_clean = hashtag.lower().strip('#')
                    tweet_text_lower = tweet_data['texto'].lower()
                    if f"#{hashtag_clean}" not in tweet_text_lower and f" {hashtag_clean} " not in tweet_text_lower:
                        continue
                
                # Only add tweet if it has valid content and is not already in our list
                if len(tweet_data['texto'].strip()) > 0:
                    # Check if this tweet is a duplicate of one we already have
                    is_duplicate = False
                    for existing_tweet in tweets_data:
                        if tweet_data['texto'] == existing_tweet.get('texto'):
                            is_duplicate = True
                            break
                    
                    if not is_duplicate:
                        tweets_data.append(tweet_data)
                        logger.debug(f"Tweet {i+1} processed: {tweet_data['texto'][:30]}...")
                    else:
                        logger.debug(f"Skipping duplicate tweet: {tweet_data['texto'][:30]}...")
            
            except Exception as e:
                logger.error(f"Error processing tweet {i+1}: {str(e)}")
        
        logger.info(f"Successfully extracted {len(tweets_data)} tweets after filtering")
        return tweets_data

    def dataframe_to_csv(self, df):
        """
        Convert DataFrame to CSV string.
        
        Args:
            df (pandas.DataFrame): DataFrame to convert
            
        Returns:
            str: CSV string
        """
        csv_buffer = io.StringIO()
        df.to_csv(csv_buffer, index=False)
        csv_buffer.seek(0)
        return csv_buffer.getvalue()


# Helper function to run asynchronous code from synchronous code
def run_async(coro):
    """
    Run an asynchronous coroutine from synchronous code.
    
    Args:
        coro: Coroutine to run
        
    Returns:
        Result of the coroutine
    """
    return asyncio.get_event_loop().run_until_complete(coro)


# Wrapper for compatibility with existing code
class TwitterScraper:
    """Wrapper for compatibility for the Twitter scraper based on Playwright."""
    
    def __init__(self, username=None, password=None, bypass_login=False):
        self.username = username
        self.password = password
        self.bypass_login = bypass_login
        self.scraper = None
    
    def __enter__(self):
        # Create asynchronous scraper and run it
        async def setup():
            self.scraper = TwitterPlaywrightScraper(
                username=self.username,
                password=self.password,
                bypass_login=self.bypass_login
            )
            return await self.scraper.__aenter__()
        
        run_async(setup())
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        # Close asynchronous scraper
        if self.scraper:
            run_async(self.scraper.__aexit__(exc_type, exc_val, exc_tb))
    
    def extract_by_hashtag(self, hashtag, max_tweets=30, min_tweets=10, max_scrolls=10):
        """Wrapper synchronous for extract_by_hashtag."""
        return run_async(self.scraper.extract_by_hashtag(
            hashtag=hashtag,
            max_tweets=max_tweets,
            min_tweets=min_tweets,
            max_scrolls=max_scrolls
        ))
    
    def extract_by_user(self, username, max_tweets=30, min_tweets=10, max_scrolls=10):
        """Wrapper synchronous for extract_by_user."""
        return run_async(self.scraper.extract_by_user(
            username=username,
            max_tweets=max_tweets,
            min_tweets=min_tweets,
            max_scrolls=max_scrolls
        ))
    
    def dataframe_to_csv(self, df):
        """Wrapper for dataframe_to_csv."""
        return self.scraper.dataframe_to_csv(df) 