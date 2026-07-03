import argparse
import re
import time
from pathlib import Path

import cv2


AUTHORIZED_PLATES = {"ABCD12", "UTEM24", "LAB404"}


def normalize_plate(text: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", text.upper())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Visualizador ANPR en vivo para Laboratorio 4.")
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--interval", type=float, default=2.5, help="Segundos entre lecturas OCR.")
    parser.add_argument("--output", default="informe3/images/lab4/anpr_camara_real.jpg")
    parser.add_argument("--plate", default="UTEM24", help="Patente esperada para validacion.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    import easyocr

    reader = easyocr.Reader(["en"], gpu=False)
    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        print(f"No se pudo abrir la camara {args.camera}.")
        return 1

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    last_ocr = 0.0
    last_text = "SIN LECTURA"
    status = "MOSTRAR PATENTE EN EL RECUADRO"
    status_color = (0, 255, 255)
    best_frame = None

    while True:
        ok, frame = cap.read()
        if not ok:
            continue

        h, w = frame.shape[:2]
        x1, y1 = int(w * 0.12), int(h * 0.36)
        x2, y2 = int(w * 0.88), int(h * 0.66)
        roi = frame[y1:y2, x1:x2]

        now = time.monotonic()
        if now - last_ocr >= args.interval:
            last_ocr = now
            results = reader.readtext(roi)
            candidates = [normalize_plate(item[1]) for item in results]
            candidates = [candidate for candidate in candidates if len(candidate) >= 4]
            last_text = candidates[0] if candidates else "SIN_TEXTO"

            if last_text in AUTHORIZED_PLATES or last_text == normalize_plate(args.plate):
                status = "ACCESO AUTORIZADO"
                status_color = (0, 220, 0)
                best_frame = frame.copy()
                cv2.imwrite(str(output), best_frame)
                print(f"Patente autorizada detectada: {last_text}. Evidencia guardada en {output}")
            else:
                status = "NO AUTORIZADA / NO DETECTADA"
                status_color = (0, 0, 255)

        cv2.rectangle(frame, (x1, y1), (x2, y2), status_color, 2)
        cv2.rectangle(frame, (0, 0), (w, 95), (0, 0, 0), -1)
        cv2.putText(frame, f"OCR: {last_text}", (16, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.8, status_color, 2)
        cv2.putText(frame, f"Estado: {status}", (16, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.75, status_color, 2)
        cv2.putText(frame, "Presiona s para guardar, q para salir", (16, h - 18), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)

        cv2.imshow("Laboratorio 4 - ANPR en vivo", frame)
        key = cv2.waitKey(1) & 0xFF
        if key == ord("s"):
            cv2.imwrite(str(output), frame)
            print(f"Evidencia manual guardada en {output}")
        elif key == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
