#!/usr/bin/env python3
"""
Extractor de tweets mejorado para línea de comandos.
Prioriza tweets recientes y filtra correctamente tweets fijados/promocionados.
"""

import sys
import os
import logging
import asyncio
import pandas as pd
from datetime import datetime
from app.services.twitter_playwright import TwitterPlaywrightScraper

# Configurar logging más detallado
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("twitter_extractor")

# Asegurar que el directorio temporal exista
os.makedirs("/tmp", exist_ok=True)

async def extract_tweets(username, max_tweets=20, min_tweets=10, max_scrolls=10):
    """Extraer tweets de un usuario específico."""
    logger.info(f"Iniciando extracción para @{username}")
    logger.info(f"Parámetros: max_tweets={max_tweets}, min_tweets={min_tweets}, max_scrolls={max_scrolls}")
    
    try:
        async with TwitterPlaywrightScraper(bypass_login=True) as scraper:
            # Omitir verificación de autenticación
            logger.info("Omitiendo verificación de autenticación - accediendo directamente al perfil público")
            
            # Extraer tweets directamente sin verificar autenticación
            df = await scraper.extract_by_user(
                username=username,
                max_tweets=max_tweets,
                min_tweets=min_tweets,
                max_scrolls=max_scrolls
            )
            
            return df
    except Exception as e:
        logger.error(f"Error en extracción: {str(e)}")
        raise

def main():
    """Función principal del script."""
    if len(sys.argv) < 2:
        print("Uso: python extract_cmd.py <username> [max_tweets] [min_tweets] [max_scrolls]")
        sys.exit(1)
    
    # Extraer parámetros
    username = sys.argv[1]
    max_tweets = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    min_tweets = int(sys.argv[3]) if len(sys.argv) > 3 else 10
    max_scrolls = int(sys.argv[4]) if len(sys.argv) > 4 else 10
    
    # Ejecutar extracción asincrónica
    try:
        # Crear un nuevo event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Ejecutar extracción
        df = loop.run_until_complete(extract_tweets(username, max_tweets, min_tweets, max_scrolls))
        
        # Cerrar el loop
        loop.close()
        
        # Si la extracción fue exitosa, guardar resultados
        if not df.empty:
            # Crear nombre de archivo con timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"{username}_tweets_{timestamp}.csv"
            
            # Guardar a CSV
            df.to_csv(output_file, index=False)
            logger.info(f"✓ Extracción exitosa: {len(df)} tweets guardados en '{output_file}'")
            
            # Mostrar primeros tweets para validación
            logger.info("\nPrimeros 5 tweets extraídos:")
            for i, row in df.head(5).iterrows():
                tweet_date = row.get('timestamp', 'Sin fecha')
                tweet_text = row.get('texto', '')[:50] + ('...' if len(row.get('texto', '')) > 50 else '')
                logger.info(f"   Tweet {i+1}: [{tweet_date}] {tweet_text}")
            
            print(f"\nTotal tweets extraídos: {len(df)}")
            print(f"Archivo guardado en: {output_file}")
        else:
            logger.warning("⚠ No se encontraron tweets.")
    except Exception as e:
        logger.error(f"❌ Error en la extracción: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main() 