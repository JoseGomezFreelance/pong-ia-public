# Generar ejecutables de PongIA

Guía completa para empaquetar PongIA como aplicación nativa
(`.app` en macOS, `.exe` en Windows) con todas las funcionalidades de IA.

## Requisitos previos

### Dependencias de build

```bash
python3 -m pip install pyinstaller pygame mido tomli
```

### Dependencias de IA (opcionales pero recomendadas)

Para incluir narración IA y generación de imágenes en el ejecutable:

```bash
python3 -m pip install llama-cpp-python torch diffusers transformers accelerate safetensors peft huggingface_hub
```

El script de build detecta automáticamente qué paquetes están instalados
e incluye solo los disponibles.

### Anaconda: eliminar `pathlib` obsoleto

Si usas Anaconda, el paquete `pathlib` (backport obsoleto de Python 2)
es incompatible con PyInstaller. Elimínalo antes de construir:

```bash
pip uninstall pathlib -y
```

## Build paso a paso

### 1. Ejecutar el script de build

```bash
python3 scripts/build_with_pyinstaller.py
```

Opciones disponibles:

| Flag        | Efecto                                              |
|-------------|-----------------------------------------------------|
| `--onefile` | Genera un único binario (más lento al arrancar)     |
| `--target`  | `auto` (defecto), `mac`, `win`, `linux`             |

En macOS genera `dist/PongIA.app` (modo directorio, arranque rápido).
En Windows genera `dist/PongIA.exe` (modo `--onefile` por defecto).

### 2. Layout de distribución

Tras el build, organiza la carpeta `dist/` así:

```
dist/
  PongIA.app/                               # El ejecutable
  models/
    qwen2.5-3b-instruct-q4_k_m.gguf        # Modelo LLM (narración)
    diffusion/                               # Cache HuggingFace (auto)
  models.toml                                # Config de modelos (opcional)
  saves/                                     # Partidas guardadas (auto)
```

- **models/**: coloca el archivo GGUF junto al `.app`. El ejecutable
  busca el modelo en esta carpeta automáticamente.
- **models.toml**: copia de `models.toml.example` para personalizar
  modelos de IA. Si no existe, usa los defaults.
- **saves/**: se crea automáticamente en la primera partida.

### 3. Probar el ejecutable

```bash
open dist/PongIA.app          # macOS
dist\PongIA.exe               # Windows
```

Para diagnosticar errores, ejecuta el binario desde terminal:

```bash
# macOS
/ruta/a/dist/PongIA.app/Contents/MacOS/PongIA

# Windows
dist\PongIA.exe
```

Esto muestra los errores por stderr en vez de fallar silenciosamente.

## Qué incluye el script de build

El script `scripts/build_with_pyinstaller.py` configura PyInstaller con:

### Assets empaquetados (`--add-data`)

- `assets/music/main_theme.mid` — tema MIDI sintetizado en runtime
- `assets/images/` — iconos de logros y arte del juego

### Hidden imports

PyInstaller no detecta automáticamente las importaciones dinámicas.
El script incluye explícitamente:

- **Todos los módulos de `pong/`** y `pong/config/`
- **llama_cpp** — cargado via `importlib.import_module()` en `providers.py`
- **mido** — importado dentro de `music.py` con `try/except`
- **torch, diffusers, transformers** — cargados en el worker de generación
  de imágenes (proceso separado con `multiprocessing.spawn`)
- **accelerate, safetensors, peft, huggingface_hub** — dependencias
  indirectas de diffusers/transformers

### Exclusiones para reducir tamaño

- `tkinter`, `xmlrpc`, `doctest`, `distutils` — no usados
- En macOS: `torch.cuda`, `torch.distributed`, `torch.testing`,
  `torch.utils.tensorboard` — sin GPU NVIDIA en Mac

### Tamaño resultante

| Configuración            | Tamaño aprox.  |
|--------------------------|----------------|
| Solo juego + música      | ~150 MB        |
| Con llama-cpp            | ~200 MB        |
| Completo (torch+diffusers) | ~1.2 GB     |

Los modelos de IA (GGUF, diffusion) van **aparte** del ejecutable
y no cuentan en estas cifras.

## Arquitectura de rutas para PyInstaller

PyInstaller empaqueta el código Python en un directorio temporal
(`sys._MEIPASS`) que es de solo lectura. Esto requiere resolver
las rutas de forma diferente según el contexto:

### Assets de solo lectura (música, imágenes)

`pong/config/media.py` usa `_resolve_asset_path()`:

1. Si `sys._MEIPASS` existe → busca en `_MEIPASS/assets/...`
2. Si no → busca relativo a la raíz del proyecto

### Directorios escribibles (saves, cache de modelos)

`pong/config/media.py` usa `_resolve_writable_dir()` y
`pong/save_manager.py` usa `_resolve_save_dir()`:

1. Si `sys.frozen` es `True` (ejecutable empaquetado):
   - En macOS `.app`: resuelve junto al bundle
     (`Contents/MacOS/` → `../../..` → carpeta padre del `.app`)
   - En otros: junto al ejecutable
2. Si no → ruta relativa normal (desarrollo)

### Configuración (`models.toml`)

`pong/config/models.py` aplica la misma lógica frozen-aware para
encontrar `models.toml` junto al `.app` en vez de dentro de `_MEIPASS`.

### Modelo LLM

`pong/providers.py` ya tenía resolución de rutas compatible con
PyInstaller desde antes (busca en `sys.executable`, `_MEIPASS`,
estructura `.app`, variable de entorno `PONG_IA_MODEL_PATH`).

## Generar instalador DMG (macOS)

Tras el build, puedes crear un `.dmg` con drag & drop a Applications:

```bash
./scripts/create_dmg.sh   # → dist/PongIA.dmg (~416 MB comprimido)
```

No requiere dependencias externas (`hdiutil` viene con macOS).


## Generar instalador y ZIP para Windows

Tras el build en Windows, puedes crear dos formatos de distribución:

### ZIP para itch.io (sin dependencias extra)

```bash
python scripts/create_zip_win.py   # → dist/PongIA_Alfa_0.07.zip
```

Crea un ZIP con la estructura estándar para itch.io:

```
PongIA/
  PongIA.exe
  models.toml.example
  LICENSE
  models/          # vacio, se llena al descargar modelos in-game
  saves/           # vacio, se crea en la primera partida
```

La app de itch.io auto-extrae ZIPs y lanza el ejecutable directamente.
No requiere dependencias externas (usa `zipfile` de la stdlib de Python).

### Instalador con Inno Setup (para distribución directa)

Requisito: instalar [Inno Setup 6](https://jrsoftware.org/isdownload.php)
(gratuito, open-source, ~3 MB).

```bash
iscc /DAppVersion="Alfa 0.07" scripts\create_installer_win.iss
# → dist/PongIA_Setup.exe
```

El instalador genera:
- Asistente "Next → Next → Install"
- Acceso directo en escritorio (opcional)
- Entrada en menu Inicio
- Desinstalador en "Agregar o quitar programas"
- Instalación sin admin por defecto (`%LOCALAPPDATA%\Programs\PongIA`)


## Build automático con GitHub Actions

El workflow `.github/workflows/build-binaries.yml` construye
automáticamente para macOS y Windows en los servidores de GitHub,
sin necesidad de tener ambos sistemas operativos.

### Cómo se ejecuta

- **Manualmente**: en tu repo en GitHub → pestaña **Actions** →
  **Build executables** → **Run workflow** → click
- **Automáticamente**: al hacer push de un tag con formato `v*`:
  ```bash
  git tag v0.1.0
  git push origin v0.1.0
  ```

### Artefactos generados

El workflow lanza dos maquinas en paralelo (macOS y Windows) y sube:
- `pong-ia-macos-app` (`PongIA.app`)
- `pong-ia-macos-dmg` (`PongIA.dmg`)
- `pong-ia-windows-exe` (`PongIA.exe`)
- `pong-ia-windows-zip` (`PongIA_Alfa_0.07.zip` — para itch.io)
- `pong-ia-windows-setup` (`PongIA_Setup.exe` — instalador Inno Setup)

### Cómo descargar los ejecutables

1. Ve a tu repo en GitHub → pestaña **Actions**
2. Click en la ejecución del workflow que te interese
3. En la parte inferior de la página, sección **Artifacts**, descarga
   el archivo `.zip` correspondiente

### Limitaciones del build en Actions

El workflow actual instala solo las dependencias básicas:
- `pygame` — motor del juego
- `llama-cpp-python` (opcional, `continue-on-error`) — narración local

**No incluye** torch, diffusers, transformers ni el resto del stack de IA.
Los ejecutables generados por Actions funcionan perfectamente para jugar,
pero no tendrán generación de imágenes con IA.

Para un build completo con todas las funcionalidades de IA, sigue el
proceso manual descrito en las secciones anteriores de este documento.

## Troubleshooting

### `No module named 'pydoc'`

Causado por `nltk` (dependencia transitiva de transformers).
No excluir `pydoc` en el script de build.

### `No module named 'unittest'`

`pong/harness.py` usa `unittest.mock.patch`.
No excluir `unittest` en el script de build.

### `pathlib is an obsolete backport`

Anaconda instala un paquete `pathlib` de Python 2 que es incompatible
con PyInstaller. Elimínalo con `pip uninstall pathlib -y`.

### Gatekeeper en macOS

La primera vez que abras el `.app`, macOS puede bloquearlo porque
no está firmado con un certificado de Apple. Solución:

1. Clic derecho sobre `PongIA.app` → **Abrir**
2. O desde terminal: `xattr -cr dist/PongIA.app`

### El ejecutable no encuentra el modelo GGUF

Asegúrate de que el modelo está en `dist/models/` (junto al `.app`),
o define la variable de entorno `PONG_IA_MODEL_PATH` con la ruta absoluta.
