from django.apps import AppConfig


class DetectionConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "detection"

    def ready(self):
        import threading

        def _warm_up():
            try:
                from detection.views import _load_prediction_assets
                _load_prediction_assets()
            except Exception:
                pass

        # Load model in background so Django starts instantly
        threading.Thread(target=_warm_up, daemon=True).start()
