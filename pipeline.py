#!/usr/bin/env python3

import json
import argparse
import os
import subprocess
import random
import copy
import sys
import shutil
import time
import math
import glob
import zipfile
from datetime import datetime
from pathlib import Path

script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(script_dir, 'scripts'))
try:
    from generate_questions_mapping import generate_mapping_with_questions
except ImportError:
    generate_mapping_with_questions = None

def find_blender():
    hf_paths = [
        '/opt/blender/blender',
        '/usr/local/bin/blender',
    ]
    
    home = os.environ.get('HOME', os.path.expanduser('~'))
    user_blender_paths = [
        os.path.join(home, 'blender', 'blender'),
        os.path.join(home, '.local', 'bin', 'blender'),
    ]
    hf_paths.extend(user_blender_paths)
    
    for path in hf_paths:
        if os.path.exists(path):
            return path
    
    if sys.platform == 'win32':
        common_paths = [
            r"C:\Program Files\Blender Foundation\Blender 4.5\blender.exe",
            r"C:\Program Files\Blender Foundation\Blender 4.3\blender.exe",
            r"C:\Program Files\Blender Foundation\Blender 4.2\blender.exe",
        ]
        for path in common_paths:
            if os.path.exists(path):
                return path
    
    try:
        env = os.environ.copy()
        result = subprocess.run(['which', 'blender'], capture_output=True, timeout=5, env=env)
        if result.returncode == 0:
            blender_path = result.stdout.decode().strip()
            if blender_path and os.path.exists(blender_path):
                return blender_path
    except:
        pass
    
    home = os.environ.get('HOME', os.path.expanduser('~'))
    blender_default = os.path.join(home, 'blender', 'blender')
    if os.path.exists(blender_default):
        return blender_default
    
    return 'blender'
    

def create_run_directory(base_output_dir, run_name=None):
    if run_name:
        run_name = "".join(c for c in run_name if c.isalnum() or c in ('_', '-'))
        run_dir = os.path.join(base_output_dir, run_name)
    else:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        run_dir = os.path.join(base_output_dir, timestamp)
    
    os.makedirs(run_dir, exist_ok=True)
    return run_dir

def save_checkpoint(checkpoint_file, completed_scenes):
    with open(checkpoint_file, 'w') as f:
        json.dump({'completed_scenes': completed_scenes}, f)
    print(f"  [CHECKPOINT] Saved: {len(completed_scenes)} scenes completed")

def load_checkpoint(checkpoint_file):
    if os.path.exists(checkpoint_file):
        with open(checkpoint_file, 'r') as f:
            data = json.load(f)
            return set(data.get('completed_scenes', []))
    return set()

def get_completed_scenes_from_folder(images_dir):
    if not os.path.exists(images_dir):
        return set()
    
    completed = set()
    files = os.listdir(images_dir)
    
    for f in files:
        if f.startswith('scene_') and '_original.png' in f:
            try:
                scene_num = int(f.split('_')[1])
                completed.add(scene_num)
            except (IndexError, ValueError):
                continue
    
    return completed

def create_patched_utils():
    return None

def create_patched_render_script():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    render_path = os.path.join(current_dir, 'scripts', 'render.py')
    
    with open(render_path, 'r', encoding='utf-8') as f:
        original_content = f.read()
    
    patched_content = original_content
    
    import_patterns = [
        'if INSIDE_BLENDER:\n  import sys\n  import os\n  current_dir = os.path.dirname(os.path.abspath(__file__))\n  if current_dir not in sys.path:\n    sys.path.insert(0, current_dir)\n  \n  try:\n    import utils',
        'if INSIDE_BLENDER:\n  try:\n    import utils',
    ]
    
    for pattern in import_patterns:
        if pattern in patched_content:
            import_start = patched_content.find(pattern)
            if import_start != -1:
                import_end = patched_content.find('    sys.exit(1)', import_start)
                if import_end == -1:
                    import_end = patched_content.find('\nparser =', import_start)
                if import_end != -1:
                    import_end = patched_content.find('\n', import_end)
                    patched_content = patched_content[:import_start] + patched_content[import_end:]
                    break
    
    patched_content = patched_content.replace(
        '  render_args.tile_x = args.render_tile_size\n  render_args.tile_y = args.render_tile_size',
        '  # tile_x/tile_y removed in Blender 4.x'
    )
    
    patched_content = patched_content.replace("render_args.engine = 'BLENDER_EEVEE'", "render_args.engine = 'CYCLES'")
    
    patched_content = patched_content.replace(
        "bpy.data.worlds['World'].cycles.sample_as_light = True",
        "# sample_as_light removed in Blender 5.x"
    )
    patched_content = patched_content.replace(
        "bpy.context.scene.cycles.transparent_min_bounces = args.render_min_bounces",
        "# transparent_min_bounces removed in Blender 5.x"
    )
    patched_content = patched_content.replace(
        "bpy.context.scene.cycles.transparent_max_bounces = args.render_max_bounces",
        "# transparent_max_bounces removed in Blender 5.x"
    )
    
    # Disable margin check to prevent "BROKEN MARGIN!" errors
    # This makes object placement more flexible
    if "margins_good = True" in patched_content and "BROKEN MARGIN!" in patched_content:
        # Replace the margin check loop with a simple pass
        old_margin_check = """          for direction_name in ['left', 'right', 'front', 'behind']:
            direction_vec = scene_struct['directions'][direction_name]
            assert direction_vec[2] == 0
            margin = dx * direction_vec[0] + dy * direction_vec[1]
            if 0 < margin < args.margin:
              print(margin, args.margin, direction_name)
              print('BROKEN MARGIN!')
              margins_good = False
              break"""
        
        new_margin_check = """          # Margin check disabled for more flexible object placement
          # margins_good remains True"""
        
        if old_margin_check in patched_content:
            patched_content = patched_content.replace(old_margin_check, new_margin_check)
    
    check_vis_start = patched_content.find('def check_visibility(blender_objects, min_pixels_per_object):')
    if check_vis_start != -1:
        docstring_end = patched_content.find('"""', check_vis_start + 50)
        docstring_end = patched_content.find('\n', docstring_end) + 1
        next_def = patched_content.find('\ndef ', docstring_end)
        if next_def == -1:
            next_def = len(patched_content)
        
        new_function = '''def check_visibility(blender_objects, min_pixels_per_object):
  return True

'''
        patched_content = patched_content[:check_vis_start] + new_function + patched_content[next_def:]
    
    patched_content = patched_content.replace(
        "parser.add_argument('--min_pixels_per_object', default=200, type=int,",
        "parser.add_argument('--min_pixels_per_object', default=50, type=int,"
    )
    patched_content = patched_content.replace(
        "parser.add_argument('--max_retries', default=50, type=int,",
        "parser.add_argument('--max_retries', default=200, type=int,"
    )
    # Also catch the default=100 case if it was already patched
    patched_content = patched_content.replace(
        "parser.add_argument('--max_retries', default=100, type=int,",
        "parser.add_argument('--max_retries', default=200, type=int,"
    )
    patched_content = patched_content.replace(
        "parser.add_argument('--margin', default=0.4, type=float,",
        "parser.add_argument('--margin', default=0.05, type=float,"
    )
    patched_content = patched_content.replace(
        "parser.add_argument('--margin', default=0.2, type=float,",
        "parser.add_argument('--margin', default=0.05, type=float,"
    )
    patched_content = patched_content.replace(
        "parser.add_argument('--min_dist', default=0.25, type=float,",
        "parser.add_argument('--min_dist', default=0.15, type=float,"
    )
    
    script_path = os.path.abspath('render_images_patched.py')
    with open(script_path, 'w', encoding='utf-8') as f:
        f.write(patched_content)
    
    return script_path

def create_render_from_json_script():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    render_path = os.path.join(current_dir, 'scripts', 'render.py')
    return render_path

def generate_base_scene(num_objects, blender_path, scene_idx):
    cwd = os.getcwd()
    script_file = os.path.abspath(__file__)
    current_dir = os.path.dirname(script_file)
    
    possible_dirs = [
        current_dir,
        cwd,
        os.path.join(os.environ.get('HOME', ''), 'app'),
        '/home/user/app',
        os.path.dirname(cwd),
        '/app',
    ]
    
    data_dir = None
    for possible_dir in possible_dirs:
        if not possible_dir:
            continue
        test_data_dir = os.path.join(possible_dir, 'data')
        if os.path.exists(test_data_dir) and os.path.exists(os.path.join(test_data_dir, 'base_scene.blend')):
            data_dir = test_data_dir
            break
    
    if data_dir is None:
        print(f"  ERROR: Could not find data directory")
        print(f"  Searched in:")
        for pd in possible_dirs:
            if pd:
                test_path = os.path.join(pd, 'data')
                exists = os.path.exists(test_path)
                print(f"    - {test_path}: {'EXISTS' if exists else 'NOT FOUND'}")
                if exists:
                    try:
                        contents = os.listdir(test_path)
                        print(f"      Contents: {contents[:5]}")
                    except:
                        pass
        print(f"  Current working directory: {cwd}")
        print(f"  Script directory: {current_dir}")
        print(f"  Script file: {script_file}")
        print(f"  HOME: {os.environ.get('HOME', 'NOT SET')}")
        return None
    
    temp_images_dir = os.path.join(cwd, 'temp_output', 'images')
    temp_scenes_dir = os.path.join(cwd, 'temp_output', 'scenes')
    
    os.makedirs(temp_images_dir, exist_ok=True)
    os.makedirs(temp_scenes_dir, exist_ok=True)
    
    patched_script = create_patched_render_script()
    
    if blender_path == 'blender':
        blender_path = find_blender()
    
    if not os.path.exists(blender_path) and blender_path != 'blender':
        print(f"  ERROR: Blender path does not exist: {blender_path}")
        return None
    
    base_scene = os.path.join(data_dir, 'base_scene.blend')
    properties_json = os.path.join(data_dir, 'properties.json')
    shape_dir = os.path.join(data_dir, 'shapes')
    material_dir = os.path.join(data_dir, 'materials')
    
    base_scene = os.path.abspath(base_scene)
    properties_json = os.path.abspath(properties_json)
    shape_dir = os.path.abspath(shape_dir)
    material_dir = os.path.abspath(material_dir)
    temp_images_dir = os.path.abspath(temp_images_dir)
    temp_scenes_dir = os.path.abspath(temp_scenes_dir)
    
    if not os.path.exists(base_scene):
        print(f"  ERROR: Base scene file not found: {base_scene}")
        print(f"  Data directory contents: {os.listdir(data_dir) if os.path.exists(data_dir) else 'N/A'}")
        return None
    if not os.path.exists(properties_json):
        print(f"  ERROR: Properties JSON not found: {properties_json}")
        return None
    if not os.path.exists(shape_dir):
        print(f"  ERROR: Shape directory not found: {shape_dir}")
        if os.path.exists(data_dir):
            print(f"  Data directory contents: {os.listdir(data_dir)}")
        return None
    if not os.path.exists(material_dir):
        print(f"  ERROR: Material directory not found: {material_dir}")
        return None
    
    env = os.environ.copy()
    
    cmd = [
        blender_path, '--background', '-noaudio', '--python', patched_script, '--',
        '--num_images', '1',
        '--start_idx', str(scene_idx),
        '--min_objects', str(num_objects),
        '--max_objects', str(num_objects),
        '--min_pixels_per_object', '50',
        '--min_dist', '0.20',
        '--margin', '0.2',
        '--max_retries', '100',
        '--output_image_dir', temp_images_dir,
        '--output_scene_dir', temp_scenes_dir,
        '--filename_prefix', f'SCENE_{scene_idx:04d}',
        '--base_scene_blendfile', base_scene,
        '--properties_json', properties_json,
        '--shape_dir', shape_dir,
        '--material_dir', material_dir,
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, env=env, cwd=cwd)
    
    if result.returncode != 0:
        print(f"ERROR: Blender returned code {result.returncode}")
        print(f"  Blender path used: {blender_path}")
        print(f"  Command: {' '.join(cmd[:3])}...")
        if result.stderr:
            print(f"  Error details (last 1000 chars): {result.stderr[-1000:]}")
        if result.stdout:
            error_lines = [line for line in result.stdout.split('\n') if 'error' in line.lower() or 'Error' in line or 'ERROR' in line or 'Traceback' in line]
            if error_lines:
                print(f"  Error lines from stdout: {error_lines[-10:]}")
            print(f"  Full stdout (last 500 chars): {result.stdout[-500:]}")
        return None
    
    if not os.path.exists(temp_scenes_dir):
        print(f"ERROR: temp_output/scenes directory does not exist")
        print(f"  Expected: {temp_scenes_dir}")
        print(f"  Current directory: {cwd}")
        print(f"  Temp output dir exists: {os.path.exists(os.path.join(cwd, 'temp_output'))}")
        if os.path.exists(os.path.join(cwd, 'temp_output')):
            print(f"  Contents: {os.listdir(os.path.join(cwd, 'temp_output'))}")
        return None
    
    scene_file = os.path.join(temp_scenes_dir, f'SCENE_{scene_idx:04d}_new_{scene_idx:06d}.json')
    if not os.path.exists(scene_file):
        print(f"  Scene file not found at expected path: {scene_file}")
        if os.path.exists(temp_scenes_dir):
            scene_files = os.listdir(temp_scenes_dir)
            print(f"  Available scene files ({len(scene_files)}): {scene_files[:10]}")
            matching_files = [f for f in scene_files if f.startswith(f'SCENE_{scene_idx:04d}')]
            print(f"  Files matching SCENE_{scene_idx:04d}: {matching_files}")
            if matching_files:
                scene_file = os.path.join(temp_scenes_dir, matching_files[0])
                print(f"  Using: {scene_file}")
            else:
                print(f"ERROR: No matching scene file found for scene_idx {scene_idx}")
                print(f"  Checked for files starting with: SCENE_{scene_idx:04d}")
                return None
        else:
            print(f"ERROR: temp_output/scenes directory does not exist: {temp_scenes_dir}")
            return None
    
    if not os.path.exists(scene_file):
        print(f"ERROR: Scene file not found: {scene_file}")
        return None
    
    try:
        with open(scene_file, 'r') as f:
            scene = json.load(f)
    except Exception as e:
        print(f"ERROR: Failed to read scene file {scene_file}: {e}")
        return None
    
    if 'objects' not in scene:
        print(f"ERROR: Scene file missing 'objects' key. Scene keys: {list(scene.keys())}")
        print(f"  Scene file contents (first 500 chars): {json.dumps(scene, indent=2)[:500]}")
        return None
    
    if len(scene['objects']) == 0:
        print(f"WARNING: Scene has 0 objects")
        print(f"  This usually means Blender hit max_retries trying to place objects")
        print(f"  Scene file contents (first 1000 chars): {json.dumps(scene, indent=2)[:1000]}")
        if result and result.stdout:
            retry_lines = [line for line in result.stdout.split('\n') if 'retry' in line.lower() or 'Retry' in line or 'attempt' in line.lower()]
            if retry_lines:
                print(f"  Retry-related output: {retry_lines[-5:]}")
        return None
    
    print(f"  [OK] Generated scene with {len(scene['objects'])} objects")
    return scene

def cf_change_color(scene):
    cf_scene = copy.deepcopy(scene)
    
    if len(cf_scene['objects']) == 0:
        return cf_scene, "no change (0 objects)"
    
    change_idx = random.randint(0, len(cf_scene['objects']) - 1)
    obj = cf_scene['objects'][change_idx]
    
    colors = ['gray', 'red', 'blue', 'green', 'brown', 'purple', 'cyan', 'yellow']
    old_color = obj['color']
    new_color = random.choice([c for c in colors if c != old_color])
    obj['color'] = new_color
    
    return cf_scene, f"changed {old_color} {obj['shape']} to {new_color}"

def cf_change_position(scene):
    cf_scene = copy.deepcopy(scene)
    
    if len(cf_scene['objects']) == 0:
        return cf_scene, "no move (0 objects)"
    
    move_idx = random.randint(0, len(cf_scene['objects']) - 1)
    obj = cf_scene['objects'][move_idx]
    old_coords = obj['3d_coords']
    
    try:
        with open('data/properties.json', 'r') as f:
            properties = json.load(f)
            size_mapping = properties['sizes']
    except:
        size_mapping = {'small': 0.35, 'large': 0.7}
    
    r = size_mapping.get(obj['size'], 0.5)
    if obj['shape'] == 'cube':
        r /= math.sqrt(2)
    
    min_dist = 0.25
    
    max_attempts = 100
    for attempt in range(max_attempts):
        new_x = random.uniform(-3, 3)
        new_y = random.uniform(-3, 3)

        try:
            dx0 = float(new_x) - float(old_coords[0])
            dy0 = float(new_y) - float(old_coords[1])
            if math.sqrt(dx0 * dx0 + dy0 * dy0) < 1.0:
                continue
        except Exception:
            pass
        
        collision = False
        for other_idx, other_obj in enumerate(cf_scene['objects']):
            if other_idx == move_idx:
                continue
            
            other_x, other_y, _ = other_obj['3d_coords']
            other_r = size_mapping.get(other_obj['size'], 0.5)
            if other_obj['shape'] == 'cube':
                other_r /= math.sqrt(2)
            
            dist = math.sqrt((new_x - other_x)**2 + (new_y - other_y)**2)
            
            if dist < (r + other_r + min_dist):
                collision = True
                break
        
        if not collision:
            obj['3d_coords'] = [new_x, new_y, old_coords[2]]
            obj['pixel_coords'] = [0, 0, 0]
            return cf_scene, f"moved {obj['color']} {obj['shape']} from ({old_coords[0]:.1f},{old_coords[1]:.1f}) to ({new_x:.1f},{new_y:.1f})"
    
    return cf_scene, f"no move (couldn't find collision-free position for {obj['color']} {obj['shape']})"

def cf_change_surrounding_count(scene):
    cf_scene = copy.deepcopy(scene)
    
    if len(cf_scene['objects']) == 0:
        return cf_scene, "no change (0 objects)"
    
    try:
        with open('data/properties.json', 'r') as f:
            properties = json.load(f)
            size_mapping = properties['sizes']
    except:
        size_mapping = {'small': 0.35, 'large': 0.7}
    
    action = random.choice(['add', 'remove'])
    
    if action == 'add' or len(cf_scene['objects']) <= 1:
        target_idx = random.randint(0, len(cf_scene['objects']) - 1)
        target_obj = cf_scene['objects'][target_idx]
        target_x, target_y, target_z = target_obj['3d_coords']
        
        num_to_add = random.randint(1, 2)
        shapes = ['cube', 'sphere', 'cylinder']
        colors = ['gray', 'red', 'blue', 'green', 'brown', 'purple', 'cyan', 'yellow']
        materials = ['metal', 'rubber']
        sizes = ['small', 'large']
        
        min_dist = 0.25
        added_count = 0
        
        for _ in range(num_to_add):
            for attempt in range(50):
                offset_x = random.uniform(-1.5, 1.5)
                offset_y = random.uniform(-1.5, 1.5)
                new_x = max(-3, min(3, target_x + offset_x))
                new_y = max(-3, min(3, target_y + offset_y))
                
                # Choose random size for new object
                new_size = random.choice(sizes)
                new_shape = random.choice(shapes)
                new_r = size_mapping[new_size]
                if new_shape == 'cube':
                    new_r /= math.sqrt(2)
                
                collision = False
                for other_obj in cf_scene['objects']:
                    other_x, other_y, _ = other_obj['3d_coords']
                    other_r = size_mapping.get(other_obj['size'], 0.5)
                    if other_obj['shape'] == 'cube':
                        other_r /= math.sqrt(2)
                    
                    dist = math.sqrt((new_x - other_x)**2 + (new_y - other_y)**2)
                    if dist < (new_r + other_r + min_dist):
                        collision = True
                        break
                
                # If no collision, add the object
                if not collision:
                    new_obj = {
                        'shape': new_shape,
                        'color': random.choice(colors),
                        'material': random.choice(materials),
                        'size': new_size,
                        '3d_coords': [new_x, new_y, 0.35],
                        'rotation': random.uniform(0, 360),
                        'pixel_coords': [0, 0, 0]
                    }
                    cf_scene['objects'].append(new_obj)
                    added_count += 1
                    break
        
        if added_count > 0:
            return cf_scene, f"added {added_count} objects near {target_obj['color']} {target_obj['shape']}"
        else:
            return cf_scene, "no change (couldn't find valid positions for new objects)"
    
    else:
        # Remove 1-2 objects
        num_to_remove = min(random.randint(1, 2), len(cf_scene['objects']) - 1)
        removed = []
        for _ in range(num_to_remove):
            if len(cf_scene['objects']) > 1:
                remove_idx = random.randint(0, len(cf_scene['objects']) - 1)
                removed_obj = cf_scene['objects'].pop(remove_idx)
                removed.append(f"{removed_obj['color']} {removed_obj['shape']}")
        
        return cf_scene, f"removed {', '.join(removed)}"

def cf_add_object(scene):
    cf_scene = copy.deepcopy(scene)
    
    shapes = ['cube', 'sphere', 'cylinder']
    colors = ['gray', 'red', 'blue', 'green', 'brown', 'purple', 'cyan', 'yellow']
    materials = ['metal', 'rubber']
    sizes = ['small', 'large']
    
    # Load size mapping
    try:
        with open('data/properties.json', 'r') as f:
            properties = json.load(f)
            size_mapping = properties['sizes']
    except:
        size_mapping = {'small': 0.35, 'large': 0.7}
    
    min_dist = 0.25
    
    for attempt in range(100):
        new_shape = random.choice(shapes)
        new_size = random.choice(sizes)
        new_r = size_mapping[new_size]
        if new_shape == 'cube':
            new_r /= math.sqrt(2)
        
        new_x = random.uniform(-3, 3)
        new_y = random.uniform(-3, 3)
        
        collision = False
        for other_obj in cf_scene['objects']:
            other_x, other_y, _ = other_obj['3d_coords']
            other_r = size_mapping.get(other_obj['size'], 0.5)
            if other_obj['shape'] == 'cube':
                other_r /= math.sqrt(2)
            
            dist = math.sqrt((new_x - other_x)**2 + (new_y - other_y)**2)
            if dist < (new_r + other_r + min_dist):
                collision = True
                break
        
        if not collision:
            new_obj = {
                'shape': new_shape,
                'color': random.choice(colors),
                'material': random.choice(materials),
                'size': new_size,
                '3d_coords': [new_x, new_y, 0.35],
                'rotation': random.uniform(0, 360),
                'pixel_coords': [0, 0, 0]
            }
            cf_scene['objects'].append(new_obj)
            return cf_scene, f"added {new_obj['color']} {new_obj['material']} {new_obj['shape']}"
    
    return cf_scene, "no change (couldn't find collision-free position for new object)"

def cf_remove_object(scene):
    cf_scene = copy.deepcopy(scene)
    
    if len(cf_scene['objects']) <= 1:
        return cf_scene, "no removal (1 or fewer objects)"
    
    remove_idx = random.randint(0, len(cf_scene['objects']) - 1)
    removed_obj = cf_scene['objects'].pop(remove_idx)
    
    return cf_scene, f"removed {removed_obj['color']} {removed_obj['shape']}"

def cf_replace_object(scene):
    cf_scene = copy.deepcopy(scene)
    
    if len(cf_scene['objects']) == 0:
        return cf_scene, "no replace (0 objects)"
    
    replace_idx = random.randint(0, len(cf_scene['objects']) - 1)
    old_obj = cf_scene['objects'][replace_idx]
    old_desc = f"{old_obj['color']} {old_obj['shape']}"
    
    shapes = ['cube', 'sphere', 'cylinder']
    colors = ['gray', 'red', 'blue', 'green', 'brown', 'purple', 'cyan', 'yellow']
    materials = ['metal', 'rubber']
    sizes = ['small', 'large']
    
    new_shape = random.choice([s for s in shapes if s != old_obj['shape']] or shapes)
    new_color = random.choice([c for c in colors if c != old_obj['color']] or colors)
    
    new_obj = {
        'shape': new_shape,
        'color': new_color,
        'material': random.choice(materials),
        'size': random.choice(sizes),
        '3d_coords': old_obj['3d_coords'],
        'rotation': random.uniform(0, 360),
        'pixel_coords': [0, 0, 0]
    }
    
    cf_scene['objects'][replace_idx] = new_obj
    
    return cf_scene, f"replaced {old_desc} with {new_color} {new_shape}"

def cf_change_background(scene):
    cf_scene = copy.deepcopy(scene)
    
    background_colors = ['gray', 'blue', 'green', 'brown', 'purple', 'orange', 'white', 'dark_gray']
    current_bg = cf_scene.get('background_color', 'default')
    
    alternatives = [c for c in background_colors if c != current_bg]
    new_background = random.choice(alternatives) if alternatives else 'gray'
    
    cf_scene['background_color'] = new_background
    
    return cf_scene, f"changed background to {new_background}"

def cf_change_texture(scene):
    cf_scene = copy.deepcopy(scene)
    
    if len(cf_scene['objects']) == 0:
        return cf_scene, "no change (0 objects)"
    
    current_materials = {obj.get('material') for obj in cf_scene.get('objects', [])}
    new_material = random.choice(['metal', 'rubber'])
    if len(current_materials) == 1 and new_material in current_materials:
        new_material = 'rubber' if new_material == 'metal' else 'metal'
    changed_count = 0
    
    for obj in cf_scene['objects']:
        if obj['material'] != new_material:
            obj['material'] = new_material
            changed_count += 1
    
    cf_scene['texture_style'] = new_material
    
    return cf_scene, f"changed {changed_count} objects to {new_material} texture"

def cf_change_shape(scene):
    cf_scene = copy.deepcopy(scene)
    
    if len(cf_scene['objects']) == 0:
        return cf_scene, "no change (0 objects)"
    
    change_idx = random.randint(0, len(cf_scene['objects']) - 1)
    obj = cf_scene['objects'][change_idx]
    
    shapes = ['cube', 'sphere', 'cylinder']
    old_shape = obj['shape']
    new_shape = random.choice([s for s in shapes if s != old_shape])
    obj['shape'] = new_shape
    
    return cf_scene, f"changed {obj['color']} {old_shape} to {new_shape}"

def cf_change_size(scene):
    cf_scene = copy.deepcopy(scene)
    
    if len(cf_scene['objects']) == 0:
        return cf_scene, "no change (0 objects)"
    
    change_idx = random.randint(0, len(cf_scene['objects']) - 1)
    obj = cf_scene['objects'][change_idx]
    
    old_size = obj['size']
    new_size = 'large' if old_size == 'small' else 'small'
    obj['size'] = new_size
    
    return cf_scene, f"changed {obj['color']} {obj['shape']} from {old_size} to {new_size}"

def cf_change_material(scene):
    cf_scene = copy.deepcopy(scene)
    
    if len(cf_scene['objects']) == 0:
        return cf_scene, "no change (0 objects)"
    
    change_idx = random.randint(0, len(cf_scene['objects']) - 1)
    obj = cf_scene['objects'][change_idx]
    
    old_material = obj['material']
    new_material = 'rubber' if old_material == 'metal' else 'metal'
    obj['material'] = new_material
    
    return cf_scene, f"changed {obj['color']} {obj['shape']} from {old_material} to {new_material}"

def cf_change_lighting(scene):
    cf_scene = copy.deepcopy(scene)
    
    lighting_conditions = ['bright', 'dim', 'warm', 'cool', 'dramatic']
    current_lighting = cf_scene.get('lighting', 'default')
    
    alternatives = [l for l in lighting_conditions if l != current_lighting]
    new_lighting = random.choice(alternatives) if alternatives else 'bright'
    
    cf_scene['lighting'] = new_lighting
    
    return cf_scene, f"changed lighting to {new_lighting}"

def cf_add_noise(scene, min_noise_level='light'):
    cf_scene = copy.deepcopy(scene)
    
    noise_levels = ['light', 'medium', 'heavy']
    noise_weights = {'light': 0, 'medium': 1, 'heavy': 2}
    
    min_weight = noise_weights.get(min_noise_level, 0)
    valid_levels = [n for n in noise_levels if noise_weights[n] >= min_weight]
    
    current = cf_scene.get('noise_level', None)
    choices = [n for n in valid_levels if n != current] if current in valid_levels else valid_levels
    
    if not choices:
        choices = [min_noise_level] if min_noise_level in noise_levels else ['medium']
    
    cf_scene['noise_level'] = random.choice(choices)
    
    return cf_scene, f"added {cf_scene['noise_level']} noise (min: {min_noise_level})"

def cf_apply_fisheye(scene):
    cf_scene = copy.deepcopy(scene)
    
    current_filter = cf_scene.get('filter_type', None)
    if current_filter == 'fisheye':
        filter_strength = random.uniform(0.8, 1.2)
    else:
        filter_strength = random.uniform(0.8, 1.2)
    
    cf_scene['filter_type'] = 'fisheye'
    cf_scene['filter_strength'] = filter_strength
    
    return cf_scene, f"applied fisheye filter (strength: {filter_strength:.2f})"

def cf_apply_blur(scene):
    cf_scene = copy.deepcopy(scene)
    
    current_filter = cf_scene.get('filter_type', None)
    if current_filter == 'blur':
        filter_strength = random.uniform(8.0, 15.0)
    else:
        filter_strength = random.uniform(8.0, 15.0)
    
    cf_scene['filter_type'] = 'blur'
    cf_scene['filter_strength'] = filter_strength
    
    return cf_scene, f"applied blur filter (strength: {filter_strength:.2f})"

def cf_apply_vignette(scene):
    cf_scene = copy.deepcopy(scene)
    
    current_filter = cf_scene.get('filter_type', None)
    if current_filter == 'vignette':
        filter_strength = random.uniform(3.0, 5.0)
    else:
        filter_strength = random.uniform(3.0, 5.0)
    
    cf_scene['filter_type'] = 'vignette'
    cf_scene['filter_strength'] = filter_strength
    
    return cf_scene, f"applied vignette filter (strength: {filter_strength:.2f})"

def cf_apply_chromatic_aberration(scene):
    cf_scene = copy.deepcopy(scene)
    
    current_filter = cf_scene.get('filter_type', None)
    if current_filter == 'chromatic_aberration':
        filter_strength = random.uniform(1.0, 4.0)
    else:
        filter_strength = random.uniform(1.0, 4.0)
    
    cf_scene['filter_type'] = 'chromatic_aberration'
    cf_scene['filter_strength'] = filter_strength
    
    return cf_scene, f"applied chromatic aberration filter (strength: {filter_strength:.2f})"

IMAGE_COUNTERFACTUALS = {
    'change_color': cf_change_color,
    'change_shape': cf_change_shape,
    'change_size': cf_change_size,
    'change_material': cf_change_material,
    'change_position': cf_change_position,
    'change_count': cf_change_surrounding_count,
    'add_object': cf_add_object,
    'remove_object': cf_remove_object,
    'replace_object': cf_replace_object,
}

# Negative CFs - These should NOT change answers to questions
NEGATIVE_COUNTERFACTUALS = {
    'change_background': cf_change_background,
    'change_texture': cf_change_texture,
    'change_lighting': cf_change_lighting,
    'add_noise': cf_add_noise,
    'apply_fisheye': cf_apply_fisheye,
    'apply_blur': cf_apply_blur,
    'apply_vignette': cf_apply_vignette,
    'apply_chromatic_aberration': cf_apply_chromatic_aberration,
}

COUNTERFACTUAL_TYPES = {**IMAGE_COUNTERFACTUALS, **NEGATIVE_COUNTERFACTUALS}

def generate_counterfactuals(scene, num_counterfactuals=2, cf_types=None, min_change_score=1.0, max_cf_attempts=10, min_noise_level='light'):
    counterfactuals = []

    def compute_change_score(original_scene, cf_scene):
        score = 0.0
        if not isinstance(original_scene, dict) or not isinstance(cf_scene, dict):
            return score

        orig_objs = original_scene.get('objects', []) or []
        cf_objs = cf_scene.get('objects', []) or []

        # Count changes are usually very noticeable
        if len(orig_objs) != len(cf_objs):
            score += 5.0

        # Object-level changes
        n = min(len(orig_objs), len(cf_objs))
        for i in range(n):
            o = orig_objs[i] or {}
            c = cf_objs[i] or {}
            for k in ['color', 'shape', 'size', 'material']:
                if o.get(k) != c.get(k):
                    score += 1.0

            # Position change (XY distance)
            o3 = o.get('3d_coords')
            c3 = c.get('3d_coords')
            try:
                if o3 and c3 and len(o3) >= 2 and len(c3) >= 2:
                    dx = float(c3[0]) - float(o3[0])
                    dy = float(c3[1]) - float(o3[1])
                    dist = math.sqrt(dx * dx + dy * dy)
                    score += min(dist, 3.0)  # cap so it doesn't dominate
            except Exception:
                pass

            # Rotation change (small weight)
            try:
                if o.get('rotation') is not None and c.get('rotation') is not None:
                    rot_diff = abs(float(c.get('rotation')) - float(o.get('rotation')))
                    rot_diff = min(rot_diff, 360.0 - rot_diff)
                    score += min(rot_diff / 180.0, 1.0) * 0.5
            except Exception:
                pass

        # Scene-level (negative CF) fields
        if 'background_color' in cf_scene and original_scene.get('background_color') != cf_scene.get('background_color'):
            score += 1.0
            if cf_scene.get('background_color') in ['white', 'dark_gray']:
                score += 0.5
        if 'lighting' in cf_scene and original_scene.get('lighting') != cf_scene.get('lighting'):
            score += 1.0
        # NOTE: we intentionally DO NOT score `texture_style` because it is a
        # derived field; the true visual change is captured by object material diffs.
        if 'noise_level' in cf_scene and original_scene.get('noise_level') != cf_scene.get('noise_level'):
            score += {'light': 0.5, 'medium': 1.0, 'heavy': 1.5}.get(cf_scene.get('noise_level'), 0.8)
        if 'filter_type' in cf_scene and original_scene.get('filter_type') != cf_scene.get('filter_type'):
            # Filters are usually quite noticeable
            filter_strength = cf_scene.get('filter_strength', 1.0)
            score += min(filter_strength, 2.0)  # Cap at 2.0

        return score

    def generate_one_with_min_change(cf_func, min_change_score=0.0, max_attempts=10):
        best_scene = None
        best_desc = None
        best_score = -1.0
        attempts = 0
        for attempt in range(max_attempts):
            attempts = attempt + 1
            # Special handling for add_noise to pass min_noise_level
            if cf_func == cf_add_noise:
                candidate_scene, candidate_desc = cf_func(scene, min_noise_level=min_noise_level)
            else:
                candidate_scene, candidate_desc = cf_func(scene)
            score = compute_change_score(scene, candidate_scene)
            if score > best_score:
                best_scene, best_desc, best_score = candidate_scene, candidate_desc, score
            if score >= min_change_score:
                break
        return best_scene, best_desc, best_score, attempts
    
    # If specific types requested
    if cf_types:
        # Deterministic: follow the order provided on the command line; cycle if needed.
        selected_types = (cf_types * ((num_counterfactuals // len(cf_types)) + 1))[:num_counterfactuals]
        
        for cf_type in selected_types:
            if cf_type not in COUNTERFACTUAL_TYPES:
                print(f"WARNING: Unknown CF type '{cf_type}', skipping")
                continue
            
            cf_func = COUNTERFACTUAL_TYPES[cf_type]
            cf_scene, cf_desc, change_score, change_attempts = generate_one_with_min_change(
                cf_func,
                min_change_score=min_change_score,
                max_attempts=max_cf_attempts
            )
            cf_category = 'image_cf' if cf_type in IMAGE_COUNTERFACTUALS else 'negative_cf'
            
            counterfactuals.append({
                'scene': cf_scene,
                'description': cf_desc,
                'type': cf_type,
                'cf_category': cf_category,
                'change_score': change_score,
                'change_attempts': change_attempts,
            })
    
    # Default behavior (existing code)
    elif num_counterfactuals >= 2:
        # One Image CF + One Negative CF
        image_cf_type = random.choice(list(IMAGE_COUNTERFACTUALS.keys()))
        image_cf_func = IMAGE_COUNTERFACTUALS[image_cf_type]
        cf_scene, cf_desc, change_score, change_attempts = generate_one_with_min_change(
            image_cf_func,
            min_change_score=min_change_score,
            max_attempts=max_cf_attempts
        )
        counterfactuals.append({
            'scene': cf_scene,
            'description': cf_desc,
            'type': image_cf_type,
            'cf_category': 'image_cf',
            'change_score': change_score,
            'change_attempts': change_attempts,
        })
        
        neg_cf_type = random.choice(list(NEGATIVE_COUNTERFACTUALS.keys()))
        neg_cf_func = NEGATIVE_COUNTERFACTUALS[neg_cf_type]
        cf_scene, cf_desc, change_score, change_attempts = generate_one_with_min_change(
            neg_cf_func,
            min_change_score=min_change_score,
            max_attempts=max_cf_attempts
        )
        counterfactuals.append({
            'scene': cf_scene,
            'description': cf_desc,
            'type': neg_cf_type,
            'cf_category': 'negative_cf',
            'change_score': change_score,
            'change_attempts': change_attempts,
        })
        
        # Add more if requested
        remaining = num_counterfactuals - 2
        if remaining > 0:
            all_cf_types = list(COUNTERFACTUAL_TYPES.keys())
            used_types = {image_cf_type, neg_cf_type}
            available = [t for t in all_cf_types if t not in used_types]
            
            extra_types = random.sample(available, min(remaining, len(available)))
            for cf_type in extra_types:
                cf_func = COUNTERFACTUAL_TYPES[cf_type]
                cf_scene, cf_desc, change_score, change_attempts = generate_one_with_min_change(
                    cf_func,
                    min_change_score=min_change_score,
                    max_attempts=max_cf_attempts
                )
                cf_category = 'image_cf' if cf_type in IMAGE_COUNTERFACTUALS else 'negative_cf'
                counterfactuals.append({
                    'scene': cf_scene,
                    'description': cf_desc,
                    'type': cf_type,
                    'cf_category': cf_category,
                    'change_score': change_score,
                    'change_attempts': change_attempts,
                })
    
    elif num_counterfactuals == 1:
        if random.random() < 0.5:
            cf_type = random.choice(list(IMAGE_COUNTERFACTUALS.keys()))
            cf_func = IMAGE_COUNTERFACTUALS[cf_type]
            cf_category = 'image_cf'
        else:
            cf_type = random.choice(list(NEGATIVE_COUNTERFACTUALS.keys()))
            cf_func = NEGATIVE_COUNTERFACTUALS[cf_type]
            cf_category = 'negative_cf'
        
        cf_scene, cf_desc, change_score, change_attempts = generate_one_with_min_change(
            cf_func,
            min_change_score=min_change_score,
            max_attempts=max_cf_attempts
        )
        counterfactuals.append({
            'scene': cf_scene,
            'description': cf_desc,
            'type': cf_type,
            'cf_category': cf_category,
            'change_score': change_score,
            'change_attempts': change_attempts,
        })
    
    return counterfactuals

def render_scene(blender_path, scene_file, output_image, use_gpu=0, samples=512, width=320, height=240):
    current_dir = os.path.dirname(os.path.abspath(__file__))
    current_dir = os.path.dirname(os.path.abspath(__file__))
    render_script = os.path.join(current_dir, 'scripts', 'render.py')
    render_script = os.path.normpath(render_script)
    
    # Get paths to data files
    base_scene = os.path.join(current_dir, 'data', 'base_scene.blend')
    properties_json = os.path.join(current_dir, 'data', 'properties.json')
    shape_dir = os.path.join(current_dir, 'data', 'shapes')
    material_dir = os.path.join(current_dir, 'data', 'materials')
    
    # Normalize all paths for Windows compatibility
    base_scene = os.path.normpath(base_scene)
    properties_json = os.path.normpath(properties_json)
    shape_dir = os.path.normpath(shape_dir)
    material_dir = os.path.normpath(material_dir)
    scene_file = os.path.normpath(scene_file)
    output_image = os.path.normpath(output_image)
    
    # Verify required files exist
    if not os.path.exists(base_scene):
        print(f"  ERROR: Base scene file not found: {base_scene}")
        return False
    if not os.path.exists(properties_json):
        print(f"  ERROR: Properties JSON not found: {properties_json}")
        return False
    if not os.path.exists(scene_file):
        print(f"  ERROR: Scene file not found: {scene_file}")
        return False
    
    # Ensure output directory exists
    output_dir = os.path.dirname(output_image)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
    
    # Use absolute path for output_image to avoid path mismatch issues
    output_image_abs = os.path.abspath(output_image)
    
    cmd = [
        blender_path, '--background', '-noaudio', '--python', render_script, '--',
        '--scene_file', scene_file,
        '--output_image', output_image_abs,
        '--base_scene_blendfile', base_scene,
        '--properties_json', properties_json,
        '--shape_dir', shape_dir,
        '--material_dir', material_dir,
        '--use_gpu', str(use_gpu),
        '--render_num_samples', str(samples),
        '--width', str(width),
        '--height', str(height)
    ]
    
    env = os.environ.copy()
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600, env=env)
    
    # Apply filters using system Python (PIL might not be available in Blender's Python)
    if result.returncode == 0 and os.path.exists(output_image_abs):
        try:
            import json
            with open(scene_file, 'r') as f:
                scene_data = json.load(f)
            
            filter_type = scene_data.get('filter_type')
            noise_level = scene_data.get('noise_level')
            
            if filter_type or noise_level:
                try:
                    from PIL import Image, ImageFilter
                    import math
                    
                    filter_strength = scene_data.get('filter_strength', 1.0)
                    img = Image.open(output_image_abs)
                    
                    if filter_type == 'blur':
                        radius = max(1, int(filter_strength))
                        img = img.filter(ImageFilter.GaussianBlur(radius=radius))
                    
                    elif filter_type == 'vignette':
                        width, height = img.size
                        center_x, center_y = width // 2, height // 2
                        max_dist = math.sqrt(center_x**2 + center_y**2)
                        img = img.convert('RGB')
                        pixels = img.load()
                        for y in range(height):
                            for x in range(width):
                                dist = math.sqrt((x - center_x)**2 + (y - center_y)**2)
                                factor = 1.0 - (dist / max_dist) * (filter_strength / 5.0)
                                factor = max(0.0, min(1.0, factor))
                                r, g, b = pixels[x, y]
                                pixels[x, y] = (int(r * factor), int(g * factor), int(b * factor))
                    
                    elif filter_type == 'fisheye':
                        width, height = img.size
                        center_x, center_y = width / 2.0, height / 2.0
                        max_radius = min(center_x, center_y)
                        img = img.convert('RGB')
                        output = Image.new('RGB', (width, height))
                        out_pixels = output.load()
                        in_pixels = img.load()
                        
                        distortion_strength = 0.55 * filter_strength
                        
                        for y in range(height):
                            for x in range(width):
                                dx = (x - center_x) / max_radius
                                dy = (y - center_y) / max_radius
                                distance = math.sqrt(dx*dx + dy*dy)
                                
                                if distance >= 1.0:
                                    out_pixels[x, y] = in_pixels[x, y]
                                else:
                                    theta = math.atan2(dy, dx)
                                    r_normalized = distance
                                    
                                    r_distorted = math.atan(2 * r_normalized * distortion_strength) / math.atan(2 * distortion_strength)
                                    r_distorted = min(0.999, r_distorted)
                                    
                                    src_x = int(center_x + r_distorted * max_radius * math.cos(theta))
                                    src_y = int(center_y + r_distorted * max_radius * math.sin(theta))
                                    
                                    if 0 <= src_x < width and 0 <= src_y < height:
                                        out_pixels[x, y] = in_pixels[src_x, src_y]
                                    else:
                                        out_pixels[x, y] = in_pixels[x, y]
                        
                        img = output
                    
                    elif filter_type == 'chromatic_aberration':
                        width, height = img.size
                        img = img.convert('RGB')
                        output = Image.new('RGB', (width, height))
                        out_pixels = output.load()
                        in_pixels = img.load()
                        
                        offset = int(filter_strength * 2)
                        
                        for y in range(height):
                            for x in range(width):
                                r_x = max(0, min(width - 1, x - offset))
                                g_x = x
                                b_x = max(0, min(width - 1, x + offset))
                                
                                r = in_pixels[r_x, y][0] if 0 <= r_x < width else 0
                                g = in_pixels[g_x, y][1] if 0 <= g_x < width else 0
                                b = in_pixels[b_x, y][2] if 0 <= b_x < width else 0
                                
                                out_pixels[x, y] = (r, g, b)
                        
                        img = output
                    
                    # Apply noise if present (separate from filter_type)
                    if noise_level:
                        import random
                        noise_amounts = {'light': 10, 'medium': 25, 'heavy': 50}
                        noise_amount = noise_amounts.get(noise_level, 20)
                        img = img.convert('RGB')
                        pixels = img.load()
                        width, height = img.size
                        
                        for y in range(height):
                            for x in range(width):
                                r, g, b = pixels[x, y]
                                noise_r = random.randint(-noise_amount, noise_amount)
                                noise_g = random.randint(-noise_amount, noise_amount)
                                noise_b = random.randint(-noise_amount, noise_amount)
                                
                                r = max(0, min(255, r + noise_r))
                                g = max(0, min(255, g + noise_g))
                                b = max(0, min(255, b + noise_b))
                                
                                pixels[x, y] = (r, g, b)
                    
                    img.save(output_image_abs)
                except ImportError:
                    pass
                except Exception as e:
                    print(f"  Warning: Could not apply filter {filter_type}: {e}")
        
        except Exception as e:
            pass
    
    if result.returncode == 0 and os.path.exists(output_image_abs):
        return True
    else:
        print(f"  ERROR rendering {output_image_abs}")
        print(f"  Return code: {result.returncode}")
        print(f"  Output file exists: {os.path.exists(output_image_abs)}")
        if result.stderr:
            print(f"  Blender stderr (last 1000 chars):")
            print(result.stderr[-1000:])
        if result.stdout:
            # Print all output for debugging
            print(f"  Blender stdout (last 1000 chars):")
            print(result.stdout[-1000:])
            error_lines = [line for line in result.stdout.split('\n') if 'ERROR' in line.upper() or 'Traceback' in line or 'Exception' in line or 'failed' in line.lower()]
            if error_lines:
                error_msg = '\n'.join(error_lines[-20:])
                print(f"  Error lines found: {error_msg}")
        return False

def save_scene(scene, output_path):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(scene, f, indent=2)

def list_counterfactual_types():
    print("\n" + "="*70)
    print("AVAILABLE COUNTERFACTUAL TYPES")
    print("="*70)
    
    print("\nIMAGE COUNTERFACTUALS (Should change VQA answers):")
    print("  change_color       - Change color of an object")
    print("  change_shape       - Change shape of an object (cube/sphere/cylinder)")
    print("  change_size        - Change size of an object (small/large)")
    print("  change_material    - Change material of an object (metal/rubber)")
    print("  change_position    - Move an object to a different location")
    print("  change_count       - Add or remove objects from the scene")
    print("  add_object         - Add a new random object")
    print("  remove_object      - Remove a random object")
    print("  replace_object     - Replace an object with a different one")
    
    print("\nNEGATIVE COUNTERFACTUALS (Should NOT change VQA answers):")
    print("  change_background  - Change background/ground color")
    print("  change_texture     - Change texture style (all objects)")
    print("  change_lighting    - Change lighting conditions")
    print("  add_noise          - Add image noise/grain")
    print("  apply_fisheye      - Apply fisheye lens distortion")
    print("  apply_blur         - Apply Gaussian blur")
    print("  apply_vignette     - Apply vignette (edge darkening)")
    print("  apply_chromatic_aberration - Apply chromatic aberration (color fringing)")
    
    print("\n" + "="*70)
    print("\nUsage examples:")
    print("  # Use specific types")
    print("  python pipeline.py --num_scenes 10 --cf_types change_color change_position")
    print("  ")
    print("  # Mix image and negative CFs")
    print("  python pipeline.py --num_scenes 10 --cf_types change_shape change_lighting")
    print("  ")
    print("  # Only negative CFs")
    print("  python pipeline.py --num_scenes 10 --cf_types change_background add_noise")
    print("="*70 + "\n")

def find_scene_files(scenes_dir):
    scene_files = glob.glob(os.path.join(scenes_dir, 'scene_*.json'))
    scene_sets = {}
    
    for scene_file in scene_files:
        basename = os.path.basename(scene_file)
        # Parse: scene_0000_original.json or scene_0000_cf1.json
        parts = basename.replace('.json', '').split('_')
        if len(parts) >= 3:
            scene_num = int(parts[1])
            variant = '_'.join(parts[2:])  # original, cf1, cf2, etc.
            
            if scene_num not in scene_sets:
                scene_sets[scene_num] = {}
            scene_sets[scene_num][variant] = scene_file
    
    return scene_sets

def render_existing_scenes(args):
    import json
    
    # Determine run directory
    if args.run_dir:
        run_dir = args.run_dir
    elif args.run_name:
        run_dir = os.path.join(args.output_dir, args.run_name)
    elif args.auto_latest:
        # Find latest run
        if not os.path.exists(args.output_dir):
            print(f"ERROR: Output directory does not exist: {args.output_dir}")
            return
        
        subdirs = [d for d in os.listdir(args.output_dir) 
                  if os.path.isdir(os.path.join(args.output_dir, d))]
        if not subdirs:
            print(f"ERROR: No run directories found in {args.output_dir}")
            return
        
        # Sort by modification time
        dirs_with_time = [(d, os.path.getmtime(os.path.join(args.output_dir, d))) 
                         for d in subdirs]
        latest = max(dirs_with_time, key=lambda x: x[1])[0]
        run_dir = os.path.join(args.output_dir, latest)
        print(f"Using latest run: {run_dir}")
    else:
        print("ERROR: Must specify --run_dir, --run_name, or --auto_latest for --render_only")
        return
    
    if not os.path.exists(run_dir):
        print(f"ERROR: Run directory does not exist: {run_dir}")
        return
    
    scenes_dir = os.path.join(run_dir, 'scenes')
    images_dir = os.path.join(run_dir, 'images')
    
    if not os.path.exists(scenes_dir):
        print(f"ERROR: Scenes directory does not exist: {scenes_dir}")
        return
    
    os.makedirs(images_dir, exist_ok=True)
    
    # Find Blender
    blender_path = args.blender_path or find_blender()
    print(f"Using Blender: {blender_path}")
    
    # Create patched render script
    print("\nPreparing render scripts...")
    create_patched_render_script()
    
    # Find all scene files
    scene_sets = find_scene_files(scenes_dir)
    total_scenes = len(scene_sets)
    
    if total_scenes == 0:
        print(f"ERROR: No scene JSON files found in {scenes_dir}")
        return
    
    print(f"\nFound {total_scenes} scene sets to render")
    
    # Checkpoint file
    checkpoint_file = os.path.join(run_dir, 'render_checkpoint.json')
    
    # Check for resume
    completed_scenes = set()
    if args.resume:
        completed_scenes = load_checkpoint(checkpoint_file)
        # Also check rendered images
        rendered_scenes = get_completed_scenes_from_folder(images_dir)
        completed_scenes.update(rendered_scenes)
        
        if completed_scenes:
            print(f"\n[RESUME] Found {len(completed_scenes)} already rendered scenes")
    
    print("\n" + "="*70)
    print(f"RENDERING {total_scenes} SCENE SETS")
    print("="*70)
    
    successful_renders = 0
    
    for scene_num in sorted(scene_sets.keys()):
        if scene_num in completed_scenes:
            print(f"\n[SKIP] Skipping scene {scene_num} (already rendered)")
            successful_renders += 1
            continue
        
        print(f"\n{'='*70}")
        print(f"SCENE SET {scene_num+1}/{total_scenes} (Scene #{scene_num})")
        print(f"{'='*70}")
        
        scene_set = scene_sets[scene_num]
        total_to_render = len(scene_set)
        render_success = 0
        
        for variant, scene_file in scene_set.items():
            scene_prefix = f"scene_{scene_num:04d}"
            image_file = os.path.join(images_dir, f"{scene_prefix}_{variant}.png")
            
            print(f"  Rendering {variant}...")
            if render_scene(blender_path, scene_file, image_file, 
                          args.use_gpu, args.samples, args.width, args.height):
                render_success += 1
                print(f"    [OK] {variant}")
            else:
                print(f"    [FAILED] {variant}")
        
            if render_success == total_to_render:
                successful_renders += 1
                completed_scenes.add(scene_num)
                save_checkpoint(checkpoint_file, list(completed_scenes))
        
        print(f"  [OK] Rendered {render_success}/{total_to_render} images")
    
    # Update metadata
    metadata_path = os.path.join(run_dir, 'run_metadata.json')
    if os.path.exists(metadata_path):
        with open(metadata_path, 'r') as f:
            metadata = json.load(f)
        metadata['successful_renders'] = successful_renders
        metadata['rendered_timestamp'] = datetime.now().isoformat()
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
    
    # Summary
    print("\n" + "="*70)
    print("RENDERING COMPLETE")
    print("="*70)
    print(f"Run directory: {run_dir}")
    print(f"Successfully rendered: {successful_renders}/{total_scenes} scene sets")
    print(f"\nOutput:")
    print(f"  Images: {images_dir}/")
    print(f"  Checkpoint: {checkpoint_file}")
    print("="*70)

def is_running_on_huggingface():
    return (
        os.environ.get('SPACES_REPO_TYPE') is not None or
        os.environ.get('SPACES_REPO_ID') is not None or
        os.environ.get('SPACE_ID') is not None or
        os.environ.get('HF_HOME') is not None or
        'huggingface' in str(os.environ.get('PATH', '')).lower() or
        os.path.exists('/.dockerenv')
    )

def create_downloadable_archive(run_dir, output_zip_path=None):
    if not is_running_on_huggingface():
        return None
    
    if not os.path.exists(run_dir):
        print(f"Warning: Run directory does not exist: {run_dir}")
        return None
    
    if output_zip_path is None:
        run_name = os.path.basename(run_dir)
        # Save to workspace root for Hugging Face Spaces accessibility
        output_zip_path = os.path.join(os.path.dirname(os.path.dirname(run_dir)) if 'output' in run_dir else '.', f"{run_name}.zip")
        # Ensure absolute path for clarity
        output_zip_path = os.path.abspath(output_zip_path)
    
    print(f"\n[ARCHIVE] Creating downloadable archive: {output_zip_path}")
    print(f"   (This file will be available in the Files tab)")
    
    try:
        with zipfile.ZipFile(output_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(run_dir):
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                
                for file in files:
                    if file.startswith('.'):
                        continue
                    
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, os.path.dirname(run_dir))
                    zipf.write(file_path, arcname)
        
        zip_size = os.path.getsize(output_zip_path) / (1024 * 1024)
        print(f"[OK] Archive created successfully ({zip_size:.2f} MB)")
        print(f"  File location: {os.path.abspath(output_zip_path)}")
        print(f"  To download: Go to the 'Files' tab in your Hugging Face Space and download '{os.path.basename(output_zip_path)}'")
        return output_zip_path
    except Exception as e:
        print(f"[WARNING] Could not create archive: {e}")
        return None

def save_run_metadata(run_dir, args, successful_scenes, successful_renders):
    metadata = {
        'timestamp': datetime.now().isoformat(),
        'run_directory': run_dir,
        'arguments': {
            'num_scenes': args.num_scenes,
            'num_objects': args.num_objects,
            'min_objects': args.min_objects,
            'max_objects': args.max_objects,
            'num_counterfactuals': args.num_counterfactuals,
            'use_gpu': args.use_gpu,
            'samples': args.samples,
            'width': args.width,
            'height': args.height,
            'cf_types': args.cf_types if args.cf_types else 'default (1 image + 1 negative)',
            'min_cf_change_score': args.min_cf_change_score,
            'max_cf_attempts': args.max_cf_attempts,
        },
        
        'results': {
            'scenes_generated': successful_scenes,
            'scenes_rendered': successful_renders,
            'total_images': successful_renders * (args.num_counterfactuals + 1) if not args.skip_render else 0,
        },
        'cf_types_used': args.cf_types if args.cf_types else list(COUNTERFACTUAL_TYPES.keys())
    }
    
    metadata_path = os.path.join(run_dir, 'run_metadata.json')
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    print(f"\n[OK] Saved run metadata to: {metadata_path}")

def main():
    # When run as a script, ensure we're in the project root
    # Change to script directory so relative paths work
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    
    parser = argparse.ArgumentParser(description='Generate and render multiple CLEVR scene sets with diverse counterfactuals and resume support')
    parser.add_argument('--num_scenes', type=int, default=5,
                       help='Number of scene sets to generate')
    parser.add_argument('--num_objects', type=int, default=None,
                       help='Fixed number of objects per scene')
    parser.add_argument('--min_objects', type=int, default=3,
                       help='Minimum objects per scene (if num_objects not set)')
    parser.add_argument('--max_objects', type=int, default=7,
                       help='Maximum objects per scene (if num_objects not set)')
    parser.add_argument('--num_counterfactuals', type=int, default=2,
                       help='Number of counterfactual variants per scene (default: 2 = 1 Image CF + 1 Negative CF)')
    parser.add_argument('--blender_path', default=None,
                       help='Path to Blender executable')
    parser.add_argument('--output_dir', default='output',
                       help='Base output directory')
    parser.add_argument('--run_name', default=None,
                       help='Optional name for this run (required for resume)')
    parser.add_argument('--resume', action='store_true',
                       help='Resume from last checkpoint (requires --run_name)')
    parser.add_argument('--use_gpu', type=int, default=0,
                       help='Use GPU rendering (0 or 1)')
    parser.add_argument('--samples', type=int, default=512,
                       help='Number of render samples')
    parser.add_argument('--width', type=int, default=320,
                       help='Image width in pixels (default: 320)')
    parser.add_argument('--height', type=int, default=240,
                       help='Image height in pixels (default: 240)')
    parser.add_argument('--skip_render', action='store_true',
                       help='Only generate scenes, skip rendering')
    parser.add_argument('--render_only', action='store_true',
                       help='Only render existing scene JSON files (no generation). Requires --run_dir, --run_name, or --auto_latest')
    parser.add_argument('--run_dir', type=str, default=None,
                       help='Run directory containing scenes/ folder (for --render_only mode)')
    parser.add_argument('--auto_latest', action='store_true',
                       help='Automatically use the latest run in output_dir (for --render_only mode)')
    parser.add_argument('--cf_types', nargs='+', 
                   choices=[
                       # Image CFs (should change answers)
                       'change_color', 'change_shape', 'change_size', 
                       'change_material', 'change_position', 
                       'change_count', 'add_object', 'remove_object',
                       'replace_object',
                       # Negative CFs (should NOT change answers)
                       'change_background', 'change_texture', 
                       'change_lighting', 'add_noise',
                       'apply_fisheye', 'apply_blur', 'apply_vignette', 'apply_chromatic_aberration'
                   ],
                   help='Specific counterfactual types to use (if not specified, uses default: 1 image CF + 1 negative CF)')
    parser.add_argument('--min_cf_change_score', type=float, default=1.0,
                   help='Minimum heuristic change score for a counterfactual to be accepted (retries until met). Increase for more noticeable CFs.')
    parser.add_argument('--max_cf_attempts', type=int, default=10,
                   help='Max retries per counterfactual type to meet --min_cf_change_score (default: 10)')
    parser.add_argument('--min_noise_level', type=str, default='light',
                   choices=['light', 'medium', 'heavy'],
                   help='Minimum noise level when using add_noise counterfactual (default: light)')

    parser.add_argument('--list_cf_types', action='store_true',
                   help='List all available counterfactual types and exit')
    
    # Question generation arguments
    parser.add_argument('--generate_questions', action='store_true',
                       help='Generate questions and answers CSV after rendering completes')
    parser.add_argument('--csv_name', default='image_mapping_with_questions.csv',
                       help='Output CSV filename for question generation (default: image_mapping_with_questions.csv)')
    
    args = parser.parse_args()

    # List CF types and exit early (before any other validation/work)
    if args.list_cf_types:
        list_counterfactual_types()
        return
    
    # Handle render_only mode
    if args.render_only:
        render_existing_scenes(args)
        return
    
    # Validate resume
    if args.resume and not args.run_name:
        print("ERROR: --run_name is required when using --resume")
        return
    
    # Find Blender
    blender_path = args.blender_path or find_blender()
    print(f"Using Blender: {blender_path}")
    
    # Create patched files once
    print("\nPreparing scripts...")
    create_patched_render_script()
    # Note: utils functions are now merged into render.py, so no separate utils_patched needed
    
    # Create run directory
    run_dir = create_run_directory(args.output_dir, args.run_name)
    print(f"\n{'='*70}")
    print(f"RUN DIRECTORY: {run_dir}")
    print(f"{'='*70}")
    
    # Create output directories inside run folder
    scenes_dir = os.path.join(run_dir, 'scenes')
    images_dir = os.path.join(run_dir, 'images')
    os.makedirs(scenes_dir, exist_ok=True)
    os.makedirs(images_dir, exist_ok=True)
    
    # Checkpoint file
    checkpoint_file = os.path.join(run_dir, 'checkpoint.json')
    
    # Check for resume
    completed_scenes = set()
    if args.resume:
        # Check local checkpoint
        completed_scenes = load_checkpoint(checkpoint_file)
        
        # Also check rendered images
        rendered_scenes = get_completed_scenes_from_folder(images_dir)
        completed_scenes.update(rendered_scenes)
        
        if completed_scenes:
            print(f"\n[RESUME] Found {len(completed_scenes)} already completed scenes")
            print(f"   Completed: {sorted(completed_scenes)}")
            print(f"   Will generate scenes: {args.num_scenes}")
            print(f"   Remaining: {args.num_scenes - len(completed_scenes)}")
        else:
            print("\n[WARNING] Resume flag set but no checkpoint found, starting fresh")
    
    print("\n" + "="*70)
    print(f"GENERATING {args.num_scenes} SCENE SETS")
    print(f"Each with {args.num_counterfactuals} counterfactual variants")
    print(f"Available CF types: {len(COUNTERFACTUAL_TYPES)}")
    print("="*70)
    
    successful_scenes = 0
    successful_renders = 0
    
    for i in range(args.num_scenes):
        # Skip if already completed
        if i in completed_scenes:
            print(f"\n[SKIP] Skipping scene {i} (already completed)")
            successful_scenes += 1
            successful_renders += 1
            continue
        
        print(f"\n{'='*70}")
        print(f"SCENE SET {i+1}/{args.num_scenes} (Scene #{i})")
        print(f"{'='*70}")
        
        if args.num_objects is not None:
            num_objects = args.num_objects
        else:
            num_objects = random.randint(args.min_objects, args.max_objects)
        
        base_scene = None
        for retry in range(3):
            base_scene = generate_base_scene(num_objects, blender_path, i)
            if base_scene and len(base_scene['objects']) > 0:
                break
            print(f"  Retry {retry + 1}/3...")
        
        if not base_scene or len(base_scene['objects']) == 0:
            print(f"  [FAILED] Failed to generate scene {i+1}")
            continue
        
        successful_scenes += 1
        
        print(f"  Creating {args.num_counterfactuals} counterfactuals...")
        counterfactuals = generate_counterfactuals(
            base_scene,
            args.num_counterfactuals,
            cf_types=args.cf_types,
            min_change_score=args.min_cf_change_score,
            max_cf_attempts=args.max_cf_attempts,
            min_noise_level=args.min_noise_level
        )
        
        for idx, cf in enumerate(counterfactuals):
            cf_cat = cf.get('cf_category', 'unknown')
            print(f"    CF{idx+1} [{cf_cat}] ({cf['type']}): {cf['description']}")
        
        scene_prefix = f"scene_{i:04d}"
        scene_paths = {'original': os.path.join(scenes_dir, f"{scene_prefix}_original.json")}
        image_paths = {'original': os.path.join(images_dir, f"{scene_prefix}_original.png")}

        base_scene['cf_metadata'] = {
            'variant': 'original',
            'is_counterfactual': False,
            'cf_index': None,
            'cf_category': 'original',
            'cf_type': None,
            'cf_description': None,
            'source_scene': scene_prefix,
        }
        save_scene(base_scene, scene_paths['original'])
        
        for idx, cf in enumerate(counterfactuals):
            cf_name = f"cf{idx+1}"
            scene_paths[cf_name] = os.path.join(scenes_dir, f"{scene_prefix}_{cf_name}.json")
            image_paths[cf_name] = os.path.join(images_dir, f"{scene_prefix}_{cf_name}.png")

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
            save_scene(cf_scene, scene_paths[cf_name])
        
        print(f"  [OK] Saved {len(counterfactuals) + 1} scene files")
        
        if not args.skip_render:
            print("  Rendering...")
            render_success = 0
            total_to_render = len(counterfactuals) + 1
            
            for scene_type, scene_path in scene_paths.items():
                if render_scene(blender_path, scene_path, image_paths[scene_type], 
                               args.use_gpu, args.samples, args.width, args.height):
                    render_success += 1
                    print(f"    [OK] {scene_type}")
            
            if render_success == total_to_render:
                successful_renders += 1
                completed_scenes.add(i)
                save_checkpoint(checkpoint_file, list(completed_scenes))
            
            print(f"  [OK] Rendered {render_success}/{total_to_render} images")
        else:
            completed_scenes.add(i)
            save_checkpoint(checkpoint_file, list(completed_scenes))
    
    save_run_metadata(run_dir, args, successful_scenes, successful_renders)
    
    archive_path = create_downloadable_archive(run_dir)
    
    if os.path.exists('temp_output'):
        shutil.rmtree('temp_output')
    if os.path.exists('render_images_patched.py'):
        os.remove('render_images_patched.py')
    
    print("\n" + "="*70)
    print("PIPELINE COMPLETE")
    print("="*70)
    print(f"Run directory: {run_dir}")
    print(f"Successfully generated: {successful_scenes}/{args.num_scenes} scene sets")
    if not args.skip_render:
        print(f"Successfully rendered: {successful_renders}/{successful_scenes} scene sets")
    print(f"\nOutput:")
    print(f"  Scene files: {scenes_dir}/")
    if not args.skip_render:
        print(f"  Images: {images_dir}/")
    print(f"  Metadata: {os.path.join(run_dir, 'run_metadata.json')}")
    print(f"  Checkpoint: {checkpoint_file}")
    if archive_path:
        print(f"\n[ARCHIVE] Downloadable archive created:")
        print(f"  Filename: {os.path.basename(archive_path)}")
        print(f"  Location: {os.path.abspath(archive_path)}")
        print(f"  To download: Go to the 'Files' tab in your Hugging Face Space")
        print(f"     and look for '{os.path.basename(archive_path)}' in the file list")
    print(f"\nFile naming: scene_XXXX_original/cf1/cf2/....json/png")
    if args.cf_types:
        print(f"\nCounterfactual types requested: {', '.join(args.cf_types)}")
    else:
        print("\nCounterfactual types: default (mix of image_cf + negative_cf)")
    
    if args.resume and completed_scenes:
        print(f"\n[OK] Resume successful! Completed {len(completed_scenes)}/{args.num_scenes} scenes total")
    
    # Generate questions if requested
    if args.generate_questions and not args.skip_render:
        if generate_mapping_with_questions is None:
            print("\n[WARNING] Question generation module not found. Skipping question generation.")
        else:
            print("\n" + "="*70)
            print("GENERATING QUESTIONS AND ANSWERS")
            print("="*70)
            try:
                generate_mapping_with_questions(
                    run_dir,
                    args.csv_name,
                    generate_questions=True
                )
                print(f"\n[OK] Question generation complete! CSV saved to: {os.path.join(run_dir, args.csv_name)}")
            except Exception as e:
                print(f"\n[ERROR] Error generating questions: {e}")
                import traceback
                traceback.print_exc()

if __name__ == '__main__':
    main()