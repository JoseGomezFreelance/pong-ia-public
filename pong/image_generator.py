"""
pong/image_generator.py -- Motor de generacion de imagenes de fondo con IA.

Genera fondos para la zona de juego usando Stable Diffusion 1.5
(Juggernaut Reborn) con LCM LoRA para generacion rapida (~3-6 s).

Arquitectura: proceso separado (multiprocessing) para evitar bloqueos
del GIL. El juego sigue a 60 FPS mientras el modelo genera imagenes
en un proceso independiente con su propio GIL.

La carga del modelo es lazy: solo se descarga e inicializa cuando
el juego activa la fase visual generativa (minuto 3 de partida, tras
haber desbloqueado la fase con 5 min de juego acumulado).

Fases del generador:
  idle     -> activate() -> loading -> ready <-> generating
"""

from __future__ import annotations

import logging
import multiprocessing as mp
import queue
import time
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    import pygame

    from pong.config.models import ImageModelConfig

from pong.config.layout import GAME_AREA_HEIGHT, WINDOW_WIDTH
from pong.config.media import (
    IMAGEGEN_CACHE_DIR,
    IMAGEGEN_DEBUG_SAVE,
)

logger = logging.getLogger(__name__)


# ============================================================
# Descarga de modelos (sin cargar en memoria)
# ============================================================

def _get_image_config() -> Any:
    """Obtiene la configuracion de imagen activa (lazy, sin importar al nivel de modulo)."""
    from pong.config.models import ImageModelConfig, load_models_config
    _, image_config = load_models_config()
    return image_config


def is_model_cached(config: ImageModelConfig | None = None) -> bool:
    """Comprueba si los pesos del modelo SD y LoRAs estan en la cache local.

    Ademas de verificar que existan los repos, comprueba que el modelo base
    tenga un tamano minimo razonable (>100 MB) para evitar falsos positivos
    con descargas incompletas.

    Args:
        config: ``ImageModelConfig`` opcional; si es ``None`` lee models.toml.
    """
    if config is None:
        config = _get_image_config()

    try:
        from huggingface_hub import scan_cache_dir

        if not IMAGEGEN_CACHE_DIR.is_dir():
            return False

        cache_info = scan_cache_dir(str(IMAGEGEN_CACHE_DIR))
        repos = {repo.repo_id: repo for repo in cache_info.repos}

        if config.model_id not in repos:
            return False

        # Verificar tamano minimo del modelo base (~2 GB esperado)
        model_size = repos[config.model_id].size_on_disk
        if model_size < 100_000_000:  # < 100 MB = descarga incompleta
            return False

        # Verificar LoRAs de HuggingFace
        for lora in config.loras:
            if lora.source == "huggingface" and lora.id not in repos:
                return False

        return True
    except (ImportError, OSError):
        return False


def ensure_models_downloaded(
    progress_callback: Callable[[str], None] | None = None,
    config: ImageModelConfig | None = None,
) -> bool:
    """
    Descarga los pesos del modelo SD y LoRAs a disco sin cargarlos.

    Se llama desde la pantalla de carga ZX Terminal para que los pesos
    esten listos cuando se active la fase visual generativa.

    Args:
        progress_callback: funcion(msg: str) opcional para reportar progreso.
        config: ``ImageModelConfig`` opcional; si es ``None`` lee models.toml.
    """
    if config is None:
        config = _get_image_config()

    def _report(msg: str) -> None:
        if progress_callback:
            progress_callback(msg)
        logger.info(msg)

    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        _report("huggingface_hub no instalado, omitiendo descarga SD")
        return False

    IMAGEGEN_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    try:
        _report(f"Descargando modelo base {config.model_id}...")
        snapshot_download(
            repo_id=config.model_id,
            cache_dir=str(IMAGEGEN_CACHE_DIR),
            ignore_patterns=["*.md", "*.txt", "*.png", "*.jpg"],
        )
        for lora in config.loras:
            if lora.source == "huggingface":
                _report(f"Descargando LoRA {lora.id}...")
                snapshot_download(
                    repo_id=lora.id,
                    cache_dir=str(IMAGEGEN_CACHE_DIR),
                )
        _report("Modelos de difusion descargados")
        return True
    except (OSError, ConnectionError, ValueError) as e:
        _report(f"ModelDownloadError: {e}")
        return False


# ============================================================
# Estilo base ZX Spectrum: se antepone a TODOS los prompts
# para garantizar coherencia con la estetica retro del juego.
# ============================================================

ZX_STYLE_PREFIX = (
    "pixel art, 8-bit retro game art, Sinclair ZX Spectrum style, "
    "limited color palette, blocky pixels, low resolution, "
    "retro computer graphics, 1980s home computer aesthetic"
)

# ============================================================
# Mapeo mood_tag -> estilo visual para prompts de imagen
# ============================================================

MOOD_VISUAL_STYLES: dict[str, str] = {
    "neutral": (
        "geometric grid pattern, calm blue and cyan blocks, "
        "simple tiled background, orderly squares"
    ),
    "relajado": (
        "simple rolling hills, green pixel grass, "
        "blue sky with blocky clouds, peaceful 8-bit landscape"
    ),
    "tenso": (
        "dark sky with red zigzag lightning bolts, "
        "jagged pixel shapes, ominous diagonal lines, warning stripes"
    ),
    "irritado": (
        "erupting pixel volcano, bright red and yellow blocks, "
        "sharp angular shapes, hot pixel lava flow"
    ),
    "furioso": (
        "dark red and black checkerboard chaos, "
        "sharp spikes and angular fragments, intense pixel destruction"
    ),
    "deprimido": (
        "gray pixel rain falling on dark landscape, "
        "lonely single tree silhouette, overcast blocky sky"
    ),
    "aburrido": (
        "flat empty pixel desert, muted brown blocks, "
        "simple horizon line, sparse scattered dots"
    ),
    "euforico": (
        "bright pixel fireworks bursting on black sky, "
        "colorful star shapes, celebration confetti blocks"
    ),
    "erratico": (
        "glitch pixel mosaic, scrambled color blocks, "
        "broken grid pattern, chaotic pixel noise, static interference"
    ),
}

DEFAULT_NEGATIVE_PROMPT = (
    "photorealistic, photograph, camera, cinematic, film grain, "
    "3d render, smooth gradients, soft focus, depth of field, bokeh, "
    "high detail, intricate, fine texture, realistic lighting, "
    "human faces, fingers, hands, text, watermark, logo, "
    "blurry, deformed, ugly"
)


def build_image_prompt(context: dict[str, Any]) -> tuple[str, str]:
    """
    Construye un prompt artistico para la generacion de fondo.

    Args:
        context: dict con claves:
            - mood_tag: estado emocional actual
            - score_player / score_computer: marcador
            - rally_hits: golpes del rally actual
            - narration_text: ultima narracion del LLM
            - elapsed: tiempo transcurrido
            - dialogue_history: ultimos dialogos

    Returns:
        (prompt, negative_prompt)
    """
    mood = context.get("mood_tag", "neutral")
    style = MOOD_VISUAL_STYLES.get(mood, MOOD_VISUAL_STYLES["neutral"])

    # Contexto competitivo
    score_p = context.get("score_player", 0)
    score_c = context.get("score_computer", 0)
    rally = context.get("rally_hits", 0)

    parts = [ZX_STYLE_PREFIX, style]

    # Intensidad del rally
    if rally > 20:
        parts.append("speed lines, fast pixel streaks, intense scrolling pattern")
    elif rally > 10:
        parts.append("diagonal pixel trails, repeating motion pattern")

    # Dominio del marcador
    if score_p > score_c + 2:
        parts.append("bright golden pixel crown, victory banner, shining star blocks")
    elif score_c > score_p + 2:
        parts.append("dark pixel shadows closing in, oppressive black blocks, cage bars")

    parts.append("retro pixel art style, low resolution, sharp pixels, no anti-aliasing, flat colors")

    prompt = ", ".join(parts)
    return prompt, DEFAULT_NEGATIVE_PROMPT


# ============================================================
# Proceso worker (ejecuta SD en proceso separado con su propio GIL)
# ============================================================

def _detect_device() -> str:
    """Detecta el mejor device disponible para torch: mps > cuda > cpu."""
    try:
        import torch
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return "cpu"


# Mapeo de nombre de scheduler → clase en diffusers
_SCHEDULER_MAP: dict[str, str] = {
    "lcm": "LCMScheduler",
    "euler": "EulerDiscreteScheduler",
    "euler_a": "EulerAncestralDiscreteScheduler",
    "dpm": "DPMSolverMultistepScheduler",
}


def _worker_process_main(
    request_queue: mp.Queue[Any],
    result_queue: mp.Queue[Any],
    stop_event: mp.synchronize.Event,
    log_queue: mp.Queue[Any],
    config_dict: dict[str, Any] | None = None,
) -> None:
    """
    Entry point del proceso worker de Stable Diffusion.

    Corre en un proceso completamente separado con su propio GIL,
    eliminando cualquier bloqueo sobre el hilo principal del juego.

    Args:
        config_dict: Configuracion serializada del modelo de imagen.
                     Si es ``None`` se usan los defaults de ImageModelConfig.
    """
    import torch

    if config_dict is None:
        config_dict = {}

    pipeline_type = config_dict.get("pipeline", "sd15")
    model_id = config_dict.get("model_id", "stablediffusionapi/juggernaut-reborn")
    loras = config_dict.get("loras", [])
    scheduler_type = config_dict.get("scheduler_type", "lcm")
    steps = config_dict.get("steps", 4)
    guidance_scale = config_dict.get("guidance_scale", 1.5)
    gen_width = config_dict.get("width", 512)
    gen_height = config_dict.get("height", 512)

    def _log(msg: str) -> None:
        try:
            log_queue.put_nowait(msg)
        except queue.Full:
            pass

    # --- Seleccionar pipeline ---
    _log(f"Cargando modelo {model_id} (pipeline={pipeline_type})...")
    try:
        IMAGEGEN_CACHE_DIR.mkdir(parents=True, exist_ok=True)

        if pipeline_type == "sdxl":
            from diffusers import StableDiffusionXLPipeline
            pipe = StableDiffusionXLPipeline.from_pretrained(
                model_id,
                torch_dtype=torch.float16,
                cache_dir=str(IMAGEGEN_CACHE_DIR),
            )
        else:  # sd15 (default)
            from diffusers import StableDiffusionPipeline
            pipe = StableDiffusionPipeline.from_pretrained(
                model_id,
                torch_dtype=torch.float32,
                cache_dir=str(IMAGEGEN_CACHE_DIR),
                safety_checker=None,
                requires_safety_checker=False,
            )

        # --- Cargar LoRAs ---
        for lora_cfg in loras:
            lora_id = lora_cfg.get("id", "")
            lora_source = lora_cfg.get("source", "huggingface")
            lora_weight = lora_cfg.get("weight", 1.0)
            _log(f"Cargando LoRA {lora_id} (source={lora_source})...")

            if lora_source in ("local", "civitai"):
                # Ruta local al .safetensors
                pipe.load_lora_weights(lora_id)
            else:
                # HuggingFace repo
                pipe.load_lora_weights(
                    lora_id,
                    cache_dir=str(IMAGEGEN_CACHE_DIR),
                )

            # Aplicar peso si no es 1.0
            if lora_weight != 1.0:
                try:
                    pipe.fuse_lora(lora_scale=lora_weight)
                except (AttributeError, TypeError):
                    pass

        # --- Aplicar scheduler ---
        if scheduler_type != "default":
            scheduler_cls_name = _SCHEDULER_MAP.get(scheduler_type)
            if scheduler_cls_name:
                import diffusers
                scheduler_cls = getattr(diffusers, scheduler_cls_name, None)
                if scheduler_cls is not None:
                    pipe.scheduler = scheduler_cls.from_config(pipe.scheduler.config)

        # --- Mover a device ---
        device = _detect_device()
        _log(f"Moviendo a {device}...")
        pipe.to(device)
        pipe.enable_attention_slicing()
    except (OSError, RuntimeError, ValueError) as e:
        _log(f"PipelineLoadError: {e}")
        return

    # --- Warm-up ---
    device = _detect_device()
    _log(f"Warm-up: compilando kernels {device}...")
    try:
        with torch.inference_mode():
            pipe(
                "warmup test image",
                num_inference_steps=1,
                guidance_scale=1.0,
                width=64,
                height=64,
            )
        if device == "mps":
            torch.mps.empty_cache()
        elif device == "cuda":
            torch.cuda.empty_cache()
        _log("Warm-up completado")
    except RuntimeError as e:
        _log(f"Warm-up fallido (no critico): {e}")

    # Senalar al proceso principal que el modelo esta listo
    _log("__READY__")

    # --- Bucle principal ---
    while not stop_event.is_set():
        try:
            item = request_queue.get(timeout=1.0)
        except queue.Empty:
            continue

        if item is None:
            break  # Senal de shutdown

        prompt, negative_prompt = item
        try:
            _t0 = time.perf_counter()
            with torch.inference_mode():
                result = pipe(
                    prompt,
                    negative_prompt=negative_prompt,
                    num_inference_steps=steps,
                    guidance_scale=guidance_scale,
                    width=gen_width,
                    height=gen_height,
                )
            _sd_dur = time.perf_counter() - _t0
            _log(f"__TIMING__ {_sd_dur:.2f}")
            pil_image = result.images[0]
            if device == "mps":
                torch.mps.empty_cache()
            elif device == "cuda":
                torch.cuda.empty_cache()

            # Debug: guardar imagen si esta habilitado
            if IMAGEGEN_DEBUG_SAVE:
                try:
                    debug_path = IMAGEGEN_CACHE_DIR / "_debug_last.png"
                    pil_image.save(str(debug_path))
                except OSError:
                    pass

            # Convertir PIL -> bytes crudos (en este proceso, con su propio GIL)
            if pil_image.mode != "RGB":
                pil_image = pil_image.convert("RGB")
            raw_bytes = pil_image.tobytes()
            size = pil_image.size

            result_queue.put((raw_bytes, size))
            _log(f"Imagen generada ({size[0]}x{size[1]})")
        except (RuntimeError, ValueError) as e:
            _log(f"ImageGenerationError: {e}")

    _log("Worker process terminado")


# ============================================================
# Clase ImageGenerator (API publica -- misma interfaz que antes)
# ============================================================

class ImageGenerator:
    """
    Motor de generacion de imagenes con Stable Diffusion en proceso separado.

    Uso tipico desde game.py:

        gen = ImageGenerator()
        gen.activate()              # Carga lazy del modelo (proceso de fondo)
        # ... mas tarde ...
        gen.request(prompt, neg)    # Encolar peticion
        # ... cada frame ...
        surface = gen.consume()     # Recoger resultado si hay
        if surface:
            renderer.set_background_image(surface)
    """

    def __init__(self, config: ImageModelConfig | None = None) -> None:
        self._state: str = "idle"  # idle / loading / ready / generating
        self._target_size: tuple[int, int] = (WINDOW_WIDTH, GAME_AREA_HEIGHT)
        self._config = config  # ImageModelConfig o None

        # Primitivas multiprocessing (creadas en activate())
        self._process: mp.process.BaseProcess | None = None
        self._request_queue: mp.Queue[Any] | None = None
        self._result_queue: mp.Queue[Any] | None = None
        self._log_queue: mp.Queue[Any] | None = None
        self._stop_event: mp.synchronize.Event | None = None

        # Funcion de log externa (inyectada desde Game)
        self._log_fn: Callable[[str, str], None] | None = None

        # Metricas de rendimiento (opcional)
        self._perf: Any = None

    @property
    def state(self) -> str:
        return self._state

    @property
    def is_ready(self) -> bool:
        return self._state in ("ready", "generating")

    def set_perf(self, perf: Any) -> None:
        """Inyecta el recolector de metricas de rendimiento."""
        self._perf = perf

    def set_log_fn(self, fn: Callable[[str, str], None]) -> None:
        """Inyecta funcion de log desde Game."""
        self._log_fn = fn

    def _log(self, msg: str) -> None:
        if self._log_fn:
            self._log_fn("IMAGEGEN", msg)
        logger.info(msg)

    def _serialize_config(self) -> dict[str, Any]:
        """Serializa la config a un dict plano para pasar al proceso worker."""
        cfg = self._config
        if cfg is None:
            return {}
        return {
            "pipeline": cfg.pipeline,
            "model_id": cfg.model_id,
            "loras": [
                {"id": l.id, "source": l.source, "weight": l.weight}
                for l in cfg.loras
            ],
            "scheduler_type": cfg.scheduler_type,
            "steps": cfg.steps,
            "guidance_scale": cfg.guidance_scale,
            "width": cfg.width,
            "height": cfg.height,
        }

    def activate(self) -> None:
        """Inicia la carga lazy del modelo en un proceso separado."""
        if self._state != "idle":
            return
        self._state = "loading"

        # Contexto 'spawn' obligatorio en macOS con MPS para evitar deadlocks
        ctx = mp.get_context("spawn")
        self._request_queue = ctx.Queue(maxsize=1)
        self._result_queue = ctx.Queue(maxsize=2)
        self._log_queue = ctx.Queue(maxsize=50)
        self._stop_event = ctx.Event()

        self._process = ctx.Process(
            target=_worker_process_main,
            args=(
                self._request_queue,
                self._result_queue,
                self._stop_event,
                self._log_queue,
                self._serialize_config(),
            ),
            daemon=True,
        )
        assert self._process is not None
        self._process.start()
        self._log("Cargando modelo de difusion (proceso separado)...")

    def request(self, prompt: str, negative_prompt: str = "") -> None:
        """
        Encola una peticion de generacion de imagen.

        Si ya hay una peticion pendiente en la cola, la descarta
        y pone la nueva (solo nos interesa la mas reciente).
        """
        if self._state not in ("ready", "generating"):
            return

        # Vaciar cola (descartar peticion obsoleta)
        if self._request_queue is None:
            return
        try:
            self._request_queue.get_nowait()
        except queue.Empty:
            pass

        try:
            self._request_queue.put_nowait((prompt, negative_prompt))
        except queue.Full:
            pass

    def consume(self) -> pygame.Surface | None:
        """
        Devuelve la imagen generada mas reciente si hay alguna nueva.

        Llamar cada frame desde game.py. Tambien drena mensajes de log
        del proceso worker y detecta la transicion loading -> ready.

        Returns:
            pygame.Surface escalada al tamano del area de juego, o None.
        """
        # 1. Drenar mensajes de log del worker
        if self._log_queue is not None:
            while True:
                try:
                    msg = self._log_queue.get_nowait()
                except queue.Empty:
                    break
                if msg == "__READY__":
                    self._state = "ready"
                    self._log("Modelo de difusion listo")
                elif isinstance(msg, str) and msg.startswith("__TIMING__ "):
                    try:
                        dur = float(msg.split(" ", 1)[1])
                        if self._perf:
                            self._perf.record_sd(dur)
                    except (ValueError, IndexError):
                        pass
                else:
                    self._log(msg)

        # 2. Comprobar si hay imagen lista
        if self._result_queue is None:
            return None
        try:
            raw_bytes, size = self._result_queue.get_nowait()
        except queue.Empty:
            return None

        # 3. Convertir bytes -> pygame.Surface en el hilo principal (~0.5ms)
        import pygame
        surface = pygame.image.fromstring(raw_bytes, size, "RGB")
        return pygame.transform.smoothscale(surface, self._target_size)

    def shutdown(self) -> None:
        """Detiene el proceso de fondo y libera recursos."""
        if self._stop_event is not None:
            self._stop_event.set()
        # Desbloquear el worker si esta esperando en la cola
        if self._request_queue is not None:
            try:
                self._request_queue.put_nowait(None)
            except queue.Full:
                pass
        if self._process is not None and self._process.is_alive():
            self._process.join(timeout=5.0)
            if self._process.is_alive():
                self._process.terminate()
        self._process = None
        self._state = "idle"
        self._log("Motor de imagen detenido")
