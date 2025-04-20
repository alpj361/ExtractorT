#!/bin/bash
# Script para desplegar la versión ultra minimalista del extractor de tweets en Railway
# desde la rama específica de Git

# Colores para mensajes
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuración
BRANCH_NAME="branch3"
GIT_REPO_URL=$(git config --get remote.origin.url 2>/dev/null)

echo -e "${BLUE}=== Preparando despliegue MINIMALISTA en Railway ===${NC}"
echo -e "${YELLOW}Rama Git:${NC} $BRANCH_NAME"
echo -e "${YELLOW}Repositorio:${NC} $GIT_REPO_URL"

# Verificar si estamos en un repositorio Git
if ! git rev-parse --is-inside-work-tree &>/dev/null; then
    echo -e "${RED}Error: No estás dentro de un repositorio Git${NC}"
    exit 1
fi

# Verificar si la rama existe localmente
if ! git show-ref --verify --quiet refs/heads/$BRANCH_NAME; then
    echo -e "${RED}Error: La rama '$BRANCH_NAME' no existe localmente${NC}"
    
    # Preguntar si quiere crearla
    read -p "¿Quieres crear esta rama? (s/n): " create_branch
    if [[ $create_branch == "s" || $create_branch == "S" ]]; then
        git checkout -b $BRANCH_NAME
        echo -e "${GREEN}Rama '$BRANCH_NAME' creada y activa${NC}"
    else
        exit 1
    fi
fi

# Cambiar a la rama correcta si no estamos en ella
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ "$CURRENT_BRANCH" != "$BRANCH_NAME" ]; then
    echo -e "${YELLOW}Cambiando de rama '$CURRENT_BRANCH' a '$BRANCH_NAME'...${NC}"
    git checkout $BRANCH_NAME
    
    if [ $? -ne 0 ]; then
        echo -e "${RED}Error al cambiar a la rama '$BRANCH_NAME'${NC}"
        exit 1
    fi
    echo -e "${GREEN}Ahora estás en la rama '$BRANCH_NAME'${NC}"
fi

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

# Verificar que existen los archivos necesarios
if [ ! -f "Dockerfile.minimal" ]; then
    echo -e "${RED}No se encontró el archivo Dockerfile.minimal${NC}"
    exit 1
fi

if [ ! -f "minimal_railway_extractor.py" ]; then
    echo -e "${RED}No se encontró el archivo minimal_railway_extractor.py${NC}"
    exit 1
fi

if [ ! -f "railway_minimal.json" ]; then
    echo -e "${RED}No se encontró el archivo railway_minimal.json${NC}"
    exit 1
fi

# Asegurar que los archivos están añadidos al control de versiones
if ! git ls-files --error-unmatch Dockerfile.minimal minimal_railway_extractor.py railway_minimal.json &>/dev/null; then
    echo -e "${YELLOW}Algunos archivos no están en control de versiones. Añadiéndolos...${NC}"
    
    if ! git ls-files --error-unmatch Dockerfile.minimal &>/dev/null; then
        git add Dockerfile.minimal
        echo -e "${GREEN}Añadido: Dockerfile.minimal${NC}"
    fi
    
    if ! git ls-files --error-unmatch minimal_railway_extractor.py &>/dev/null; then
        git add minimal_railway_extractor.py
        echo -e "${GREEN}Añadido: minimal_railway_extractor.py${NC}"
    fi
    
    if ! git ls-files --error-unmatch railway_minimal.json &>/dev/null; then
        git add railway_minimal.json
        echo -e "${GREEN}Añadido: railway_minimal.json${NC}"
    fi
    
    # Preguntar si quiere hacer commit
    read -p "¿Hacer commit de estos cambios? (s/n): " do_commit
    if [[ $do_commit == "s" || $do_commit == "S" ]]; then
        git commit -m "Añadir archivos para despliegue minimalista en Railway"
        echo -e "${GREEN}Commit realizado${NC}"
    fi
fi

# Copiar railway_minimal.json a railway.json temporalmente
echo -e "${BLUE}Copiando archivo de configuración para Railway...${NC}"
cp railway_minimal.json railway.json

# Verificar que railway.json tiene la configuración correcta
if ! grep -q "Dockerfile.minimal" railway.json; then
    echo -e "${RED}El archivo railway.json no está configurado correctamente${NC}"
    exit 1
fi

# Desplegar el proyecto especificando la rama
echo -e "${GREEN}Desplegando versión MINIMALISTA en Railway desde rama '$BRANCH_NAME'...${NC}"
railway up --branch $BRANCH_NAME

if [ $? -eq 0 ]; then
    echo -e "${GREEN}¡Versión minimalista desplegada exitosamente desde la rama '$BRANCH_NAME'!${NC}"
    echo -e "${BLUE}Para abrir el proyecto en el navegador:${NC} railway open"
    echo -e "${BLUE}Para ver los logs:${NC} railway logs"
    echo -e "${BLUE}Para verificar estado del servicio:${NC} railway status"
    
    echo -e "\n${GREEN}Endpoints disponibles:${NC}"
    echo -e "  - GET / - Información de la API"
    echo -e "  - GET /health - Estado de salud del servicio"
    echo -e "  - GET /extract/{username} - Extraer tweets de un usuario (hasta 50 tweets)"
else
    echo -e "${RED}Error al desplegar el proyecto. Revisa los logs para más información.${NC}"
fi

# Eliminar el railway.json temporal
echo -e "${BLUE}Limpiando archivos temporales...${NC}"
if [ -f "railway.json" ]; then
    rm railway.json
fi

echo -e "${BLUE}=== Proceso completado ===${NC}" 