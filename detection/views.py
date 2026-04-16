import json
import mimetypes
import os
import re
import subprocess
import threading
from collections import Counter
from pathlib import Path

import numpy as np
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from PIL import Image, UnidentifiedImageError

from account.utils import get_leaf_quota_summary

from .forms import DiagnosisForm, LeafDiagnosisForm
from .models import Diagnosis, Disease, LeafDiagnosis


MODEL = None
CLASS_NAMES = None
_MODEL_LOCK = threading.Lock()
SUPPORTED_TRANSLATION_LANGUAGES = {
    "en": "English",
    "ml": "Malayalam",
    "hi": "Hindi",
    "ta": "Tamil",
    "te": "Telugu",
    "kn": "Kannada",
    "ar": "Arabic",
}

LOCAL_UI_DICTIONARY = {
    "ml": {
        "result_labels": {
            "plant": "ചെടി",
            "disease": "രോഗം",
            "confidence": "ഉറപ്പ്",
            "severity": "തീവ്രത",
            "source": "ഉറവിടം",
        },
        "treatment_title": "ചികിത്സാ പദ്ധതി",
        "result_values": {
            "Healthy": "ആരോഗ്യമുള്ളത്",
            "Moderate": "മിതമായ",
            "High": "കൂടുതൽ",
            "None": "ഇല്ല",
        },
        "kind_labels": {
            "Plant:": "ചെടി:",
            "Disease:": "രോഗം:",
            "Severity:": "തീവ്രത:",
            "Symptoms:": "ലക്ഷണങ്ങൾ:",
            "Possible Causes:": "സാധ്യമായ കാരണങ്ങൾ:",
            "Treatment:": "ചികിത്സാ രീതികൾ:",
            "Prevention:": "പ്രതിരോധ മാർഗങ്ങൾ:",
        }
    }
}


def _get_model_path():
    configured_path = getattr(settings, "PLANT_DISEASE_MODEL_PATH", "")
    if configured_path:
        return Path(configured_path)

    default_h5 = Path(settings.BASE_DIR) / "model.h5"
    default_keras = (
        Path(settings.BASE_DIR)
        / "ml_testing"
        / "trained_models"
        / "plant_disease_mobilenetv2.keras"
    )

    if default_h5.exists():
        return default_h5
    return default_keras


def _get_class_names_path():
    configured_path = getattr(settings, "PLANT_DISEASE_CLASS_NAMES_PATH", "")
    if configured_path:
        return Path(configured_path)

    return (
        Path(settings.BASE_DIR)
        / "ml_testing"
        / "trained_models"
        / "plant_disease_mobilenetv2_class_names.json"
    )


def _get_ml_runtime_python():
    configured_path = getattr(settings, "ML_RUNTIME_PYTHON", "")
    if configured_path:
        return Path(configured_path)

    scripts_dir = "Scripts" if os.name == "nt" else "bin"
    executable = "python.exe" if os.name == "nt" else "python"
    return Path(settings.BASE_DIR) / "ml_venv" / scripts_dir / executable


def _get_ml_runtime_predict_script():
    configured_path = getattr(settings, "ML_RUNTIME_PREDICT_SCRIPT", "")
    if configured_path:
        return Path(configured_path)

    return Path(settings.BASE_DIR) / "ml_testing" / "predict_image.py"


def _get_image_size():
    configured_size = getattr(settings, "PLANT_DISEASE_IMAGE_SIZE", (224, 224))
    return tuple(configured_size)


def _format_disease_name(label):
    cleaned = label.replace("___", " ").replace("__", " ").replace("_", " ")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _clean_prediction_text(value, fallback="Unknown"):
    normalized = str(value or "").strip()
    normalized = normalized.strip(" .:;,'\"`")
    normalized = re.sub(r"^[\-\*\s]+", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized or fallback


def _extract_json_fragment(text):
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return ""
    return text[start : end + 1]


def _normalize_gemini_prediction(raw_response):
    if not raw_response:
        raise RuntimeError("Gemini returned an empty response.")

    payload = None
    json_fragment = _extract_json_fragment(raw_response)
    if json_fragment:
        try:
            payload = json.loads(json_fragment)
        except json.JSONDecodeError:
            payload = None

    plant_name = "Unknown"
    disease_name = "Uncertain"
    status = ""

    if isinstance(payload, dict):
        plant_name = payload.get("plant_name") or payload.get("plant") or payload.get("crop") or plant_name
        disease_name = payload.get("disease_name") or payload.get("disease") or payload.get("result") or disease_name
        status = str(payload.get("status") or "").strip().lower()
    else:
        plant_match = re.search(r"plant(?:_name)?\s*:\s*(.+)", raw_response, flags=re.IGNORECASE)
        disease_match = re.search(r"disease(?:_name)?\s*:\s*(.+)", raw_response, flags=re.IGNORECASE)
        if plant_match:
            plant_name = plant_match.group(1)
        if disease_match:
            disease_name = disease_match.group(1)
        elif not plant_match:
            disease_name = raw_response

    plant_name = _clean_prediction_text(plant_name, fallback="Unknown")
    disease_name = _clean_prediction_text(disease_name, fallback="Uncertain")

    if disease_name.lower() in {"healthy leaf", "no visible disease", "no disease"}:
        disease_name = "Healthy"
    if status == "healthy":
        disease_name = "Healthy"

    if plant_name.lower() in {"uncertain", "unknown plant", "not sure"}:
        plant_name = "Unknown"

    if status == "uncertain" or disease_name.lower() in {"uncertain", "unknown", "not sure"}:
        raise RuntimeError("Gemini could not confidently identify the disease from this image.")

    return {
        "plant_name": plant_name,
        "disease": disease_name,
    }


def _parse_local_model_label(raw_label):
    label = str(raw_label or "").strip()
    if "___" in label:
        plant_raw, disease_raw = label.split("___", 1)
    elif "_" in label:
        plant_raw, disease_raw = label.split("_", 1)
    else:
        return {"plant_name": "Unknown", "disease": _format_disease_name(label) or "Unknown"}

    plant_name = _format_disease_name(plant_raw) or "Unknown"
    disease_name = _format_disease_name(disease_raw) or "Unknown"

    plant_prefix = f"{plant_name} "
    if disease_name.lower().startswith(plant_prefix.lower()):
        disease_name = disease_name[len(plant_prefix):].strip()

    if disease_name.lower() == "healthy":
        disease_name = "Healthy"

    return {
        "plant_name": plant_name,
        "disease": disease_name or "Unknown",
    }


def _build_local_prediction(raw_label, confidence):
    parsed_prediction = _parse_local_model_label(raw_label)
    return {
        "plant_name": parsed_prediction["plant_name"],
        "disease": parsed_prediction["disease"],
        "confidence": round(confidence * 100, 2) if confidence is not None else None,
        "source": "local_model",
    }


def _lookup_disease_record(disease_name, plant_name=None):
    if not disease_name:
        return None

    queryset = Disease.objects.all()
    if plant_name and plant_name.lower() != "unknown":
        queryset = queryset.filter(crop__name__iexact=plant_name)

    return queryset.select_related("crop").filter(name__iexact=disease_name).first()


def _is_healthy_prediction(disease_name):
    return "healthy" in (disease_name or "").lower()


def _split_guidance_points(text):
    if not text:
        return []

    segments = re.split(r"[\r\n;]+", text)
    points = [segment.strip(" -•\t") for segment in segments if segment.strip()]
    return points or [text.strip()]


def _result_session_key(scan_id):
    return f"scan_result_{scan_id}"


def _format_treatment_lines(text):
    formatted_lines = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if line.lower().startswith("plant:"):
            plant_value = line.split(":", 1)[1].strip()
            formatted_lines.append("Plant:")
            if plant_value:
                formatted_lines.append(plant_value)
            continue
            
        if line.lower().startswith("disease:"):
            disease_value = line.split(":", 1)[1].strip()
            formatted_lines.append("Disease:")
            if disease_value:
                formatted_lines.append(disease_value)
            continue
            
        if line.lower().startswith("severity:"):
            severity_value = line.split(":", 1)[1].strip()
            formatted_lines.append("Severity:")
            if severity_value:
                formatted_lines.append(severity_value)
            continue

        if line.lower().startswith("symptoms:"):
            formatted_lines.append("Symptoms:")
            symptoms_value = line.split(":", 1)[1].strip()
            if symptoms_value:
                if re.match(r"^[\-\*\s]+", symptoms_value):
                    formatted_lines.append(f"- {re.sub(r'^[\-\*\s]+', '', symptoms_value)}")
                else:
                    formatted_lines.append(f"- {symptoms_value}")
            continue

        if line.lower().startswith("possible causes:"):
            formatted_lines.append("Possible Causes:")
            causes_value = line.split(":", 1)[1].strip()
            if causes_value:
                if re.match(r"^[\-\*\s]+", causes_value):
                    formatted_lines.append(f"- {re.sub(r'^[\-\*\s]+', '', causes_value)}")
                else:
                    formatted_lines.append(f"- {causes_value}")
            continue

        if line.lower().startswith("treatment:") or line.lower().startswith("suggested action:"):
            formatted_lines.append("Treatment:")
            action_value = line.split(":", 1)[1].strip()
            if action_value:
                if re.match(r"^[\-\*\s]+", action_value):
                    formatted_lines.append(f"- {re.sub(r'^[\-\*\s]+', '', action_value)}")
                else:
                    formatted_lines.append(f"- {action_value}")
            continue
            
        if line.lower().startswith("prevention:"):
            formatted_lines.append("Prevention:")
            prevention_value = line.split(":", 1)[1].strip()
            if prevention_value:
                if re.match(r"^[\-\*\s]+", prevention_value):
                    formatted_lines.append(f"- {re.sub(r'^[\-\*\s]+', '', prevention_value)}")
                else:
                    formatted_lines.append(f"- {prevention_value}")
            continue

        if re.match(r"^[\-\*]\s*", line):
            cleaned_line = re.sub(r"^[\-\*]\s*", "", line)
            formatted_lines.append(f"- {cleaned_line}")
            continue

        formatted_lines.append(line)

    return formatted_lines


def _normalize_translation_payload(original_payload, translated_payload):
    if not isinstance(original_payload, dict):
        return {}

    safe_payload = {
        "result_labels": dict(original_payload.get("result_labels") or {}),
        "result_values": dict(original_payload.get("result_values") or {}),
        "treatment_title": str(
            original_payload.get("treatment_title") or "Treatment plan"
        ),
        "treatment_items": [
            {
                "text": str(item.get("text") or ""),
                "kind": str(item.get("kind") or "text"),
            }
            for item in (original_payload.get("treatment_items") or [])
            if isinstance(item, dict)
        ],
    }

    if not isinstance(translated_payload, dict):
        return safe_payload

    translated_labels = translated_payload.get("result_labels")
    if isinstance(translated_labels, dict):
        for key, original_value in safe_payload["result_labels"].items():
            safe_payload["result_labels"][key] = str(
                translated_labels.get(key) or original_value
            )

    translated_values = translated_payload.get("result_values")
    if isinstance(translated_values, dict):
        for key, original_value in safe_payload["result_values"].items():
            safe_payload["result_values"][key] = str(
                translated_values.get(key) or original_value
            )

    translated_title = translated_payload.get("treatment_title")
    if translated_title:
        safe_payload["treatment_title"] = str(translated_title)

    translated_items = translated_payload.get("treatment_items")
    if isinstance(translated_items, list):
        normalized_items = []
        for index, original_item in enumerate(safe_payload["treatment_items"]):
            translated_item = (
                translated_items[index]
                if index < len(translated_items) and isinstance(translated_items[index], dict)
                else {}
            )
            normalized_items.append(
                {
                    "text": str(translated_item.get("text") or original_item["text"]),
                    "kind": original_item["kind"],
                }
            )
        safe_payload["treatment_items"] = normalized_items

    return safe_payload


def _translate_diagnosis_payload(payload, target_lang):
    if target_lang == "en":
        return _normalize_translation_payload(payload, payload)

    language_name = SUPPORTED_TRANSLATION_LANGUAGES.get(target_lang)
    if not language_name:
        raise ValueError("Unsupported translation language.")

    # 1. Check for manual translations in Database for the specific disease/crop
    translated_payload = {
        "result_labels": {},
        "result_values": {},
        "treatment_items": []
    }
    
    plant_name = payload.get("result_values", {}).get("plant")
    disease_name = payload.get("result_values", {}).get("disease")
    
    disease_record = _lookup_disease_record(disease_name, plant_name=plant_name)
    if disease_record and target_lang == "ml":
        if disease_record.name_ml:
            translated_payload["result_values"]["disease"] = disease_record.name_ml
        if disease_record.crop and disease_record.crop.name_ml:
            translated_payload["result_values"]["plant"] = disease_record.crop.name_ml
            
        # If we have full manual treatment fields, use them
        if disease_record.symptoms_ml or disease_record.treatment_recommendations_ml:
            # We construct a full payload manually
            # This is complex, but let's at least handle name/crop
            pass

    # 2. Local UI Dictionary Fallback (labels like "Symptoms", "Treatment")
    local_dict = LOCAL_UI_DICTIONARY.get(target_lang)
    if local_dict:
        translated_payload["result_labels"] = local_dict.get("result_labels", {})
        translated_payload["treatment_title"] = local_dict.get("treatment_title")
        
        # Translate values if standard
        for k, v in payload.get("result_values", {}).items():
            if v in local_dict.get("result_values", {}):
                translated_payload["result_values"][k] = local_dict["result_values"][v]
                
        # Handle treatment labels (kind)
        kind_map = local_dict.get("kind_labels", {})
        for item in payload.get("treatment_items", []):
            text = item.get("text", "")
            if item.get("kind") == "label" and text in kind_map:
                translated_payload["treatment_items"].append({
                    "text": kind_map[text],
                    "kind": "label"
                })
            else:
                translated_payload["treatment_items"].append(item)

    # 3. Call Gemini if quota allows (or if we need more depth)
    try:
        client = _get_gemini_client()
        from google.genai import types

        prompt = (
            f"Translate this plant diagnosis UI content from English to {language_name}.\n"
            "Return JSON only.\n"
            "Rules:\n"
            "- Preserve the same keys and overall JSON structure.\n"
            "- Keep all treatment_items in the same order.\n"
            "- Preserve each treatment_items.kind value exactly as provided.\n"
            "- Translate user-facing labels, values, and treatment text.\n"
            "- Keep numbers and percentages unchanged.\n"
            "- If a crop or disease does not have a natural translation, transliterate it or keep the English term.\n\n"
            f"{json.dumps(payload, ensure_ascii=False)}"
        )

        response = client.models.generate_content(
            model=getattr(settings, "GEMINI_MODEL_NAME", "gemini-2.0-flash"),
            contents=[prompt],
            config=types.GenerateContentConfig(temperature=0),
        )

        translated_text = (getattr(response, "text", "") or "").strip()
        translated_fragment = _extract_json_fragment(translated_text)
        if translated_fragment:
            gemini_payload = json.loads(translated_fragment)
            return _normalize_translation_payload(payload, gemini_payload)
    except Exception as exc:
        # If Gemini fails (429 Resource Exhausted), we return what we have (Local + DB)
        # or at least a graceful English version with translated UI labels
        return _normalize_translation_payload(payload, translated_payload)

    return _normalize_translation_payload(payload, translated_payload)


def _build_prediction_error(local_error=None, gemini_error=None):
    message_parts = ["Prediction is currently unavailable."]
    if local_error:
        message_parts.append(f"Local model error: {local_error}")
    if gemini_error:
        message_parts.append(f"Gemini fallback error: {gemini_error}")
    return " ".join(message_parts)


def _require_gemini_for_low_confidence():
    return bool(getattr(settings, "REQUIRE_GEMINI_FOR_LOW_CONFIDENCE", True))


def _load_prediction_assets():
    global MODEL, CLASS_NAMES

    if MODEL is not None and CLASS_NAMES is not None:
        return MODEL, CLASS_NAMES

    with _MODEL_LOCK:
        # Double-check after acquiring lock
        if MODEL is not None and CLASS_NAMES is not None:
            return MODEL, CLASS_NAMES

        try:
            import tensorflow as tf
        except ImportError as exc:
            raise RuntimeError(
                "TensorFlow is not installed in the Django environment."
            ) from exc

        model_path = _get_model_path()
        class_names_path = _get_class_names_path()

        if not model_path.exists():
            raise RuntimeError(f"Model file not found: {model_path}")
        if not class_names_path.exists():
            raise RuntimeError(f"Class names file not found: {class_names_path}")

        MODEL = tf.keras.models.load_model(model_path)
        with class_names_path.open(encoding="utf-8") as class_file:
            CLASS_NAMES = json.load(class_file)

    return MODEL, CLASS_NAMES


def _predict_with_external_runtime(image_path):
    runtime_python = _get_ml_runtime_python()
    predict_script = _get_ml_runtime_predict_script()

    if not runtime_python.exists():
        raise RuntimeError(
            f"External ML runtime not found: {runtime_python}"
        )

    if not predict_script.exists():
        raise RuntimeError(
            f"External ML prediction script not found: {predict_script}"
        )

    width, height = _get_image_size()
    completed_process = subprocess.run(
        [
            str(runtime_python),
            str(predict_script),
            "--image",
            str(image_path),
            "--model",
            str(_get_model_path()),
            "--classes",
            str(_get_class_names_path()),
            "--width",
            str(width),
            "--height",
            str(height),
        ],
        cwd=settings.BASE_DIR,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )

    if completed_process.returncode != 0:
        error_output = (
            completed_process.stderr.strip() or completed_process.stdout.strip()
        )
        error_line = error_output.splitlines()[-1] if error_output else "unknown error"
        raise RuntimeError(f"External ML runtime failed: {error_line}")

    output_lines = [
        line.strip() for line in completed_process.stdout.splitlines() if line.strip()
    ]
    if not output_lines:
        raise RuntimeError("External ML runtime returned no prediction output.")

    try:
        result = json.loads(output_lines[-1])
    except json.JSONDecodeError as exc:
        raise RuntimeError("External ML runtime returned invalid prediction output.") from exc

    raw_label = result.get("disease")
    confidence = result.get("confidence")
    if not raw_label:
        raise RuntimeError("External ML runtime returned no disease label.")

    try:
        confidence_value = float(confidence) if confidence is not None else None
    except (TypeError, ValueError) as exc:
        raise RuntimeError("External ML runtime returned an invalid confidence value.") from exc

    return _build_local_prediction(raw_label, confidence_value)


def _get_gemini_client():
    api_key = getattr(settings, "GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("Gemini API key is not configured.")

    try:
        import google.genai as genai
    except ImportError as exc:
        raise RuntimeError(
            "google-genai is not installed in the Django environment."
        ) from exc

    return genai.Client(api_key=api_key)


def preprocess_image(image_path):
    try:
        image = Image.open(image_path).convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValueError("Please upload a valid plant leaf image.") from exc

    image = image.resize(_get_image_size())
    image_array = np.asarray(image, dtype=np.float32)  # keep 0-255, model has preprocess_input built-in
    return np.expand_dims(image_array, axis=0)


def _predict_with_local_runtime(image_path):
    try:
        model, class_names = _load_prediction_assets()
        processed_image = preprocess_image(image_path)
        probabilities = model.predict(processed_image, verbose=0)[0]
    except ValueError:
        raise
    except Exception as exc:
        raise RuntimeError(f"Local TensorFlow prediction failed: {exc}") from exc

    predicted_index = int(np.argmax(probabilities))
    confidence = float(np.max(probabilities))

    return _build_local_prediction(class_names[predicted_index], confidence)


def _predict_with_local_model(image_path):
    try:
        return _predict_with_local_runtime(image_path)
    except RuntimeError as local_runtime_error:
        try:
            return _predict_with_external_runtime(image_path)
        except RuntimeError as external_runtime_error:
            raise RuntimeError(
                _build_prediction_error(
                    local_error=(
                        "Django runtime could not load the TensorFlow model. "
                        f"{local_runtime_error}. "
                        "External ML runtime also failed. "
                        f"{external_runtime_error}"
                    )
                )
            ) from external_runtime_error


def _call_gemini_once(image_path):
    client = _get_gemini_client()

    try:
        from google.genai import types
    except ImportError as exc:
        raise RuntimeError(
            "google-genai is not installed in the Django environment."
        ) from exc

    mime_type = mimetypes.guess_type(str(image_path))[0] or "image/jpeg"
    prompt = (
        "Analyze this plant leaf image carefully.\n\n"
        "Step 1: Identify the plant or crop name.\n"
        "Step 2: Identify the disease only if clearly visible.\n\n"
        "If the leaf appears healthy return:\n"
        'disease_name = "Healthy"\n\n'
        "If the plant or disease cannot be confidently identified return:\n"
        'status = "uncertain"\n\n'
        "Return JSON ONLY in this format:\n"
        "{\n"
        ' "plant_name": "<plant name or unknown>",\n'
        ' "disease_name": "<disease name or Healthy>",\n'
        ' "status": "healthy | diseased | uncertain"\n'
        "}\n\n"
        "Do not include explanations or markdown."
    )

    with open(image_path, "rb") as image_file:
        image_bytes = image_file.read()

    response = client.models.generate_content(
        model=getattr(settings, "GEMINI_MODEL_NAME", "gemini-2.5-flash"),
        contents=[
            prompt,
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
        ],
        config=types.GenerateContentConfig(temperature=0),
    )

    gemini_text = (getattr(response, "text", "") or "").strip()
    return _normalize_gemini_prediction(gemini_text)


def call_gemini_api(image_path):
    vote_count = max(1, int(getattr(settings, "GEMINI_VOTE_COUNT", 1)))
    return _call_gemini_once(image_path)


def generate_treatment_guidance(disease_name, disease_record=None, plant_name="Unknown"):
    if not disease_name:
        return ""

    if _is_healthy_prediction(disease_name):
        return "\n".join(
            [
                f"Plant:\n{plant_name}",
                "",
                "Disease:\nHealthy",
                "",
                "Severity:\nNone",
                "",
                "Symptoms:\n- No visible signs of infection or infestation.",
                "",
                "Possible Causes:\n- Optimal growing conditions and care.",
                "",
                "Treatment:\n- No treatment required.",
                "",
                "Prevention:",
                "- Continue regular monitoring.",
                "- Maintain balanced irrigation and plant nutrition.",
                "- Keep tools and growing areas clean to prevent future infections.",
            ]
        )

    if disease_record:
        symptoms_points = _split_guidance_points(disease_record.symptoms)
        treatment_points = _split_guidance_points(disease_record.treatment_recommendations)
        preventive_points = _split_guidance_points(disease_record.preventive_measures)

        lines = [
            f"Plant:\n{plant_name}",
            "",
            "Disease:",
            disease_record.name,
            "",
            "Severity:\nModerate to High",
            "",
            "Symptoms:",
        ]
        
        if not symptoms_points:
             lines.append("- Visual abnormalities on leaves, stems, or fruit.")
        else:
             lines.extend(f"- {point}" for point in symptoms_points)
             
        lines.extend(["", "Possible Causes:", "- Pathogen infection, environmental stress, or pests.", "", "Treatment:"])
        lines.extend(f"- {point}" for point in treatment_points)
        
        lines.extend(["", "Prevention:"])
        lines.extend(f"- {point}" for point in preventive_points)
        return "\n".join(lines)

    # Static fallback — no Gemini call here, treatment via Gemini is on-demand only
    return "\n".join(
        [
            f"Plant:\n{plant_name}",
            "",
            f"Disease:\n{disease_name}",
            "",
            "Severity:\nModerate",
            "",
            "Symptoms:\n- Typical signs of infection or environmental stress.",
            "",
            "Possible Causes:\n- Unknown pathogen or nutrient deficiency.",
            "",
            "Treatment:",
            "- Remove visibly infected leaves and isolate affected plants.",
            "- Avoid overhead watering and improve air circulation around the crop.",
            "- Use a crop-appropriate treatment and confirm with a local agricultural expert.",
            "",
            "Prevention:",
            "- Ensure proper plant spacing.",
            "- Water plants at soil level.",
            "- Monitor crops regularly.",
        ]
    )


def predict_leaf_disease(image_path):
    """Always returns local model result immediately. Gemini is on-demand only."""
    try:
        local_result = _predict_with_local_model(image_path)
    except ValueError:
        raise
    except RuntimeError as exc:
        raise RuntimeError(_build_prediction_error(local_error=exc)) from exc

    return local_result


def diagnose_leaf_image(image_path):
    prediction_result = predict_leaf_disease(image_path)
    disease_record = _lookup_disease_record(
        prediction_result["disease"],
        plant_name=prediction_result.get("plant_name"),
    )
    treatment_guidance = generate_treatment_guidance(
        prediction_result["disease"],
        disease_record=disease_record,
        plant_name=prediction_result.get("plant_name", "Unknown"),
    )
    prediction_result["treatment_guidance"] = treatment_guidance
    prediction_result["treatment_lines"] = _format_treatment_lines(treatment_guidance)
    return prediction_result


def _gemini_treatment_plan(disease_name, plant_name):
    """Ask Gemini for a rich treatment plan. Called only on user request."""
    disease_record = _lookup_disease_record(disease_name, plant_name=plant_name)
    if disease_record:
        return generate_treatment_guidance(disease_name, disease_record=disease_record, plant_name=plant_name)
    try:
        client = _get_gemini_client()
        from google.genai import types
        prompt = (
            f"Create a short structured agricultural treatment plan for '{plant_name}' with disease '{disease_name}'.\n"
            "Use EXACTLY these headings:\nPlant:\nDisease:\nSeverity:\nSymptoms:\nPossible Causes:\nTreatment:\nPrevention:\n"
            "Put bullet points under each heading. No markdown, no extra text."
        )
        response = client.models.generate_content(
            model=getattr(settings, "GEMINI_MODEL_NAME", "gemini-2.0-flash"),
            contents=[prompt],
            config=types.GenerateContentConfig(temperature=0.2),
        )
        return (getattr(response, "text", "") or "").strip()
    except Exception:
        return generate_treatment_guidance(disease_name, plant_name=plant_name)


@login_required
def gemini_verify(request):
    """On-demand Gemini verification called via AJAX from the result page."""
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed."}, status=405)

    diagnosis_id = request.POST.get("diagnosis_id")
    if not diagnosis_id:
        return JsonResponse({"error": "Missing diagnosis_id."}, status=400)

    try:
        diagnosis_log = LeafDiagnosis.objects.get(pk=diagnosis_id, user=request.user)
    except LeafDiagnosis.DoesNotExist:
        return JsonResponse({"error": "Diagnosis not found."}, status=404)

    try:
        gemini_result = call_gemini_api(diagnosis_log.image.path)
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=503)

    plant_name = gemini_result["plant_name"]
    if plant_name.lower() == "unknown" and diagnosis_log.plant_name:
        plant_name = diagnosis_log.plant_name

    disease_name = gemini_result["disease"]
    treatment_guidance = _gemini_treatment_plan(disease_name, plant_name)
    treatment_lines = _format_treatment_lines(treatment_guidance)

    # Persist Gemini result back to the diagnosis log
    diagnosis_log.plant_name = plant_name
    diagnosis_log.predicted_disease = disease_name
    diagnosis_log.source = "gemini_api"
    diagnosis_log.treatment_guidance = treatment_guidance
    diagnosis_log.save(update_fields=["plant_name", "predicted_disease", "source", "treatment_guidance"])

    return JsonResponse({
        "plant_name": plant_name,
        "disease": disease_name,
        "source": "gemini_api",
        "treatment_lines": treatment_lines,
    })


@login_required
def translate_diagnosis_content(request):
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed."}, status=405)

    try:
        request_payload = json.loads(request.body.decode("utf-8"))
    except (AttributeError, UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({"error": "Invalid JSON payload."}, status=400)

    target_lang = str(request_payload.get("target_lang") or "").strip().lower()
    if not target_lang:
        return JsonResponse({"error": "Missing target language."}, status=400)

    ui_payload = request_payload.get("payload")
    if not isinstance(ui_payload, dict):
        return JsonResponse({"error": "Missing diagnosis payload."}, status=400)

    try:
        translated_payload = _translate_diagnosis_payload(ui_payload, target_lang)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=503)

    return JsonResponse(
        {
            "target_lang": target_lang,
            "payload": translated_payload,
        }
    )


@login_required
def upload_scan(request):
    leaf_quota = get_leaf_quota_summary(request.user)

    if request.method == "POST":
        if not leaf_quota["can_submit"]:
            limit_message = (
                f"You have reached your free plan limit of {leaf_quota['limit']} leaf checks. "
                "Upgrade to premium to continue."
            )
            messages.error(request, limit_message)
            if "application/json" in request.headers.get("Accept", ""):
                return JsonResponse({"error": limit_message}, status=403)
            return redirect("account:membership")

        form = DiagnosisForm(request.POST, request.FILES)
        if form.is_valid():
            diagnosis = form.save(commit=False)
            diagnosis.user = request.user
            diagnosis.save()

            try:
                prediction_result = diagnose_leaf_image(diagnosis.leaf_image.path)
            except ValueError as exc:
                diagnosis.leaf_image.delete(save=False)
                diagnosis.delete()
                form.add_error("leaf_image", str(exc))
                messages.error(request, str(exc))
            except RuntimeError as exc:
                diagnosis.leaf_image.delete(save=False)
                diagnosis.delete()
                form.add_error("leaf_image", str(exc))
                messages.error(request, str(exc))
                if "application/json" in request.headers.get("Accept", ""):
                    return JsonResponse({"error": str(exc)}, status=503)
            except Exception as exc:
                prediction_result = {
                    "disease": "Prediction unavailable",
                    "confidence": None,
                    "source": "local_model",
                    "error": str(exc),
                }
                messages.warning(
                    request,
                    "The image was saved, but prediction could not be completed.",
                )
            else:
                diagnosis.confidence_score = prediction_result["confidence"]
                diagnosis.predicted_disease = _lookup_disease_record(
                    prediction_result["disease"],
                    plant_name=prediction_result.get("plant_name"),
                )
                diagnosis.save(update_fields=["confidence_score", "predicted_disease"])
                messages.success(request, "Leaf image uploaded and analyzed successfully.")
                if prediction_result.get("warning"):
                    messages.warning(request, prediction_result["warning"])

            if "prediction_result" in locals():
                request.session[_result_session_key(diagnosis.pk)] = prediction_result
                request.session.modified = True

                if "application/json" in request.headers.get("Accept", ""):
                    return JsonResponse(prediction_result, status=201)

                return redirect("detection:scan_result", scan_id=diagnosis.pk)
    else:
        form = DiagnosisForm()

    return render(request, "detection/upload.html", {"form": form, "leaf_quota": leaf_quota})


@login_required
def leaf_diagnosis_view(request):
    form = LeafDiagnosisForm()
    diagnosis_log = None
    diagnosis_result = None
    leaf_quota = get_leaf_quota_summary(request.user)

    if request.method == "POST":
        if not leaf_quota["can_submit"]:
            messages.error(
                request,
                f"You have used all {leaf_quota['limit']} free leaf checks. Upgrade to premium to keep analyzing new images.",
            )
        else:
            form = LeafDiagnosisForm(request.POST, request.FILES)
            if form.is_valid():
                diagnosis_log = form.save(commit=False)
                diagnosis_log.user = request.user
                diagnosis_log.original_filename = request.FILES["image"].name
                diagnosis_log.save()

                try:
                    diagnosis_result = diagnose_leaf_image(diagnosis_log.image.path)
                except ValueError as exc:
                    diagnosis_log.image.delete(save=False)
                    diagnosis_log.delete()
                    diagnosis_log = None
                    form.add_error("image", str(exc))
                    messages.error(request, str(exc))
                except RuntimeError as exc:
                    diagnosis_log.image.delete(save=False)
                    diagnosis_log.delete()
                    diagnosis_log = None
                    form.add_error("image", str(exc))
                    messages.error(request, str(exc))
                except Exception:
                    diagnosis_log.image.delete(save=False)
                    diagnosis_log.delete()
                    diagnosis_log = None
                    messages.error(
                        request,
                        "We could not analyze this image because the prediction service failed unexpectedly.",
                    )
                else:
                    diagnosis_log.plant_name = diagnosis_result.get("plant_name", "")
                    diagnosis_log.predicted_disease = diagnosis_result["disease"]
                    diagnosis_log.confidence = diagnosis_result["confidence"]
                    diagnosis_log.source = diagnosis_result["source"]
                    diagnosis_log.treatment_guidance = diagnosis_result["treatment_guidance"]
                    diagnosis_log.save(
                        update_fields=[
                            "plant_name",
                            "predicted_disease",
                            "confidence",
                            "source",
                            "treatment_guidance",
                        ]
                    )
                    leaf_quota = get_leaf_quota_summary(request.user)
                    messages.success(request, "Leaf analysis completed successfully.")
                    if diagnosis_result.get("warning"):
                        messages.warning(request, diagnosis_result["warning"])

    recent_diagnoses = LeafDiagnosis.objects.filter(user=request.user)[:5]

    return render(
        request,
        "detection/diagnosis.html",
        {
            "form": form,
            "diagnosis_log": diagnosis_log,
            "diagnosis_result": diagnosis_result,
            "recent_diagnoses": recent_diagnoses,
            "leaf_quota": leaf_quota,
        },
    )


@login_required
def scan_result(request, scan_id):
    diagnosis = get_object_or_404(
        Diagnosis.objects.select_related("predicted_disease", "predicted_disease__crop"),
        pk=scan_id,
        user=request.user,
    )

    prediction_result = request.session.get(_result_session_key(scan_id))
    if not prediction_result:
        prediction_result = {
            "plant_name": diagnosis.predicted_disease.crop.name if diagnosis.predicted_disease else "Unknown",
            "disease": diagnosis.predicted_disease.name if diagnosis.predicted_disease else "Prediction unavailable",
            "confidence": diagnosis.confidence_score,
            "source": "local_model" if diagnosis.predicted_disease else "local_model",
        }

    if request.GET.get("format") == "json" or "application/json" in request.headers.get("Accept", ""):
        return JsonResponse(prediction_result)

    return render(
        request,
        "detection/scan_result.html",
        {
            "diagnosis": diagnosis,
            "prediction_result": prediction_result,
        },
    )
