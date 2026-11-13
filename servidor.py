import os
import subprocess
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from faster_whisper import WhisperModel

app = Flask(__name__)
CORS(app)  # permite que la página HTML se comunique con este servidor

CARPETA = "salida"
os.makedirs(CARPETA, exist_ok=True)

# "small" es un buen equilibrio. Si tu equipo es lento, usa "base".
modelo = WhisperModel("small", device="cpu", compute_type="int8")

def hms(segundos):
    h, rem = divmod(int(segundos), 3600)
    m, s = divmod(rem, 60)
    return f"{h:02}:{m:02}:{s:02}"

def srt_tiempo(t):
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02}:{int(m):02}:{s:06.3f}".replace(".", ",")

@app.route("/clip")
def clip():
    url = request.args["url"]
    ini = float(request.args["ini"])
    fin = float(request.args["fin"])
    nombre = request.args.get("nombre", "clip").replace("/", "-").replace("\\", "-")
    base = os.path.join(CARPETA, nombre)

    # 1. Descargar solo el tramo como MP3
    subprocess.run([
        "yt-dlp", "-x", "--audio-format", "mp3",
        "--download-sections", f"*{hms(ini)}-{hms(fin)}",
        "-o", base + ".%(ext)s", url
    ], check=True)
    mp3 = base + ".mp3"

    # 2. Transcribir el audio del clip
    segmentos, _ = modelo.transcribe(mp3)

    # 3. Crear el archivo de subtítulos
    with open(base + ".srt", "w", encoding="utf-8") as f:
        for i, s in enumerate(segmentos, 1):
            f.write(f"{i}\n{srt_tiempo(s.start)} --> {srt_tiempo(s.end)}\n{s.text.strip()}\n\n")

    return jsonify(
        mp3=f"/archivo/{nombre}.mp3",
        srt=f"/archivo/{nombre}.srt"
    )

@app.route("/archivo/<path:nombre_archivo>")
def archivo(nombre_archivo):
    return send_from_directory(CARPETA, nombre_archivo, as_attachment=True)

if __name__ == "__main__":
    app.run(port=5000)