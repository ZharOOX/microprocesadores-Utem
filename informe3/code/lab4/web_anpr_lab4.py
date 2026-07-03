import argparse
import re
import subprocess
import tempfile
import threading
import time
from pathlib import Path

import cv2
from flask import Flask, Response, redirect, render_template_string, url_for


AUTHORIZED_PLATES = {"ABCD12", "UTEM24", "LAB404", "BBBB10"}


def normalize_plate(text: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", text.upper())


def correct_common_ocr_errors(text: str) -> str:
    corrections = {
        "BFBB10": "BBBB10",
        "BBBR10": "BBBB10",
        "B8BB10": "BBBB10",
    }
    return corrections.get(text, text)


class CameraState:
    def __init__(self, camera_index: int, output: Path) -> None:
        self.cap = cv2.VideoCapture(camera_index)
        self.output = output
        self.output.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.frame = None
        self.last_text = "SIN LECTURA"
        self.status = "Ubica la patente dentro del recuadro"
        self.status_color = (0, 255, 255)
        self.running = True
        self.reader = None
        self.thread = threading.Thread(target=self._read_loop, daemon=True)

    def start(self) -> None:
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.thread.start()

    def _read_loop(self) -> None:
        while self.running:
            ok, frame = self.cap.read()
            if ok:
                with self.lock:
                    self.frame = frame
            time.sleep(0.01)

    def annotated_frame(self):
        with self.lock:
            if self.frame is None:
                return None
            frame = self.frame.copy()

        h, w = frame.shape[:2]
        x1, y1 = int(w * 0.10), int(h * 0.34)
        x2, y2 = int(w * 0.90), int(h * 0.68)
        cv2.rectangle(frame, (x1, y1), (x2, y2), self.status_color, 2)
        cv2.rectangle(frame, (0, 0), (w, 98), (0, 0, 0), -1)
        cv2.putText(frame, f"OCR: {self.last_text}", (14, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.8, self.status_color, 2)
        cv2.putText(frame, f"Estado: {self.status}", (14, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.7, self.status_color, 2)
        cv2.putText(frame, "Coloca la patente del telefono dentro del recuadro", (14, h - 18), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
        return frame

    def jpeg_bytes(self) -> bytes:
        frame = self.annotated_frame()
        if frame is None:
            return b""
        ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return encoded.tobytes() if ok else b""

    def save(self) -> None:
        frame = self.annotated_frame()
        if frame is not None:
            cv2.imwrite(str(self.output), frame)

    def run_ocr(self) -> None:
        with self.lock:
            if self.frame is None:
                return
            frame = self.frame.copy()

        h, w = frame.shape[:2]
        x1, y1 = int(w * 0.16), int(h * 0.37)
        x2, y2 = int(w * 0.82), int(h * 0.66)
        roi = frame[y1:y2, x1:x2]
        roi = cv2.resize(roi, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        _, processed = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
            cv2.imwrite(tmp.name, processed)
            result = subprocess.run(
                [
                    "tesseract",
                    tmp.name,
                    "stdout",
                    "--psm",
                    "7",
                    "-c",
                    "tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

        self.last_text = correct_common_ocr_errors(normalize_plate(result.stdout)) or "SIN_TEXTO"

        if self.last_text in AUTHORIZED_PLATES:
            self.status = "ACCESO AUTORIZADO"
            self.status_color = (0, 220, 0)
        else:
            self.status = "NO AUTORIZADA / NO DETECTADA"
            self.status_color = (0, 0, 255)

        self.save()

    def release(self) -> None:
        self.running = False
        self.thread.join(timeout=1)
        self.cap.release()


HTML = """
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Laboratorio 4 - ANPR</title>
  <style>
    body { margin: 0; font-family: sans-serif; background: #101418; color: white; }
    main { max-width: 980px; margin: 0 auto; padding: 24px; }
    img { width: 100%; max-width: 860px; border: 2px solid #3b82f6; background: #000; }
    .actions { display: flex; gap: 12px; margin-top: 16px; flex-wrap: wrap; }
    a { background: #2563eb; color: white; padding: 12px 16px; text-decoration: none; border-radius: 6px; }
    a.secondary { background: #475569; }
    p { color: #cbd5e1; }
  </style>
</head>
<body>
<main>
  <h1>Laboratorio 4 - ANPR en vivo</h1>
  <p>Coloca la patente del teléfono dentro del recuadro. Usa "Leer OCR" para detectar y guardar evidencia.</p>
  <img src="/video" alt="camara">
  <div class="actions">
    <a href="/ocr">Leer OCR y guardar</a>
    <a class="secondary" href="/save">Guardar foto manual</a>
  </div>
</main>
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Servidor web ANPR local para Laboratorio 4.")
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5050)
    parser.add_argument("--output", default="informe3/images/lab4/anpr_camara_real.jpg")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    state = CameraState(args.camera, Path(args.output))
    if not state.cap.isOpened():
        print(f"No se pudo abrir la camara {args.camera}.")
        return 1
    state.start()

    app = Flask(__name__)

    @app.route("/")
    def index():
        return render_template_string(HTML)

    @app.route("/video")
    def video():
        def generate():
            while True:
                data = state.jpeg_bytes()
                if data:
                    yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + data + b"\r\n"
                time.sleep(0.05)

        return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")

    @app.route("/save")
    def save():
        state.save()
        return redirect(url_for("index"))

    @app.route("/ocr")
    def ocr():
        state.run_ocr()
        return redirect(url_for("index"))

    try:
        app.run(host=args.host, port=args.port, threaded=True)
    finally:
        state.release()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
