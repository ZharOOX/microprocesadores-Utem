import argparse
import os
import threading
import time
from dataclasses import dataclass

import cv2
import numpy as np


DEFAULT_URL = os.environ.get("ESP32_CAM_URL", "http://172.20.10.12:81/stream")
MODEL_PATH = os.environ.get("YOLO_MODEL", "yolov8n.onnx")
INPUT_SIZE = 640
IOU_THRESHOLD = 0.45
TRACK_MAX_DISTANCE = 90
TRACK_TTL = 12


@dataclass
class Track:
    centroid: tuple[int, int]
    last_side: int
    missed: int = 0


@dataclass
class Detection:
    cls_id: int
    confidence: float
    box: tuple[int, int, int, int]


class LatestFrameStream:
    def __init__(self, url: str) -> None:
        self.url = url
        self.cap = open_stream(url)
        self.frame = None
        self.ok = self.cap.isOpened()
        self.stopped = False
        self.lock = threading.Lock()
        self.thread = threading.Thread(target=self._reader, daemon=True)

    def start(self) -> "LatestFrameStream":
        self.thread.start()
        return self

    def _reader(self) -> None:
        while not self.stopped:
            if not self.cap.isOpened():
                time.sleep(1)
                self.cap.release()
                self.cap = open_stream(self.url)
                continue

            ret, frame = self.cap.read()
            if not ret:
                self.ok = False
                self.cap.release()
                time.sleep(0.5)
                self.cap = open_stream(self.url)
                continue

            with self.lock:
                self.frame = frame
                self.ok = True

    def read(self):
        with self.lock:
            if self.frame is None:
                return False, None
            return True, self.frame.copy()

    def release(self) -> None:
        self.stopped = True
        self.thread.join(timeout=2)
        self.cap.release()


class YoloOnnxDetector:
    def __init__(self, model_path: str, confidence: float) -> None:
        self.net = cv2.dnn.readNetFromONNX(model_path)
        self.confidence = confidence

    def detect(self, frame) -> list[Detection]:
        height, width = frame.shape[:2]
        blob = cv2.dnn.blobFromImage(
            frame,
            scalefactor=1 / 255.0,
            size=(INPUT_SIZE, INPUT_SIZE),
            mean=(0, 0, 0),
            swapRB=True,
            crop=False,
        )
        self.net.setInput(blob)
        output = self.net.forward()[0].T

        boxes: list[list[int]] = []
        scores: list[float] = []
        class_ids: list[int] = []
        x_scale = width / INPUT_SIZE
        y_scale = height / INPUT_SIZE

        for row in output:
            class_scores = row[4:]
            cls_id = int(np.argmax(class_scores))
            confidence = float(class_scores[cls_id])
            if cls_id not in (0, 2) or confidence < self.confidence:
                continue

            cx, cy, w, h = row[:4]
            x1 = int((cx - w / 2) * x_scale)
            y1 = int((cy - h / 2) * y_scale)
            bw = int(w * x_scale)
            bh = int(h * y_scale)

            boxes.append([x1, y1, bw, bh])
            scores.append(confidence)
            class_ids.append(cls_id)

        keep = cv2.dnn.NMSBoxes(boxes, scores, self.confidence, IOU_THRESHOLD)
        if len(keep) == 0:
            return []

        detections: list[Detection] = []
        for idx in np.array(keep).flatten():
            x, y, w, h = boxes[int(idx)]
            x1 = max(0, x)
            y1 = max(0, y)
            x2 = min(width - 1, x + w)
            y2 = min(height - 1, y + h)
            detections.append(Detection(class_ids[int(idx)], scores[int(idx)], (x1, y1, x2, y2)))

        return detections


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Servidor IA Raspberry Pi para ESP32-CAM LAB3.")
    parser.add_argument("--url", default=DEFAULT_URL, help="URL MJPEG de la ESP32-CAM.")
    parser.add_argument("--model", default=MODEL_PATH, help="Ruta del modelo YOLOv8 ONNX.")
    parser.add_argument("--confidence", type=float, default=0.35, help="Confianza minima.")
    parser.add_argument("--line-y", type=int, default=120, help="Linea virtual horizontal para aforo.")
    parser.add_argument("--infer-every", type=int, default=2, help="Ejecuta YOLO cada N frames.")
    parser.add_argument("--headless", action="store_true", help="Ejecuta sin ventana grafica.")
    return parser.parse_args()


def distance_sq(a: tuple[int, int], b: tuple[int, int]) -> int:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


def update_tracks(
    tracks: dict[int, Track],
    people: list[tuple[int, int]],
    line_y: int,
    next_id: int,
    occupancy: int,
) -> tuple[int, int]:
    assigned_tracks: set[int] = set()

    for centroid in people:
        best_id = None
        best_distance = TRACK_MAX_DISTANCE**2

        for track_id, track in tracks.items():
            if track_id in assigned_tracks:
                continue
            dist = distance_sq(centroid, track.centroid)
            if dist < best_distance:
                best_distance = dist
                best_id = track_id

        current_side = 1 if centroid[1] >= line_y else -1

        if best_id is None:
            tracks[next_id] = Track(centroid=centroid, last_side=current_side)
            assigned_tracks.add(next_id)
            next_id += 1
            continue

        track = tracks[best_id]
        if track.last_side != current_side:
            occupancy += 1 if current_side == 1 else -1
            occupancy = max(0, occupancy)
        track.centroid = centroid
        track.last_side = current_side
        track.missed = 0
        assigned_tracks.add(best_id)

    for track_id in list(tracks):
        if track_id not in assigned_tracks:
            tracks[track_id].missed += 1
            if tracks[track_id].missed > TRACK_TTL:
                del tracks[track_id]

    return next_id, occupancy


def draw_label(frame, text: str, x: int, y: int, color: tuple[int, int, int]) -> None:
    y = max(20, y)
    cv2.putText(frame, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)


def open_stream(url: str) -> cv2.VideoCapture:
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return cap


def main() -> int:
    args = parse_args()
    args.infer_every = max(1, args.infer_every)
    print("Cargando modelo YOLOv8 ONNX...")
    detector = YoloOnnxDetector(args.model, args.confidence)

    print(f"Conectando al stream: {args.url}")
    stream = LatestFrameStream(args.url)
    if not stream.cap.isOpened():
        print(f"Error al conectar con {args.url}")
        return 1
    stream.start()

    print("Conexion establecida. Presiona 'q' para salir.")
    tracks: dict[int, Track] = {}
    next_id = 1
    occupancy = 0
    last_frame_time = time.monotonic()
    frame_count = 0
    cached_detections: list[Detection] = []

    while True:
        ret, frame = stream.read()
        if not ret:
            time.sleep(0.02)
            continue

        people_centroids: list[tuple[int, int]] = []
        frame_count += 1
        if frame_count % args.infer_every == 1 or not cached_detections:
            cached_detections = detector.detect(frame)

        for detection in cached_detections:
            cls_id = detection.cls_id
            conf = detection.confidence
            x1, y1, x2, y2 = detection.box
            centroid = ((x1 + x2) // 2, (y1 + y2) // 2)

            if cls_id == 0:
                color = (0, 255, 0)
                label = f"Persona {conf:.2f}"
                people_centroids.append(centroid)
                cv2.circle(frame, centroid, 4, color, -1)
            else:
                color = (255, 180, 0)
                label = f"Auto {conf:.2f}"

            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            draw_label(frame, label, x1, y1 - 8, color)

        next_id, occupancy = update_tracks(tracks, people_centroids, args.line_y, next_id, occupancy)

        now = time.monotonic()
        fps = 1.0 / max(now - last_frame_time, 1e-6)
        last_frame_time = now

        cv2.line(frame, (0, args.line_y), (frame.shape[1], args.line_y), (0, 255, 255), 2)
        draw_label(frame, f"Aforo: {occupancy}", 12, 28, (0, 255, 255))
        draw_label(frame, f"FPS: {fps:.1f}", 12, 55, (255, 255, 255))

        if not args.headless:
            cv2.imshow("Servidor Central - Monitoreo IoT", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    stream.release()
    cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
