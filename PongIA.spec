# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = ['pong', 'pong.__init__', 'pong.config', 'pong.config.__init__', 'pong.config.layout', 'pong.config.colors', 'pong.config.gameplay', 'pong.config.media', 'pong.config.models', 'pong.config.narrator', 'pong.config.version', 'pong.config.zx_spectrum', 'pong.config.ui_end_screen', 'pong.config.ui_achievements', 'pong.entities', 'pong.sound', 'pong.music', 'pong.game', 'pong.game_ai', 'pong.game_persistence', 'pong.game_imagegen', 'pong.scoring', 'pong.narrator', 'pong.narrator_questions', 'pong.narrator_summary', 'pong.narration_bridge', 'pong.renderer', 'pong.renderer_achievements', 'pong.renderer_end_screen', 'pong.image_generator', 'pong.providers', 'pong.save_manager', 'pong.emotional_state', 'pong.achievements', 'pong.achievement_icons', 'pong.splash', 'pong.theme', 'pong.question_system', 'pong.perf', 'pong.harness', 'pong.exceptions', 'pong.protocols', 'llama_cpp', 'mido', 'mido.backends', 'mido.backends.backend_python', 'tomli', 'torch', 'torch.utils', 'torch.utils.data', 'diffusers', 'diffusers.pipelines.stable_diffusion', 'diffusers.pipelines.stable_diffusion_xl', 'diffusers.schedulers', 'transformers', 'transformers.models.clip', 'transformers.models.auto', 'accelerate', 'safetensors', 'peft', 'huggingface_hub']
hiddenimports += collect_submodules('diffusers.schedulers')
hiddenimports += collect_submodules('torch.backends')


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('assets', 'assets')],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'xmlrpc', 'doctest', 'distutils', 'torch.cuda', 'torch.distributed', 'torch.testing', 'torch.utils.tensorboard', 'torch.utils.bottleneck', 'torch.utils.benchmark'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PongIA',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=True,
    upx=True,
    upx_exclude=[],
    name='PongIA',
)
app = BUNDLE(
    coll,
    name='PongIA.app',
    icon=None,
    bundle_identifier='com.pongia.app',
)
