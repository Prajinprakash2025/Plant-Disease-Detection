import argparse
from pathlib import Path

from config import RAW_DATA_DIR


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp"}


def count_images(folder: Path) -> int:
    return sum(1 for file_path in folder.rglob("*") if file_path.suffix.lower() in IMAGE_SUFFIXES)


def inspect_directory(dataset_root: Path):
    if not dataset_root.exists():
        raise SystemExit(f"Dataset path does not exist: {dataset_root}")

    split_dirs = [name for name in ("train", "val", "validation", "test") if (dataset_root / name).exists()]

    if split_dirs:
        print(f"Dataset root: {dataset_root}")
        print("Detected split folders:")
        for split_name in split_dirs:
            split_path = dataset_root / split_name
            print(f"\n[{split_name}]")
            for class_dir in sorted(path for path in split_path.iterdir() if path.is_dir()):
                print(f"  {class_dir.name}: {count_images(class_dir)} images")
    else:
        print(f"Dataset root: {dataset_root}")
        print("Detected class folders:")
        for class_dir in sorted(path for path in dataset_root.iterdir() if path.is_dir()):
            print(f"  {class_dir.name}: {count_images(class_dir)} images")


def main():
    parser = argparse.ArgumentParser(description="Inspect image dataset folders for model training.")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=RAW_DATA_DIR,
        help="Path to the dataset root.",
    )
    args = parser.parse_args()
    inspect_directory(args.dataset.resolve())


if __name__ == "__main__":
    main()
