#!/usr/bin/env python3
"""
Script de login simplificado
"""

import os
import asyncio
import time
from playwright.async_api import async_playwright

# Credenciales directas (para pruebas)
USERNAME = "StandPd2007"
PASSWORD = "Welcome2024!"

async def main():
    print("\n===== Login simplificado =====")
    
    print(f"Usando credenciales: {USERNAME} / {'*' * len(PASSWORD)}")
    
    async with async_playwright() as p:
        # Lanzar navegador visible
        browser = await p.chromium.launch(headless=False, slow_mo=100)
        page = await browser.new_page()
        
        try:
            # Ir a la página de login
            print("Navegando a Twitter...")
            await page.goto("https://twitter.com/i/flow/login")
            
            # Esperar a que cargue la página
            await page.wait_for_load_state("networkidle")
            print("Página de login cargada")
            
            # Esperar campo de usuario
            print("Buscando campo de usuario...")
            await page.wait_for_selector('input[autocomplete="username"]')
            
            # Ingresar usuario
            print(f"Ingresando usuario: {USERNAME}")
            await page.fill('input[autocomplete="username"]', USERNAME)
            
            # Esperar un momento
            time.sleep(2)
            
            # Hacer clic en botón Siguiente
            print("Haciendo clic en Siguiente")
            await page.click('div[role="button"]:has-text("Next")')
            
            # Esperar campo de contraseña
            time.sleep(2)
            print("Buscando campo de contraseña...")
            await page.wait_for_selector('input[type="password"]')
            
            # Ingresar contraseña
            print(f"Ingresando contraseña")
            await page.fill('input[type="password"]', PASSWORD)
            
            # Esperar un momento
            time.sleep(2)
            
            # Hacer clic en botón Login
            print("Haciendo clic en Iniciar sesión")
            await page.click('div[data-testid="LoginForm_Login_Button"]')
            
            # Esperar a que se cargue la página principal
            print("Esperando inicio de sesión exitoso...")
            try:
                await page.wait_for_selector('div[data-testid="primaryColumn"]', timeout=20000)
                print("¡Inicio de sesión exitoso!")
                
                # Guardar estado
                await browser.contexts[0].storage_state(path="twitter_storage_simple.json")
                print("Estado guardado en twitter_storage_simple.json")
                
            except Exception as e:
                print(f"Error al esperar página principal: {e}")
                print("Revisando si hay verificación...")
                
                # Verificar si hay CAPTCHA o verificación
                if await page.is_visible('div[data-testid="OCF_CallToAction_Button"]'):
                    print("Verificación detectada. Por favor complétala manualmente...")
                    
                    # Pausa para intervención manual
                    print("Presiona Enter en esta terminal cuando termines...")
                    input()
                    
                    # Verificar si ahora estamos logueados
                    try:
                        await page.wait_for_selector('div[data-testid="primaryColumn"]', timeout=10000)
                        print("¡Inicio de sesión exitoso después de verificación!")
                        
                        # Guardar estado
                        await browser.contexts[0].storage_state(path="twitter_storage_simple.json")
                        print("Estado guardado en twitter_storage_simple.json")
                        
                    except Exception as e2:
                        print(f"Login fallido después de verificación: {e2}")
                else:
                    print("No se detectó verificación, pero el login falló")
            
            # Mantener abierto el navegador
            print("\nNavegador mantenido abierto para inspección")
            print("Presiona Enter en esta terminal para cerrar...")
            input()
                
        except Exception as e:
            print(f"Error durante el login: {e}")
        
        finally:
            # Cerrar navegador
            await browser.close()
            print("Navegador cerrado")

if __name__ == "__main__":
    asyncio.run(main()) 