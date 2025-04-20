#!/usr/bin/env python3
"""
Script de prueba para la extracción de tweets con login automático

Este script prueba la extracción de tweets utilizando el nuevo sistema
de login automático para asegurar acceso a tweets recientes.
"""

import os
import sys
import asyncio
import logging
import pandas as pd
from pathlib import Path

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("test_manual")

# Asegurar que existe el directorio temporal
os.makedirs("/tmp", exist_ok=True)

async def run_test():
    """Ejecutar prueba de extracción con login"""
    try:
        print("\n===== PRUEBA DE EXTRACCIÓN CON LOGIN AUTOMÁTICO =====")
        
        # 1. Primero, verificar que exista la sesión o crear una nueva
        from twitter_login import get_storage_state
        storage_path = await get_storage_state()
        
        if not storage_path:
            print("❌ Error: No se pudo obtener una sesión válida de Twitter")
            return False
        
        print(f"✅ Sesión de Twitter disponible en: {storage_path}")
        
        # 2. Cargar el módulo de integración de login
        print("\nConfigurando integración de login...")
        sys.path.append(os.path.abspath("app/services"))
        try:
            from twitter_login_integration import patch_twitter_scraper
            patch_twitter_scraper()
            print("✅ Integración de login configurada correctamente")
        except Exception as e:
            print(f"❌ Error al configurar integración: {str(e)}")
            return False
        
        # 3. Crear instancia del extractor
        print("\nInicializando extractor...")
        from app.services.twitter_playwright import TwitterPlaywrightScraper
        
        # Usuario a probar (ha reportado problemas previamente)
        test_user = "KarinHerreraVP"
        print(f"Usuario de prueba: @{test_user}")
        
        tweets_df = None
        
        # 4. Extraer tweets
        print("\nExtrayendo tweets...")
        scraper = TwitterPlaywrightScraper(bypass_login=True)
        
        async with scraper:
            # Verificar autenticación
            auth_ok = await scraper.verify_auth()
            if not auth_ok:
                print("❌ Error de autenticación")
                return False
                
            print("✅ Autenticación exitosa")
                
            # Extraer tweets
            print(f"Extrayendo tweets para @{test_user}...")
            tweets_df = await scraper.extract_by_user(
                username=test_user,
                max_tweets=15,
                min_tweets=5,
                max_scrolls=5
            )
        
        # 5. Verificar y mostrar resultados
        if tweets_df is None or tweets_df.empty:
            print("❌ No se encontraron tweets")
            return False
            
        # Ordenar por timestamp descendente
        if 'timestamp' in tweets_df.columns:
            tweets_df = tweets_df.sort_values(by='timestamp', ascending=False)
            
        # Guardar resultados
        output_file = f"{test_user}_test_manual.csv"
        tweets_df.to_csv(output_file, index=False)
        
        # Mostrar resultados
        num_tweets = len(tweets_df)
        print(f"\n✅ Extracción exitosa: {num_tweets} tweets")
        print(f"Resultados guardados en: {output_file}")
        
        # Mostrar los tweets más recientes
        print("\nTweets más recientes:")
        for i, (_, row) in enumerate(tweets_df.head(5).iterrows()):
            fecha = row.get('timestamp', 'Fecha desconocida')
            texto = row.get('texto', '')[:100] + ('...' if len(row.get('texto', '')) > 100 else '')
            print(f"{i+1}. [{fecha}] {texto}")
            
        return True
        
    except Exception as e:
        import traceback
        print(f"❌ Error durante la prueba: {str(e)}")
        traceback.print_exc()
        return False

def main():
    """Función principal"""
    try:
        # Configurar event loop
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            
        # Usar event loop existente o crear uno nuevo
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
        # Ejecutar prueba
        success = loop.run_until_complete(run_test())
        
        # Mostrar resultado final
        if success:
            print("\n✅ La prueba finalizó correctamente")
            return 0
        else:
            print("\n❌ La prueba falló")
            return 1
            
    except Exception as e:
        print(f"\n❌ Error fatal: {str(e)}")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 