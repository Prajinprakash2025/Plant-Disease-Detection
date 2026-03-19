import argparse
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import numpy as np
import tensorflow as tf
from PIL import Image, UnidentifiedImageError


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--classes", required=True)
    parser.add_argument("--width", type=int, default=224)
    parser.add_argument("--height", type=int, default=224)
    return parser.parse_args()


def load_image(image_path, width, height):
    try:
        image = Image.open(image_path).convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValueError("Please upload a valid plant leaf image.") from exc

    image = image.resize((width, height))
    image_array = np.asarray(image, dtype=np.float32)  # keep 0-255, model has preprocess_input built-in
    return np.expand_dims(image_array, axis=0)


def main():
    args = parse_args()

    model_path = Path(args.model)
    class_names_path = Path(args.classes)
    image_path = Path(args.image)

    if not model_path.exists():
        print(f"Model file not found: {model_path}", file=sys.stderr)
        return 1

    if not class_names_path.exists():
        print(f"Class names file not found: {class_names_path}", file=sys.stderr)
        return 1

    if not image_path.exists():
        print(f"Image file not found: {image_path}", file=sys.stderr)
        return 1

    try:
        model = tf.keras.models.load_model(model_path)
        with class_names_path.open(encoding="utf-8") as class_file:
            class_names = json.load(class_file)

        processed_image = load_image(image_path, args.width, args.height)
        probabilities = model.predict(processed_image, verbose=0)[0]

        predicted_index = int(np.argmax(probabilities))
        confidence = float(np.max(probabilities))

        print(
            json.dumps(
                {
                    "disease": str(class_names[predicted_index]),
                    "confidence": confidence,
                }
            )
        )
        return 0
    except Exception as exc:
        print(f"{exc.__class__.__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
