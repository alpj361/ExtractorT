# Configuración del Perfil de Chrome para Docker

Este documento explica cómo resolver el problema de autenticación en Twitter cuando se ejecuta el contenedor Docker.

## Problema

El error `"Failed to log in after 3 attempts: Login required but running in production mode"` ocurre cuando el contenedor Docker no puede encontrar o acceder correctamente al perfil de Chrome existente donde ya hay una sesión iniciada.

## Solución

La solución consiste en **montar correctamente el directorio del perfil de Chrome como un volumen** cuando se inicia el contenedor.

### Pasos para solucionar

1. **Asegúrate de tener un perfil de Chrome con sesión iniciada**:
   - El directorio `chrome_profile` debe contener una carpeta `Default` con archivos como `Cookies` y `Login Data`.
   - Si estos archivos no existen, es necesario crear el perfil ejecutando el servicio en modo local primero.

2. **Usa el script `run_docker.sh` para iniciar el contenedor**:
   ```bash
   ./run_docker.sh
   ```
   
   Este script:
   - Verifica si la carpeta `chrome_profile` existe
   - Detiene y elimina contenedores previos
   - Ejecuta el contenedor con el volumen montado correctamente

3. **Verifica que el contenedor esté accediendo al perfil**:
   ```bash
   docker logs extractor_container
   ```
   
   Deberías ver mensajes indicando que el directorio `/chrome_profile/Default` existe y que los archivos `Cookies` y `Login Data` fueron encontrados.

## Solución de problemas

1. **Si el perfil no tiene sesión iniciada**:
   - Detén el contenedor: `docker stop extractor_container`
   - Elimina la carpeta `chrome_profile` existente: `rm -rf chrome_profile`
   - Ejecuta la aplicación en modo local para hacer login manual:
     ```bash
     python run_local.py
     ```
   - Una vez que hayas iniciado sesión manualmente en Twitter, la nueva sesión se guardará en `chrome_profile`
   - Vuelve a iniciar el contenedor: `./run_docker.sh`

2. **Si hay problemas de permisos**:
   ```bash
   chmod -R 777 chrome_profile
   ```

3. **Si el perfil no es compatible con la versión de Chrome en el contenedor**:
   - Asegúrate de que estás usando Chrome versión 114 (o compatible) para crear el perfil
   - Alternativamente, modifica el Dockerfile para usar la misma versión de Chrome que usaste para crear el perfil

## Verificación

Para comprobar que todo funciona correctamente:

1. Accede a la API del servicio: http://localhost:8000/docs
2. Prueba el endpoint de extracción de tweets
3. Revisa los logs del contenedor: `docker logs extractor_container`

## Notas adicionales

- El perfil de Chrome debe crearse y guardar la sesión antes de utilizarlo en Docker.
- Asegúrate de que no hay problemas de permisos para acceder al perfil.
- Si cambias entre diferentes máquinas o sistemas operativos, es posible que necesites recrear el perfil. 