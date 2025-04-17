#!/bin/bash

# Nombre de la nueva rama
BRANCH_NAME="feature/recent-tweets-extraction"

# Crear nueva rama
echo "Creando nueva rama: $BRANCH_NAME"
git checkout -b $BRANCH_NAME

# Añadir los nuevos scripts
git add user_profile_direct.py
git add test_specific_user.py
git add user_search_with_date.py

# Hacer commit con mensaje descriptivo
git commit -m "Implementación de extracción de tweets recientes:
- Script directo al perfil de usuario que obtiene tweets recientes
- Mejora en el manejo de tiempos de espera y navegación
- Ordenamiento de tweets por fecha (más recientes primero)
- Mejor manejo de errores y diagnóstico con capturas de pantalla"

# Mostrar estado
echo "Cambios guardados en rama $BRANCH_NAME"
git status

echo ""
echo "Para enviar la rama al repositorio remoto, ejecuta:"
echo "git push -u origin $BRANCH_NAME"
echo ""
echo "Para volver a la rama principal:"
echo "git checkout main" 