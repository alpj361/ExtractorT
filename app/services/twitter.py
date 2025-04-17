import logging
import pandas as pd
import io
import time
import os
import json
import random
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from app.utils.browser import setup_browser, random_delay, scroll_page, cleanup_user_data_dir
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

class TwitterScraper:
    """Service for scraping tweets from Twitter."""
    
    def __init__(self, username=None, password=None, bypass_login=False):
        """
        Initialize TwitterScraper with optional credentials.
        
        Args:
            username (str, optional): Twitter username or email
            password (str, optional): Twitter password
            bypass_login (bool): Whether to bypass login and attempt direct access
        """
        self.driver = None
        self.user_data_dir = None
        self.username = username or os.environ.get('TWITTER_USERNAME')
        self.password = password or os.environ.get('TWITTER_PASSWORD')
        self.bypass_login = bypass_login
        
        # Only check for credentials if we're not bypassing login
        if not self.bypass_login and (not self.username or not self.password):
            raise ValueError("Twitter credentials not provided. Set TWITTER_USERNAME and TWITTER_PASSWORD environment variables or pass them to the constructor.")
    
    def __enter__(self):
        """Set up the browser when entering context."""
        try:
            logger.info("Initializing browser for Twitter scraping")
            self.driver, self.user_data_dir = setup_browser()
            
            # Inject anti-detection scripts
            logger.info("Injecting anti-detection scripts")
            self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": """
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                    Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                    Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
                    window.chrome = { runtime: {} };
                """
            })
            
            logger.info("Browser setup successful")
            return self
        except Exception as e:
            logger.error(f"Browser setup failed: {str(e)}")
            if self.user_data_dir:
                cleanup_user_data_dir(self.user_data_dir)
            raise
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Clean up resources when exiting context."""
        if self.driver:
            logger.info("Closing browser")
            try:
                self.driver.quit()
            except Exception as e:
                logger.error(f"Error closing browser: {e}")

    def load_cookies_from_file(self):
        """
        Load cookies from the JSON file to authenticate with Twitter/X.
        
        Returns:
            bool: True if cookies were loaded successfully, False otherwise
        """
        try:
            # Twitter has rebranded as X, so we might need to handle both domains
            twitter_domains = ["x.com", "twitter.com"]  # Intenta primero x.com
            
            # Cuenta cookies válidas encontradas
            cookie_count = 0
            
            # Intenta cargar cookies de cada archivo posible
            cookie_paths = [
                "/app/cookies/twitter_cookies.json",  # Docker container path
                "twitter_cookies.json"                # Local development path
            ]
            
            # Encuentra el primer archivo de cookies existente
            cookie_file = None
            for path in cookie_paths:
                if os.path.exists(path):
                    cookie_file = path
                    logger.info(f"Encontrado archivo de cookies: {cookie_file}")
                    break
            
            if not cookie_file:
                logger.error("No se encontró ningún archivo de cookies")
                return False
            
            # Carga cookies del archivo
            logger.info(f"Cargando cookies desde {cookie_file}")
            with open(cookie_file, 'r') as f:
                cookies = json.load(f)
            
            logger.info(f"Archivo contiene {len(cookies)} cookies")
            
            # Verifica si hay cookies clave de autenticación
            auth_cookies = ["auth_token", "ct0", "twid", "kdt"]
            found_auth_cookies = [cookie['name'] for cookie in cookies if cookie.get('name') in auth_cookies]
            logger.info(f"Cookies de autenticación encontradas: {found_auth_cookies}")
            
            if not any(cookie.get('name') in auth_cookies for cookie in cookies):
                logger.warning("No se encontraron cookies de autenticación importantes en el archivo. El inicio de sesión puede fallar.")
            
            # Try cada dominio
            for domain in twitter_domains:
                try:
                    # Navega al dominio específico
                    url = f"https://{domain}"
                    logger.info(f"Navegando a {url}")
                    self.driver.get(url)
                    random_delay(5, 7)  # Espera más tiempo para cargar completamente
                    
                    # Guarda captura de estado inicial
                    self.driver.save_screenshot(f"/tmp/before_cookies_{domain}.png")
                    
                    # Agrega cada cookie al driver
                    for cookie in cookies:
                        # Omite cookies con datos incompletos
                        if not all(k in cookie for k in ['name', 'value']):
                            continue
                            
                        # Crear una copia para modificar
                        cookie_dict = {
                            'name': cookie['name'],
                            'value': cookie['value'],
                            'path': '/'
                        }
                        
                        # Usa el dominio original de la cookie si está disponible
                        if 'domain' in cookie and cookie['domain']:
                            if cookie['domain'].startswith('.'):
                                # Mantén el dominio original con el punto inicial
                                cookie_dict['domain'] = cookie['domain']
                            else:
                                # Asegúrate de que el dominio coincida con el sitio actual
                                cookie_dict['domain'] = f".{domain}" if not domain.startswith('.') else domain
                        else:
                            # Si no hay dominio en la cookie original, usa el dominio actual
                            cookie_dict['domain'] = f".{domain}" if not domain.startswith('.') else domain
                        
                        # Copia atributos adicionales importantes si existen
                        for attr in ['expiry', 'secure', 'httpOnly']:
                            if attr in cookie:
                                # Selenium usa 'httpOnly', pero algunas exportaciones usan 'httponly'
                                key = attr if attr != 'httpOnly' or 'httpOnly' in cookie else 'httponly'
                                cookie_dict[attr] = cookie[key]
                        
                        try:
                            self.driver.add_cookie(cookie_dict)
                            cookie_count += 1
                            logger.debug(f"Agregada cookie {cookie_dict['name']} para dominio {cookie_dict['domain']}")
                        except Exception as e:
                            logger.debug(f"Error agregando cookie {cookie_dict['name']}: {str(e)}")
                    
                    logger.info(f"Se agregaron {cookie_count} cookies para {domain}")
                    
                    # Actualiza la página para aplicar cookies
                    logger.info(f"Actualizando página para aplicar cookies para {domain}")
                    self.driver.get(url)  # Mejor que refresh para asegurar la carga completa con cookies
                    random_delay(5, 7)  # Espera más tiempo para aplicar cookies
                    
                    # Guarda captura después de aplicar cookies
                    self.driver.save_screenshot(f"/tmp/after_cookies_{domain}.png")
                    
                    # Navega a la página principal para verificar inicio de sesión
                    self.driver.get(f"https://{domain}/home")
                    random_delay(5, 7)
                    
                    # Guarda captura de la página principal
                    self.driver.save_screenshot(f"/tmp/home_page_{domain}.png")
                    
                    # Verifica si el inicio de sesión fue exitoso buscando el botón de tweet
                    try:
                        # Busca íconos de inicio, botón de tweet u otros elementos que indiquen estado de sesión iniciada
                        selectors = [
                            "a[data-testid='SideNav_NewTweet_Button']",
                            "a[aria-label='Post']",
                            "a[data-testid='AppTabBar_Home_Link']",
                            "a[href='/home']",
                            "svg[data-testid='tweetButtonInline']",
                            "a[data-testid='SideNav_NewTweet_Button']",
                            "div[data-testid='tweetButtonInline']",
                            "div[aria-label='Timeline: Your Home Timeline']"
                        ]
                        
                        wait = WebDriverWait(self.driver, 15)  # Aumenta el tiempo de espera
                        for selector in selectors:
                            try:
                                element = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                                logger.info(f"Inicio de sesión con cookies exitoso en {domain} (encontrado {selector})")
                                return True
                            except TimeoutException:
                                continue
                                
                        # Comprueba si estamos en la URL /home sin redireccionamiento
                        if "/home" in self.driver.current_url and "login" not in self.driver.current_url:
                            logger.info(f"Detectada URL de inicio de sesión exitoso: {self.driver.current_url}")
                            return True
                            
                        logger.warning(f"No se encontraron indicadores de inicio de sesión en {domain}")
                    except Exception as e:
                        logger.error(f"Error verificando estado de inicio de sesión: {str(e)}")
                
                except Exception as e:
                    logger.warning(f"Error con dominio {domain}: {str(e)}")
            
            # Si llegamos aquí, todos los dominios fallaron
            logger.error("Error al iniciar sesión con cookies en todos los dominios")
            return False
                
        except Exception as e:
            logger.error(f"Error cargando cookies: {str(e)}")
            self.driver.save_screenshot("/tmp/cookie_loading_error.png")
            return False

    def login(self, max_retries=3):
        """
        Log in to Twitter using either cookies or credentials.
        
        Args:
            max_retries (int): Maximum number of retry attempts for login
        """
        # If we're bypassing login, just return
        if self.bypass_login:
            logger.info("Login bypassed - proceeding without authentication")
            return
        
        logger.info("Attempting to log in to Twitter")
        
        # In production mode, try to use cookies file first
        if os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("DOCKER_ENVIRONMENT"):
            logger.info("Running in production mode - trying to login with cookies")
            if self.load_cookies_from_file():
                return
            else:
                logger.warning("Cookie login failed, will try profile authentication")
        
        for attempt in range(max_retries):
            try:
                # Check if we need to log in
                logger.info("Checking login status")
                self.driver.get("https://twitter.com")
                random_delay(3, 5)  # Longer initial delay
                
                # Try to find login button
                try:
                    login_button = WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "a[href='/login']"))
                    )
                    
                    # Need to log in
                    logger.info("Login required - profile not found or session expired")
                    if not os.environ.get("RAILWAY_ENVIRONMENT") and not os.environ.get("DOCKER_ENVIRONMENT"):
                        logger.info("Running in local mode - please log in manually to create profile")
                        login_button.click()
                        # Wait for manual login (up to 5 minutes)
                        wait = WebDriverWait(self.driver, 300)
                        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a[data-testid='SideNav_NewTweet_Button']")))
                        logger.info("Manual login successful - profile saved")
                        return
                    else:
                        raise Exception("Login required but running in production mode")
                        
                except TimeoutException:
                    # No login button found - we might be logged in
                    try:
                        wait = WebDriverWait(self.driver, 5)
                        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a[data-testid='SideNav_NewTweet_Button']")))
                        logger.info("Already logged in")
                        return
                    except TimeoutException:
                        # Neither login button nor tweet button found
                        raise Exception("Could not determine login status")
                
                # Check for unusual activity detection with shorter timeout
                unusual_activity_wait = WebDriverWait(self.driver, 3)
                try:
                    unusual_activity = unusual_activity_wait.until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "input[data-testid='ocfEnterTextTextInput']"))
                    )
                    logger.warning("Unusual activity check detected")
                    self.driver.save_screenshot("/tmp/unusual_activity.png")
                    raise Exception("Twitter detected unusual activity")
                except TimeoutException:
                    pass  # No unusual activity detected, continue
                
                # Wait for and fill password field with human-like typing
                password_field = wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='password']"))
                )
                
                # Type password with random delays between characters
                for char in self.password:
                    password_field.send_keys(char)
                    time.sleep(random.uniform(0.1, 0.3))
                
                random_delay(0.5, 1)  # Pause before hitting enter
                password_field.send_keys(Keys.RETURN)
                logger.info("Password entered")
                
                # Add longer delay to simulate human behavior
                random_delay(2.5, 4)
                
                # Verify login success
                try:
                    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a[data-testid='SideNav_NewTweet_Button']")))
                    logger.info("Successfully logged in to Twitter")
                    return
                except TimeoutException:
                    # Take screenshot for debugging
                    self.driver.save_screenshot("/tmp/login_failed.png")
                    if attempt < max_retries - 1:
                        logger.warning(f"Login verification failed, retrying... (Attempt {attempt + 1}/{max_retries})")
                        continue
                    raise Exception("Could not verify successful login")
                
            except Exception as e:
                self.driver.save_screenshot(f"/tmp/login_error_{attempt}.png")
                if attempt < max_retries - 1:
                    logger.error(f"Login attempt {attempt + 1} failed: {str(e)}")
                    time.sleep(2)  # Wait before retry
                    continue
                logger.error(f"All login attempts failed: {str(e)}")
                raise Exception(f"Failed to log in after {max_retries} attempts: {str(e)}")

    def verify_login(self):
        """
        Verify that we are still logged in.
        
        Returns:
            bool: True if logged in, False otherwise
        """
        # If bypassing login, don't bother checking
        if self.bypass_login:
            return True
            
        wait = WebDriverWait(self.driver, 20)
        try:
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a[data-testid='SideNav_NewTweet_Button']")))
            logger.info("Login status verified")
            return True
        except TimeoutException:
            logger.error("Login verification failed")
            self.driver.save_screenshot("/tmp/login_verification_failed.png")
            return False
    
    def extract_by_hashtag(self, hashtag, max_tweets=30, min_tweets=10, max_scrolls=10):
        """
        Extract tweets containing a specific hashtag.
        
        Args:
            hashtag (str): Hashtag to search for (without the # symbol)
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
        
        # If not bypassing login, try to log in first
        login_success = False
        if not self.bypass_login:
            try:
                self.login()
                login_success = self.verify_login()
                if login_success:
                    logger.info("Login successful, proceeding with authenticated session")
                else:
                    logger.warning("Login failed, will try to continue unauthenticated")
            except Exception as e:
                logger.warning(f"Login failed but attempting to continue without authentication: {str(e)}")
                # Continue without login
        
        # Construct search URLs - try both exploration mode and search mode
        search_urls = [
            f"https://twitter.com/search?q=%23{clean_hashtag}&src=typed_query&f=top",
            f"https://twitter.com/hashtag/{clean_hashtag}?src=hashtag_click",
            f"https://x.com/search?q=%23{clean_hashtag}&src=typed_query&f=top",
            f"https://x.com/hashtag/{clean_hashtag}?src=hashtag_click"
        ]
        
        logger.info(f"Will try {len(search_urls)} different search URLs")
        
        # Try each URL until we find one that works
        for url_index, url in enumerate(search_urls):
            try:
                logger.info(f"Trying URL {url_index+1}/{len(search_urls)}: {url}")
                
                # Navigate to the search URL
                self.driver.get(url)
                
                # Tomar captura inicial para ver cómo se ve la página
                initial_screenshot_path = f"/tmp/search_initial_{clean_hashtag}_{url_index}.png"
                self.driver.save_screenshot(initial_screenshot_path)
                logger.info(f"Initial screenshot saved at {initial_screenshot_path}")
                
                # Save current URL for debugging
                logger.info(f"Current URL after navigation: {self.driver.current_url}")
                
                # If we encounter the login overlay, try to dismiss it or work around it
                try:
                    # Wait a short time to check for login overlay
                    logger.info("Checking for login overlay...")
                    close_button = WebDriverWait(self.driver, 3).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "div[aria-label='Close']"))
                    )
                    logger.info("Found login overlay, attempting to dismiss")
                    close_button.click()
                    random_delay(1, 2)
                except TimeoutException:
                    # No login overlay, continue
                    logger.info("No login overlay detected")
                
                # Try to use keyboard to access the explore/guest view on Twitter/X
                # This can help bypass the login requirement in some cases
                if not login_success and "login" in self.driver.current_url:
                    logger.info("Detected login redirect, trying to access explore view...")
                    try:
                        # Twitter sometimes allows access to the explore/search page with this trick
                        self.driver.get(f"https://twitter.com/explore")
                        random_delay(3, 5)
                        self.driver.get(url)  # Try the original URL again
                        random_delay(3, 5)
                    except Exception as e:
                        logger.warning(f"Error trying alternative access: {str(e)}")
                
                # Take a screenshot after attempts to bypass login
                self.driver.save_screenshot(f"/tmp/search_afterbypass_{clean_hashtag}_{url_index}.png")
                
                # If still on login page, this URL won't work - try next one
                if "login" in self.driver.current_url:
                    logger.warning(f"Still redirected to login page, skipping URL: {url}")
                    continue  # Try next URL
                
                # Take a longer time to wait for the search results
                logger.info("Waiting for search results to load")
                wait = WebDriverWait(self.driver, 30)
                
                # Look for tweet containers with various selectors used by Twitter
                tweet_selectors = [
                    "article[data-testid='tweet']",
                    "div[data-testid='cellInnerDiv']",
                    "div.css-1dbjc4n.r-1iusvr4.r-16y2uox", # Common CSS class for tweet containers
                    "div[data-testid='tweet']",
                    "div.css-1dbjc4n.r-1loqt21.r-18u37iz.r-1ny4l3l.r-1udh08x" # Another common tweet container
                ]
                
                found_selector = None
                for selector in tweet_selectors:
                    try:
                        # Try to find at least one element with this selector
                        logger.info(f"Trying to find tweets with selector: {selector}")
                        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                        found_selector = selector
                        logger.info(f"Found tweets using selector: {selector}")
                        break
                    except TimeoutException:
                        logger.warning(f"Selector not found: {selector}")
                        continue
                
                if not found_selector:
                    logger.warning(f"Could not locate the primary tweet element selector with URL {url}. Trying next URL...")
                    # Save debug info before moving to next URL
                    try:
                        screenshot_path = f"/app/debug_screenshot_{url_index}.png"
                        self.driver.save_screenshot(screenshot_path)
                        logger.info(f"Screenshot saved to {screenshot_path} inside the container.")
                        
                        # Save page source for debugging
                        with open(f"/tmp/page_source_{url_index}.html", "w", encoding="utf-8") as f:
                            f.write(self.driver.page_source)
                            logger.info(f"Page source saved to /tmp/page_source_{url_index}.html")
                    except Exception as screenshot_error:
                        logger.error(f"Failed to save debug info: {screenshot_error}")
                    continue  # Try next URL
                
                # Wait for page to fully load
                random_delay(2, 4)
                
                # Scroll to load more tweets
                logger.info("Scrolling to load more tweets")
                for i in range(max_scrolls):
                    self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    random_delay(1, 3)  # Random delay between scrolls
                    logger.info(f"Scroll {i+1}/{max_scrolls} completed")
                
                # Take a screenshot after scrolling
                self.driver.save_screenshot(f"/tmp/search_result_{clean_hashtag}_{url_index}.png")
                
                # Extract tweets using the found selector
                tweets_data = self._find_and_process_tweets_without_login(found_selector, clean_hashtag, max_tweets, min_tweets)
                
                # Create DataFrame
                if tweets_data:
                    df = pd.DataFrame(tweets_data)
                    logger.info(f"Successfully extracted {len(df)} tweets for #{clean_hashtag} with URL {url}")
                    return df
                else:
                    logger.warning(f"No tweets found for #{clean_hashtag} with URL {url}")
                    # Continue to next URL instead of returning empty DataFrame immediately
            
            except TimeoutException:
                logger.error(f"Timeout while loading Twitter page for URL: {url}")
                # Try next URL instead of raising exception
            except WebDriverException as e:
                logger.error(f"WebDriver error with URL {url}: {str(e)}")
                # Try next URL instead of raising exception
            except Exception as e:
                logger.error(f"Unexpected error with URL {url}: {str(e)}")
                # Try next URL
        
        # If we reached here, all URLs failed
        logger.error(f"Could not extract tweets for #{clean_hashtag} with any URL")
        return pd.DataFrame(columns=["texto", "usuario", "timestamp", "numero"])
    
    def _find_and_process_tweets_without_login(self, selector, search_term, max_tweets, min_tweets):
        """
        Find and process tweets without requiring login.
        
        Args:
            selector (str): CSS selector to use for finding tweets
            search_term (str): Term to filter tweets by (None for no filtering)
            max_tweets (int): Maximum number of tweets to extract
            min_tweets (int): Minimum number of tweets to extract before stopping
        
        Returns:
            list: List of dictionaries containing tweet data
        """
        logger.info(f"Searching for tweets with selector: {selector} and term: {search_term}")
        tweets_data = []
        processed = 0
        
        try:
            # Find all tweet elements
            tweets = self.driver.find_elements(By.CSS_SELECTOR, selector)
            logger.info(f"Found {len(tweets)} potential tweet elements")
            
            # Take a screenshot for debugging
            self.driver.save_screenshot("/tmp/tweets_found.png")
            
            # Save page source for debugging
            with open("/tmp/page_source.html", "w", encoding="utf-8") as f:
                f.write(self.driver.page_source)
                
            # Process each tweet with a broader approach to extract text content
            for i, tweet in enumerate(tweets[:max_tweets]):
                try:
                    # Try multiple selectors to extract text
                    text_selectors = [
                        "div[data-testid='tweetText']",
                        "div.css-901oao",  # General text class
                        ".r-1qd0xha" # Another common class for tweet text
                    ]
                    
                    text = None
                    for text_selector in text_selectors:
                        try:
                            text_elements = tweet.find_elements(By.CSS_SELECTOR, text_selector)
                            if text_elements:
                                text = " ".join([el.text for el in text_elements if el.text.strip()])
                                if text:
                                    break
                        except Exception:
                            continue
                    
                    # If no text found with selectors, try getting all text from the tweet
                    if not text:
                        text = tweet.text
                    
                    # Skip tweets with no text
                    if not text or len(text.strip()) == 0:
                        continue
                        
                    # Try to extract username and timestamp
                    username = "Unknown"
                    timestamp = ""
                    try:
                        username_element = tweet.find_element(By.CSS_SELECTOR, "div[data-testid='User-Name']")
                        username = username_element.text
                    except Exception:
                        pass
                        
                    try:
                        time_element = tweet.find_element(By.CSS_SELECTOR, "time")
                        timestamp = time_element.get_attribute("datetime")
                    except Exception:
                        pass
                    
                    # Filter by search term if provided
                    if search_term is None or search_term.lower() in text.lower() or f"#{search_term.lower()}" in text.lower():
                        tweets_data.append({
                            'texto': text,
                            'usuario': username,
                            'timestamp': timestamp,
                            'numero': i+1
                        })
                        processed += 1
                        logger.debug(f"Tweet {i+1} processed: {text[:30]}...")
                        
                        # Stop if we have enough tweets
                        if processed >= min_tweets and len(tweets_data) >= min_tweets:
                            logger.info(f"Reached minimum of {min_tweets} tweets, stopping")
                            break
                    
                    # Add a random delay between processing tweets
                    random_delay(0.2, 0.5)
                            
                except Exception as e:
                    logger.error(f"Error processing tweet {i+1}: {str(e)}")
            
            logger.info(f"Successfully processed {len(tweets_data)} tweets")
            return tweets_data
            
        except Exception as e:
            logger.error(f"Error finding tweets: {str(e)}")
            return tweets_data

    def extract_by_user(self, username, max_tweets=30, min_tweets=10, max_scrolls=10):
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
        logger.info(f"Opening URL: {url}")
        
        try:
            # Navigate to the profile URL
            self.driver.get(url)
            
            # Wait for page to load
            random_delay(5, 7)
            
            # Scroll to load more tweets
            logger.info("Scrolling to load more tweets")
            scroll_page(self.driver, num_scrolls=max_scrolls)
            
            # Find tweets (no filtering by hashtag for user timeline)
            tweets_data = self._find_and_process_tweets(None, max_tweets, min_tweets)
            
            # Create DataFrame
            if tweets_data:
                df = pd.DataFrame(tweets_data)
                logger.info(f"Successfully extracted {len(df)} tweets for @{clean_username}")
                return df
            else:
                logger.warning(f"No tweets found for @{clean_username}")
                return pd.DataFrame(columns=["texto", "numero"])
                
        except TimeoutException:
            logger.error("Timeout while loading Twitter page")
            raise Exception("Timeout while loading Twitter page")
        except WebDriverException as e:
            logger.error(f"WebDriver error: {str(e)}")
            raise Exception(f"Browser error: {str(e)}")
        except Exception as e:
            logger.error(f"Error extracting tweets: {str(e)}")
            raise Exception(f"Failed to extract tweets: {str(e)}")
    
    def _find_and_process_tweets(self, search_term, max_tweets, min_tweets):
        """
        Find and process tweets from the current page.
        
        Args:
            search_term (str): Term to filter tweets by (None for no filtering)
            max_tweets (int): Maximum number of tweets to extract
            min_tweets (int): Minimum number of tweets to extract before stopping
        
        Returns:
            list: List of dictionaries containing tweet data
        """
        logger.info(f"Searching for tweets with term: {search_term}")
        tweets = []
        wait = WebDriverWait(self.driver, 20)
        try:
            # Wait for tweets to be present
            wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'article[data-testid="tweet"]')))
            
            # Find tweets
            tweets = self.driver.find_elements(By.CSS_SELECTOR, 'article[data-testid="tweet"]')
            logger.info(f"Found {len(tweets)} tweets")
            
            if len(tweets) < min_tweets:
                logger.warning(f"Found fewer tweets than expected: {len(tweets)} < {min_tweets}")
                
            # Take a screenshot for debugging
            self.driver.save_screenshot('/tmp/tweets_found.png')
            logger.info("Screenshot saved as /tmp/tweets_found.png")
            
            # Log page source for debugging
            with open('/tmp/page_source.html', 'w', encoding='utf-8') as f:
                f.write(self.driver.page_source)
            logger.info("Page source saved as /tmp/page_source.html")
            
        except TimeoutException:
            logger.error("Timeout while waiting for tweets to load")
            self.driver.save_screenshot('/tmp/tweets_timeout.png')
            raise Exception("Failed to load tweets")
        
        logger.info(f"Total elements found: {len(tweets)}")
        
        # Process tweets
        tweets_data = []
        processed = 0
        
        for i, tweet in enumerate(tweets[:max_tweets]):
            try:
                # Extract text and other relevant information
                text = tweet.find_element(By.CSS_SELECTOR, 'div[data-testid="tweetText"]').text
                username = tweet.find_element(By.CSS_SELECTOR, 'div[data-testid="User-Name"]').text
                timestamp = tweet.find_element(By.CSS_SELECTOR, 'time').get_attribute('datetime')
                
                logger.debug(f"Raw tweet text: {text[:100]}...")  # Log first 100 characters
                
                # Filter by search term if provided
                if search_term is None or search_term.lower() in text.lower() or f"#{search_term.lower()}" in text.lower():
                    tweets_data.append({
                        'texto': text,
                        'usuario': username,
                        'timestamp': timestamp,
                        'numero': i+1
                    })
                    processed += 1
                    logger.debug(f"Tweet {i+1} processed")
                    
                    # Stop if we have enough tweets
                    if processed >= min_tweets and len(tweets_data) >= min_tweets:
                        logger.info(f"Reached minimum of {min_tweets} tweets, stopping")
                        break
                
                # Add a random delay between processing tweets
                random_delay(0.5, 1.5)
                        
            except Exception as e:
                logger.error(f"Error processing tweet {i+1}: {str(e)}")
        
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
