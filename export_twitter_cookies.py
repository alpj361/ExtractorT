#!/usr/bin/env python
"""
Script para iniciar sesión en Twitter y exportar las cookies a un archivo JSON.
"""
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import json
import time
import os
import sys

def main():
    # Configuración
    print("🔧 Configurando navegador...")
    
    # Directorio para el perfil temporal
    temp_profile = "/tmp/twitter_temp_profile"
    os.makedirs(temp_profile, exist_ok=True)
    
    # Configurar opciones de Chrome
    options = Options()
    options.add_argument(f"--user-data-dir={temp_profile}")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    
    # Determinar la ruta del chromedriver
    chromedriver_path = None
    if os.path.exists("./twitter_login_test/drivers/chromedriver"):
        chromedriver_path = "./twitter_login_test/drivers/chromedriver"
    elif os.path.exists("./drivers/chromedriver"):
        chromedriver_path = "./drivers/chromedriver"
    
    if not chromedriver_path:
        print("❌ Error: No se pudo encontrar chromedriver. Asegúrate de que esté descargado.")
        sys.exit(1)
    
    print(f"🔍 Usando chromedriver en: {chromedriver_path}")
    
    # Iniciar Chrome
    print("🚀 Iniciando Chrome...")
    service = Service(executable_path=chromedriver_path)
    driver = webdriver.Chrome(service=service, options=options)
    
    # Desactivar la detección de webdriver
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    # Abrir Twitter
    print("🌐 Abriendo Twitter...")
    driver.get("https://twitter.com/login")
    print("🧠 Por favor, inicia sesión manualmente en la ventana del navegador.")
    print("🔒 Esperando que completes el login...")
    
    # Esperar login manual (máximo 2 minutos)
    logged_in = False
    for i in range(120):
        print(f"⏳ Esperando... ({i+1}/120)")
        time.sleep(1)
        
        # Verificar si ya se inició sesión
        current_url = driver.current_url
        print(f"URL actual: {current_url}")
        
        if "twitter.com/home" in current_url or "/flow/login" not in current_url:
            print("✅ Sesión iniciada detectada!")
            logged_in = True
            break
    
    if not logged_in:
        print("⚠️ No se detectó inicio de sesión automáticamente.")
        input("Presiona Enter si ya has iniciado sesión para continuar...")
    
    # Exportar cookies
    print("📦 Exportando cookies...")
    cookies = driver.get_cookies()
    
    # Guardar cookies en archivo JSON
    cookie_file = "twitter_cookies.json"
    with open(cookie_file, "w") as f:
        json.dump(cookies, f, indent=2)
    
    print(f"✅ Cookies guardadas en {cookie_file}")
    print(f"📝 Se exportaron {len(cookies)} cookies.")
    
    # Cerrar navegador
    print("🔒 Cerrando navegador...")
    driver.quit()
    
    print("✅ Proceso completado. Ahora puedes usar estas cookies en tu contenedor Docker.")
    print("   Ejecuta: docker cp twitter_cookies.json extractor_container:/app/cookies/twitter_cookies.json")

if __name__ == "__main__":
    main() 