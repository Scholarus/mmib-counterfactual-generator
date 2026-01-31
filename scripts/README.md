# Scripts

Utility scripts for working with CLEVR counterfactual scenes.

## Available Scripts

### generate_scenes.py
Generate scene JSON files with counterfactuals (no rendering).

**Purpose**: Create scene JSON files that can be rendered later.

**Usage:**
```bash
# Generate 10 scene sets
python scripts/generate_scenes.py --num_scenes 10 --num_objects 5 --run_name experiment1

# Resume from checkpoint
python scripts/generate_scenes.py --num_scenes 100 --run_name experiment1 --resume
```

**Output**: Scene JSON files in `output/run_name/scenes/`

**Next step**: Use `pipeline.py --render_only` to render these scenes.

**Note**: Alternatively, you can use `pipeline.py --skip_render` instead of this script.

---

### generate_examples.py
Generate examples of each counterfactual type applied to a base scene. Optionally renders scenes to images.

**Purpose**: Create reference examples demonstrating all counterfactual types.

**Usage:**
```bash
# Generate scene JSON files only
python scripts/generate_examples.py [--output_dir DIR] [--num_objects N]

# Generate and render to images
python scripts/generate_examples.py --render [--output_dir DIR] [--num_objects N] [--use_gpu 0|1]
```

**Options:**
- `--output_dir`: Output directory (default: `output/counterfactual_examples`)
- `--num_objects`: Number of objects in base scene (default: 5)
- `--render`: Render scenes to PNG images
- `--use_gpu`: Use GPU rendering (0 = CPU, 1 = GPU, default: 0)

**Output**: 
- Scene JSON files for all counterfactual types
- Optional: PNG images (if `--render` is used)

---

### generate_questions_mapping.py
Generate CSV mapping with questions and counterfactual questions for scenes.

**Purpose**: Create question-answer datasets for training/evaluation.

**Usage:**
```bash
# For a specific run directory
python scripts/generate_questions_mapping.py --output_dir output/experiment1 --generate_questions

# Auto-detect latest run
python scripts/generate_questions_mapping.py --output_dir output --auto_latest --generate_questions

# Generate CSV with scene_id and links (relative paths)
python scripts/generate_questions_mapping.py --output_dir output/experiment1 --generate_questions --with_links

# Generate CSV with scene_id and full URLs
python scripts/generate_questions_mapping.py --output_dir output/experiment1 --generate_questions --with_links --base_url https://example.com/dataset
```

**Options:**
- `--output_dir`: Run directory or base output directory (default: `output`)
- `--auto_latest`: Automatically find and use the latest run in output_dir
- `--csv_name`: Output CSV filename (default: `image_mapping_with_questions.csv`)
- `--generate_questions`: Generate questions and answers for each scene set
- `--with_links`: Include scene_id and image/scene link columns (for URLs or file paths)
- `--base_url`: Base URL for links (e.g., `https://example.com`). If not provided, uses relative paths like `images/filename.png`

**Output**: CSV files with question-answer mappings

---


## Main Pipeline

For production use (generating large datasets), use the main pipeline script:

```bash
python pipeline.py --num_scenes 100 --num_objects 5 --run_name my_experiment
```

See the main `README.md` for full documentation of the production pipeline.

---

## Script Summary

| Script | Purpose | When to Use |
|--------|---------|-------------|
| `generate_scenes.py` | Generate scene JSON files | Generate scenes separately (alternative to `pipeline.py --skip_render`) |
| `generate_examples.py` | Generate reference examples | Creating demonstrations, testing counterfactuals |
| `generate_questions_mapping.py` | Create QA datasets | Preparing training/evaluation data |
| `pipeline.py` | Combined generation + rendering | Main entry point. Supports `--skip_render` and `--render_only` modes |
