#!/usr/bin/env python3

"""
Script para ejecutar la aplicación en modo local.
Este script configura el entorno para desarrollo local y ejecuta el servidor API.
"""

import os
import sys
import uvicorn
import logging
from dotenv import load_dotenv

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

# Cargar variables de entorno desde .env si existe
load_dotenv()

# Establecer configuración para modo local
os.environ["DOCKER_ENVIRONMENT"] = "0"
os.environ["RAILWAY_ENVIRONMENT"] = "0"
os.environ["LOCAL_DEVELOPMENT"] = "1"

# Asegurarse de que el navegador sea visible en local
os.environ["HEADLESS"] = "0"  # Forzar modo visible

def main():
    """Función principal para ejecutar la aplicación en modo local."""
    logger.info("Iniciando aplicación en modo local...")
    
    # Importar la aplicación después de configurar el entorno
    from docker_extract_recent import app
    
    # Ejecutar servidor uvicorn
    logger.info("Iniciando servidor en http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)

if __name__ == "__main__":
    main()
