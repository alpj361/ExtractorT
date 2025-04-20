#!/usr/bin/env python3
"""
API Extract - Extractor de tweets recientes utilizando APIs no oficiales
Este script utiliza la biblioteca Twikit para extraer tweets recientes de un perfil específico
evitando completamente las limitaciones de la interfaz web de Twitter.
"""

import os
import sys
import json
import logging
import pandas as pd
import argparse
import asyncio
from datetime import datetime
from pathlib import Path

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('api_extract')

def setup_twikit():
    """Instala Twikit si no está disponible."""
    try:
        from twikit import Client
        logger.info("Twikit ya está instalado.")
        return True
    except ImportError:
        logger.warning("Twikit no está instalado. Intentando instalar...")
        try:
            import subprocess
            subprocess.check_call([sys.executable, "-m", "pip", "install", "twikit"])
            logger.info("Twikit instalado correctamente.")
            return True
        except Exception as e:
            logger.error(f"Error al instalar Twikit: {str(e)}")
            logger.error("Por favor, instale manualmente: pip install twikit")
            return False

async def extract_tweets(username, count=10, min_tweets=10):
    """
    Extrae tweets recientes usando Twikit como API no oficial.
    
    Args:
        username (str): Nombre de usuario de Twitter (sin @)
        count (int): Número máximo de tweets a extraer
        min_tweets (int): Número mínimo de tweets a extraer
        
    Returns:
        pandas.DataFrame: DataFrame con los tweets extraídos
    """
    # Importar después de asegurar que está instalado
    try:
        from twikit import Client as AsyncClient
        logger.info("Utilizando Client para la extracción asíncrona")
    except ImportError:
        logger.error("No se pudo importar la clase Client de twikit")
        return pd.DataFrame(columns=["texto", "usuario", "timestamp", "numero", "retweets", "favoritos", "id", "url"])
    
    logger.info(f"Iniciando extracción de tweets para usuario @{username}")
    
    try:
        # Inicializar cliente sin autenticación (modo guest)
        client = AsyncClient()
        
        # Obtener detalles del usuario
        user = await client.get_user_by_screen_name(username)
        logger.info(f"Usuario encontrado: {user.name} (@{user.screen_name})")
        logger.info(f"Descripción: {user.description}")
        logger.info(f"Seguidores: {user.followers_count} | Siguiendo: {user.following_count}")
        
        # Extraer tweets
        logger.info(f"Extrayendo hasta {count} tweets recientes...")
        tweets = await user.get_tweets('Tweets', count=count)
        
        # Procesar tweets
        tweets_data = []
        pinned_tweet_id = None
        
        # Detectar si hay tweet fijado
        if hasattr(user, 'pinned_tweet_id') and user.pinned_tweet_id:
            pinned_tweet_id = user.pinned_tweet_id
            logger.info(f"Tweet fijado detectado con ID: {pinned_tweet_id}")
        
        # Procesar cada tweet
        for i, tweet in enumerate(tweets):
            # Verificar si es un tweet fijado
            is_pinned = (pinned_tweet_id and str(tweet.id) == str(pinned_tweet_id))
            if is_pinned:
                logger.info(f"Omitiendo tweet fijado: {tweet.full_text[:50]}...")
                continue
            
            # Obtener fecha en formato legible
            fecha = tweet.created_at.strftime('%Y-%m-%d %H:%M:%S') if hasattr(tweet, 'created_at') else 'Desconocido'
            logger.debug(f"Procesando tweet del {fecha}: {tweet.full_text[:50]}...")
                
            tweet_data = {
                'texto': tweet.full_text,
                'usuario': tweet.user.screen_name,
                'timestamp': tweet.created_at,
                'numero': i + 1,
                'retweets': tweet.retweet_count,
                'favoritos': tweet.favorite_count,
                'id': tweet.id,
                'url': f"https://twitter.com/{tweet.user.screen_name}/status/{tweet.id}"
            }
            
            # Añadir medios si existen
            if hasattr(tweet, 'media') and tweet.media:
                medias = []
                for media in tweet.media:
                    if hasattr(media, 'media_url_https'):
                        medias.append(media.media_url_https)
                if medias:
                    tweet_data['media_urls'] = "|".join(medias)
            
            tweets_data.append(tweet_data)
            logger.info(f"Tweet {i+1} procesado ({fecha}): {tweet.full_text[:50]}...")
            
        # Crear DataFrame
        if tweets_data:
            df = pd.DataFrame(tweets_data)
            # Ordenar por timestamp de más reciente a más antiguo
            df = df.sort_values(by='timestamp', ascending=False)
            logger.info(f"Extracción exitosa: {len(df)} tweets para @{username}")
            
            # Guardar en un archivo CSV con timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{username}_tweets_api_{timestamp}.csv"
            df.to_csv(filename, index=False)
            logger.info(f"Tweets guardados en {filename}")
            
            return df
        else:
            logger.warning(f"No se encontraron tweets para @{username}")
            return pd.DataFrame(columns=["texto", "usuario", "timestamp", "numero", "retweets", "favoritos", "id", "url"])
    
    except Exception as e:
        logger.error(f"Error extrayendo tweets: {str(e)}", exc_info=True)
        return pd.DataFrame(columns=["texto", "usuario", "timestamp", "numero", "retweets", "favoritos", "id", "url"])
    finally:
        # Asegurar que el cliente se cierre correctamente
        if 'client' in locals():
            await client.close()
            logger.info("Cliente de Twikit cerrado correctamente")

def main():
    """Función principal del script."""
    parser = argparse.ArgumentParser(description='Extractor de tweets usando APIs no oficiales')
    parser.add_argument('username', help='Nombre de usuario de Twitter (sin @)')
    parser.add_argument('--count', '-c', type=int, default=20, help='Número máximo de tweets a extraer')
    parser.add_argument('--min', '-m', type=int, default=10, help='Número mínimo de tweets a extraer')
    parser.add_argument('--debug', action='store_true', help='Activar logs de depuración')
    
    args = parser.parse_args()
    
    # Configurar nivel de log si se solicita depuración
    if args.debug:
        logger.setLevel(logging.DEBUG)
        logger.debug("Modo de depuración activado")
    
    # Asegurar que Twikit está instalado
    if not setup_twikit():
        sys.exit(1)
    
    try:
        # Limpiar username si tiene @
        username = args.username.strip('@')
        
        # Crear un nuevo event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # Ejecutar la función asíncrona
            df = loop.run_until_complete(extract_tweets(username, args.count, args.min))
        finally:
            # Asegurar que el loop se cierre correctamente
            loop.close()
        
        # Mostrar resultados
        if not df.empty:
            print("\n===== TWEETS EXTRAÍDOS =====")
            for _, row in df.iterrows():
                fecha = pd.to_datetime(row['timestamp']).strftime('%Y-%m-%d %H:%M:%S') if pd.notna(row['timestamp']) else 'Desconocido'
                print(f"\n[{fecha}] @{row['usuario']}:")
                print(f"{row['texto']}")
                print(f"Retweets: {row['retweets']} | Favoritos: {row['favoritos']}")
                print(f"URL: {row['url']}")
                print("-" * 50)
        else:
            print("No se encontraron tweets para mostrar.")
        
    except Exception as e:
        logger.error(f"Error en la ejecución: {str(e)}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main() 