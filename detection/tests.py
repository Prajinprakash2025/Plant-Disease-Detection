import json
import shutil
import tempfile
from unittest import mock

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from . import views
from .models import Diagnosis, LeafDiagnosis


GIF_BYTES = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00"
    b"\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,\x00"
    b"\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)


class DetectionViewTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.user = User.objects.create_user(
            username="scanner",
            email="scanner@example.com",
            password="StrongPass123!",
        )

    def tearDown(self):
        shutil.rmtree(self.media_root, ignore_errors=True)

    @override_settings(MEDIA_ROOT=tempfile.gettempdir())
    def test_upload_requires_login(self):
        response = self.client.get(reverse("detection:upload_scan"))
        self.assertRedirects(
            response,
            f"{reverse('account:login')}?next={reverse('detection:upload_scan')}",
        )

    def test_authenticated_user_can_upload_scan(self):
        self.client.force_login(self.user)
        with override_settings(MEDIA_ROOT=self.media_root), mock.patch(
            "detection.views.diagnose_leaf_image",
            return_value={
                "plant_name": "Tomato",
                "disease": "Tomato Early blight",
                "confidence": 0.94,
                "source": "local_model",
                "treatment_guidance": "Suggested Action:\n- Remove infected leaves",
                "treatment_lines": ["Suggested Action:", "- Remove infected leaves"],
            },
        ):
            response = self.client.post(
                reverse("detection:upload_scan"),
                {
                    "leaf_image": SimpleUploadedFile(
                        "leaf.png",
                        GIF_BYTES,
                        content_type="image/png",
                    )
                },
            )

        scan = Diagnosis.objects.get()
        self.assertRedirects(response, reverse("detection:scan_result", args=[scan.pk]))
        self.assertEqual(scan.user, self.user)
        self.assertEqual(scan.confidence_score, 0.94)

    def test_upload_returns_json_when_requested(self):
        self.client.force_login(self.user)
        with override_settings(MEDIA_ROOT=self.media_root), mock.patch(
            "detection.views.diagnose_leaf_image",
            return_value={
                "plant_name": "Tomato",
                "disease": "healthy",
                "confidence": 0.83,
                "source": "local_model",
                "treatment_guidance": "Suggested Action:\n- Continue monitoring",
                "treatment_lines": ["Suggested Action:", "- Continue monitoring"],
            },
        ):
            response = self.client.post(
                reverse("detection:upload_scan"),
                {
                    "leaf_image": SimpleUploadedFile(
                        "leaf.png",
                        GIF_BYTES,
                        content_type="image/png",
                    )
                },
                HTTP_ACCEPT="application/json",
            )

        self.assertEqual(response.status_code, 201)
        self.assertJSONEqual(
            response.content,
            {
                "plant_name": "Tomato",
                "disease": "healthy",
                "confidence": 0.83,
                "source": "local_model",
                "treatment_guidance": "Suggested Action:\n- Continue monitoring",
                "treatment_lines": ["Suggested Action:", "- Continue monitoring"],
            },
        )

    def test_leaf_diagnosis_requires_login(self):
        response = self.client.get(reverse("detection:leaf_diagnosis"))
        self.assertRedirects(
            response,
            f"{reverse('account:login')}?next={reverse('detection:leaf_diagnosis')}",
        )

    def test_translate_diagnosis_requires_login(self):
        response = self.client.post(
            reverse("detection:translate_diagnosis"),
            content_type="application/json",
            data='{"target_lang":"ml","payload":{}}',
        )
        self.assertRedirects(
            response,
            f"{reverse('account:login')}?next={reverse('detection:translate_diagnosis')}",
        )

    def test_translate_diagnosis_returns_translated_payload(self):
        self.client.force_login(self.user)
        payload = {
            "result_labels": {
                "plant": "Plant",
                "disease": "Disease",
                "confidence": "Confidence",
                "source": "Source",
            },
            "result_values": {
                "plant": "Tomato",
                "disease": "Early blight",
                "confidence": "94.7%",
                "source": "Local CNN model",
            },
            "treatment_title": "Treatment plan",
            "treatment_items": [
                {"text": "Symptoms:", "kind": "heading"},
                {"text": "Typical leaf spots.", "kind": "bullet"},
            ],
        }
        translated_payload = {
            "result_labels": {
                "plant": "ചെടി",
                "disease": "രോഗം",
                "confidence": "വിശ്വാസ്യത",
                "source": "ഉറവിടം",
            },
            "result_values": {
                "plant": "തക്കാളി",
                "disease": "എർലി ബ്ലൈറ്റ്",
                "confidence": "94.7%",
                "source": "ലോക്കൽ സി.എൻ.എൻ മോഡൽ",
            },
            "treatment_title": "ചികിത്സാ പദ്ധതി",
            "treatment_items": [
                {"text": "ലക്ഷണങ്ങൾ:", "kind": "heading"},
                {"text": "സാധാരണ ഇല പാടുകൾ.", "kind": "bullet"},
            ],
        }

        with mock.patch(
            "detection.views._translate_diagnosis_payload",
            return_value=translated_payload,
        ) as translate_mock:
            response = self.client.post(
                reverse("detection:translate_diagnosis"),
                data=json.dumps(
                    {
                        "target_lang": "ml",
                        "payload": payload,
                    }
                ),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(
            response.content,
            {
                "target_lang": "ml",
                "payload": translated_payload,
            },
        )
        translate_mock.assert_called_once_with(payload, "ml")

    def test_translate_diagnosis_rejects_invalid_payload(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("detection:translate_diagnosis"),
            data=json.dumps({"target_lang": "ml"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertJSONEqual(
            response.content,
            {"error": "Missing diagnosis payload."},
        )

    def test_leaf_diagnosis_page_logs_result(self):
        self.client.force_login(self.user)
        with override_settings(MEDIA_ROOT=self.media_root), mock.patch(
            "detection.views.diagnose_leaf_image",
            return_value={
                "plant_name": "Rose",
                "disease": "Tomato Early blight",
                "confidence": 0.76,
                "source": "gemini_api",
                "treatment_guidance": "Disease:\nTomato Early blight\n\nSuggested Action:\n- Remove infected leaves",
                "treatment_lines": [
                    "Disease:",
                    "Tomato Early blight",
                    "Suggested Action:",
                    "- Remove infected leaves",
                ],
            },
        ):
            response = self.client.post(
                reverse("detection:leaf_diagnosis"),
                {
                    "image": SimpleUploadedFile(
                        "leaf.png",
                        GIF_BYTES,
                        content_type="image/png",
                    )
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(LeafDiagnosis.objects.exists())
        diagnosis = LeafDiagnosis.objects.get()
        self.assertEqual(diagnosis.original_filename, "leaf.png")
        self.assertEqual(diagnosis.plant_name, "Rose")
        self.assertEqual(diagnosis.source, "gemini_api")
        self.assertContains(response, "Tomato Early blight")
        self.assertContains(response, "Rose")

    def test_predict_leaf_disease_uses_external_runtime_when_tensorflow_is_unavailable(self):
        with mock.patch(
            "detection.views._predict_with_local_runtime",
            side_effect=RuntimeError("TensorFlow is not installed in the Django environment."),
        ), mock.patch(
            "detection.views._predict_with_external_runtime",
            return_value={
                "disease": "Tomato Early blight",
                "confidence": 0.91,
                "source": "local_model",
            },
        ):
            result = views.predict_leaf_disease("leaf.png")

        self.assertEqual(
            result,
            {
                "disease": "Tomato Early blight",
                "confidence": 0.91,
                "source": "local_model",
            },
        )

    @override_settings(GEMINI_VOTE_COUNT=3)
    def test_call_gemini_api_returns_majority_vote(self):
        with mock.patch(
            "detection.views._call_gemini_once",
            side_effect=[
                {"plant_name": "Rose", "disease": "Powdery mildew"},
                {"plant_name": "Rose", "disease": "Powdery mildew"},
                {"plant_name": "Rose", "disease": "Leaf spot"},
            ],
        ):
            result = views.call_gemini_api("leaf.png")

        self.assertEqual(result, {"plant_name": "Rose", "disease": "Powdery mildew"})

    @override_settings(GEMINI_VOTE_COUNT=3)
    def test_call_gemini_api_rejects_inconsistent_votes(self):
        with mock.patch(
            "detection.views._call_gemini_once",
            side_effect=[
                {"plant_name": "Rose", "disease": "Powdery mildew"},
                {"plant_name": "Rose", "disease": "Leaf spot"},
                {"plant_name": "Rose", "disease": "Rust"},
            ],
        ):
            with self.assertRaises(RuntimeError) as raised_error:
                views.call_gemini_api("leaf.png")

        self.assertIn("inconsistent", str(raised_error.exception))

    @override_settings(GEMINI_VOTE_COUNT=1)
    def test_call_gemini_api_uses_single_request_when_vote_count_is_one(self):
        with mock.patch(
            "detection.views._call_gemini_once",
            return_value={"plant_name": "Rose", "disease": "Powdery mildew"},
        ) as gemini_call:
            result = views.call_gemini_api("leaf.png")

        self.assertEqual(result, {"plant_name": "Rose", "disease": "Powdery mildew"})
        self.assertEqual(gemini_call.call_count, 1)

    @override_settings(REQUIRE_GEMINI_FOR_LOW_CONFIDENCE=True)
    def test_predict_leaf_disease_requires_gemini_for_low_confidence_results(self):
        with mock.patch(
            "detection.views._predict_with_local_model",
            return_value={
                "disease": "Corn (maize) healthy",
                "confidence": 0.35,
                "source": "local_model",
            },
        ), mock.patch(
            "detection.views.call_gemini_api",
            side_effect=RuntimeError("Gemini API key is not configured."),
        ):
            with self.assertRaises(RuntimeError) as raised_error:
                views.predict_leaf_disease("leaf.png")

        self.assertIn("requires Gemini verification", str(raised_error.exception))
        self.assertIn("Gemini API key is not configured", str(raised_error.exception))

    def test_leaf_diagnosis_shows_runtime_error_and_does_not_keep_failed_log(self):
        self.client.force_login(self.user)
        with override_settings(MEDIA_ROOT=self.media_root), mock.patch(
            "detection.views.diagnose_leaf_image",
            side_effect=RuntimeError(
                "Prediction is currently unavailable. Local model error: TensorFlow is not installed."
            ),
        ):
            response = self.client.post(
                reverse("detection:leaf_diagnosis"),
                {
                    "image": SimpleUploadedFile(
                        "leaf.png",
                        GIF_BYTES,
                        content_type="image/png",
                    )
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(LeafDiagnosis.objects.exists())
        self.assertContains(response, "Prediction is currently unavailable.")

    @override_settings(MEDIA_ROOT=tempfile.gettempdir(), REQUIRE_GEMINI_FOR_LOW_CONFIDENCE=True)
    def test_leaf_diagnosis_rejects_low_confidence_result_when_gemini_is_unavailable(self):
        self.client.force_login(self.user)
        with mock.patch(
            "detection.views.diagnose_leaf_image",
            side_effect=RuntimeError(
                "Low-confidence local prediction (35.0%) requires Gemini verification. "
                "Gemini fallback is unavailable: Gemini API key is not configured."
            ),
        ):
            response = self.client.post(
                reverse("detection:leaf_diagnosis"),
                {
                    "image": SimpleUploadedFile(
                        "leaf.png",
                        GIF_BYTES,
                        content_type="image/png",
                    )
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(LeafDiagnosis.objects.exists())
        self.assertContains(response, "requires Gemini verification")

    def test_generate_treatment_guidance_uses_local_fallback_without_gemini_call(self):
        with mock.patch("detection.views._get_gemini_client") as gemini_client:
            guidance = views.generate_treatment_guidance("Powdery mildew")

        self.assertIn("Powdery mildew", guidance)
        gemini_client.assert_not_called()

    @override_settings(FREE_TIER_LEAF_DIAGNOSIS_LIMIT=20)
    def test_leaf_diagnosis_blocks_free_user_when_limit_is_reached(self):
        self.client.force_login(self.user)
        LeafDiagnosis.objects.bulk_create(
            [
                LeafDiagnosis(
                    user=self.user,
                    original_filename=f"leaf-{index}.png",
                    predicted_disease="Healthy",
                    plant_name="Tomato",
                )
                for index in range(20)
            ]
        )

        response = self.client.post(
            reverse("detection:leaf_diagnosis"),
            {
                "image": SimpleUploadedFile(
                    "blocked.png",
                    GIF_BYTES,
                    content_type="image/png",
                )
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "used all 20 free leaf checks")
        self.assertEqual(LeafDiagnosis.objects.filter(user=self.user).count(), 20)

    def test_predict_leaf_disease_uses_local_plant_name_when_gemini_returns_unknown(self):
        with mock.patch(
            "detection.views._predict_with_local_model",
            return_value={
                "plant_name": "Rose",
                "disease": "Powdery mildew",
                "confidence": 0.35,
                "source": "local_model",
            },
        ), mock.patch(
            "detection.views.call_gemini_api",
            return_value={"plant_name": "Unknown", "disease": "Powdery mildew"},
        ):
            result = views.predict_leaf_disease("leaf.png")

        self.assertEqual(result["source"], "gemini_api")
        self.assertEqual(result["plant_name"], "Rose")
