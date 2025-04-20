#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import logging
import pandas as pd
import asyncio
import json
from datetime import datetime, timedelta

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

# Add parent directory to path to import app modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.twitter_playwright import TwitterPlaywrightScraper
from playwright.async_api import async_playwright

async def extract_from_profile():
    """
    Test extraction directly from user profile.
    """
    # Test parameters
    username = "KarinHerreraVP"
    max_tweets = 30
    min_tweets = 5
    max_scrolls = 10
    
    print(f"\n===== Extracción directa del perfil de @{username} =====")
    
    async with async_playwright() as playwright:
        # Launch browser
        browser = await playwright.chromium.launch(headless=False)
        
        # Load cookies if exist
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
        )
        
        # Load cookies
        cookie_paths = [
            "twitter_cookies.json",
            "playwright_data/twitter_cookies.json"
        ]
        
        cookies_loaded = False
        for cookie_path in cookie_paths:
            if os.path.exists(cookie_path):
                try:
                    print(f"Cargando cookies desde {cookie_path}")
                    with open(cookie_path, 'r') as f:
                        cookies = json.load(f)
                    await context.add_cookies(cookies)
                    cookies_loaded = True
                    print(f"Se cargaron {len(cookies)} cookies")
                    break
                except Exception as e:
                    print(f"Error al cargar cookies: {str(e)}")
        
        if not cookies_loaded:
            print("No se pudieron cargar cookies. El scraping puede fallar.")
        
        # Create page with shorter timeout
        page = await context.new_page()
        page.set_default_timeout(15000)  # 15 segundos timeout por defecto
        
        try:
            # First navigate to Twitter homepage to set up cookies
            print("Navegando primero a Twitter homepage para establecer cookies...")
            await page.goto("https://twitter.com", wait_until="domcontentloaded")
            await asyncio.sleep(3)
            
            # Take screenshot of homepage
            await page.screenshot(path="/tmp/twitter_homepage.png")
            
            # Go to user profile - use both URLs
            profile_url = f"https://twitter.com/{username}"
            print(f"Navegando a: {profile_url}")
            
            try:
                # Use domcontentloaded instead of networkidle
                await page.goto(profile_url, wait_until="domcontentloaded", timeout=15000)
            except Exception as e:
                print(f"Error inicial al navegar: {str(e)}")
                # Try alternative URL
                alt_url = f"https://x.com/{username}"
                print(f"Intentando URL alternativa: {alt_url}")
                await page.goto(alt_url, wait_until="domcontentloaded", timeout=15000)
            
            # Check current URL
            current_url = page.url
            print(f"URL actual: {current_url}")
            
            # Wait for page content
            print("Esperando a que cargue el contenido...")
            await asyncio.sleep(5)
            
            # Take screenshot
            screenshot_path = f"/tmp/{username}_profile.png"
            await page.screenshot(path=screenshot_path)
            print(f"Captura de pantalla guardada en: {screenshot_path}")
            
            # Extract tweets
            tweets_data = []
            scrolls = 0
            
            # Define tweet selectors
            tweet_selectors = [
                "article[data-testid='tweet']",
                "div[data-testid='tweet']",
                "div[data-testid='cellInnerDiv']"
            ]
            
            print("Comenzando scrolling para cargar más tweets...")
            while scrolls < max_scrolls and len(tweets_data) < max_tweets:
                print(f"Scroll {scrolls+1}/{max_scrolls}")
                
                # Try each selector
                found_tweets = False
                for selector in tweet_selectors:
                    try:
                        tweet_elements = await page.query_selector_all(selector)
                        if tweet_elements and len(tweet_elements) > 0:
                            print(f"Encontrados {len(tweet_elements)} tweets con selector: {selector}")
                            found_tweets = True
                            
                            # Process each tweet
                            for tweet_el in tweet_elements:
                                tweet_data = {}
                                
                                # Extract text
                                try:
                                    text_selector = "div[data-testid='tweetText']"
                                    text_el = await tweet_el.query_selector(text_selector)
                                    if text_el:
                                        tweet_data['texto'] = await text_el.inner_text()
                                    else:
                                        # Try to get all text as fallback
                                        tweet_data['texto'] = await tweet_el.inner_text()
                                except Exception as e:
                                    print(f"Error al extraer texto: {str(e)}")
                                    continue
                                
                                # Skip if no text
                                if not tweet_data.get('texto'):
                                    continue
                                
                                # Extract username
                                try:
                                    user_selector = "div[data-testid='User-Name'] span"
                                    user_el = await tweet_el.query_selector(user_selector)
                                    if user_el:
                                        tweet_data['usuario'] = username
                                    else:
                                        tweet_data['usuario'] = username
                                except:
                                    tweet_data['usuario'] = username
                                
                                # Extract timestamp
                                try:
                                    time_selector = "time"
                                    time_el = await tweet_el.query_selector(time_selector)
                                    if time_el:
                                        tweet_data['timestamp'] = await time_el.get_attribute("datetime")
                                except:
                                    tweet_data['timestamp'] = ""
                                
                                # Add tweet if not already in dataset
                                tweet_text = tweet_data.get('texto', '').strip()
                                if tweet_text and not any(t.get('texto') == tweet_text for t in tweets_data):
                                    tweets_data.append(tweet_data)
                                    print(f"Tweet extraído: {tweet_text[:50]}...")
                            
                            break  # Exit selector loop if found
                    except Exception as e:
                        print(f"Error con selector {selector}: {str(e)}")
                
                if not found_tweets:
                    print("No se encontraron tweets en esta página. Intentando scroll...")
                
                # Scroll down
                await page.evaluate("window.scrollBy(0, window.innerHeight)")
                await asyncio.sleep(2)
                
                scrolls += 1
                print(f"Total acumulado: {len(tweets_data)} tweets")
                
                # Take screenshot periodically
                if scrolls % 3 == 0:
                    await page.screenshot(path=f"/tmp/{username}_scroll_{scrolls}.png")
                
                # Stop if we have enough tweets
                if len(tweets_data) >= min_tweets and scrolls > 1:
                    print(f"Se alcanzó el mínimo de {min_tweets} tweets. Deteniendo...")
                    break
            
            # Create DataFrame
            if tweets_data:
                df = pd.DataFrame(tweets_data)
                
                # Add sequential numbering
                df['numero'] = range(1, len(df) + 1)
                
                # Sort by timestamp if available
                if 'timestamp' in df.columns and not df['timestamp'].isna().all():
                    try:
                        df['timestamp_parsed'] = pd.to_datetime(df['timestamp'])
                        df = df.sort_values(by='timestamp_parsed', ascending=False)
                        df = df.drop('timestamp_parsed', axis=1)
                        print("Tweets ordenados por timestamp (más recientes primero)")
                    except Exception as e:
                        print(f"No se pudieron ordenar los tweets por fecha: {str(e)}")
                
                # Display results
                print(f"\nExtraídos {len(df)} tweets de @{username}")
                
                if not df.empty:
                    print("\nEjemplos de tweets:")
                    for i, row in df.head(5).iterrows():
                        timestamp = row.get('timestamp', 'No date')
                        print(f"- [{timestamp}] {row['usuario']}: {row['texto'][:100]}...")
                    
                    # Save results to CSV
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    csv_path = f"user_{username}_direct_{timestamp}.csv"
                    df.to_csv(csv_path, index=False)
                    print(f"Resultados guardados en: {csv_path}")
                    
                    # Show all timestamps
                    if 'timestamp' in df.columns:
                        print("\nTodos los timestamps:")
                        for ts in df['timestamp'].values:
                            print(f"- {ts}")
            else:
                print("No se encontraron tweets.")
        
        except Exception as e:
            print(f"Error durante la extracción: {str(e)}")
            # Take a screenshot for debugging
            try:
                await page.screenshot(path=f"/tmp/{username}_error.png")
                print(f"Captura de error guardada en: /tmp/{username}_error.png")
            except:
                pass
        
        finally:
            # Close browser
            await context.close()
            await browser.close()
            print("Navegador cerrado.")

def main():
    asyncio.run(extract_from_profile())

if __name__ == "__main__":
    main() 