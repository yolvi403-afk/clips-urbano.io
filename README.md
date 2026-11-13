# Clips Urbano V2

Proyecto dividido en:
- `static/index.html`: interfaz web para GitHub Pages.
- `app.py`: API que transcribe audio en español con Whisper, corta el video y quema los subtítulos dentro de cada MP4.
- `Dockerfile`: despliegue del backend con FFmpeg.

## Importante
Procesa únicamente videos propios o para los que tengas permiso de edición. Este backend **no descarga videos desde enlaces de YouTube**. Sube un archivo de video desde tu dispositivo. Un enlace de YouTube incrustado no es un archivo de video descargable.

## 1. Publicar la página en GitHub Pages
1. Sube `static/index.html` a tu repositorio como `index.html` (o mueve su contenido a la raíz).
2. En GitHub abre Settings → Pages.
3. Selecciona la rama y la carpeta raíz y guarda.

## 2. Desplegar el servidor
Despliega este repositorio en un servicio que admita Docker y almacenamiento suficiente. El servidor necesita FFmpeg y memoria para Whisper. El primer procesamiento puede tardar porque descarga el modelo de reconocimiento.
1. Crea un servicio web desde el repositorio.
2. Selecciona Docker como entorno.
3. Configura `WHISPER_MODEL=small`.
4. Configura `MAX_UPLOAD_MB=500`.
5. Cuando el servicio esté activo, copia su URL HTTPS.

## 3. Conectar GitHub Pages con el backend
En `static/index.html`, busca:
`const API_BASE = window.CLIPS_API_BASE || "";`
y reemplaza la cadena vacía por la URL HTTPS del backend, por ejemplo:
`const API_BASE = "https://TU-SERVIDOR.example.com";`
No agregues `/` al final.

En el backend configura `ALLOWED_ORIGINS` con el dominio de tu página GitHub Pages. Ejemplo:
`https://TU-USUARIO.github.io`

## 4. Ejecutar localmente (opcional)
Necesitas Python 3.11+, FFmpeg y las dependencias:
```bash
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000
```
Abre `static/index.html` desde un servidor web local y configura `API_BASE` como `http://127.0.0.1:8000`.

## Qué hace
- Transcribe el audio en español con faster-whisper.
- Muestra una muestra de la transcripción para que puedas revisar de qué trata el video.
- Crea hasta 10 clips distribuidos a lo largo del video.
- Genera un archivo SRT por clip y lo incrusta visualmente en el MP4.
- Ofrece descarga del MP4 y del SRT.

## Limitaciones
- No selecciona automáticamente los momentos más virales; distribuye los clips a lo largo del video.
- El análisis mostrado es una transcripción, no un resumen semántico generado por IA.
- Los archivos procesados se guardan en el disco del servidor; configura almacenamiento persistente y una política de limpieza antes de uso público.
- Añade autenticación, límites de uso y limpieza de trabajos antes de abrirlo a todo el mundo.
