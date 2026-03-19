import tensorflow as tf
import numpy as np
from PIL import Image
import json

MODEL_PATH = "ml_testing/trained_models/plant_disease_mobilenetv2.keras"
CLASSES_PATH = "ml_testing/trained_models/plant_disease_mobilenetv2_class_names.json"

# load model
model = tf.keras.models.load_model(MODEL_PATH)

# load class names
with open(CLASSES_PATH) as f:
    class_names = json.load(f)

# test image
image_path = "test_leaf1.JPG"

img = Image.open(image_path).resize((224, 224))
img = np.array(img) / 255.0
img = np.expand_dims(img, axis=0)

prediction = model.predict(img)

index = np.argmax(prediction)
print("Prediction:", class_names[index])