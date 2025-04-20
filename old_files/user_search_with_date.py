#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import logging
import pandas as pd
from datetime import datetime

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

from app.services.twitter_playwright import TwitterScraper, TwitterPlaywrightScraper
import asyncio

async def extract_user_tweets_recent():
    """
    Test extraction for a specific user using search with live filter to get recent tweets.
    """
    # Test parameters
    username = "KarinHerreraVP"
    max_tweets = 30
    min_tweets = 5
    max_scrolls = 10
    
    print(f"\n===== Testing extraction for @{username} with live filter =====")
    
    # Initialize the scraper directly
    async with TwitterPlaywrightScraper(bypass_login=True) as scraper:
        print(f"Extracting tweets from user @{username} using search with 'live' filter...")
        
        # URL que muestra tweets más recientes primero
        search_url = f"https://twitter.com/search?q=from%3A{username}&src=typed_query&f=live"
        
        print(f"Navegando a: {search_url}")
        await scraper.page.goto(search_url, wait_until="domcontentloaded")
        
        # Verificar redirección a login
        current_url = scraper.page.url
        if "login" in current_url:
            print(f"Redirigido a página de login: {current_url}")
            # Intentar con URL alternativa
            alt_url = f"https://x.com/search?q=from%3A{username}&src=typed_query&f=live"
            print(f"Intentando URL alternativa: {alt_url}")
            await scraper.page.goto(alt_url, wait_until="domcontentloaded")
            current_url = scraper.page.url
            
            if "login" in current_url:
                print(f"Redirigido nuevamente a login: {current_url}")
                # Intentar con perfil directo
                profile_url = f"https://twitter.com/{username}"
                print(f"Intentando perfil directo: {profile_url}")
                await scraper.page.goto(profile_url, wait_until="domcontentloaded")
        
        # Esperar a que cargue la página
        await asyncio.sleep(5)
        
        # Tomar captura de pantalla para ver qué se está mostrando
        screenshot_path = f"/tmp/{username}_search_page.png"
        await scraper.page.screenshot(path=screenshot_path)
        print(f"Captura de pantalla guardada en: {screenshot_path}")
        
        # Iniciar scrolling para cargar más tweets
        print("Haciendo scroll para cargar más tweets...")
        tweets_data = []
        scrolls = 0
        
        while len(tweets_data) < max_tweets and scrolls < max_scrolls:
            # Scroll down
            await scraper.page.evaluate("window.scrollBy(0, window.innerHeight)")
            await asyncio.sleep(2)
            
            # Obtener tweets en la página actual
            new_tweets = await scraper._extract_tweets_data(None)
            
            # Imprimir información sobre los tweets encontrados
            print(f"Scroll {scrolls+1}: Encontrados {len(new_tweets)} tweets nuevos")
            
            # Agregar tweets únicos
            for tweet in new_tweets:
                if tweet not in tweets_data:
                    tweets_data.append(tweet)
            
            print(f"Total acumulado: {len(tweets_data)} tweets")
            
            # Detener si tenemos suficientes tweets
            if len(tweets_data) >= min_tweets and scrolls > 0:
                break
                
            scrolls += 1
        
        # Crear DataFrame y ordenar por fecha (más recientes primero)
        if tweets_data:
            df = pd.DataFrame(tweets_data)
            
            # Añadir numeración
            df['numero'] = range(1, len(df) + 1)
            
            # Ordenar por timestamp si disponible
            if 'timestamp' in df.columns and not df['timestamp'].isna().all():
                try:
                    df['timestamp_parsed'] = pd.to_datetime(df['timestamp'])
                    df = df.sort_values(by='timestamp_parsed', ascending=False)
                    df = df.drop('timestamp_parsed', axis=1)
                    print("Tweets ordenados por timestamp (más recientes primero)")
                except Exception as e:
                    print(f"No se pudieron ordenar los tweets por fecha: {str(e)}")
            
            # Mostrar resultados
            print(f"\nExtraídos {len(df)} tweets de @{username}")
            
            if not df.empty:
                print("\nEjemplos de tweets:")
                for i, row in df.head(5).iterrows():
                    timestamp = row.get('timestamp', 'No date')
                    print(f"- [{timestamp}] {row['usuario']}: {row['texto'][:100]}...")
                
                # Guardar resultados a CSV
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                csv_path = f"user_{username}_live_{timestamp}.csv"
                df.to_csv(csv_path, index=False)
                print(f"Resultados guardados en: {csv_path}")
                
                # Mostrar todos los timestamps
                if 'timestamp' in df.columns:
                    print("\nTodos los timestamps:")
                    for ts in df['timestamp'].values:
                        print(f"- {ts}")
                
                return df
        else:
            print("No se encontraron tweets.")
            return pd.DataFrame()

def main():
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(extract_user_tweets_recent())
    finally:
        loop.close()

if __name__ == "__main__":
    main() 