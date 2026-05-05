"""Tests para pong/config/models.py — parseo de models.toml."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pong.config.models import (
    ImageModelConfig,
    LLMModelConfig,
    LoRAConfig,
    load_models_config,
    save_llm_config,
)


class TestDefaults(unittest.TestCase):
    """Sin models.toml, se devuelven los defaults."""

    def test_defaults_without_file(self) -> None:
        llm, image = load_models_config(Path("/tmp/nonexistent_models.toml"))
        self.assertEqual(llm.filename, "qwen2.5-3b-instruct-q4_k_m.gguf")
        self.assertEqual(llm.context_window, 4096)
        self.assertEqual(llm.threads, 4)
        self.assertEqual(image.pipeline, "sd15")
        self.assertEqual(image.model_id, "stablediffusionapi/juggernaut-reborn")
        self.assertEqual(len(image.loras), 1)
        self.assertEqual(image.loras[0].id, "latent-consistency/lcm-lora-sdv1-5")


class TestParseToml(unittest.TestCase):
    """Parsea models.toml con valores custom."""

    def test_custom_llm(self) -> None:
        toml_content = b"""
[llm]
filename = "llama-3.2-3b-instruct-q4_k_m.gguf"
context_window = 8192
threads = 6
display_name = "Llama 3.2 3B"
"""
        with tempfile.NamedTemporaryFile(suffix=".toml", delete=False) as f:
            f.write(toml_content)
            f.flush()
            llm, _ = load_models_config(Path(f.name))

        self.assertEqual(llm.filename, "llama-3.2-3b-instruct-q4_k_m.gguf")
        self.assertEqual(llm.context_window, 8192)
        self.assertEqual(llm.threads, 6)
        self.assertEqual(llm.display_name, "Llama 3.2 3B")
        self.assertEqual(llm.resolved_display_name, "Llama 3.2 3B")

    def test_custom_image_with_loras(self) -> None:
        toml_content = b"""
[image]
pipeline = "sdxl"
model_id = "stabilityai/stable-diffusion-xl-base-1.0"
steps = 25
guidance_scale = 7.0
width = 1024
height = 1024

[[image.loras]]
id = "some-lora/repo"
source = "huggingface"
weight = 0.8

[[image.loras]]
id = "/local/path/style.safetensors"
source = "local"

[image.scheduler]
type = "euler_a"
"""
        with tempfile.NamedTemporaryFile(suffix=".toml", delete=False) as f:
            f.write(toml_content)
            f.flush()
            _, image = load_models_config(Path(f.name))

        self.assertEqual(image.pipeline, "sdxl")
        self.assertEqual(image.model_id, "stabilityai/stable-diffusion-xl-base-1.0")
        self.assertEqual(image.steps, 25)
        self.assertEqual(image.guidance_scale, 7.0)
        self.assertEqual(image.width, 1024)
        self.assertEqual(len(image.loras), 2)
        self.assertEqual(image.loras[0].weight, 0.8)
        self.assertEqual(image.loras[1].source, "local")
        self.assertEqual(image.scheduler_type, "euler_a")

    def test_partial_override_keeps_defaults(self) -> None:
        toml_content = b"""
[llm]
filename = "other.gguf"
"""
        with tempfile.NamedTemporaryFile(suffix=".toml", delete=False) as f:
            f.write(toml_content)
            f.flush()
            llm, image = load_models_config(Path(f.name))

        self.assertEqual(llm.filename, "other.gguf")
        self.assertEqual(llm.context_window, 4096)  # default
        # Image should be fully default
        self.assertEqual(image.model_id, "stablediffusionapi/juggernaut-reborn")

    def test_empty_loras_list(self) -> None:
        toml_content = b"""
[image]
model_id = "test/model"
loras = []
"""
        with tempfile.NamedTemporaryFile(suffix=".toml", delete=False) as f:
            f.write(toml_content)
            f.flush()
            _, image = load_models_config(Path(f.name))

        self.assertEqual(len(image.loras), 0)

    def test_display_name_fallback(self) -> None:
        config = LLMModelConfig(filename="qwen2.5-3b-instruct-q4_k_m.gguf")
        self.assertEqual(
            config.resolved_display_name, "qwen2.5-3b-instruct-q4_k_m"
        )


class TestSaveLLMConfig(unittest.TestCase):
    """Tests para save_llm_config."""

    def test_save_creates_file(self) -> None:
        config = LLMModelConfig(
            filename="test-model.gguf",
            download_url="https://example.com/test.gguf",
            context_window=8192,
            threads=8,
            display_name="Test Model",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "models.toml"
            save_llm_config(config, path)
            self.assertTrue(path.exists())
            content = path.read_text()
            self.assertIn("[llm]", content)
            self.assertIn('filename = "test-model.gguf"', content)
            self.assertIn("context_window = 8192", content)
            self.assertIn("threads = 8", content)
            self.assertIn('display_name = "Test Model"', content)

    def test_save_roundtrip(self) -> None:
        config = LLMModelConfig(
            filename="roundtrip.gguf",
            download_url="https://example.com/rt.gguf",
            context_window=4096,
            threads=4,
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "models.toml"
            save_llm_config(config, path)
            llm, _ = load_models_config(path)
            self.assertEqual(llm.filename, "roundtrip.gguf")
            self.assertEqual(llm.context_window, 4096)
            self.assertEqual(llm.threads, 4)

    def test_save_preserves_image_section(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "models.toml"
            # Write initial file with image section
            path.write_text(
                '[llm]\nfilename = "old.gguf"\n\n'
                '[image]\nmodel_id = "test/model"\nsteps = 4\n',
                encoding="utf-8",
            )
            # Save new LLM config
            new_config = LLMModelConfig(filename="new.gguf")
            save_llm_config(new_config, path)

            content = path.read_text()
            self.assertIn('filename = "new.gguf"', content)
            self.assertIn("[image]", content)
            self.assertIn('model_id = "test/model"', content)
            self.assertIn("steps = 4", content)

    def test_save_without_display_name(self) -> None:
        config = LLMModelConfig(filename="nodisplay.gguf")
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "models.toml"
            save_llm_config(config, path)
            content = path.read_text()
            self.assertNotIn("display_name", content)

    def test_save_preserves_image_loras_and_scheduler(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "models.toml"
            path.write_text(
                '[llm]\nfilename = "old.gguf"\n\n'
                "[image]\n"
                'model_id = "test/model"\n'
                "steps = 4\n\n"
                "[image.scheduler]\n"
                'type = "LCM"\n\n'
                "[[image.loras]]\n"
                'repo_id = "test/lora"\n'
                "weight = 0.8\n",
                encoding="utf-8",
            )
            new_config = LLMModelConfig(filename="new.gguf")
            save_llm_config(new_config, path)

            content = path.read_text()
            self.assertIn("[image.scheduler]", content)
            self.assertIn("[[image.loras]]", content)
            self.assertIn('repo_id = "test/lora"', content)


if __name__ == "__main__":
    unittest.main()
