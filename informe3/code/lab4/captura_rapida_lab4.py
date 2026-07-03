import argparse
from pathlib import Path

import cv2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Captura rapida desde camara conectada a Raspberry Pi.")
    parser.add_argument("--camera", type=int, default=0, help="Indice de camara OpenCV.")
    parser.add_argument("--output", default="prueba_lab4.jpg", help="Archivo de salida.")
    parser.add_argument("--width", type=int, default=640, help="Ancho solicitado.")
    parser.add_argument("--height", type=int, default=480, help="Alto solicitado.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        print(f"No se pudo abrir la camara {args.camera}.")
        return 1

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)

    frame = None
    for _ in range(12):
        ret, frame = cap.read()
        if not ret:
            frame = None

    cap.release()

    if frame is None:
        print("No se pudo capturar frame.")
        return 1

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output), frame)
    print(f"Imagen guardada en {output} ({frame.shape[1]} x {frame.shape[0]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
