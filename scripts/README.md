# Scripts de extracción de tweets de Twitter

Este directorio contiene scripts optimizados para extraer tweets de perfiles de Twitter, con enfoque en obtener tweets recientes y filtrar correctamente tweets fijados/promocionados.

## Archivos principales

### `login_direct.py`

Script para iniciar sesión en Twitter y guardar el estado de la sesión.

**Uso:**
```bash
python login_direct.py
```

- Abre un navegador Firefox
- Inicia sesión con las credenciales hardcodeadas (reemplazar con las tuyas)
- Guarda las cookies y estado de sesión en `firefox_storage.json`

### `twitter_login.py`

Versión avanzada del script de login que usa las credenciales del archivo `.env`.

**Uso:**
```bash
python twitter_login.py [--force] [--interactive] [--headless]
```

**Opciones:**
- `--force`: Fuerza un nuevo login descartando sesiones existentes
- `--interactive`: Modo interactivo (muestra el navegador)
- `--headless`: Modo headless (sin navegador visible)

### `docker_compatible_extract.py`

Script principal para extracción de tweets, compatible con Docker y entornos locales.

**Uso:**
```bash
python docker_compatible_extract.py USERNAME [MAX_TWEETS] [MIN_TWEETS] [MAX_SCROLLS]
```

**Parámetros:**
- `USERNAME`: Nombre de usuario de Twitter (sin @)
- `MAX_TWEETS`: Número máximo de tweets a extraer (predeterminado: 15)
- `MIN_TWEETS`: Número mínimo de tweets a extraer (predeterminado: 5)
- `MAX_SCROLLS`: Número máximo de desplazamientos (predeterminado: 5)

**Características:**
- Prioriza tweets recientes usando URLs de búsqueda con filtro "latest"
- Filtra correctamente tweets fijados/promocionados
- Compatible con Docker y entornos locales
- Genera un archivo CSV con los tweets extraídos

### `final_extract.py`

Versión alternativa del extractor con funcionalidades adicionales.

**Uso:**
```bash
python final_extract.py USERNAME [MAX_TWEETS] [MIN_TWEETS] [MAX_SCROLLS]
```

## Flujo de trabajo recomendado

1. Primero inicia sesión con `login_direct.py` o `twitter_login.py`
2. Luego extrae tweets con `docker_compatible_extract.py`
3. Verifica el archivo CSV generado

## Solución de problemas

Si encuentras problemas con la extracción:

1. Verifica que el archivo de estado de sesión (`firefox_storage.json`) existe
2. Asegúrate de que las credenciales son correctas
3. Revisa los logs para identificar problemas específicos
4. Intenta iniciar sesión nuevamente con el modo interactivo 