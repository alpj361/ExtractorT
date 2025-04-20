#!/usr/bin/env python3
"""
Docker-compatible tweet extractor

Este script está diseñado para ejecutarse dentro de un contenedor Docker
y extraer tweets recientes de un usuario de Twitter. Proporciona una interfaz
simple de línea de comandos y maneja correctamente la ejecución asíncrona.
"""

import os
import sys
import argparse
import logging
import asyncio
import pandas as pd
from datetime import datetime
from pathlib import Path

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("docker_extractor")

# Crear directorio temporal si no existe
os.makedirs("/tmp", exist_ok=True)

# Importar el extractor
try:
    from app.services.twitter_playwright import TwitterPlaywright
except ImportError:
    logger.error("No se pudo importar TwitterPlaywright. Asegúrate de estar en el directorio correcto.")
    sys.exit(1)

async def extract_tweets(username, max_tweets=20, min_tweets=10, max_scrolls=10):
    """
    Extrae tweets recientes de un usuario utilizando Playwright.
    
    Args:
        username (str): Nombre de usuario de Twitter (sin @)
        max_tweets (int): Número máximo de tweets a extraer
        min_tweets (int): Número mínimo de tweets a extraer
        max_scrolls (int): Número máximo de desplazamientos a realizar
        
    Returns:
        pandas.DataFrame: DataFrame con los tweets extraídos
    """
    logger.info(f"Iniciando extracción para usuario @{username}")
    logger.info(f"Configuración: max_tweets={max_tweets}, min_tweets={min_tweets}, max_scrolls={max_scrolls}")
    
    try:
        # Inicializar el extractor
        extractor = TwitterPlaywright()
        await extractor.setup_browser()
        
        # Extraer tweets
        logger.info("Extrayendo tweets...")
        tweets_df = await extractor.extract_by_user(
            username=username,
            max_tweets=max_tweets,
            min_tweets=min_tweets,
            max_scrolls=max_scrolls
        )
        
        # Cerrar el navegador
        await extractor.close_browser()
        
        # Registrar resultados
        num_tweets = len(tweets_df) if tweets_df is not None else 0
        logger.info(f"Extracción completada. Se obtuvieron {num_tweets} tweets.")
        
        # Guardar como CSV
        if tweets_df is not None and not tweets_df.empty:
            # Crear nombre de archivo con timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"/app/output/{username}_{timestamp}.csv"
            
            # Asegurar que existe el directorio de salida
            os.makedirs("/app/output", exist_ok=True)
            
            # Guardar CSV
            tweets_df.to_csv(output_file, index=False)
            logger.info(f"Tweets guardados en {output_file}")
            
            # También guardar en directorio local
            local_file = f"{username}_{timestamp}.csv"
            tweets_df.to_csv(local_file, index=False)
            logger.info(f"Tweets guardados localmente en {local_file}")
            
            return tweets_df
        else:
            logger.warning("No se encontraron tweets para guardar.")
            return pd.DataFrame()
            
    except Exception as e:
        logger.error(f"Error durante la extracción: {str(e)}", exc_info=True)
        return pd.DataFrame()

def main():
    """Función principal del script."""
    parser = argparse.ArgumentParser(description='Extractor de tweets compatible con Docker')
    parser.add_argument('username', help='Nombre de usuario de Twitter (sin @)')
    parser.add_argument('--max', '-m', type=int, default=20, help='Número máximo de tweets a extraer')
    parser.add_argument('--min', type=int, default=10, help='Número mínimo de tweets a extraer')
    parser.add_argument('--scrolls', '-s', type=int, default=10, help='Número máximo de desplazamientos')
    
    args = parser.parse_args()
    
    # Limpiar username si tiene @
    username = args.username.strip('@')
    
    try:
        # Ejecutar la función asíncrona
        df = asyncio.run(extract_tweets(username, args.max, args.min, args.scrolls))
        
        # Mostrar información de tweets
        if not df.empty:
            print("\n===== TWEETS EXTRAÍDOS =====")
            print(f"Total de tweets: {len(df)}")
            print(f"Tweets más reciente: {df['timestamp'].iloc[0] if 'timestamp' in df.columns else 'Desconocido'}")
            print(f"Tweet más antiguo: {df['timestamp'].iloc[-1] if 'timestamp' in df.columns else 'Desconocido'}")
        else:
            print("No se encontraron tweets.")
            
    except Exception as e:
        logger.error(f"Error en la ejecución: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main() 