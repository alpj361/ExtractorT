#!/usr/bin/env python3
"""
Script ultra-simplificado de login de Twitter con credenciales directas
"""

import asyncio
from playwright.async_api import async_playwright

# Credenciales directas (cambiar por las reales)
USERNAME = "StandPd2007"
PASSWORD = "Welcome2024!"

async def main():
    # Lanzar Playwright y browser
    async with async_playwright() as p:
        browser = await p.firefox.launch(headless=False)  # Usamos Firefox en lugar de Chrome
        context = await browser.new_context()
        page = await context.new_page()
        
        try:
            # 1. Navegar a Twitter
            print("Navegando a Twitter...")
            await page.goto("https://twitter.com/i/flow/login")
            
            # 2. Esperar el campo de usuario
            print("Esperando campo de usuario...")
            await page.wait_for_selector('input[autocomplete="username"]')
            
            # 3. Ingresar usuario
            print(f"Ingresando usuario: {USERNAME}")
            await page.fill('input[autocomplete="username"]', USERNAME)
            
            # Pequeña pausa
            await asyncio.sleep(1)
            
            # 4. Hacer clic en Next usando diferentes selectores
            print("Haciendo clic en Next...")
            
            # Intentamos múltiples selectores para encontrar el botón Next
            next_selectors = [
                'div[role="button"]:has-text("Next")',
                'div[data-testid="auth_login-next"]',
                'div[role="button"] span:has-text("Next")',
                'div[role="button"]',
                'div[data-testid="nextButton"]',
                'button[data-testid="nextButton"]',
            ]
            
            next_button_found = False
            for selector in next_selectors:
                try:
                    print(f"Intentando selector: {selector}")
                    if await page.query_selector(selector):
                        await page.click(selector, timeout=5000)
                        next_button_found = True
                        print(f"Botón encontrado con selector: {selector}")
                        break
                except Exception as e:
                    print(f"Selector {selector} falló: {e}")
            
            if not next_button_found:
                print("Intentando presionar Enter en el campo de usuario...")
                await page.press('input[autocomplete="username"]', 'Enter')
            
            # 5. Pequeña pausa
            await asyncio.sleep(3)
            
            # 6. Esperar e ingresar contraseña
            print("Ingresando contraseña...")
            try:
                await page.wait_for_selector('input[type="password"]', timeout=10000)
                await page.fill('input[type="password"]', PASSWORD)
                
                # 7. Hacer clic en Log in
                print("Haciendo clic en Log in...")
                login_button_selectors = [
                    'div[data-testid="LoginForm_Login_Button"]',
                    'div[role="button"]:has-text("Log in")',
                    'div[data-testid="LoginButton"]',
                    'button[data-testid="LoginButton"]'
                ]
                
                login_button_found = False
                for selector in login_button_selectors:
                    try:
                        if await page.query_selector(selector):
                            await page.click(selector, timeout=5000)
                            login_button_found = True
                            print(f"Botón login encontrado con selector: {selector}")
                            break
                    except Exception as e:
                        print(f"Selector login {selector} falló: {e}")
                
                if not login_button_found:
                    print("Intentando presionar Enter en el campo de contraseña...")
                    await page.press('input[type="password"]', 'Enter')
                
                # 8. Esperar a que se complete el login
                print("Esperando a que se complete el login...")
                await page.wait_for_selector('div[data-testid="primaryColumn"]', timeout=30000)
                
                # 9. Guardar el estado
                print("Login exitoso!")
                await context.storage_state(path="firefox_storage.json")
                print("Estado guardado en firefox_storage.json")
                
                # 10. Tomar captura de éxito
                await page.screenshot(path="login_success_firefox.png")
                print("Captura guardada como login_success_firefox.png")
            except Exception as e:
                print(f"Error después de Next: {e}")
                await page.screenshot(path="error_after_next.png")
                print("Captura guardada como error_after_next.png")
            
            # 11. Mantener el navegador abierto para inspección
            print("\nNavegador abierto para inspección. Presiona Enter para cerrar.")
            input()
            
        except Exception as e:
            print(f"Error durante el login: {e}")
            
            try:
                # Tomar captura de error para diagnóstico
                await page.screenshot(path="login_error_firefox.png")
                print("Captura de error guardada como login_error_firefox.png")
                
                # Mostrar HTML para diagnóstico
                content = await page.content()
                with open("login_error.html", "w", encoding="utf-8") as f:
                    f.write(content)
                print("HTML guardado como login_error.html")
                
                # Mantener navegador abierto para depuración manual
                print("\nError detectado. Navegador mantenido abierto para inspección.")
                print("Presiona Enter para cerrar.")
                input()
            except:
                pass
            
        finally:
            # Cerrar browser
            await browser.close()
            print("Navegador cerrado.")

if __name__ == "__main__":
    asyncio.run(main()) 