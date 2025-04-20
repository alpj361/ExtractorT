#!/bin/bash
# Script para desplegar el extracto de tweets recientes en Railway

# Colores para mensajes
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== Preparando despliegue en Railway ===${NC}"

# Verificar si Railway CLI está instalado
if ! command -v railway &> /dev/null; then
    echo -e "${RED}Railway CLI no está instalado. Instalando...${NC}"
    npm i -g @railway/cli
    
    if [ $? -ne 0 ]; then
        echo -e "${RED}Error al instalar Railway CLI. Por favor, instálalo manualmente:${NC}"
        echo -e "${BLUE}npm i -g @railway/cli${NC}"
        exit 1
    fi
fi

# Verificar si estamos logueados en Railway
railway whoami &> /dev/null
if [ $? -ne 0 ]; then
    echo -e "${BLUE}Iniciando sesión en Railway...${NC}"
    railway login
    
    if [ $? -ne 0 ]; then
        echo -e "${RED}Error al iniciar sesión en Railway. Por favor, inténtalo manualmente:${NC}"
        echo -e "${BLUE}railway login${NC}"
        exit 1
    fi
fi

# Asegurarse de que tenemos un proyecto activo
railway project &> /dev/null
if [ $? -ne 0 ]; then
    echo -e "${BLUE}Vinculando a un proyecto de Railway...${NC}"
    railway link
    
    if [ $? -ne 0 ]; then
        echo -e "${RED}Error al vincular el proyecto. Por favor, intenta manualmente:${NC}"
        echo -e "${BLUE}railway link${NC}"
        exit 1
    fi
fi

# Verificar y configurar variables de entorno
echo -e "${GREEN}Configurando variables de entorno...${NC}"

# Comprobar si las variables están configuradas
if ! railway variables | grep -q TWITTER_USERNAME; then
    echo -e "${BLUE}Configurando credenciales de Twitter...${NC}"
    
    # Leer desde .env o pedir al usuario
    if [ -f ".env" ]; then
        source .env
        if [ -n "$TWITTER_USERNAME" ] && [ -n "$TWITTER_PASSWORD" ]; then
            railway variables set TWITTER_USERNAME="$TWITTER_USERNAME" TWITTER_PASSWORD="$TWITTER_PASSWORD" DOCKER_ENVIRONMENT=1 RAILWAY_ENVIRONMENT=1
        else
            read -p "Ingresa tu nombre de usuario de Twitter: " twitter_user
            read -sp "Ingresa tu contraseña de Twitter: " twitter_pass
            echo
            railway variables set TWITTER_USERNAME="$twitter_user" TWITTER_PASSWORD="$twitter_pass" DOCKER_ENVIRONMENT=1 RAILWAY_ENVIRONMENT=1
        fi
    else
        read -p "Ingresa tu nombre de usuario de Twitter: " twitter_user
        read -sp "Ingresa tu contraseña de Twitter: " twitter_pass
        echo
        railway variables set TWITTER_USERNAME="$twitter_user" TWITTER_PASSWORD="$twitter_pass" DOCKER_ENVIRONMENT=1 RAILWAY_ENVIRONMENT=1
    fi
fi

# Desplegar el proyecto
echo -e "${GREEN}Desplegando proyecto en Railway...${NC}"
railway up

if [ $? -eq 0 ]; then
    echo -e "${GREEN}¡Proyecto desplegado exitosamente!${NC}"
    echo -e "${BLUE}Para abrir el proyecto en el navegador:${NC} railway open"
    echo -e "${BLUE}Para ver los logs:${NC} railway logs"
    echo -e "${BLUE}Para verificar estado del servicio:${NC} railway status"
else
    echo -e "${RED}Error al desplegar el proyecto. Revisa los logs para más información.${NC}"
fi

echo -e "${BLUE}=== Proceso completado ===${NC}" 