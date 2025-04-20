#!/bin/bash
# Script para construir y ejecutar el Docker con el extractor de tweets recientes usando el Dockerfile específico

# Colores para mensajes
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== Iniciando construcción del Docker para el extractor de tweets recientes (FIXED VERSION) ===${NC}"

# Verificar si docker está instalado
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Docker no está instalado. Por favor, instálalo primero.${NC}"
    exit 1
fi

# Verificar que el Dockerfile.recent existe
if [ ! -f "Dockerfile.recent" ]; then
    echo -e "${RED}No se encontró el archivo Dockerfile.recent${NC}"
    exit 1
fi

# Construir la imagen Docker usando el Dockerfile específico
echo -e "${GREEN}Construyendo la imagen Docker con Dockerfile.recent...${NC}"
docker build --platform=linux/amd64 -t extractor-tweets-recientes-fixed -f Dockerfile.recent .

# Verificar si la construcción fue exitosa
if [ $? -eq 0 ]; then
    echo -e "${GREEN}Imagen Docker construida exitosamente.${NC}"
    
    # Detener y eliminar contenedor existente si existe
    if docker ps -a | grep -q extractor-recent-container; then
        echo -e "${BLUE}Deteniendo y eliminando contenedor existente...${NC}"
        docker stop extractor-recent-container
        docker rm extractor-recent-container
    fi
    
    # Extraer credenciales desde el archivo .env si existe
    if [ -f ".env" ]; then
        source .env
        echo -e "${BLUE}Usando credenciales desde .env file${NC}"
    else
        echo -e "${BLUE}Archivo .env no encontrado. Usando credenciales por defecto o variables de entorno existentes.${NC}"
    fi
    
    # Ejecutar el contenedor
    echo -e "${GREEN}Ejecutando el contenedor...${NC}"
    docker run -d \
        --platform=linux/amd64 \
        -e DOCKER_ENVIRONMENT=1 \
        -e TWITTER_USERNAME="${TWITTER_USERNAME:-StandPd2007}" \
        -e TWITTER_PASSWORD="${TWITTER_PASSWORD:-Welcome2024!}" \
        -p 8000:8000 \
        --name extractor-recent-container \
        extractor-tweets-recientes-fixed
    
    # Verificar si el contenedor está corriendo
    if docker ps | grep -q extractor-recent-container; then
        echo -e "${GREEN}Contenedor iniciado correctamente.${NC}"
        echo -e "${BLUE}La API está disponible en: http://localhost:8000${NC}"
        echo -e "${BLUE}Endpoints disponibles:${NC}"
        echo -e "  - GET / - Información de la API"
        echo -e "  - GET /status - Estado del servicio"
        echo -e "  - GET /extract/{username} - Extraer tweets de un usuario (GET)"
        echo -e "  - POST /extract_recent - Extraer tweets de un usuario (POST)"
        echo -e "  - GET /health - Estado de salud del servicio"
        echo -e "${BLUE}Para ver los logs: docker logs extractor-recent-container${NC}"
        echo -e "${BLUE}Para detener el contenedor: docker stop extractor-recent-container${NC}"
    else
        echo -e "${RED}Error al iniciar el contenedor. Revisa los logs con 'docker logs extractor-recent-container'${NC}"
    fi
else
    echo -e "${RED}Error al construir la imagen Docker. Verifica los errores anteriores.${NC}"
fi

echo -e "${BLUE}=== Proceso completado ===${NC}" 