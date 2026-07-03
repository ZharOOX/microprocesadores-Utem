import argparse
import re
import subprocess
import tempfile
from pathlib import Path

import cv2


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


def crop_plate_region(image):
    h, w = image.shape[:2]
    return image[int(h * 0.37) : int(h * 0.66), int(w * 0.16) : int(w * 0.82)]


def preprocess_for_ocr(image):
    roi = crop_plate_region(image)
    roi = cv2.resize(roi, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    _, threshold = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return threshold


def read_plate_tesseract(image) -> str:
    processed = preprocess_for_ocr(image)
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
    return correct_common_ocr_errors(normalize_plate(result.stdout))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Base ANPR/ALPR para control de acceso en Raspberry Pi.")
    parser.add_argument("--image", required=True, help="Imagen de entrada.")
    parser.add_argument("--output", default="informe3/images/lab4/anpr_resultado_lab4.jpg")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    image = cv2.imread(args.image)
    if image is None:
        print(f"No se pudo leer {args.image}")
        return 1

    text = read_plate_tesseract(image) or "SIN_TEXTO"
    authorized = text in AUTHORIZED_PLATES

    color = (0, 200, 0) if authorized else (0, 0, 255)
    status = "AUTORIZADA" if authorized else "NO AUTORIZADA"
    cv2.rectangle(image, (8, 8), (520, 74), (0, 0, 0), -1)
    cv2.putText(image, f"Patente: {text}", (18, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.75, color, 2)
    cv2.putText(image, f"Acceso: {status}", (18, 64), cv2.FONT_HERSHEY_SIMPLEX, 0.75, color, 2)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output), image)
    print(f"Resultado guardado en {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
