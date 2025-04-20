# Instrucciones para probar la extracción de tweets con login automático

Estas instrucciones te guiarán a través del proceso para probar la nueva funcionalidad de login automático con Playwright, que permite una extracción más fiable de tweets recientes.

## Preparación

1. **Configura el entorno**:
   ```bash
   # Asegúrate de que todas las dependencias estén instaladas
   pip install python-dotenv playwright
   playwright install chromium
   ```

2. **Configura las credenciales**:
   - Copia el archivo de ejemplo:
     ```bash
     cp .env.example .env
     ```
   - Edita el archivo `.env` y añade tus credenciales de Twitter:
     ```
     TWITTER_USERNAME=tu_usuario_de_twitter
     TWITTER_PASSWORD=tu_contraseña_de_twitter
     ```

## Opción 1: Prueba paso a paso

Puedes probar cada componente por separado siguiendo estos pasos:

1. **Prueba el login automático**:
   ```bash
   python twitter_login.py
   ```
   Este comando abrirá una ventana de navegador y realizará el login automáticamente.
   Si aparece un CAPTCHA, deberás resolverlo manualmente.

2. **Prueba la integración del login**:
   ```bash
   python app/services/twitter_login_integration.py
   ```
   Este comando probará la integración del login con el scraper.

3. **Prueba la extracción completa**:
   ```bash
   python final_extract.py KarinHerreraVP 15 5 5
   ```
   Este comando extraerá los tweets del usuario especificado.

## Opción 2: Prueba automática

Para ejecutar una prueba completa del flujo de trabajo:

```bash
./test_login_extraction.sh
```

Este script realizará automáticamente los siguientes pasos:
1. Verificar las credenciales de Twitter
2. Iniciar sesión y guardar el estado
3. Configurar la integración de login
4. Extraer tweets de un usuario de prueba
5. Mostrar los resultados

## Opción 3: Prueba manual simplificada

Para una prueba más visual y detallada:

```bash
python test_manual.py
```

Este script muestra paso a paso el proceso con indicadores claros de éxito o error.

## Solución de problemas

- **Error de login**: Verifica tus credenciales en el archivo `.env`
- **CAPTCHA**: Si aparece un CAPTCHA, la ventana del navegador permanecerá abierta para que lo resuelvas manualmente
- **Error de conexión**: Asegúrate de tener una conexión a Internet estable
- **Error de extracción**: Revisa los logs para identificar el problema específico

## Verificación de resultados

Después de ejecutar cualquiera de las pruebas, verifica los archivos CSV generados:
- `KarinHerreraVP_latest.csv`: Para el script principal y el test automático
- `KarinHerreraVP_test_manual.csv`: Para la prueba manual

Los tweets deben estar ordenados por fecha, con los más recientes primero. Verifica que no aparezcan tweets fijados al principio de la lista si no son recientes. 