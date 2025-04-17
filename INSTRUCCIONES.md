# Instrucciones para el Scraper de Twitter

Este documento proporciona instrucciones detalladas para configurar y ejecutar el scraper de Twitter en diferentes entornos, con especial atención a la solución de problemas en máquinas con Apple Silicon (ARM64).

## Requisitos previos

- Docker instalado
- Python 3.11 o superior
- Una cuenta de Twitter/X y estar logueado en Chrome

## Preparación de cookies para autenticación

El scraper utiliza cookies de tu sesión de Twitter para autenticarse. Para extraer estas cookies:

1. Inicia sesión en Twitter/X usando Chrome en tu computadora
2. Ejecuta el script de extracción de cookies:
   ```
   python extract_cookies.py
   ```
3. Esto creará un archivo `twitter_cookies.json` en el directorio actual

## Ejecución del scraper

### Usando Docker (recomendado)

El método más sencillo para ejecutar el scraper es usar Docker:

1. Asegúrate de que el archivo `twitter_cookies.json` está en el directorio del proyecto
2. Ejecuta el script de Docker:
   ```
   bash run_docker.sh
   ```
3. El script construirá la imagen Docker (si es necesario) y ejecutará el contenedor
4. La API estará disponible en http://localhost:8000

#### Solución de problemas para Apple Silicon (M1/M2/M3)

Si estás utilizando una Mac con Apple Silicon, el script `run_docker.sh` detectará automáticamente la arquitectura ARM64 y aplicará la configuración necesaria (`--platform=linux/amd64`).

Si encuentras algún error, puedes:

1. Verificar que el script haya detectado correctamente la arquitectura:
   ```
   uname -m
   ```
   Debería mostrar `arm64` en Macs con Apple Silicon.

2. Si persisten los problemas, prueba construir manualmente la imagen con:
   ```
   docker build --platform=linux/amd64 -t extractor .
   ```

3. Y luego ejecutar el contenedor:
   ```
   docker run -d --platform=linux/amd64 -e DOCKER_ENVIRONMENT=1 -v "$(pwd)/twitter_cookies.json:/app/cookies/twitter_cookies.json" -p 8000:8000 --name extractor_container extractor
   ```

### Ejecución local (desarrollo)

Para desarrollar o probar sin Docker:

1. Crea un entorno virtual:
   ```
   python -m venv venv
   source venv/bin/activate  # En Windows: venv\Scripts\activate
   ```

2. Instala las dependencias:
   ```
   pip install -r requirements.txt
   ```

3. Ejecuta la aplicación:
   ```
   uvicorn app.main:app --reload
   ```

4. La API estará disponible en http://localhost:8000

## Uso de la API

### Extraer tweets por hashtag

```
GET http://localhost:8000/extract/hashtag/{hashtag}?max_tweets=30&min_tweets=10&max_scrolls=10
```

Ejemplo:
```
http://localhost:8000/extract/hashtag/python?max_tweets=20
```

### Extraer tweets de un usuario

```
GET http://localhost:8000/extract/user/{username}?max_tweets=30&min_tweets=10&max_scrolls=10
```

Ejemplo:
```
http://localhost:8000/extract/user/elonmusk?max_tweets=20
```

## Solución de problemas comunes

### Error en la construcción de la imagen Docker

Si encuentras errores relacionados con ChromeDriver durante la construcción de la imagen, verifica:

1. Que los cambios en el `Dockerfile` se han aplicado correctamente, especialmente la sección que instala `chromedriver-py`
2. Que `requirements.txt` incluye `chromedriver-py`

### Problemas de autenticación

Si el scraper no puede autenticarse con Twitter:

1. Verifica que el archivo `twitter_cookies.json` está presente y tiene el formato correcto
2. Regenera las cookies usando `extract_cookies.py` después de iniciar sesión manualmente en Twitter
3. Revisa los logs del contenedor para obtener más información:
   ```
   docker logs extractor_container
   ```

### Problemas de visualización en el navegador

Si la aplicación está ejecutándose pero no puedes ver la interfaz web:

1. Verifica que la API está funcionando con:
   ```
   curl http://localhost:8000/health
   ```
2. Asegúrate de que el puerto 8000 no está bloqueado por un firewall
3. Intenta acceder a la documentación de la API en http://localhost:8000/docs 