from pathlib import Path


ML_ROOT = Path(__file__).resolve().parent
DATA_ROOT = ML_ROOT / "data"
RAW_DATA_DIR = DATA_ROOT / "raw"
PREPARED_DATA_DIR = DATA_ROOT / "prepared"
TRAINED_MODELS_DIR = ML_ROOT / "trained_models"
ARTIFACTS_DIR = ML_ROOT / "artifacts"
LOGS_DIR = ML_ROOT / "logs"

IMAGE_SIZE = (224, 224)
BATCH_SIZE = 32
EPOCHS = 10
VALIDATION_SPLIT = 0.2
RANDOM_SEED = 42
MODEL_NAME = "plant_disease_mobilenetv2"


def ensure_directories():
    for directory in (
        DATA_ROOT,
        RAW_DATA_DIR,
        PREPARED_DATA_DIR,
        TRAINED_MODELS_DIR,
        ARTIFACTS_DIR,
        LOGS_DIR,
    ):
        directory.mkdir(parents=True, exist_ok=True)
