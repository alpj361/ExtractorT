# Importamos selenium directamente, que es más estable
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
# from webdriver_manager.chrome import ChromeDriverManager  # Comentamos esta línea
import time
import os

# Ruta donde se guardará el perfil de Chrome
profile_path = "/tmp/twitter_profile"


# Configurar opciones
options = Options()
options.add_argument(f"--user-data-dir={profile_path}")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")

# Opciones para evitar detección
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_experimental_option("excludeSwitches", ["enable-automation"])
options.add_experimental_option("useAutomationExtension", False)

# Ruta al ChromeDriver descargado manualmente
chromedriver_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "drivers", "chromedriver")
print(f"Usando ChromeDriver en: {chromedriver_path}")

# Iniciar Chrome
print("Iniciando Chrome...")
service = Service(executable_path=chromedriver_path)
print("📦 Configuración de Chrome lista, inicializando el navegador...")
driver = webdriver.Chrome(service=service, options=options)
print("✅ Navegador iniciado correctamente.")





# Desactivar la detección de webdriver
driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

print("Abriendo Twitter...")
driver.get("https://twitter.com/login")
print("🧠 Inicia sesión manualmente en la ventana del navegador.")
print("🔒 Esperando que completes el login...")

# Esperar para login manual
for i in range(120):
    print(f"⏳ Esperando... ({i+1}/120)")
    time.sleep(1)
    
    # Intentar detectar si ya iniciaste sesión
    if "home" in driver.current_url:
        print("✅ Sesión iniciada detectada!")
        break

print("✅ Si lograste iniciar sesión, el perfil se guardó. Cerrando navegador.")
driver.quit()