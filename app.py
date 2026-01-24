import streamlit as st
import os
import sys
import tempfile
import zipfile
import json
import random
import math
import csv
from pathlib import Path
from datetime import datetime
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

script_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scripts')
sys.path.insert(0, script_dir)

try:
    from pipeline import (
        generate_counterfactuals,
        generate_base_scene,
        save_scene,
        render_scene,
        create_patched_render_script,
        IMAGE_COUNTERFACTUALS,
        NEGATIVE_COUNTERFACTUALS
    )
    try:
        from generate_questions_mapping import (
            load_scene,
            generate_question_for_scene as _generate_question_for_scene_file,
            answer_question_for_scene,
            generate_mapping_with_questions
        )
    except ImportError:
        def load_scene(scene_file):
            with open(scene_file, 'r') as f:
                return json.load(f)
        def answer_question_for_scene(question, scene):
            objects = scene.get('objects', [])
            return len(objects)
        _generate_question_for_scene_file = None
        generate_mapping_with_questions = None
    PIPELINE_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Error importing pipeline functions: {e}")
    PIPELINE_AVAILABLE = False
    answer_question_for_scene = None
    load_scene = None
    _generate_question_for_scene_file = None

st.set_page_config(
    page_title="Counterfactual Image Generator",
    page_icon="🎨",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
    <style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
    }
    .stButton>button {
        width: 100%;
        height: 3.5rem;
        font-size: 1.2rem;
        font-weight: bold;
        background-color: #1f77b4;
        color: white;
        border-radius: 0.5rem;
    }
    .stButton>button:hover {
        background-color: #1565c0;
    }
    .info-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #f0f2f6;
        margin: 1rem 0;
    }
    </style>
""", unsafe_allow_html=True)

def create_zip_file(output_dir, zip_path):
    """Create a zip file from the output directory"""
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(output_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, output_dir)
                zipf.write(file_path, arcname)


def generate_synthetic_scene(num_objects, scene_idx):
    """
    Generate a synthetic scene JSON without Blender.
    Creates a scene with random objects positioned in 3D space.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    props_path = os.path.join(script_dir, 'data', 'properties.json')
    
    try:
        with open(props_path, 'r') as f:
            properties = json.load(f)
    except:
        properties = {
            'shapes': {'cube': 'SmoothCube_v2', 'sphere': 'Sphere', 'cylinder': 'SmoothCylinder'},
            'colors': {'gray': [87, 87, 87], 'red': [173, 35, 35], 'blue': [42, 75, 215], 
                      'green': [29, 105, 20], 'brown': [129, 74, 25], 'purple': [129, 38, 192],
                      'cyan': [41, 208, 208], 'yellow': [255, 238, 51]},
            'materials': {'rubber': 'Rubber', 'metal': 'MyMetal'},
            'sizes': {'large': 0.7, 'small': 0.35}
        }
    
    shapes = list(properties['shapes'].keys())
    colors = list(properties['colors'].keys())
    materials = list(properties['materials'].keys())
    sizes = list(properties['sizes'].keys())
    
    scene_num = scene_idx + 1
    scene = {
        'split': 'synthetic',
        'image_index': scene_num,
        'image_filename': f'scene_{scene_num:04d}_original.png',
        'objects': [],
        'directions': {
            'behind': (0.0, -1.0, 0.0),
            'front': (0.0, 1.0, 0.0),
            'left': (-1.0, 0.0, 0.0),
            'right': (1.0, 0.0, 0.0),
            'above': (0.0, 0.0, 1.0),
            'below': (0.0, 0.0, -1.0)
        }
    }
    
    positions = []
    min_dist = 0.25
    
    for i in range(num_objects):
        max_attempts = 100
        placed = False
        
        for attempt in range(max_attempts):
            x = random.uniform(-3, 3)
            y = random.uniform(-3, 3)
            z = random.uniform(0.35, 0.7)
            
            collision = False
            size = random.choice(sizes)
            r = properties['sizes'][size]
            
            for (px, py, pz, pr) in positions:
                dist = math.sqrt((x - px)**2 + (y - py)**2)
                if dist < (r + pr + min_dist):
                    collision = True
                    break
            
            if not collision:
                positions.append((x, y, z, r))
                placed = True
                break
        
        if not placed:
            x = random.uniform(-3, 3)
            y = random.uniform(-3, 3)
            z = random.uniform(0.35, 0.7)
            size = random.choice(sizes)
            r = properties['sizes'][size]
            positions.append((x, y, z, r))
        
        shape = random.choice(shapes)
        color = random.choice(colors)
        material = random.choice(materials)
        
        obj = {
            'shape': shape,
            'size': size,
            'material': material,
            '3d_coords': [x, y, z],
            'rotation': random.uniform(0, 360),
            'pixel_coords': [0, 0, 0],
            'color': color
        }
        
        scene['objects'].append(obj)
    
    return scene


def generate_question_for_scene_dict(scene):
    """Generate a question for a scene dictionary (adapter for generate_question_for_scene)"""
    if _generate_question_for_scene_file is None:
        objects = scene.get('objects', [])
        if len(objects) == 0:
            return "How many objects are in the scene?", {}
        
        colors = list(set(obj.get('color') for obj in objects if obj.get('color')))
        shapes = list(set(obj.get('shape') for obj in objects if obj.get('shape')))
        
        if colors:
            return f"How many {random.choice(colors)} objects are there?", {'color': random.choice(colors)}
        else:
            return "How many objects are in the scene?", {}
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tmp_file:
        json.dump(scene, tmp_file)
        tmp_path = tmp_file.name
    
    try:
        question, params = _generate_question_for_scene_file(tmp_path)
        return question, params
    finally:
        try:
            os.unlink(tmp_path)
        except:
            pass


def generate_counterfactual_scenes(num_scenes, num_objects, min_objects, max_objects, num_counterfactuals, 
                                    cf_types, min_change_score, max_cf_attempts, min_noise_level,
                                    output_dir, blender_path=None, use_gpu=0, samples=512, 
                                    width=320, height=240, skip_render=False, generate_questions=False):
    """
    Generate counterfactual scenes and optionally render them.
    
    Returns:
        Dictionary with success status and results
    """
    if not PIPELINE_AVAILABLE:
        return {
            'success': False,
            'error': 'Pipeline functions not available. Please ensure pipeline.py is accessible.'
        }
    
    scenes_dir = os.path.join(output_dir, 'scenes')
    images_dir = os.path.join(output_dir, 'images')
    os.makedirs(scenes_dir, exist_ok=True)
    os.makedirs(images_dir, exist_ok=True)
    
    blender_available = False
    if blender_path is None:
        try:
            from pipeline import find_blender
            blender_path = find_blender()
        except:
            blender_path = 'blender'
    
    if blender_path and blender_path != 'blender':
        blender_available = os.path.exists(blender_path)
    else:
        try:
            import subprocess
            test_path = blender_path if blender_path and blender_path != 'blender' else 'blender'
            env = os.environ.copy()
            result = subprocess.run([test_path, '--version'], capture_output=True, timeout=5, env=env)
            blender_available = (result.returncode == 0)
        except:
            blender_available = False
    
    successful_scenes = 0
    successful_renders = 0
    error_messages = []
    
    try:
        for scene_idx in range(num_scenes):
            if num_objects is not None:
                scene_num_objects = num_objects
            else:
                scene_num_objects = random.randint(min_objects, max_objects)
            
            base_scene = None
            
            if blender_available:
                scene_error = None
                for retry in range(3):
                    try:
                        import io
                        import contextlib
                        output_buffer = io.StringIO()
                        with contextlib.redirect_stdout(output_buffer), contextlib.redirect_stderr(output_buffer):
                            base_scene = generate_base_scene(
                                scene_num_objects,
                                blender_path,
                                scene_idx
                            )
                        blender_output = output_buffer.getvalue()
                        if blender_output and retry == 2:
                            st.text(f"Blender output for scene {scene_idx + 1} (last 1000 chars):")
                            st.code(blender_output[-1000:] if len(blender_output) > 1000 else blender_output)
                        
                        if base_scene and len(base_scene.get('objects', [])) > 0:
                            break
                        elif base_scene is None:
                            if retry == 2:
                                scene_error = f"generate_base_scene returned None - Blender may have failed (check output above)"
                                error_messages.append(f"Scene {scene_idx + 1}: {scene_error}")
                        elif len(base_scene.get('objects', [])) == 0:
                            if retry == 2:
                                scene_error = f"Scene has 0 objects - Blender may have hit max_retries (check output above)"
                                error_messages.append(f"Scene {scene_idx + 1}: {scene_error}")
                    except FileNotFoundError as e:
                        scene_error = f"Blender not found: {e}"
                        error_messages.append(f"Scene {scene_idx + 1}: {scene_error}")
                        blender_available = False
                        break
                    except Exception as e:
                        import traceback
                        scene_error = f"Error generating base scene: {str(e)}"
                        print(f"Error generating base scene (retry {retry + 1}/3): {e}")
                        print(f"  Traceback: {traceback.format_exc()}")
                        if retry == 2:
                            full_error = f"Scene {scene_idx + 1}: {scene_error} (Blender path: {blender_path})"
                            error_messages.append(full_error)
                            blender_available = False
                            continue
            else:
                print(f"Generating synthetic scene {scene_idx + 1} (Blender not available)...")
                base_scene = generate_synthetic_scene(scene_num_objects, scene_idx)
            
            if not base_scene or len(base_scene.get('objects', [])) == 0:
                error_detail = f"Scene {scene_idx + 1}: Failed to generate"
                if blender_available:
                    error_detail += f" (Blender was available at {blender_path} but returned empty scene)"
                else:
                    error_detail += f" (Blender not available, synthetic generation also failed)"
                print(f"Failed to generate scene {scene_idx + 1}")
                print(f"  Blender available: {blender_available}")
                print(f"  Blender path: {blender_path}")
                print(f"  Base scene: {base_scene is not None}")
                if base_scene:
                    print(f"  Objects in scene: {len(base_scene.get('objects', []))}")
                error_messages.append(error_detail)
                continue
            
            successful_scenes += 1
            
            counterfactuals = generate_counterfactuals(
                base_scene,
                num_counterfactuals=num_counterfactuals,
                cf_types=cf_types,
                min_change_score=min_change_score,
                max_cf_attempts=max_cf_attempts,
                min_noise_level='light'
            )
            
            scene_num = scene_idx + 1
            scene_prefix = f"scene_{scene_num:04d}"
            
            base_scene['cf_metadata'] = {
                'variant': 'original',
                'is_counterfactual': False,
                'cf_index': None,
                'cf_category': 'original',
                'cf_type': None,
                'cf_description': None,
                'source_scene': scene_prefix,
            }
            original_scene_path = os.path.join(scenes_dir, f"{scene_prefix}_original.json")
            save_scene(base_scene, original_scene_path)
            
            for idx, cf in enumerate(counterfactuals):
                cf_name = f"cf{idx+1}"
                cf_scene = cf['scene']
                cf_scene['cf_metadata'] = {
                    'variant': cf_name,
                    'is_counterfactual': True,
                    'cf_index': idx + 1,
                    'cf_category': cf.get('cf_category', 'unknown'),
                    'cf_type': cf.get('type', None),
                    'cf_description': cf.get('description', None),
                    'change_score': cf.get('change_score', None),
                    'change_attempts': cf.get('change_attempts', None),
                    'source_scene': scene_prefix,
                }
                cf_scene_path = os.path.join(scenes_dir, f"{scene_prefix}_{cf_name}.json")
                save_scene(cf_scene, cf_scene_path)
            
            render_success = 0
            total_to_render = len(counterfactuals) + 1
            
            if not skip_render:
                if blender_path and blender_available:
                    original_image_path = os.path.join(images_dir, f"{scene_prefix}_original.png")
                    if render_scene(
                        blender_path,
                        original_scene_path,
                        original_image_path,
                        use_gpu=use_gpu,
                        samples=samples,
                        width=width,
                        height=height
                    ):
                        render_success += 1
                    
                    for idx, cf in enumerate(counterfactuals):
                        cf_name = f"cf{idx+1}"
                        cf_scene_path = os.path.join(scenes_dir, f"{scene_prefix}_{cf_name}.json")
                        cf_image_path = os.path.join(images_dir, f"{scene_prefix}_{cf_name}.png")
                        
                        if render_scene(
                            blender_path,
                            cf_scene_path,
                            cf_image_path,
                            use_gpu=use_gpu,
                            samples=samples,
                            width=width,
                            height=height
                        ):
                            render_success += 1
                    
                    if render_success == total_to_render:
                        successful_renders += 1
                else:
                    print("Blender not available - skipping image rendering. Scene JSON files will still be generated.")
        
        csv_filename = 'image_mapping_with_questions.csv' if generate_questions else 'image_mapping.csv'
        csv_path = os.path.join(output_dir, csv_filename)
        
        try:
            if generate_questions:
                if 'generate_mapping_with_questions' in globals() and generate_mapping_with_questions:
                    generate_mapping_with_questions(
                        run_dir=output_dir,
                        csv_filename=csv_filename,
                        generate_questions=True,
                        with_links=False
                    )
                    csv_created = os.path.exists(csv_path)
                else:
                    print("WARNING: generate_mapping_with_questions not available. CSV generation skipped.")
                    csv_created = False
            else:
                if 'generate_mapping_with_questions' in globals() and generate_mapping_with_questions:
                    generate_mapping_with_questions(
                        run_dir=output_dir,
                        csv_filename=csv_filename,
                        generate_questions=False,
                        with_links=False
                    )
                    csv_created = os.path.exists(csv_path)
                else:
                    print("WARNING: generate_mapping_with_questions not available. CSV generation skipped.")
                    csv_created = False
        except Exception as e:
            print(f"WARNING: Failed to generate CSV: {e}")
            csv_created = False
        
        scene_files = list(Path(scenes_dir).glob("*.json")) if os.path.exists(scenes_dir) else []
        image_files = list(Path(images_dir).glob("*.png")) if os.path.exists(images_dir) else []
        
        statistics = {
            'scenes_generated': successful_scenes,
            'scenes_rendered': successful_renders,
            'total_scene_files': len(scene_files),
            'total_image_files': len(image_files),
            'num_counterfactuals': num_counterfactuals,
            'cf_types_used': cf_types if cf_types else 'default',
            'csv_created': csv_created,
            'csv_path': csv_path if csv_created else None
        }
        
        if successful_scenes == 0 and error_messages:
            error_summary = "Scene generation failed. Common reasons:\n"
            error_summary += "- Blender is not installed or not in PATH\n"
            error_summary += "- Blender executable not found\n"
            error_summary += f"\nFirst error: {error_messages[0] if error_messages else 'Unknown error'}"
            
            return {
                'success': False,
                'error': error_summary,
                'num_scenes': successful_scenes,
                'output_dir': output_dir,
                'error_messages': error_messages
            }
        
        return {
            'success': True,
            'num_scenes': successful_scenes,
            'output_dir': output_dir,
            'statistics': statistics,
            'error_messages': error_messages if error_messages else None
        }
    
    except Exception as e:
        import traceback
        error_msg = f"Generation error: {str(e)}\n{traceback.format_exc()}"
        print(error_msg)
        return {
            'success': False,
            'error': error_msg,
            'num_scenes': successful_scenes,
            'output_dir': output_dir,
            'error_messages': error_messages if 'error_messages' in locals() else []
        }

def main():
    st.markdown('<p class="main-header">Counterfactual Image Generator</p>', unsafe_allow_html=True)
    
    if 'output_dir' not in st.session_state:
        st.session_state.output_dir = None
    
    if 'generation_complete' not in st.session_state:
        st.session_state.generation_complete = False
    
    with st.sidebar:
        st.header("Configuration")
        
        st.subheader("Scene Settings")
        num_scenes = st.number_input(
            "Number of Scenes",
            min_value=1,
            max_value=10000,
            value=5,
            help="Number of scene sets to generate"
        )
        
        use_fixed_objects = st.checkbox("Use Fixed Number of Objects", value=True)
        
        if use_fixed_objects:
            num_objects = st.number_input(
                "Number of Objects per Scene",
                min_value=1,
                max_value=15,
                value=5,
                help="Fixed number of objects per scene"
            )
            min_objects = None
            max_objects = None
        else:
            num_objects = None
            min_objects = st.number_input(
                "Min Objects per Scene",
                min_value=1,
                max_value=15,
                value=3,
                help="Minimum objects per scene"
            )
            max_objects = st.number_input(
                "Max Objects per Scene",
                min_value=1,
                max_value=15,
                value=7,
                help="Maximum objects per scene"
            )
            if min_objects > max_objects:
                st.error("Min objects must be <= Max objects")
                return
        
        st.subheader("Counterfactual Settings")
        num_counterfactuals = st.number_input(
            "Number of Counterfactuals",
            min_value=1,
            max_value=10,
            value=2,
            help="Number of counterfactual variants per scene"
        )
        
        st.markdown("**Counterfactual Types**")
        st.caption("Leave all unchecked to use default behavior (1 Image CF + 1 Negative CF)")
        
        with st.expander("Image CFs (change answers)", expanded=False):
            use_change_color = st.checkbox("Change Color", value=False)
            use_change_shape = st.checkbox("Change Shape", value=False)
            use_change_size = st.checkbox("Change Size", value=False)
            use_change_material = st.checkbox("Change Material", value=False)
            use_change_position = st.checkbox("Change Position", value=False)
            use_change_count = st.checkbox("Change Count", value=False)
            use_add_object = st.checkbox("Add Object", value=False)
            use_remove_object = st.checkbox("Remove Object", value=False)
            use_replace_object = st.checkbox("Replace Object", value=False)
        
        with st.expander("Negative CFs (don't change answers)", expanded=False):
            use_change_background = st.checkbox("Change Background", value=False)
            use_change_texture = st.checkbox("Change Texture", value=False)
            use_change_lighting = st.checkbox("Change Lighting", value=False)
            use_add_noise = st.checkbox("Add Noise", value=False)
            use_apply_fisheye = st.checkbox("Apply Fisheye", value=False)
            use_apply_blur = st.checkbox("Apply Blur", value=False)
            use_apply_vignette = st.checkbox("Apply Vignette", value=False)
            use_apply_chromatic_aberration = st.checkbox("Apply Chromatic Aberration", value=False)
        
        with st.expander("Advanced Settings", expanded=False):
            min_change_score = st.slider(
                "Minimum Change Score",
                min_value=0.5,
                max_value=5.0,
                value=1.0,
                step=0.1,
                help="Minimum heuristic change score for counterfactuals"
            )
            
            max_cf_attempts = st.number_input(
                "Max CF Attempts",
                min_value=1,
                max_value=50,
                value=10,
                help="Maximum retries per counterfactual"
            )
            
            min_noise_level = st.selectbox(
                "Min Noise Level (for add_noise CF)",
                options=['light', 'medium', 'heavy'],
                index=0,
                help="Minimum noise level when using add_noise counterfactual"
            )
            
            st.markdown("---")
            st.markdown("**Rendering Settings**")
            
            use_gpu = st.checkbox("Use GPU Rendering", value=False)
            use_gpu_int = 1 if use_gpu else 0
            
            samples = st.number_input(
                "Render Samples",
                min_value=64,
                max_value=2048,
                value=512,
                step=64,
                help="Cycles sampling rate (higher = better quality, slower)"
            )
            
            image_width = st.number_input(
                "Image Width",
                min_value=160,
                max_value=1920,
                value=320,
                step=80
            )
            
            image_height = st.number_input(
                "Image Height",
                min_value=120,
                max_value=1080,
                value=240,
                step=60
            )
        
        st.markdown("**CSV Options**")
        generate_questions = st.checkbox(
            "Generate Questions in CSV",
            value=False,
            help="Include question and answer columns in the CSV file"
        )
        
        cf_types = []
        if use_change_color:
            cf_types.append('change_color')
        if use_change_shape:
            cf_types.append('change_shape')
        if use_change_size:
            cf_types.append('change_size')
        if use_change_material:
            cf_types.append('change_material')
        if use_change_position:
            cf_types.append('change_position')
        if use_change_count:
            cf_types.append('change_count')
        if use_add_object:
            cf_types.append('add_object')
        if use_remove_object:
            cf_types.append('remove_object')
        if use_replace_object:
            cf_types.append('replace_object')
        if use_change_background:
            cf_types.append('change_background')
        if use_change_texture:
            cf_types.append('change_texture')
        if use_change_lighting:
            cf_types.append('change_lighting')
        if use_add_noise:
            cf_types.append('add_noise')
        if use_apply_fisheye:
            cf_types.append('apply_fisheye')
        if use_apply_blur:
            cf_types.append('apply_blur')
        if use_apply_vignette:
            cf_types.append('apply_vignette')
        if use_apply_chromatic_aberration:
            cf_types.append('apply_chromatic_aberration')
        
        if not cf_types:
            cf_types = None
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.header("Generate Counterfactual Images")
        
        if st.button("Generate Counterfactual", use_container_width=True):
            if num_scenes < 1:
                st.error("Please specify at least 1 scene to generate.")
                return
            
            if use_fixed_objects and num_objects < 1:
                st.error("Please specify at least 1 object per scene.")
                return
            if not use_fixed_objects and (min_objects < 1 or max_objects < 1 or min_objects > max_objects):
                st.error("Invalid min/max objects configuration.")
                return
            
            if os.path.exists('/tmp'):
                base_dir = '/tmp'
            else:
                base_dir = tempfile.gettempdir()
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir = os.path.join(base_dir, f"counterfactual_output_{timestamp}")
            os.makedirs(output_dir, exist_ok=True)
            st.session_state.output_dir = output_dir
            
            params = {
                'num_scenes': num_scenes,
                'num_objects': num_objects,
                'num_counterfactuals': num_counterfactuals,
                'cf_types': cf_types if cf_types else None,
                'min_change_score': min_change_score,
                'max_cf_attempts': max_cf_attempts,
                'width': image_width,
                'height': image_height,
                'output_dir': output_dir
            }
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            try:
                if not PIPELINE_AVAILABLE:
                    st.error("Pipeline functions are not available. Please check your installation.")
                    return
                
                status_text.text("Initializing generator...")
                progress_bar.progress(10)
                
                if use_fixed_objects:
                    status_text.text(f"Generating {num_scenes} scenes with {num_objects} objects each...")
                else:
                    status_text.text(f"Generating {num_scenes} scenes with {min_objects}-{max_objects} objects each...")
                progress_bar.progress(30)
                
                result = generate_counterfactual_scenes(
                    num_scenes=num_scenes,
                    num_objects=num_objects,
                    min_objects=min_objects,
                    max_objects=max_objects,
                    num_counterfactuals=num_counterfactuals,
                    cf_types=cf_types,
                    min_change_score=min_change_score,
                    max_cf_attempts=max_cf_attempts,
                    min_noise_level=min_noise_level,
                    output_dir=output_dir,
                    use_gpu=use_gpu_int,
                    samples=samples,
                    width=image_width,
                    height=image_height,
                    skip_render=False,
                    generate_questions=generate_questions
                )
                
                progress_bar.progress(80)
                status_text.text("Generation complete! Preparing output...")
                
                if result and result.get('success', False):
                    num_scenes_generated = result.get('num_scenes', 0)
                    
                    if num_scenes_generated == 0:
                        st.warning("No scenes were generated. This is likely because Blender is required for scene generation and is not available in this environment.")
                        st.info("**To use this application:**\n"
                               "1. Run it locally with Blender installed\n"
                               "2. Use the command-line `pipeline.py` script\n"
                               "3. Install Blender and ensure it's in your system PATH")
                        st.session_state.generation_complete = False
                    else:
                        st.session_state.generation_complete = True
                        progress_bar.progress(100)
                        status_text.text("Generation successful!")
                        
                        st.success(f"Successfully generated {num_scenes_generated} scene sets!")
                        st.info(f"Output directory: {output_dir}")
                        
                        if 'statistics' in result and result['statistics'].get('csv_created'):
                            csv_path = result['statistics'].get('csv_path')
                            if csv_path:
                                st.success(f"CSV file created: `{os.path.basename(csv_path)}`")
                    
                    if 'statistics' in result:
                        stats = result['statistics']
                        st.json(stats)
                else:
                    error_msg = result.get('error', 'Unknown error occurred') if result else 'Generation failed'
                    st.error(f"Generation failed: {error_msg}")
                    
                    if 'blender' in error_msg.lower() or 'Blender' in error_msg or result.get('num_scenes', 0) == 0:
                        st.warning("**Important:** This application requires Blender to generate scenes. Blender is not available on Hugging Face Spaces.")
                        st.info("**To use this application:**\n"
                               "1. Run it locally with Blender installed\n"
                               "2. Use the command-line `pipeline.py` script\n"
                               "3. Install Blender and ensure it's in your system PATH")
                    
                    st.session_state.generation_complete = False
                    
            except Exception as e:
                st.error(f"Error during generation: {str(e)}")
                st.exception(e)
                st.session_state.generation_complete = False
                progress_bar.progress(0)
                status_text.text("Generation failed")
    
    with col2:
        st.header("Output")
        
        if st.session_state.generation_complete and st.session_state.output_dir:
            output_dir = st.session_state.output_dir
            
            if os.path.exists(output_dir):
                scene_files = list(Path(output_dir).rglob("*.json"))
                image_files = list(Path(output_dir).rglob("*.png"))
                csv_files = list(Path(output_dir).rglob("*.csv"))
                
                st.success(f"Generation Complete!")
                st.metric("Scene Files", len(scene_files))
                st.metric("CSV Files", len(csv_files))
                st.metric("Image Files", len(image_files))
                
                st.markdown("---")
                st.subheader("Download Output")
                
                zip_filename = f"counterfactual_output_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
                zip_path = os.path.join(tempfile.gettempdir(), zip_filename)
                
                try:
                    create_zip_file(output_dir, zip_path)
                    
                    file_size = os.path.getsize(zip_path) / (1024 * 1024)
                    
                    with open(zip_path, 'rb') as f:
                        st.download_button(
                            label=f"Download as ZIP ({file_size:.2f} MB)",
                            data=f.read(),
                            file_name=zip_filename,
                            mime="application/zip",
                            use_container_width=True
                        )
                    
                    with st.expander("Output Structure"):
                        st.text(f"Output directory: {output_dir}")
                        if scene_files:
                            st.text(f"\nScene files: {len(scene_files)}")
                            st.text("Sample files:")
                            for f in scene_files[:5]:
                                st.text(f"  - {f.name}")
                        if csv_files:
                            st.text(f"\nCSV files: {len(csv_files)}")
                            for f in csv_files:
                                st.text(f"  - {f.name}")
                        if image_files:
                            st.text(f"\nImage files: {len(image_files)}")
                            st.text("Sample files:")
                            for f in image_files[:5]:
                                st.text(f"  - {f.name}")
                
                except Exception as e:
                    st.error(f"Error creating zip file: {str(e)}")
            else:
                st.warning("Output directory not found.")
        else:
            st.info("Configure parameters and click 'Generate Counterfactual' to start.")
    
    st.markdown("---")
    st.markdown(
        "<div style='text-align: center; color: #666; padding: 1rem;'>"
        "Counterfactual Image Generation Tool | Built with Streamlit"
        "</div>",
        unsafe_allow_html=True
    )

if __name__ == "__main__":
    main()

