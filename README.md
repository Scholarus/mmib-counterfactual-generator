---
title: MMB Counterfactual Image Tool
colorFrom: blue
colorTo: indigo
sdk: docker
pinned: false
license: mit
short_description: CLEVR-style scenes with semantic and negative counterfactuals
---

Generate CLEVR-style scene triplets (original, semantic counterfactual, perturbation) with Blender, plus questions and a 3×3 answer matrix for the MMIB VQA benchmark. Configurable object counts, counterfactual types, and automated questions and answers.

**Key Features:**
- 17 different counterfactual types (9 image CFs + 8 negative CFs)
- Automated Blender rendering with GPU support
- Question-answer datasets
- Resume support for interrupted jobs
- Streamlit web interface
- Examples for all counterfactual types

## Hugging Face Spaces Deployment

This app is configured to run on Hugging Face Spaces using Docker. The Dockerfile includes Blender installation and all necessary dependencies for scenes and rendering.

## Features

- **Scenes**: Multiple scene sets with configurable object counts and properties
- **Counterfactual Variants**: Create multiple counterfactual variations per scene (color, shape, material, size changes)
- **Blender Rendering**: Automated rendering of scenes to PNG images using Blender's Cycles engine
- **Questions**: Counterfactual questions and answers for each scene set
- **Resume Support**: Resume interrupted rendering jobs

## Requirements

### Python Dependencies

Install Python dependencies using:

```bash
pip install -r requirements.txt
```

### Blender

Blender must be installed separately as it's not available via pip. The scripts are designed to run inside Blender's Python environment using:

```bash
blender --background --python <script.py> -- [arguments]
```

The pipeline will attempt to auto-detect Blender on your system, or you can specify the path manually.

## Installation

1. Clone this repository:
```bash
git clone <repository-url>
cd code
```

2. Install Python dependencies:
```bash
pip install -r requirements.txt
```

3. Ensure Blender is installed and accessible in your PATH, or note the path for manual specification.

## Usage

### Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Generate 5 scene sets with 5 objects each
python pipeline.py --num_scenes 5 --num_objects 5 --run_name my_first_run

# Generate examples of all counterfactual types
python scripts/generate_examples.py --render
```

### Web Interface (Streamlit)

Run the Streamlit web interface for an interactive experience:

```bash
streamlit run app.py
```

The web interface provides:
- Interactive parameter configuration
- Real-time progress
- Visual output preview
- Downloadable results as ZIP files

### 1. Generate and Render (Combined)

Use `python pipeline.py` to generate scene JSON files and render PNG images in one step:

```bash
python pipeline.py --num_scenes 10 --num_objects 5 --run_name experiment1
```

### 2. Generate Only (Skip Rendering)

Generate scenes without rendering:

```bash
python pipeline.py --num_scenes 10 --num_objects 5 --run_name experiment1 --skip_render
```

### 4. Render Existing Scenes Only

Render previously generated scene JSON files:

```bash
# Render scenes from a specific run
python pipeline.py --render_only --run_name experiment1

# Auto-detect latest run
python pipeline.py --render_only --auto_latest

# Use GPU rendering
python pipeline.py --render_only --run_name experiment1 --use_gpu 1
```

This allows you to:
- Generate scenes on one machine, render on another
- Generate many scenes, then render them in batches
- Re-render scenes with different settings (GPU/CPU, samples, resolution) without regenerating

### 5. Generating Scenes and Images (Full Options)

#### Arguments

| Argument                  | Default       | Description                                                                  |
| ------------------------- | ------------- | ---------------------------------------------------------------------------- |
| `--num_scenes`            | 5             | Number of scene sets to generate                                             |
| `--num_objects`           | None          | Fixed number of objects per scene (overrides min/max)                        |
| `--min_objects`           | 3             | Minimum object count (if `num_objects` not given)                            |
| `--max_objects`           | 7             | Maximum object count (if `num_objects` not given)                            |
| `--num_counterfactuals`   | 2             | Number of counterfactual variants per scene                                  |
| `--blender_path`          | auto-detected | Path to Blender executable                                                   |
| `--output_dir`            | `output`      | Base directory for all runs (each run gets a timestamped/named subfolder)    |
| `--run_name`              | None          | Optional custom name for this run (creates `output/run_name/`)               |
| `--use_gpu`               | 0             | 1 = enable GPU rendering, 0 = CPU rendering                                  |
| `--samples`               | 512           | Cycles sampling rate (higher = better quality, slower)                       |
| `--width`                 | 320           | Image width in pixels                                                        |
| `--height`                | 240           | Image height in pixels                                                       |
| `--skip_render`           | False         | Generate scenes only (JSON only, no PNG rendering)                           |
| `--render_only`           | False         | Only render existing scene JSON files. Requires --run_dir, --run_name, or --auto_latest |
| `--run_dir`               | None          | Run directory containing scenes/ folder (for --render_only mode)             |
| `--auto_latest`           | False         | Automatically use the latest run in output_dir (for --render_only mode)      |
| `--resume`                | False         | Resume from where it stopped in an existing run                              |
| `--cf_types`              | None          | Explicitly choose which counterfactual types are used (order is respected; cycles if needed) |
| `--same_cf_type`          | False         | Use the same counterfactual type for all variants (first in `--cf_types`, or one random if unset) |
| `--list_cf_types`         | False         | Print available counterfactual types and exit                                |
| `--min_cf_change_score`   | 1.0           | Minimum heuristic change score (retries CF until it’s “noticeable” enough) |
| `--max_cf_attempts`       | 10            | Max retries per counterfactual to reach `--min_cf_change_score`               |

#### Examples

```bash
# Generate 10 scene sets with 5 objects each
python3 pipeline.py --num_scenes 10 --num_objects 5 --run_name experiment1

# Generate 10 scene sets with 3-7 objects, using GPU
python3 pipeline.py --num_scenes 10 --min_objects 3 --max_objects 7 --use_gpu 1

# Resume from where it stopped
python3 pipeline.py --num_scenes 100 --run_name experiment1 --resume

# Generate scenes only (no rendering)
python3 pipeline.py --num_scenes 10 --skip_render

# List available counterfactual types
python3 pipeline.py --list_cf_types

# Force specific counterfactual types in order (CF1 then CF2)
python3 pipeline.py --num_scenes 10 --num_counterfactuals 2 --cf_types change_color add_noise
# All counterfactuals same type (e.g. both change_color):
python3 pipeline.py --num_scenes 10 --num_counterfactuals 2 --cf_types change_color --same_cf_type

# Make counterfactuals more noticeable (stricter threshold + more retries)
python3 pipeline.py --num_scenes 10 --min_cf_change_score 1.5 --max_cf_attempts 25
```

#### Counterfactual Types

The pipeline supports 17 different counterfactual types, divided into two categories:

**Image Counterfactuals** (Should change VQA answers - 10 types):
- `change_color` - Change the color of a random object (e.g., red → blue)
- `change_shape` - Change the shape of a random object (cube/sphere/cylinder)
- `change_size` - Change the size of a random object (small ↔ large)
- `change_material` - Change the material of a random object (metal ↔ rubber)
- `change_position` - Move a random object to a different location (with collision detection)
- `add_object` - Add a new random object to the scene
- `remove_object` - Remove a random object from the scene
- `replace_object` - Replace an object with a different one (keeping position)
- `swap_attribute` - Swap an attribute (e.g. color) between two objects
- `relational_flip` - Move object from left of X to right of X

**Negative Counterfactuals** (Should NOT change VQA answers - 8 types):
- `change_background` - Change the background/ground color
- `change_lighting` - Change lighting conditions (bright/dim/warm/cool/dramatic)
- `add_noise` - Add image noise/grain (light/medium/heavy levels)
- `occlusion_change` - Move object to partially hide another (visual only; answers unchanged)
- `apply_fisheye` - Apply fisheye lens distortion effect
- `apply_blur` - Apply Gaussian blur filter
- `apply_vignette` - Apply vignette effect (edge darkening)
- `apply_chromatic_aberration` - Apply chromatic aberration (color fringing)

**Default Behavior**: If `--cf_types` is not specified, the pipeline uses a default mix of 1 image counterfactual + 1 negative counterfactual per scene.

**Usage Examples**:
```bash
# List all available counterfactual types
python3 pipeline.py --list_cf_types

# Use specific counterfactual types (order is respected; cycles if needed)
python3 pipeline.py --num_scenes 10 --num_counterfactuals 2 --cf_types change_color change_position

# Mix image and negative counterfactuals
python3 pipeline.py --num_scenes 10 --cf_types change_shape change_lighting add_noise

# Use only negative counterfactuals
python3 pipeline.py --num_scenes 10 --cf_types change_background add_noise apply_blur

# Use only image counterfactuals
python3 pipeline.py --num_scenes 10 --cf_types change_color change_shape change_position
```

### 2. Generating Example Counterfactuals

Generate examples of all counterfactual types applied to a base scene:

```bash
# Generate scene JSON files only
python scripts/generate_examples.py

# Generate and render to images
python scripts/generate_examples.py --render

# Customize output directory and number of objects
python scripts/generate_examples.py --render --output_dir output/my_examples --num_objects 7

# Use GPU rendering
python scripts/generate_examples.py --render --use_gpu 1
```

This creates one example of each counterfactual type in `output/counterfactual_examples/`:
- Original scene
- 9 image counterfactual examples
- 8 negative counterfactual examples

### 3. Generating Question Mappings

Use `scripts/generate_questions_mapping.py` to create a CSV with counterfactual questions and answers.

#### Arguments

| Argument               | Default                            | Description                                                                      |
| ---------------------- | ---------------------------------- | -------------------------------------------------------------------------------- |
| `--output_dir`         | `output`                           | Run directory or base output directory                                           |
| `--auto_latest`        | False                              | Automatically find and use the latest run in `output_dir`                        |
| `--csv_name`           | `image_mapping_with_questions.csv` | Name of the generated CSV file                                                   |
| `--generate_questions` | False                              | Generate questions and answers (without this flag, only outputs image filenames) |
| `--long_format`        | False                              | Also output a long-format QA dataset CSV (one row per image-question pair)       |
| `--long_csv_name`      | `qa_dataset.csv`                   | Filename for the long-format QA dataset CSV                                      |

#### Examples

```bash
# Generate questions for a specific run
python scripts/generate_questions_mapping.py --output_dir output/experiment1 --generate_questions

# Auto-detect latest run and generate questions
python scripts/generate_questions_mapping.py --output_dir output --auto_latest --generate_questions

# Also generate a long-format QA dataset (includes correct answer labels/ids)
python scripts/generate_questions_mapping.py --output_dir output --auto_latest --generate_questions --long_format --long_csv_name qa_dataset.csv
```

#### Ensuring counterfactual answers differ

For evaluation and datasets, the **counterfactual image’s answer to its counterfactual question** should differ from the **original image’s answer to the original question**. The pipeline does this in two ways:

1. **Automatic retries**  
   When generating questions (with `--generate_questions`), the script retries up to **`MAX_CF_ANSWER_RETRIES`** (default 50) per scene. For each attempt it picks new counterfactual questions (with different randomness). It keeps a pair only when both CF1 and CF2 answers differ from the original answer (after normalizing, e.g. case and whitespace). If after all retries they still match, the scene is still included and a warning is printed.

2. **CF-specific question templates**  
   Counterfactual questions are chosen from templates that target the **changed** attribute or count, so the answer on the counterfactual image is different by design:
   - **Count-changing CFs** (e.g. `add_object`, `remove_object`): questions like “How many objects are in the scene?” or “Are there more than N objects?” so the count/yes-no differs.
   - **Attribute-changing CFs** (e.g. `change_color`, `change_shape`): questions about the **new** value (e.g. “How many red objects?” when an object was changed to red), so the count on the CF image differs from the original.

**What you need to do:**

- Run question generation **after** scenes and images exist (either as part of the pipeline with `--generate_questions`, or later on a run directory):

  ```bash
  # As part of a full run (ensures answers differ for that run’s scenes)
  python pipeline.py --num_scenes 10 --num_objects 5 --run_name my_run --generate_questions

  # Or later, on an existing run
  python scripts/generate_questions_mapping.py --output_dir output/my_run --generate_questions
  ```

- **Optional:** To allow more attempts per scene, edit `scripts/generate_questions_mapping.py` and increase **`MAX_CF_ANSWER_RETRIES`** (e.g. from 50 to 100). No CLI flag is exposed for this.

**720p dataset with different answers (distinct CF types per scene):**

- Scenes use **two distinct counterfactual types** per scene (no duplicate CF type for CF1 and CF2). To generate a 720p (1280×720) set with question/answer validation and optional removal of scenes where the CF answer matches the original:

  ```bash
  python pipeline.py --num_scenes 1000 --output_dir output --run_name dataset_720p_diff --width 1280 --height 720 --semantic_only --num_counterfactuals 2 --generate_questions --filter_same_answer
  ```

- This produces `output/dataset_720p_diff/` with scene sets where CF1 and CF2 use different types, questions are validated (original + CFs), and rows where the CF image’s answer to the CF question matches the original are removed. Increase `MAX_CF_ANSWER_RETRIES` in `scripts/generate_questions_mapping.py` if you want fewer “could not find valid questions” warnings.


## Project Structure

```
.
├── pipeline.py                     # Main pipeline and rendering (supports --render_only)
├── app.py                         # Streamlit web interface
├── requirements.txt                # Python dependencies
├── data/                           # Scene assets
│   ├── base_scene.blend           # Base Blender scene
│   ├── CoGenT_A.json              # Scene configuration A
│   ├── CoGenT_B.json              # Scene configuration B
│   ├── properties.json            # Object properties configuration
│   ├── materials/                 # Material definitions
│   └── shapes/                    # 3D shape definitions
├── scripts/                        # Scripts directory
│   ├── render.py                  # Blender rendering script (run by pipeline)
│   ├── generate_scenes.py         # Generate scene JSON files only (alternative to --skip_render)
│   ├── generate_examples.py       # Generate example counterfactuals
│   └── generate_questions_mapping.py  # Generate question-answer datasets
├── output/                         # Output directory (generated)
│   └── counterfactual_examples/    # Example counterfactuals (from generate_examples.py)
├── .gitignore                     # Git ignore rules
└── README.md                      # This file

**Note**: The pipeline dynamically generates temporary files during execution:
- `render_images_patched.py` - Patched rendering script
- `temp_output/<run_id>/` - Temporary output per run (e.g. `temp_output/2025-01-29_12-30-45/images` and `.../scenes`), so different runs use separate directories and do not overwrite each other.

These files are automatically created when needed, cleaned up after use, and are ignored by git.
```

## Output Structure

Each run creates a directory structure like:

```
output/
└── <run_name_or_timestamp>/
    ├── checkpoint.json
    ├── run_metadata.json
    ├── scenes/
    │   ├── scene_0000_original.json
    │   ├── scene_0000_cf1.json
    │   ├── scene_0000_cf2.json
    │   └── ...
    ├── images/
    │   ├── scene_0000_original.png
    │   ├── scene_0000_cf1.png
    │   ├── scene_0000_cf2.png
    │   └── ...
    ├── image_mapping_with_questions*.csv
    └── qa_dataset*.csv (if generated with --long_format)
```

### Dataset columns (high level)

**Wide Format CSV** (default with `--generate_questions`):
- **Image columns**: `original_image`, `semantic_counterfactual_image`, `negative_counterfactual_image`
- **Question columns**: `original_question`, `semantic_counterfactual_question_1`, `negative_counterfactual_question_1`
- **Answer matrix columns** (9 total, showing each image's answer to each question):
  - `original_image_answer_to_original_question`
  - `original_image_answer_to_semantic_counterfactual_question_1`
  - `original_image_answer_to_negative_counterfactual_question_1`
  - `semantic_counterfactual_image_answer_to_original_question`
  - `semantic_counterfactual_image_answer_to_semantic_counterfactual_question_1`
  - `semantic_counterfactual_image_answer_to_negative_counterfactual_question_1`
  - `negative_counterfactual_image_answer_to_original_question`
  - `negative_counterfactual_image_answer_to_semantic_counterfactual_question_1`
  - `negative_counterfactual_image_answer_to_negative_counterfactual_question_1`

**Basic Format CSV** (without `--generate_questions`):
- Only image columns: `original_image`, `semantic_counterfactual_image`, `negative_counterfactual_image`

## Code Style

The codebase follows a clean, consistent style:
- No multiline docstrings (removed for brevity)
- Consistent spacing and formatting
- Single blank lines between functions
- Clear, concise function names

## License

MIT License

## Contributing

Contributions are welcome! Please ensure:
- Code follows the existing style (no multiline docstrings, consistent spacing)
- All tests pass
- Documentation is updated as needed

## Acknowledgments

This project is inspired by the CLEVR dataset and uses Blender for 3D scene rendering.

