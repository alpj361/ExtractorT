#!/usr/bin/env python3
"""
Script de login simplificado usando .env
"""

import os
import asyncio
import time
from pathlib import Path
from dotenv import load_dotenv
from playwright.async_api import async_playwright

# Cargar variables de entorno
load_dotenv(override=True)

# Obtener credenciales desde .env
USERNAME = os.environ.get("TWITTER_USERNAME")
PASSWORD = os.environ.get("TWITTER_PASSWORD")

async def main():
    print("\n===== Login simplificado con .env =====")
    
    # Verificar credenciales
    if not USERNAME or not PASSWORD:
        print("❌ ERROR: Credenciales no encontradas en el archivo .env")
        print("Por favor, verifica que el archivo .env existe y contiene:")
        print("TWITTER_USERNAME=tu_usuario_de_twitter")
        print("TWITTER_PASSWORD=tu_contraseña_de_twitter")
        return
    
    print(f"✅ Credenciales cargadas del archivo .env:")
    print(f"   Usuario: {USERNAME}")
    print(f"   Contraseña: {'*' * len(PASSWORD)}")
    
    # Verificar si el archivo .env tiene los valores correctos
    with open(".env", "r") as f:
        env_content = f.read()
        print("\nContenido del archivo .env:")
        for line in env_content.splitlines():
            if line.startswith("TWITTER_"):
                if "PASSWORD" in line:
                    # Ocultar contraseña real
                    key, value = line.split("=", 1)
                    print(f"{key}={'*' * len(value)}")
                else:
                    print(line)
    
    # Preguntar al usuario si quiere continuar
    print("\n¿Las credenciales son correctas? (s/n)")
    response = input()
    if response.lower() != "s":
        print("Operación cancelada por el usuario.")
        return
    
    async with async_playwright() as p:
        # Lanzar navegador visible
        browser = await p.chromium.launch(headless=False, slow_mo=100)
        page = await browser.new_page()
        
        try:
            # Ir a la página de login
            print("\nNavegando a Twitter...")
            await page.goto("https://twitter.com/i/flow/login")
            
            # Esperar a que cargue la página
            await page.wait_for_load_state("networkidle")
            print("Página de login cargada")
            
            # Esperar campo de usuario
            print("Buscando campo de usuario...")
            await page.wait_for_selector('input[autocomplete="username"]', timeout=10000)
            
            # Ingresar usuario
            print(f"Ingresando usuario: {USERNAME}")
            await page.fill('input[autocomplete="username"]', USERNAME)
            
            # Esperar un momento
            time.sleep(1)
            
            # Hacer clic en botón Siguiente
            print("Haciendo clic en Siguiente")
            await page.click('div[role="button"]:has-text("Next")')
            
            # Esperar campo de contraseña
            time.sleep(2)
            print("Buscando campo de contraseña...")
            
            try:
                await page.wait_for_selector('input[type="password"]', timeout=10000)
                print("Campo de contraseña encontrado")
            except Exception as e:
                print(f"Error al buscar campo de contraseña: {e}")
                print("Tomando captura de pantalla...")
                await page.screenshot(path="login_debug_password.png")
                print("Captura guardada como login_debug_password.png")
                
                # Verificar si hay un mensaje de error
                error_text = await page.inner_text('body')
                print(f"Texto en la página: {error_text[:200]}...")
                
                # Esperar a que el usuario revise
                print("Presiona Enter para continuar...")
                input()
            
            # Ingresar contraseña
            print(f"Ingresando contraseña")
            await page.fill('input[type="password"]', PASSWORD)
            
            # Esperar un momento
            time.sleep(1)
            
            # Hacer clic en botón Login
            print("Haciendo clic en Iniciar sesión")
            try:
                await page.click('div[data-testid="LoginForm_Login_Button"]')
                print("Botón de login clickeado")
            except Exception as e:
                print(f"Error al hacer clic en el botón de login: {e}")
                print("Intentando presionar Enter...")
                await page.keyboard.press("Enter")
            
            # Esperar a que se cargue la página principal
            print("Esperando inicio de sesión exitoso...")
            try:
                await page.wait_for_selector('div[data-testid="primaryColumn"]', timeout=20000)
                print("¡Inicio de sesión exitoso!")
                
                # Guardar estado
                storage_path = "twitter_storage_env.json"
                await browser.contexts[0].storage_state(path=storage_path)
                print(f"Estado guardado en {storage_path}")
                
                # Actualizar el path en el script original
                print(f"Actualizando el path de almacenamiento en twitter_login.py...")
                with open("twitter_login.py", "r") as f:
                    content = f.read()
                
                # Reemplazar el path del storage
                updated_content = content.replace(
                    'STORAGE_PATH = Path("./twitter_storage_state.json")',
                    f'STORAGE_PATH = Path("./{storage_path}")'
                )
                
                with open("twitter_login.py", "w") as f:
                    f.write(updated_content)
                
                print("Script twitter_login.py actualizado para usar el nuevo archivo de sesión")
                
            except Exception as e:
                print(f"Error al esperar página principal: {e}")
                print("Revisando si hay verificación...")
                
                # Tomar captura para diagnóstico
                await page.screenshot(path="login_verification.png")
                
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
                        storage_path = "twitter_storage_env.json"
                        await browser.contexts[0].storage_state(path=storage_path)
                        print(f"Estado guardado en {storage_path}")
                    except Exception as e2:
                        print(f"Login fallido después de verificación: {e2}")
                else:
                    print("No se detectó verificación, pero el login falló")
                    await page.screenshot(path="login_failed.png")
            
            # Mantener abierto el navegador
            print("\nNavegador mantenido abierto para inspección")
            print("Presiona Enter en esta terminal para cerrar...")
            input()
                
        except Exception as e:
            print(f"Error durante el login: {e}")
            
            # Capturar pantalla para diagnóstico
            try:
                await page.screenshot(path="login_error.png")
                print("Captura de error guardada como login_error.png")
            except:
                pass
        
        finally:
            # Cerrar navegador
            await browser.close()
            print("Navegador cerrado")

if __name__ == "__main__":
    asyncio.run(main()) 