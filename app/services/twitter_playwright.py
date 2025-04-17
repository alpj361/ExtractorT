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
            
            # Crear contexto con UA realista
            self.context = await self.browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
            )
            
            # Inyectar scripts anti-detección
            await self.context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'languages', { get: () => ['es-ES', 'es', 'en-US', 'en'] });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            window.chrome = { runtime: {} };
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
    
    async def verify_auth(self):
        """
        Verificar si la autenticación está activa.
        
        Returns:
            bool: True si el usuario está autenticado
        """
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
                return False
            
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
            return False
            
        except Exception as e:
            logger.error(f"Error al verificar autenticación: {str(e)}")
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
        
        # Construct profile URL
        url = f"https://twitter.com/{clean_username}"
        url_alt = f"https://x.com/{clean_username}"
        logger.info(f"Attempting to open URL: {url}")
        
        try:
            # Try with twitter.com first
            await self.page.goto(url, wait_until="domcontentloaded")
            
            # Check if we were redirected to login page
            current_url = self.page.url
            if "login" in current_url:
                logger.info("Redirected to login page, trying x.com instead")
                await self.page.goto(url_alt, wait_until="domcontentloaded")
                current_url = self.page.url
                
                # If still on login page, try an alternative approach
                if "login" in current_url:
                    logger.warning("Still on login page, trying to use search-based approach")
                    search_url = f"https://twitter.com/search?q=from%3A{clean_username}&src=typed_query&f=live"
                    await self.page.goto(search_url, wait_until="domcontentloaded")
            
            # Wait for page to load
            await asyncio.sleep(random.uniform(5, 7))
            
            # Scroll to load more tweets
            logger.info("Scrolling to load more tweets")
            tweets_data = []
            scrolls = 0
            
            while len(tweets_data) < max_tweets and scrolls < max_scrolls:
                # Scroll down
                await self.page.evaluate("window.scrollBy(0, window.innerHeight)")
                await asyncio.sleep(random.uniform(1, 3))
                
                # Find and process tweets after each scroll
                new_tweets = await self._extract_tweets_data(None)  # No hashtag filtering for user timeline
                
                # Add new unique tweets
                for tweet in new_tweets:
                    if tweet not in tweets_data:
                        tweets_data.append(tweet)
                
                logger.info(f"Found {len(tweets_data)} tweets after {scrolls+1} scrolls")
                
                # Stop if we have enough tweets and have scrolled at least once
                if len(tweets_data) >= min_tweets and scrolls > 0:
                    break
                    
                scrolls += 1
            
            # Create DataFrame
            if tweets_data:
                df = pd.DataFrame(tweets_data)
                # Add sequential numbering
                df['numero'] = range(1, len(df) + 1)
                logger.info(f"Successfully extracted {len(df)} tweets for @{clean_username}")
                return df
            else:
                logger.warning(f"No tweets found for @{clean_username}")
                return pd.DataFrame(columns=["texto", "usuario", "timestamp", "numero"])
                
        except Exception as e:
            logger.error(f"Error extracting tweets: {str(e)}")
            # Save a screenshot for debugging
            await self.page.screenshot(path="/tmp/twitter_error.png")
            logger.info("Error screenshot saved to /tmp/twitter_error.png")
            raise Exception(f"Failed to extract tweets: {str(e)}")
    
    async def _extract_tweets_data(self, hashtag=None):
        """
        Extract data from tweets currently visible on the page.
        
        Args:
            hashtag (str): Hashtag to filter by (None for no filtering)
            
        Returns:
            list: List of dictionaries containing tweet data
        """
        tweets_data = []
        
        # Tweet selectors used by Twitter
        tweet_selectors = [
            "article[data-testid='tweet']",
            "div[data-testid='tweet']",
            "div.tweet",
            "div.js-stream-tweet"
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
        
        # Process each tweet
        for i, tweet_el in enumerate(tweet_elements):
            try:
                # Try to extract text
                tweet_text = ""
                text_selectors = [
                    "div[data-testid='tweetText']",
                    "div.tweet-text",
                    "p.tweet-text"
                ]
                
                for text_selector in text_selectors:
                    try:
                        text_element = await tweet_el.query_selector(text_selector)
                        if text_element:
                            tweet_text = await text_element.inner_text()
                            break
                    except:
                        continue
                
                # If no text found using selectors, try getting all text from tweet
                if not tweet_text:
                    tweet_text = await tweet_el.inner_text()
                
                # Extract username if available
                username = "Unknown"
                try:
                    user_selectors = [
                        "div[data-testid='User-Name'] span",
                        "span.username",
                        "a.user"
                    ]
                    
                    for user_selector in user_selectors:
                        try:
                            user_element = await tweet_el.query_selector(user_selector)
                            if user_element:
                                username = await user_element.inner_text()
                                # Clean username
                                username = username.strip().replace("@", "")
                                break
                        except:
                            continue
                except:
                    pass
                
                # Extract timestamp if available
                timestamp = ""
                try:
                    time_selectors = [
                        "time",
                        "span.tweet-timestamp",
                        "a.tweet-timestamp"
                    ]
                    
                    for time_selector in time_selectors:
                        try:
                            time_element = await tweet_el.query_selector(time_selector)
                            if time_element:
                                # Try to get datetime attribute first
                                datetime_attr = await time_element.get_attribute("datetime")
                                if datetime_attr:
                                    timestamp = datetime_attr
                                else:
                                    # Fallback to inner text
                                    timestamp = await time_element.inner_text()
                                break
                        except:
                            continue
                except:
                    pass
                
                # Add tweet if it has text
                if tweet_text and len(tweet_text.strip()) > 0:
                    # Filter by hashtag if specified
                    if hashtag and f"#{hashtag}" not in tweet_text and f" {hashtag} " not in tweet_text:
                        continue
                        
                    tweets_data.append({
                        'texto': tweet_text.strip(),
                        'usuario': username,
                        'timestamp': timestamp,
                    })
                    logger.debug(f"Tweet {i+1} processed: {tweet_text[:30]}...")
                
            except Exception as e:
                logger.error(f"Error processing tweet {i+1}: {str(e)}")
                
        logger.info(f"Successfully extracted {len(tweets_data)} tweets")
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