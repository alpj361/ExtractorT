#!/usr/bin/env python
"""
Script para iniciar sesión en Twitter usando Playwright y exportar cookies.
Este script es más efectivo para evitar la detección de bots que Selenium.
"""
import asyncio
import json
import os
import time
from pathlib import Path

# Antes de ejecutar, instala Playwright con:
# pip install playwright
# python -m playwright install chromium
from playwright.async_api import async_playwright

async def login_and_export_cookies():
    print("🚀 Iniciando Playwright...")
    
    # Crear directorio para cookies y capturas
    os.makedirs("playwright_data", exist_ok=True)
    
    async with async_playwright() as p:
        # Usar Chromium (más ligero que Chrome)
        browser_type = p.chromium
        
        # Configurar opciones del navegador para evitar detección
        browser = await browser_type.launch(
            headless=False,  # Visible para facilitar depuración e inicio de sesión manual
            args=[
                '--no-sandbox',
                '--disable-blink-features=AutomationControlled',
                '--disable-features=IsolateOrigins,site-per-process',
            ]
        )
        
        # Crear contexto persistente (equivalente al perfil)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
        )
        
        # Script para evitar detección
        await context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'languages', { get: () => ['es-ES', 'es', 'en-US', 'en'] });
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
        window.chrome = { runtime: {} };
        """)
        
        # Crear página
        page = await context.new_page()
        
        # Establecer timeout más alto para cargas lentas
        page.set_default_timeout(60000)
        
        # Navegar a Twitter
        print("🌐 Navegando a Twitter...")
        await page.goto("https://twitter.com/i/flow/login")
        
        # Capturar la pantalla de inicio de sesión
        await page.screenshot(path="playwright_data/login_screen.png")
        print("📸 Captura de la pantalla de inicio de sesión guardada en 'playwright_data/login_screen.png'")
        
        print("🧠 Por favor, inicia sesión manualmente en la ventana del navegador.")
        print("🔒 Esperando que completes el login... (máximo 3 minutos)")
        
        # Monitorear la URL para detectar un inicio de sesión exitoso
        start_time = time.time()
        logged_in = False
        
        while time.time() - start_time < 180:  # 3 minutos máximo
            current_url = page.url
            print(f"URL actual: {current_url}")
            
            # Verificar si ya se inició sesión
            if "twitter.com/home" in current_url or "x.com/home" in current_url:
                print("✅ Sesión iniciada detectada!")
                logged_in = True
                break
                
            # Esperar un poco antes de verificar nuevamente
            await asyncio.sleep(3)
        
        if not logged_in:
            # Si no detectó el login automáticamente, preguntar al usuario
            print("⚠️ No se detectó inicio de sesión automáticamente.")
            input("Presiona Enter cuando hayas completado el inicio de sesión para continuar...")
        
        # Capturar la pantalla principal
        await page.screenshot(path="playwright_data/home_screen.png")
        print("📸 Captura de la pantalla principal guardada en 'playwright_data/home_screen.png'")
        
        # Obtener cookies
        cookies = await context.cookies()
        
        # Guardar cookies en archivo JSON
        cookie_file = "playwright_data/twitter_cookies.json"
        with open(cookie_file, "w") as f:
            json.dump(cookies, f, indent=2)
        
        print(f"🍪 Se guardaron {len(cookies)} cookies en '{cookie_file}'")
        
        # Guardar también como twitter_cookies.json en la raíz para facilitar su uso
        with open("twitter_cookies.json", "w") as f:
            json.dump(cookies, f, indent=2)
        print(f"🍪 Se guardaron {len(cookies)} cookies en 'twitter_cookies.json'")
        
        # Realizar una prueba de búsqueda de hashtag para verificar la sesión
        try:
            print("🔍 Realizando prueba de búsqueda de hashtag...")
            test_hashtag = "HDC"
            await page.goto(f"https://twitter.com/search?q=%23{test_hashtag}&src=typed_query&f=top")
            
            # Esperar a que se carguen los resultados
            await page.wait_for_load_state("networkidle")
            
            # Capturar la pantalla de búsqueda
            await page.screenshot(path=f"playwright_data/search_{test_hashtag}.png")
            print(f"📸 Captura de la búsqueda guardada en 'playwright_data/search_{test_hashtag}.png'")
            
            # Verificar si hay tweets
            tweets_selector = "article[data-testid='tweet']"
            try:
                await page.wait_for_selector(tweets_selector, timeout=10000)
                tweet_count = await page.locator(tweets_selector).count()
                print(f"✅ Búsqueda exitosa! Se encontraron {tweet_count} tweets para #{test_hashtag}")
            except:
                print(f"⚠️ No se encontraron tweets para #{test_hashtag} o aún se requiere autenticación")
                
        except Exception as e:
            print(f"❌ Error en la prueba de búsqueda: {str(e)}")
        
        # Guardar estado del navegador para uso futuro (cookies, almacenamiento, etc.)
        storage_file = "playwright_data/twitter_state.json"
        storage = await context.storage_state()
        with open(storage_file, "w") as f:
            json.dump(storage, f, indent=2)
        
        print(f"💾 Estado del navegador guardado en '{storage_file}'")
        
        # Cerrar navegador
        await browser.close()
        
        print("✅ Proceso completado.")
        print("   Para usar estas cookies en el contenedor Docker, ejecuta:")
        print("   docker cp twitter_cookies.json extractor_container:/app/cookies/twitter_cookies.json")

if __name__ == "__main__":
    asyncio.run(login_and_export_cookies()) 