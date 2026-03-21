"""Jerarquía de excepciones personalizadas para Pong IA."""


class PongError(Exception):
    """Base para todas las excepciones de Pong IA."""


# --- LLM / Narrador ---


class NarratorError(PongError):
    """Base para fallos del narrador/LLM."""


class ModelLoadError(NarratorError):
    """El modelo LLM no se pudo cargar o inicializar."""


class LLMInferenceError(NarratorError):
    """La llamada LLM falló durante la inferencia."""


# --- Generación de imágenes (Stable Diffusion) ---


class ImageGenError(PongError):
    """Base para fallos del pipeline de Stable Diffusion."""


class PipelineLoadError(ImageGenError):
    """El pipeline SD o los pesos LoRA no se pudieron cargar."""


class ImageGenerationError(ImageGenError):
    """La generación de imagen falló con el pipeline ya cargado."""


class ModelDownloadError(ImageGenError):
    """La descarga de pesos del modelo falló."""


# --- Logros ---


class AchievementDefinitionError(PongError):
    """Metadatos de logro faltantes o inválidos."""
