import sys

import cv2


def import_status(module_name: str) -> str:
    try:
        __import__(module_name)
        return "OK"
    except ImportError:
        return "NO instalado"


def main() -> int:
    print(f"Version de Python: {sys.version}")
    print(f"Version de OpenCV: {cv2.__version__}")
    print(f"Ultralytics (YOLOv8): {import_status('ultralytics')}")
    print(f"EasyOCR: {import_status('easyocr')}")

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Error: No se pudo acceder a la camara en /dev/video0.")
        return 1

    ret, frame = cap.read()
    if ret:
        print(f"Camara funcional. Resolucion del frame: {frame.shape[1]} x {frame.shape[0]}")
    else:
        print("Camara abierta, pero sin lectura de frames.")
        cap.release()
        return 1

    cap.release()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
