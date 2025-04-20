#!/usr/bin/env python3
"""
Script simplificado para iniciar sesión en Twitter con Firefox y
guardar el estado para su uso posterior.
"""

import os
import asyncio
import logging
from playwright.async_api import async_playwright

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Credenciales
USERNAME = "StandPd2007"
PASSWORD = "Welcome2024!"

async def main():
    """Función principal para iniciar sesión y guardar estado"""
    logger.info("Iniciando proceso de login en Twitter con Firefox")
    
    async with async_playwright() as p:
        # Lanzar navegador Firefox
        browser = await p.firefox.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        
        try:
            # Navegar a Twitter login
            logger.info("Navegando a Twitter login...")
            await page.goto("https://twitter.com/i/flow/login")
            
            # Esperar a que cargue la página
            await page.wait_for_load_state("networkidle")
            
            # Capturar página inicial
            await page.screenshot(path="login_page_initial.png")
            logger.info("Captura guardada: login_page_initial.png")
            
            # Ingresar usuario
            logger.info(f"Ingresando usuario: {USERNAME}")
            await page.wait_for_selector('input[autocomplete="username"]', timeout=30000)
            await page.fill('input[autocomplete="username"]', USERNAME)
            
            # Hacer clic en Siguiente
            logger.info("Haciendo clic en Siguiente...")
            next_button = await page.query_selector('div[role="button"]:has-text("Next")')
            if next_button:
                await next_button.click()
            else:
                logger.info("Botón Next no encontrado, presionando Enter")
                await page.press('input[autocomplete="username"]', 'Enter')
            
            # Esperar antes de ingresar contraseña
            await asyncio.sleep(3)
            
            # Ingresar contraseña
            logger.info("Ingresando contraseña...")
            password_input = await page.wait_for_selector('input[type="password"]', timeout=30000)
            await password_input.fill(PASSWORD)
            
            # Hacer clic en Log in
            logger.info("Haciendo clic en Log in...")
            login_button = await page.query_selector('div[role="button"]:has-text("Log in")')
            if login_button:
                await login_button.click()
            else:
                logger.info("Botón Log in no encontrado, presionando Enter")
                await page.press('input[type="password"]', 'Enter')
            
            # Esperar a que inicie sesión
            logger.info("Esperando inicio de sesión...")
            await asyncio.sleep(10)
            
            # Verificar si estamos en la página de inicio
            current_url = page.url
            logger.info(f"URL actual: {current_url}")
            
            if "twitter.com/home" in current_url or "/flow/login" not in current_url:
                logger.info("¡Inicio de sesión exitoso!")
                
                # Guardar estado para uso posterior
                logger.info("Guardando estado de la sesión...")
                await context.storage_state(path="firefox_storage.json")
                logger.info("Estado guardado en firefox_storage.json")
                
                # Tomar captura de página después de login
                await page.screenshot(path="login_success.png")
                logger.info("Captura guardada: login_success.png")
                
                # Navegar a una página de perfil para verificar
                test_profile = "KarinHerreraVP"
                logger.info(f"Verificando acceso a perfil de prueba: {test_profile}")
                await page.goto(f"https://twitter.com/{test_profile}")
                await asyncio.sleep(5)
                await page.screenshot(path=f"profile_{test_profile}.png")
                logger.info(f"Captura de perfil guardada: profile_{test_profile}.png")
                
            else:
                logger.error("No se detectó inicio de sesión exitoso")
                await page.screenshot(path="login_error.png")
                logger.info("Captura de error guardada: login_error.png")
            
            # Esperar para inspección manual
            print("\nNavegador mantenido abierto para inspección.")
            print("Presiona Enter para cerrar...")
            input()
            
        except Exception as e:
            logger.error(f"Error durante el proceso de login: {e}")
            
            # Capturar pantalla en caso de error
            try:
                await page.screenshot(path="login_exception.png")
                logger.info("Captura de excepción guardada: login_exception.png")
            except:
                pass
            
        finally:
            # Cerrar navegador
            await browser.close()
            logger.info("Navegador cerrado.")

if __name__ == "__main__":
    asyncio.run(main()) 