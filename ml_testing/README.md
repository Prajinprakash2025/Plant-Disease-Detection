# ML Testing Workspace

This folder is separate from the Django apps so you can train and test models
without mixing ML experiments into the web code.

## Folder layout

- `data/raw/`
  Put your downloaded dataset here.
- `data/prepared/`
  Optional space for cleaned or resized datasets.
- `trained_models/`
  Saved `.keras` models and class label files.
- `artifacts/`
  Training history and run metadata.
- `logs/`
  Optional TensorBoard or custom log output.

## Recommended workflow

1. Create a separate virtual environment for model training.
   Deep-learning libraries can have different system and Python requirements
   than the Django application.
2. Install the ML dependencies from `ml_testing/requirements-train.txt`.
3. Move your dataset into `ml_testing/data/raw/`.
4. Run:

```powershell
python ml_testing\inspect_dataset.py
python ml_testing\train.py --dataset ml_testing\data\raw --epochs 10
```

## Supported dataset structures

You can use either of these layouts:

Single root with class folders:

```text
ml_testing/data/raw/
    Tomato___Early_blight/
    Tomato___Late_blight/
    Tomato___healthy/
```

Or explicit train/validation split:

```text
ml_testing/data/raw/
    train/
        Tomato___Early_blight/
        Tomato___Late_blight/
    val/
        Tomato___Early_blight/
        Tomato___Late_blight/
```

## Output files

After training, the script saves:

- `trained_models/plant_disease_mobilenetv2.keras`
- `trained_models/plant_disease_mobilenetv2_class_names.json`
- `artifacts/plant_disease_mobilenetv2_history.json`
- `artifacts/plant_disease_mobilenetv2_run.json`
