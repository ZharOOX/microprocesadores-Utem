import argparse
import time
from dataclasses import dataclass

import cv2
import numpy as np


INPUT_SIZE = 640
IOU_THRESHOLD = 0.45


@dataclass
class Detection:
    cls_id: int
    confidence: float
    box: tuple[int, int, int, int]


class YoloOnnxDetector:
    def __init__(self, model_path: str, confidence: float) -> None:
        self.net = cv2.dnn.readNetFromONNX(model_path)
        self.confidence = confidence

    def detect(self, frame) -> list[Detection]:
        height, width = frame.shape[:2]
        blob = cv2.dnn.blobFromImage(frame, 1 / 255.0, (INPUT_SIZE, INPUT_SIZE), swapRB=True, crop=False)
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
            boxes.append([x1, y1, int(w * x_scale), int(h * y_scale)])
            scores.append(confidence)
            class_ids.append(cls_id)

        keep = cv2.dnn.NMSBoxes(boxes, scores, self.confidence, IOU_THRESHOLD)
        if len(keep) == 0:
            return []

        detections: list[Detection] = []
        for idx in np.array(keep).flatten():
            x, y, w, h = boxes[int(idx)]
            detections.append(
                Detection(
                    class_ids[int(idx)],
                    scores[int(idx)],
                    (max(0, x), max(0, y), min(width - 1, x + w), min(height - 1, y + h)),
                )
            )
        return detections


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deteccion local en Raspberry Pi para laboratorio 4.")
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--model", default="yolov8n.onnx")
    parser.add_argument("--confidence", type=float, default=0.35)
    parser.add_argument("--infer-every", type=int, default=4)
    parser.add_argument("--output", default="informe3/images/lab4/deteccion_edge_lab4.jpg")
    parser.add_argument("--seconds", type=float, default=10.0)
    parser.add_argument("--headless", action="store_true")
    return parser.parse_args()


def draw_detection(frame, detection: Detection) -> None:
    x1, y1, x2, y2 = detection.box
    if detection.cls_id == 0:
        color = (0, 255, 0)
        label = f"Persona {detection.confidence:.2f}"
    else:
        color = (255, 180, 0)
        label = f"Vehiculo {detection.confidence:.2f}"
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
    cv2.putText(frame, label, (x1, max(20, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)


def main() -> int:
    args = parse_args()
    args.infer_every = max(1, args.infer_every)
    detector = YoloOnnxDetector(args.model, args.confidence)
    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        print(f"No se pudo abrir la camara {args.camera}.")
        return 1

    frame_count = 0
    detections: list[Detection] = []
    last_saved = None
    start = time.monotonic()

    while time.monotonic() - start < args.seconds:
        ok, frame = cap.read()
        if not ok:
            continue

        frame_count += 1
        if frame_count % args.infer_every == 1:
            detections = detector.detect(frame)

        for detection in detections:
            draw_detection(frame, detection)

        fps = frame_count / max(time.monotonic() - start, 1e-6)
        cv2.putText(frame, f"FPS camara: {fps:.1f}", (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        last_saved = frame

        if not args.headless:
            cv2.imshow("Laboratorio 4 - Edge Raspberry", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    cap.release()
    cv2.destroyAllWindows()

    if last_saved is not None:
        cv2.imwrite(args.output, last_saved)
        print(f"Evidencia guardada en {args.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
