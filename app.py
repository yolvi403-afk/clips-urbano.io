import os, re, uuid, shutil, subprocess
from pathlib import Path
from typing import List
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from faster_whisper import WhisperModel

ROOT = Path(__file__).parent
WORK = ROOT / "work"
WORK.mkdir(exist_ok=True)
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "500"))

app = FastAPI(title="Clips Urbano API")
allowed = os.getenv("ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed if allowed != ["*"] else ["*"],
    allow_credentials=False, allow_methods=["*"], allow_headers=["*"]
)
app.mount("/media", StaticFiles(directory=WORK), name="media")

_model = None
def whisper():
    global _model
    if _model is None:
        # "small" ofrece mejor reconocimiento que "base", pero consume más RAM.
        _model = WhisperModel(os.getenv("WHISPER_MODEL", "small"),
                              device="cpu", compute_type="int8")
    return _model

def run(cmd):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode:
        raise RuntimeError(p.stderr[-2500:])
    return p.stdout

def stamp(seconds):
    ms = max(0, int(round(seconds * 1000)))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"

def srt_for_clip(segments, start, end):
    lines, n = [], 1
    for seg in segments:
        a, b = max(seg["start"], start), min(seg["end"], end)
        text = seg["text"].strip()
        if b <= a or not text:
            continue
        # Timestamps relativos al comienzo del clip
        lines += [str(n), f"{stamp(a-start)} --> {stamp(b-start)}", text, ""]
        n += 1
    return "\n".join(lines) if lines else ""

def probe_duration(path):
    out = run(["ffprobe","-v","error","-show_entries","format=duration",
               "-of","default=noprint_wrappers=1:nokey=1",str(path)])
    return float(out.strip())

def srt_escape(path):
    return str(path).replace("\\","/").replace(":","\\:").replace("'","\\'")

@app.get("/api/health")
def health():
    return {"ok": True, "service": "Clips Urbano"}

@app.post("/api/process")
async def process_video(
    video: UploadFile = File(...),
    clip_seconds: int = Form(30),
    clip_count: int = Form(5),
    topic: str = Form("")
):
    if not video.filename:
        raise HTTPException(400, "Elige un archivo de video.")
    ext = Path(video.filename).suffix.lower()
    if ext not in {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"}:
        raise HTTPException(400, "Formato no compatible. Usa MP4, MOV, MKV o WEBM.")
    if not 10 <= clip_seconds <= 180 or not 1 <= clip_count <= 10:
        raise HTTPException(400, "Duración o cantidad de clips fuera del límite.")
    job = uuid.uuid4().hex
    folder = WORK / job
    folder.mkdir(parents=True)
    source = folder / f"source{ext}"
    try:
        size = 0
        with source.open("wb") as f:
            while chunk := await video.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_MB * 1024 * 1024:
                    raise HTTPException(413, f"El archivo supera {MAX_UPLOAD_MB} MB.")
                f.write(chunk)

        duration = probe_duration(source)
        if duration < 10:
            raise HTTPException(400, "El video es demasiado corto.")
        audio = folder / "audio.wav"
        run(["ffmpeg","-y","-i",str(source),"-vn","-ac","1","-ar","16000",
             "-c:a","pcm_s16le",str(audio)])

        model = whisper()
        segments_iter, info = model.transcribe(str(audio), language="es",
                                                vad_filter=True, word_timestamps=False)
        transcript_segments = []
        full_text = []
        for seg in segments_iter:
            text = seg.text.strip()
            transcript_segments.append({"start":float(seg.start),"end":float(seg.end),"text":text})
            if text: full_text.append(text)

        if not transcript_segments:
            raise HTTPException(422, "No se detectó voz para crear subtítulos.")

        # Distribuye los clips por el video completo; todos llevan subtítulos sincronizados.
        usable = min(duration, clip_seconds * clip_count)
        if duration <= clip_seconds:
            starts = [0]
        else:
            max_start = max(0, duration - clip_seconds)
            starts = [round(i * max_start / max(1, clip_count-1), 2) for i in range(clip_count)]
        outputs = []
        for i, start in enumerate(starts):
            end = min(duration, start + clip_seconds)
            srt = folder / f"clip_{i+1:02}.srt"
            srt.write_text(srt_for_clip(transcript_segments, start, end), encoding="utf-8")
            mp4 = folder / f"clip_{i+1:02}.mp4"
            vf = f"subtitles='{srt_escape(srt)}':force_style='FontName=Arial,FontSize=18,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=1,Alignment=2,MarginV=35'"
            run(["ffmpeg","-y","-ss",str(start),"-i",str(source),"-t",str(end-start),
                 "-vf",vf,"-c:v","libx264","-preset","veryfast","-crf","23",
                 "-c:a","aac","-b:a","128k","-movflags","+faststart",str(mp4)])
            outputs.append({
                "filename":mp4.name,"subtitle_filename":srt.name,
                "video_url":f"/media/{job}/{mp4.name}",
                "subtitle_url":f"/media/{job}/{srt.name}",
                "start_label":f"{int(start//60):02}:{int(start%60):02}",
                "end_label":f"{int(end//60):02}:{int(end%60):02}"
            })

        transcript = " ".join(full_text)
        # Presenta una muestra real de la transcripción como análisis; no inventa un resumen.
        sample = transcript[:1200] + ("…" if len(transcript) > 1200 else "")
        analysis = ("Tema indicado: " + topic.strip() + "\n" if topic.strip() else "")
        analysis += "Transcripción detectada en español:\n" + (sample or "No se detectó texto.")
        return {"analysis":analysis, "clips":outputs}
    except HTTPException:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    except Exception as e:
        shutil.rmtree(folder, ignore_errors=True)
        raise HTTPException(500, f"Error procesando el video: {str(e)}")
    finally:
        await video.close()
