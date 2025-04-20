#!/bin/bash
# Script para construir y ejecutar el Docker con el extractor de tweets recientes

# Colores para mensajes
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== Iniciando construcción del Docker para el extractor de tweets recientes ===${NC}"

# Verificar si docker está instalado
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Docker no está instalado. Por favor, instálalo primero.${NC}"
    exit 1
fi

# Construir la imagen Docker
echo -e "${GREEN}Construyendo la imagen Docker...${NC}"
docker build --platform=linux/amd64 -t extractor-tweets-recientes .

# Verificar si la construcción fue exitosa
if [ $? -eq 0 ]; then
    echo -e "${GREEN}Imagen Docker construida exitosamente.${NC}"
    
    # Detener y eliminar contenedor existente si existe
    if docker ps -a | grep -q extractor-container; then
        echo -e "${BLUE}Deteniendo y eliminando contenedor existente...${NC}"
        docker stop extractor-container
        docker rm extractor-container
    fi
    
    # Ejecutar el contenedor
    echo -e "${GREEN}Ejecutando el contenedor...${NC}"
    docker run -d \
        --platform=linux/amd64 \
        -e DOCKER_ENVIRONMENT=1 \
        -e TWITTER_USERNAME="$TWITTER_USERNAME" \
        -e TWITTER_PASSWORD="$TWITTER_PASSWORD" \
        -p 8000:8000 \
        --name extractor-container \
        extractor-tweets-recientes
    
    # Verificar si el contenedor está corriendo
    if docker ps | grep -q extractor-container; then
        echo -e "${GREEN}Contenedor iniciado correctamente.${NC}"
        echo -e "${BLUE}La API está disponible en: http://localhost:8000${NC}"
        echo -e "${BLUE}Para ver los logs: docker logs extractor-container${NC}"
        echo -e "${BLUE}Para detener el contenedor: docker stop extractor-container${NC}"
    else
        echo -e "${RED}Error al iniciar el contenedor. Revisa los logs con 'docker logs extractor-container'${NC}"
    fi
else
    echo -e "${RED}Error al construir la imagen Docker. Verifica los errores anteriores.${NC}"
fi

echo -e "${BLUE}=== Proceso completado ===${NC}" 