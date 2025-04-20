#!/usr/bin/env python3
"""
Script para extraer tweets recientes de un usuario específico usando cookies guardadas.
Este script prioriza tweets recientes usando la URL de búsqueda con filtro de recientes (f=live)
y filtra correctamente tweets fijados y promocionados.
"""

import os
import sys
import json
import logging
import asyncio
import pandas as pd
from datetime import datetime
from pathlib import Path

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("extract_with_cookies")

# Importar el extractor de Twitter
try:
    from app.services.twitter_playwright import TwitterPlaywrightScraper
except ImportError:
    # Para permitir ejecución directa desde el directorio del proyecto
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from app.services.twitter_playwright import TwitterPlaywrightScraper

async def extract_tweets(username, max_tweets=10, min_tweets=5, max_scrolls=5):
    """
    Extrae tweets de un usuario específico usando las cookies guardadas.
    
    Args:
        username (str): Nombre de usuario de Twitter (sin @)
        max_tweets (int): Número máximo de tweets a extraer
        min_tweets (int): Número mínimo de tweets a extraer
        max_scrolls (int): Número máximo de scrolls
        
    Returns:
        list: Lista de tweets extraídos
    """
    logger.info(f"Iniciando extracción de tweets para @{username}")
    
    # Verificar si existen las cookies guardadas
    cookies_path = Path("firefox_storage.json")
    if not cookies_path.exists():
        logger.error("No se encontraron cookies guardadas. Ejecute login_direct.py primero.")
        return []
    
    logger.info(f"Usando cookies guardadas en {cookies_path}")
    
    # Crear el extractor de Twitter
    extractor = TwitterPlaywrightScraper(
        browser_type="firefox",
        headless=False,  # Mostrar el navegador para depuración
        storage_state=str(cookies_path),
    )
    
    try:
        # Extraer tweets utilizando la estrategia de búsqueda reciente primero
        tweets = await extractor.extract_by_user(
            username=username,
            max_tweets=max_tweets,
            min_tweets=min_tweets,
            max_scrolls=max_scrolls,
            detect_suspicious=False,  # Desactivar detección de perfiles sospechosos
        )
        
        logger.info(f"Se extrajeron {len(tweets)} tweets para @{username}")
        
        # Ordenar tweets por fecha (más recientes primero)
        tweets.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
        
        return tweets
    except Exception as e:
        logger.error(f"Error durante la extracción: {e}")
        return []
    finally:
        await extractor.close()

def save_results(tweets, username):
    """
    Guarda los resultados en un archivo CSV y muestra un resumen.
    
    Args:
        tweets (list): Lista de tweets extraídos
        username (str): Nombre de usuario
    """
    if not tweets:
        logger.warning("No se encontraron tweets para guardar.")
        return
    
    # Convertir a DataFrame
    df = pd.DataFrame(tweets)
    
    # Nombre del archivo con timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{username}_tweets_{timestamp}.csv"
    
    # Guardar a CSV
    df.to_csv(filename, index=False)
    logger.info(f"Resultados guardados en {filename}")
    
    # Mostrar resumen
    print("\n=== RESUMEN DE TWEETS EXTRAÍDOS ===")
    print(f"Usuario: @{username}")
    print(f"Total de tweets: {len(tweets)}")
    
    if tweets:
        print("\nTweets más recientes:")
        for i, tweet in enumerate(tweets[:3], 1):
            date = datetime.fromtimestamp(tweet.get('timestamp', 0))
            formatted_date = date.strftime("%d/%m/%Y %H:%M:%S")
            text = tweet.get('text', '')[:100] + ('...' if len(tweet.get('text', '')) > 100 else '')
            print(f"{i}. [{formatted_date}] {text}")

async def main_async():
    """Función principal asíncrona."""
    if len(sys.argv) < 2:
        print("Uso: python extract_with_cookies.py <username> [max_tweets] [min_tweets] [max_scrolls]")
        return
    
    username = sys.argv[1]
    max_tweets = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    min_tweets = int(sys.argv[3]) if len(sys.argv) > 3 else 5
    max_scrolls = int(sys.argv[4]) if len(sys.argv) > 4 else 5
    
    logger.info(f"Parámetros: username={username}, max_tweets={max_tweets}, min_tweets={min_tweets}, max_scrolls={max_scrolls}")
    
    # Extraer tweets
    tweets = await extract_tweets(username, max_tweets, min_tweets, max_scrolls)
    
    # Guardar resultados
    save_results(tweets, username)

def main():
    """Punto de entrada principal que configura el bucle de eventos."""
    try:
        # Configurar y ejecutar el bucle de eventos
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logger.info("Extracción cancelada por el usuario.")
    except Exception as e:
        logger.error(f"Error en la ejecución principal: {e}")

if __name__ == "__main__":
    main() 