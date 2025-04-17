#!/usr/bin/env python3
"""
Script para extraer cookies de Twitter desde Chrome y guardarlas en un archivo JSON.
Ejecutar después de haber iniciado sesión manualmente en Twitter en Chrome.
"""

import os
import json
import platform
import sqlite3
import shutil
import tempfile
from pathlib import Path

def get_chrome_cookies_path():
    """Encuentra la ruta al archivo de cookies de Chrome según el sistema operativo."""
    home = Path.home()
    
    if platform.system() == "Darwin":  # macOS
        return home / "Library/Application Support/Google/Chrome/Default/Cookies"
    elif platform.system() == "Windows":
        return home / "AppData/Local/Google/Chrome/User Data/Default/Cookies"
    else:  # Linux
        return home / ".config/google-chrome/Default/Cookies"

def extract_twitter_cookies():
    """Extrae las cookies de Twitter desde la base de datos de Chrome."""
    cookies_path = get_chrome_cookies_path()
    
    if not cookies_path.exists():
        print(f"No se encontró el archivo de cookies en {cookies_path}")
        return []
    
    # Hacer una copia temporal de la base de datos (porque Chrome puede tenerla bloqueada)
    temp_cookies = tempfile.NamedTemporaryFile(delete=False).name
    shutil.copy2(cookies_path, temp_cookies)
    
    try:
        # Conectar a la base de datos de cookies
        conn = sqlite3.connect(temp_cookies)
        cursor = conn.cursor()
        
        # Buscar cookies relacionadas con Twitter
        twitter_domains = ["twitter.com", ".twitter.com", "x.com", ".x.com"]
        domain_query = " OR ".join([f"host_key LIKE '%{domain}%'" for domain in twitter_domains])
        
        query = f"""
            SELECT name, value, host_key, path, expires_utc, is_secure, is_httponly
            FROM cookies
            WHERE {domain_query}
        """
        
        cursor.execute(query)
        results = cursor.fetchall()
        
        # Formatear las cookies como un array de objetos
        cookies = []
        for result in results:
            name, value, host_key, path, expires_utc, is_secure, is_httponly = result
            cookie = {
                "name": name,
                "value": value,
                "domain": host_key,
                "path": path,
                "secure": bool(is_secure),
                "httpOnly": bool(is_httponly),
                "expiry": expires_utc
            }
            cookies.append(cookie)
        
        return cookies
    
    except Exception as e:
        print(f"Error al extraer cookies: {e}")
        return []
    
    finally:
        # Limpiar el archivo temporal
        try:
            os.unlink(temp_cookies)
        except:
            pass

def main():
    """Función principal que extrae las cookies y las guarda en un archivo JSON."""
    print("Extrayendo cookies de Twitter desde Chrome...")
    cookies = extract_twitter_cookies()
    
    if not cookies:
        print("No se encontraron cookies de Twitter. Asegúrate de haber iniciado sesión en Twitter en Chrome.")
        return
    
    # Guardar las cookies en un archivo JSON
    with open("twitter_cookies.json", "w") as f:
        json.dump(cookies, f, indent=2)
    
    print(f"Se extrajeron {len(cookies)} cookies y se guardaron en twitter_cookies.json")
    print("¡Listo! Ahora puedes usar estas cookies con el scraper de Twitter.")

if __name__ == "__main__":
    main() 