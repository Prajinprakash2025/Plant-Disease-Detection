import argparse
import json
from pathlib import Path

from config import (
    ARTIFACTS_DIR,
    BATCH_SIZE,
    EPOCHS,
    IMAGE_SIZE,
    MODEL_NAME,
    RAW_DATA_DIR,
    RANDOM_SEED,
    TRAINED_MODELS_DIR,
    VALIDATION_SPLIT,
    ensure_directories,
)

try:
    import tensorflow as tf
except ImportError as exc:
    raise SystemExit(
        "TensorFlow is not installed in this environment. "
        "Create a separate ML virtual environment and install "
        "ml_testing/requirements-train.txt first."
    ) from exc


def load_datasets(dataset_root: Path, image_size, batch_size, validation_split, seed):
    train_dir = dataset_root / "train"
    val_dir = dataset_root / "val"
    validation_dir = dataset_root / "validation"

    if train_dir.exists() and (val_dir.exists() or validation_dir.exists()):
        actual_val_dir = val_dir if val_dir.exists() else validation_dir
        train_ds = tf.keras.utils.image_dataset_from_directory(
            train_dir,
            image_size=image_size,
            batch_size=batch_size,
            seed=seed,
        )
        val_ds = tf.keras.utils.image_dataset_from_directory(
            actual_val_dir,
            image_size=image_size,
            batch_size=batch_size,
            seed=seed,
            shuffle=False,
        )
    else:
        train_ds = tf.keras.utils.image_dataset_from_directory(
            dataset_root,
            validation_split=validation_split,
            subset="training",
            seed=seed,
            image_size=image_size,
            batch_size=batch_size,
        )
        val_ds = tf.keras.utils.image_dataset_from_directory(
            dataset_root,
            validation_split=validation_split,
            subset="validation",
            seed=seed,
            image_size=image_size,
            batch_size=batch_size,
        )

    class_names = train_ds.class_names
    autotune = tf.data.AUTOTUNE
    train_ds = train_ds.prefetch(buffer_size=autotune)
    val_ds = val_ds.prefetch(buffer_size=autotune)
    return train_ds, val_ds, class_names


def build_model(num_classes: int, image_size):
    data_augmentation = tf.keras.Sequential(
        [
            tf.keras.layers.RandomFlip("horizontal"),
            tf.keras.layers.RandomRotation(0.1),
            tf.keras.layers.RandomZoom(0.1),
        ],
        name="augmentation",
    )

    base_model = tf.keras.applications.MobileNetV2(
        input_shape=image_size + (3,),
        include_top=False,
        weights="imagenet",
    )
    base_model.trainable = False

    inputs = tf.keras.Input(shape=image_size + (3,))
    x = data_augmentation(inputs)
    x = tf.keras.applications.mobilenet_v2.preprocess_input(x)
    x = base_model(x, training=False)
    x = tf.keras.layers.GlobalAveragePooling2D()(x)
    x = tf.keras.layers.Dropout(0.2)(x)
    outputs = tf.keras.layers.Dense(num_classes, activation="softmax")(x)

    model = tf.keras.Model(inputs, outputs, name=MODEL_NAME)
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=1e-4),
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"],
    )
    return model


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file_handle:
        json.dump(data, file_handle, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Train a starter plant disease classification model.")
    parser.add_argument("--dataset", type=Path, default=RAW_DATA_DIR, help="Dataset root folder.")
    parser.add_argument("--epochs", type=int, default=EPOCHS, help="Training epochs.")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE, help="Batch size.")
    parser.add_argument("--img-size", type=int, default=IMAGE_SIZE[0], help="Square image size in pixels.")
    parser.add_argument("--validation-split", type=float, default=VALIDATION_SPLIT, help="Validation split for single-root datasets.")
    args = parser.parse_args()

    ensure_directories()
    dataset_root = args.dataset.resolve()
    if not dataset_root.exists():
        raise SystemExit(f"Dataset path does not exist: {dataset_root}")

    image_size = (args.img_size, args.img_size)
    train_ds, val_ds, class_names = load_datasets(
        dataset_root=dataset_root,
        image_size=image_size,
        batch_size=args.batch_size,
        validation_split=args.validation_split,
        seed=RANDOM_SEED,
    )

    model = build_model(num_classes=len(class_names), image_size=image_size)

    callbacks = [
        tf.keras.callbacks.EarlyStopping(
            monitor="val_loss",
            patience=4,
            restore_best_weights=True,
        )
    ]

    history = model.fit(
        train_ds,
        validation_data=val_ds,
        epochs=args.epochs,
        callbacks=callbacks,
    )

    model_path = TRAINED_MODELS_DIR / f"{MODEL_NAME}.keras"
    class_names_path = TRAINED_MODELS_DIR / f"{MODEL_NAME}_class_names.json"
    history_path = ARTIFACTS_DIR / f"{MODEL_NAME}_history.json"
    run_path = ARTIFACTS_DIR / f"{MODEL_NAME}_run.json"

    model.save(model_path)
    save_json(class_names_path, class_names)
    save_json(history_path, history.history)
    save_json(
        run_path,
        {
            "dataset_root": str(dataset_root),
            "epochs": args.epochs,
            "batch_size": args.batch_size,
            "image_size": list(image_size),
            "validation_split": args.validation_split,
            "class_names": class_names,
            "model_path": str(model_path),
        },
    )

    print(f"Training complete. Model saved to: {model_path}")


if __name__ == "__main__":
    main()
