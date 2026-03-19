import json
import mimetypes
import os
import re
import subprocess
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

    # Fallback for unknown disease not in the DB, ask Gemini to generate structure
    client = _get_gemini_client()
    try:
        from google.genai import types
        prompt = (
            f"Create a short structured agricultural treatment plan for a plant called '{plant_name}' "
            f"with the disease '{disease_name}'.\n\n"
            "Format your response EXACTLY with these headings and bullet points below them:\n\n"
            "Plant:\n"
            "<plant name>\n\n"
            "Disease:\n"
            "<disease name>\n\n"
            "Severity:\n"
            "<Low / Moderate / Severe>\n\n"
            "Symptoms:\n"
            "- <symptom 1>\n"
            "- <symptom 2>\n\n"
            "Possible Causes:\n"
            "- <cause 1>\n"
            "- <cause 2>\n\n"
            "Treatment:\n"
            "- <treatment 1>\n"
            "- <treatment 2>\n\n"
            "Prevention:\n"
            "- <prevention step 1>\n"
            "- <prevention step 2>\n"
        )
        response = client.models.generate_content(
            model=getattr(settings, "GEMINI_MODEL_NAME", "gemini-2.5-flash"),
            contents=[prompt],
            config=types.GenerateContentConfig(temperature=0.2),
        )
        return (getattr(response, "text", "") or "").strip()
    except Exception:
        fallback_text = "\n".join(
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
        return fallback_text


def predict_leaf_disease(image_path):
    threshold = float(getattr(settings, "LOCAL_MODEL_CONFIDENCE_THRESHOLD", 0.80))

    local_result = None
    local_error = None

    try:
        local_result = _predict_with_local_model(image_path)
    except ValueError:
        raise
    except RuntimeError as exc:
        local_error = exc

    if local_result and (
        local_result["confidence"] is None or local_result["confidence"] >= (threshold * 100)
    ):
        return local_result

    low_confidence_note = None
    if local_result and local_result["confidence"] is not None:
        low_confidence_note = (
            "Low-confidence local prediction "
            f"({local_result['confidence']:.1f}%) requires Gemini verification."
        )

    try:
        gemini_prediction = call_gemini_api(image_path)
    except Exception as gemini_error:
        if local_result:
            local_result["warning"] = "Gemini verification unavailable. Using local prediction."
            return local_result
        raise RuntimeError(
            _build_prediction_error(local_error=local_error, gemini_error=gemini_error)
        ) from gemini_error

    plant_name = gemini_prediction["plant_name"]
    if (
        plant_name.lower() == "unknown"
        and local_result
        and local_result.get("plant_name")
        and local_result["plant_name"].lower() != "unknown"
    ):
        plant_name = local_result["plant_name"]

    result = {
        "plant_name": plant_name,
        "disease": gemini_prediction["disease"],
        "confidence": local_result["confidence"] if local_result else None,
        "source": "gemini_api",
    }
    if low_confidence_note:
        result["warning"] = low_confidence_note
    return result


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
