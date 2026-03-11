"""
Shared Model Loader

Loads the trained stable XGBoost model, feature names, label encoders,
DiCE explainer, and test/train data once. All tools share this singleton.
"""

import logging
import pickle
from pathlib import Path
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

MODEL_DIR = Path(__file__).parent.parent.parent / "ml_models" / "credit_scoring"


class ModelArtifacts:
    """Singleton that holds all loaded model artifacts."""

    def __init__(self):
        self.model = None
        self.feature_names = None
        self.label_encoders = None
        self.X_train = None
        self.X_test = None
        self.y_test = None
        self.dice_explainer = None
        self.dice_data = None
        self.actionable_features = None
        self.feature_labels = None
        self.shap_explainer = None
        self.mean_abs_shap = None
        self.loaded = False

        self._load()

    def _load(self):
        """Load all artifacts from ml_models/credit_scoring/."""
        try:
            model_path = MODEL_DIR / "xgboost_model.pkl"
            if not model_path.exists():
                logger.warning(f"Model not found at {model_path}")
                return

            # Core model
            with open(model_path, "rb") as f:
                self.model = pickle.load(f)
            logger.info("Loaded XGBoost model")

            # Feature names
            feat_path = MODEL_DIR / "feature_names.pkl"
            if feat_path.exists():
                with open(feat_path, "rb") as f:
                    self.feature_names = pickle.load(f)
                logger.info(f"Loaded {len(self.feature_names)} feature names")

            # Label encoders
            le_path = MODEL_DIR / "label_encoders.pkl"
            if le_path.exists():
                with open(le_path, "rb") as f:
                    self.label_encoders = pickle.load(f)
                logger.info(f"Loaded {len(self.label_encoders)} label encoders")

            # Training data
            train_path = MODEL_DIR / "X_train.parquet"
            if train_path.exists():
                self.X_train = pd.read_parquet(train_path)
                logger.info(f"Loaded X_train: {self.X_train.shape}")

            # Test data
            test_X_path = MODEL_DIR / "X_test.parquet"
            test_y_path = MODEL_DIR / "y_test.parquet"
            if test_X_path.exists() and test_y_path.exists():
                self.X_test = pd.read_parquet(test_X_path)
                self.y_test = pd.read_parquet(test_y_path).squeeze()
                logger.info(f"Loaded X_test: {self.X_test.shape}")

            # DiCE explainer
            dice_exp_path = MODEL_DIR / "dice_explainer.pkl"
            dice_data_path = MODEL_DIR / "dice_data.pkl"
            if dice_exp_path.exists() and dice_data_path.exists():
                with open(dice_exp_path, "rb") as f:
                    self.dice_explainer = pickle.load(f)
                with open(dice_data_path, "rb") as f:
                    self.dice_data = pickle.load(f)
                logger.info("Loaded DiCE explainer")

            # Actionable features for DiCE
            act_path = MODEL_DIR / "actionable_features.pkl"
            if act_path.exists():
                with open(act_path, "rb") as f:
                    self.actionable_features = pickle.load(f)

            # Feature labels
            labels_path = MODEL_DIR / "feature_labels.pkl"
            if labels_path.exists():
                with open(labels_path, "rb") as f:
                    self.feature_labels = pickle.load(f)

            # Build SHAP explainer
            self._build_shap()

            self.loaded = True
            logger.info("All model artifacts loaded successfully")

        except Exception as e:
            logger.error(f"Failed to load model artifacts: {e}")
            self.loaded = False

    def _build_shap(self):
        """Build SHAP TreeExplainer and compute mean absolute SHAP values."""
        if self.model is None or self.X_train is None or self.feature_names is None:
            return
        try:
            import shap
            self.shap_explainer = shap.TreeExplainer(self.model)
            # Compute mean_abs_shap on a sample for speed
            sample = self.X_train[self.feature_names].sample(
                n=min(1000, len(self.X_train)), random_state=42
            )
            shap_values = self.shap_explainer.shap_values(sample)
            self.mean_abs_shap = pd.Series(
                np.abs(shap_values).mean(axis=0),
                index=self.feature_names
            ).sort_values(ascending=False)
            logger.info("Built SHAP explainer with mean_abs_shap")
        except ImportError:
            logger.warning("SHAP library not installed")
        except Exception as e:
            logger.warning(f"Failed to build SHAP explainer: {e}")


# Singleton
artifacts = ModelArtifacts()
