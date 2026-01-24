

import os
import argparse
import csv
import json
import random
import re
from pathlib import Path

def find_latest_run(base_output_dir):
    if not os.path.exists(base_output_dir):
        return None
    
    subdirs = [d for d in os.listdir(base_output_dir) 
               if os.path.isdir(os.path.join(base_output_dir, d))]
    
    if not subdirs:
        return None
    
    timestamped = [d for d in subdirs if re.match(r'^\d{8}_\d{6}$', d)]
    if timestamped:
        latest = sorted(timestamped)[-1]
        return os.path.join(base_output_dir, latest)
    
    dirs_with_time = [(d, os.path.getmtime(os.path.join(base_output_dir, d))) 
                      for d in subdirs]
    latest = max(dirs_with_time, key=lambda x: x[1])[0]
    return os.path.join(base_output_dir, latest)

def find_scene_file(scenes_dir, image_filename):
    base_name = os.path.splitext(image_filename)[0]
    scene_file = os.path.join(scenes_dir, base_name + '.json')
    
    if os.path.exists(scene_file):
        return scene_file
    return None

def load_scene(scene_file):
    with open(scene_file, 'r') as f:
        return json.load(f)

def get_scene_properties(scene):
    objects = scene.get('objects', [])
    if not objects:
        return {
            'colors': ['red', 'blue', 'green'],
            'shapes': ['cube', 'sphere', 'cylinder'],
            'materials': ['metal', 'rubber'],
            'sizes': ['small', 'large']
        }
    
    colors = list(set(obj.get('color') for obj in objects if obj.get('color')))
    shapes = list(set(obj.get('shape') for obj in objects if obj.get('shape')))
    materials = list(set(obj.get('material') for obj in objects if obj.get('material')))
    sizes = list(set(obj.get('size') for obj in objects if obj.get('size')))
    
    all_colors = ['gray', 'red', 'blue', 'green', 'brown', 'purple', 'cyan', 'yellow']
    all_shapes = ['cube', 'sphere', 'cylinder']
    all_materials = ['metal', 'rubber']
    all_sizes = ['small', 'large']
    
    return {
        'colors': colors if colors else all_colors,
        'shapes': shapes if shapes else all_shapes,
        'materials': materials if materials else all_materials,
        'sizes': sizes if sizes else all_sizes,
        'all_colors': all_colors,
        'all_shapes': all_shapes,
        'all_materials': all_materials,
        'all_sizes': all_sizes
    }

def generate_question_for_scene(scene_file):
    scene = load_scene(scene_file)
    objects = scene.get('objects', [])
    
    if len(objects) == 0:
        return "How many objects are in the scene?", {}
    
    props = get_scene_properties(scene)
    
    templates = [
        ("How many objects are in the scene?", {}),
        ("How many {color} objects are there?", {'color': random.choice(props['colors'])}),
        ("Are there any {shape} objects?", {'shape': random.choice(props['shapes'])}),
        ("Are there any {shape}s present?", {'shape': random.choice(props['shapes'])}),
        ("Is there a {color} {shape}?", {
            'color': random.choice(props['colors']),
            'shape': random.choice(props['shapes'])
        }),
        ("How many {material} objects are there?", {'material': random.choice(props['materials'])}),
        ("What is the total number of {material} objects?", {'material': random.choice(props['materials'])}),
        ("What is the total number of metallic objects?", {}),
        ("What is the total number of {size} objects?", {'size': random.choice(props['sizes'])}),
        ("Is there a {material} {shape}?", {
            'material': random.choice(props['materials']),
            'shape': random.choice(props['shapes'])
        }),
        ("How many {size} {color} objects are there?", {
            'size': random.choice(props['sizes']),
            'color': random.choice(props['colors'])
        }),
        ("Is the {color} {shape} matte or shiny?", {
            'color': random.choice(props['colors']),
            'shape': random.choice(props['shapes'])
        }),
        ("Are there any {color} {shape}s?", {
            'color': random.choice(props['colors']),
            'shape': random.choice(props['shapes'])
        }),
        ("What is the total number of {color} {material} objects?", {
            'color': random.choice(props['colors']),
            'material': random.choice(props['materials'])
        }),
    ]
    
    random.seed(hash(scene_file))
    template, params = random.choice(templates)
    
    question = template.format(**params) if params else template
    
    return question, params

def calculate_question_difficulty(question, params):
    num_params = len(params) if params else 0
    
    question_lower = question.lower()
    
    if "matte or shiny" in question_lower or ("or" in question_lower and ("matte" in question_lower or "shiny" in question_lower)):
        return "hard"
    elif "metallic" in question_lower:
        return "medium"
    elif "total number" in question_lower and num_params >= 1:
        return "hard" if num_params >= 2 else "medium"
    elif num_params == 0:
        return "easy"
    elif num_params == 1:
        return "medium"
    else:  # num_params >= 2
        return "hard"

def create_counterfactual_questions(original_question, params, scene):
    props = get_scene_properties(scene)
    cf_questions = []
    
    strategies = ['attribute_swap', 'question_type', 'scope_change', 
                  'negation', 'comparative', 'multi_attribute']
    
    random.seed(hash(str(scene)))
    selected_strategies = random.sample(strategies, 2)
    
    for strategy in selected_strategies:
        cf_q = None
        cf_params = {}
        max_retries = 5
        retry_count = 0
        
        while retry_count < max_retries:
            cf_q = None
            cf_params = {}
        
        if strategy == 'attribute_swap' and params:
            cf_params = params.copy()
            param_to_change = random.choice(list(params.keys()))
            
            if param_to_change == 'color':
                alternatives = [c for c in props['all_colors'] if c != params.get('color')]
                if alternatives:
                    cf_params['color'] = random.choice(alternatives)
                else:
                    strategy = 'negation'
                    continue
            elif param_to_change == 'shape':
                alternatives = [s for s in props['all_shapes'] if s != params.get('shape')]
                if alternatives:
                    cf_params['shape'] = random.choice(alternatives)
                else:
                    strategy = 'negation'
                    continue
            elif param_to_change == 'material':
                alternatives = [m for m in props['all_materials'] if m != params.get('material')]
                if alternatives:
                    cf_params['material'] = random.choice(alternatives)
                else:
                    strategy = 'negation'
                    continue
            elif param_to_change == 'size':
                alternatives = [s for s in props['all_sizes'] if s != params.get('size')]
                if alternatives:
                    cf_params['size'] = random.choice(alternatives)
                else:
                    strategy = 'negation'
                    continue
            
            cf_q = original_question
            for key, old_val in params.items():
                new_val = cf_params[key]
                if old_val != new_val:
                    cf_q = cf_q.replace(old_val, new_val)
        
        elif strategy == 'question_type':
            cf_params = params.copy() if params else {}
            if "How many" in original_question and "objects are in the scene" in original_question:
                if props['colors']:
                    color = random.choice(props['colors'])
                    cf_q = f"How many {color} objects are there?"
                    cf_params = {'color': color}
                elif props['shapes']:
                    shape = random.choice(props['shapes'])
                    cf_q = f"Are there any {shape}s?"
                    cf_params = {'shape': shape}
                else:
                    cf_q = "Are there more than 3 objects?"
                    cf_params = {}
            elif "How many" in original_question:
                cf_q = original_question.replace("How many", "Are there any")
                cf_q = cf_q.replace(" are there?", "?")
                cf_q = cf_q.replace(" are in the scene?", " in the scene?")
            elif "Are there" in original_question or "Is there" in original_question:
                if "Are there any" in original_question:
                    cf_q = original_question.replace("Are there any", "How many")
                    if not cf_q.endswith(" are there?"):
                        cf_q = cf_q.replace("?", " are there?")
                elif "Is there a" in original_question:
                    cf_q = original_question.replace("Is there a", "How many")
                    if not cf_q.endswith(" are there?"):
                        cf_q = cf_q.replace("?", " are there?")
                else:
                    if props['colors']:
                        color = random.choice(props['colors'])
                        cf_q = f"How many {color} objects are there?"
                        cf_params = {'color': color}
                    else:
                        cf_q = "How many objects are in the scene?"
                        cf_params = {}
            elif "What is" in original_question:
                cf_q = original_question.replace("What is the total number of", "How many")
            else:
                # Fallback: add specificity
                if props['colors']:
                    color = random.choice(props['colors'])
                    cf_q = f"How many {color} objects are there?"
                    cf_params = {'color': color}
                else:
                    cf_q = "Are there more than 3 objects?"
                    cf_params = {}
        
        elif strategy == 'scope_change':
            if params and len(params) >= 2:
                cf_params = params.copy()
                key_to_remove = random.choice(list(params.keys()))
                del cf_params[key_to_remove]
                
                if len(cf_params) == 1:
                    attr_val = list(cf_params.values())[0]
                    cf_q = f"How many {attr_val} objects are there?"
                else:
                    if props['colors']:
                        color = random.choice(props['colors'])
                        cf_q = f"How many {color} objects are there?"
                        cf_params = {'color': color}
                    else:
                        cf_q = "Are there more than 3 objects?"
                        cf_params = {}
            elif params and len(params) == 1:
                new_attr = random.choice(['material', 'size'])
                if new_attr not in params:
                    new_val = random.choice(props[new_attr + 's'])
                    existing_key = list(params.keys())[0]
                    existing_val = list(params.values())[0]
                    cf_params = params.copy()
                    cf_params[new_attr] = new_val
                    if new_attr == 'size':
                        cf_q = f"How many {new_val} {existing_val} objects are there?"
                    elif new_attr == 'material':
                        if existing_key == 'size':
                            cf_q = f"How many {existing_val} {new_val} objects are there?"
                        else:
                            cf_q = f"How many {existing_val} {new_val} objects are there?"
                else:
                    strategy = 'negation'
                    continue
            else:
                if props['colors']:
                    color = random.choice(props['colors'])
                    cf_params = {'color': color}
                    cf_q = f"How many {color} objects are there?"
                elif props['shapes']:
                    shape = random.choice(props['shapes'])
                    cf_params = {'shape': shape}
                    cf_q = f"Are there any {shape}s?"
                else:
                    cf_q = "Are there more than 3 objects?"
                    cf_params = {}
        
        elif strategy == 'negation':
            cf_params = params.copy() if params else {}
            if params:
                if 'color' in params:
                    color = params['color']
                    cf_q = f"How many objects are NOT {color}?"
                elif 'shape' in params:
                    shape = params['shape']
                    cf_q = f"How many objects are NOT {shape}s?"
                else:
                    attr_val = list(params.values())[0]
                    cf_q = f"How many objects are NOT {attr_val}?"
            else:
                cf_q = "Are there fewer than 5 objects?"
                cf_params = {}
        
        elif strategy == 'comparative':
            cf_params = params.copy() if params else {}
            if "How many" in original_question:
                number = random.choice([2, 3, 4, 5])
                cf_q = original_question.replace("How many", f"Are there more than {number}")
                cf_q = cf_q.replace(" are there?", "?")
                cf_q = cf_q.replace(" are in the scene?", " in the scene?")
            elif params:
                if 'color' in params:
                    color1 = params['color']
                    alternatives = [c for c in props['all_colors'] if c != color1]
                    if alternatives:
                        color2 = random.choice(alternatives)
                        cf_params = {'color': color1, 'color2': color2}
                        cf_q = f"Are there more {color1} objects than {color2} objects?"
                    else:
                        cf_q = f"How many objects are NOT {color1}?"
                        cf_params = {'color': color1}
                elif 'shape' in params:
                    shape1 = params['shape']
                    alternatives = [s for s in props['all_shapes'] if s != shape1]
                    if alternatives:
                        shape2 = random.choice(alternatives)
                        cf_params = {'shape': shape1, 'shape2': shape2}
                        cf_q = f"Are there more {shape1}s than {shape2}s?"
                    else:
                        cf_q = f"How many objects are NOT {shape1}s?"
                        cf_params = {'shape': shape1}
                else:
                    cf_q = "Are there more than 3 objects?"
                    cf_params = {}
            else:
                cf_q = "Are there more than 3 objects?"
                cf_params = {}
        
        elif strategy == 'multi_attribute':
            if params and len(params) >= 2:
                cf_params = {}
                changed = False
                for key in params:
                    if key == 'color':
                        alternatives = [c for c in props['all_colors'] if c != params[key]]
                        if alternatives:
                            cf_params[key] = random.choice(alternatives)
                            changed = True
                        else:
                            cf_params[key] = params[key]
                    elif key == 'shape':
                        alternatives = [s for s in props['all_shapes'] if s != params[key]]
                        if alternatives:
                            cf_params[key] = random.choice(alternatives)
                            changed = True
                        else:
                            cf_params[key] = params[key]
                    elif key == 'material':
                        alternatives = [m for m in props['all_materials'] if m != params[key]]
                        if alternatives:
                            cf_params[key] = random.choice(alternatives)
                            changed = True
                        else:
                            cf_params[key] = params[key]
                    elif key == 'size':
                        alternatives = [s for s in props['all_sizes'] if s != params[key]]
                        if alternatives:
                            cf_params[key] = random.choice(alternatives)
                            changed = True
                        else:
                            cf_params[key] = params[key]
                
                if not changed:
                    strategy = 'negation'
                    continue
                
                attr_order = ['size', 'color', 'material', 'shape']
                ordered_values = []
                for attr in attr_order:
                    if attr in cf_params:
                        ordered_values.append(cf_params[attr])
                cf_q = f"How many {' '.join(ordered_values)} objects are there?"
            else:
                color = random.choice(props['colors'])
                shape = random.choice(props['shapes'])
                cf_params = {'color': color, 'shape': shape}
                cf_q = f"Is there a {color} {shape}?"
        
        if cf_q is None:
            cf_q = "How many objects are in the scene?"
            cf_params = {}
        
        # Ensure cf_params is set
        if not cf_params:
            cf_params = {}
            
            if cf_q.strip() != original_question.strip():
                break
            
            retry_count += 1
            if retry_count < max_retries:
                available_strategies = [s for s in strategies if s != strategy]
                if available_strategies:
                    strategy = random.choice(available_strategies)
                else:
                    strategy = 'negation'
        
        if cf_q.strip() == original_question.strip():
            if params:
                if 'color' in params:
                    cf_q = f"How many objects are NOT {params['color']}?"
                elif 'shape' in params:
                    cf_q = f"How many objects are NOT {params['shape']}s?"
                else:
                    attr_val = list(params.values())[0]
                    cf_q = f"How many objects are NOT {attr_val}?"
                cf_params = params.copy()
            else:
                if props['colors']:
                    color = random.choice(props['colors'])
                    cf_q = f"How many {color} objects are there?"
                    cf_params = {'color': color}
                elif props['shapes']:
                    shape = random.choice(props['shapes'])
                    cf_q = f"Are there any {shape}s?"
                    cf_params = {'shape': shape}
                else:
                    cf_q = "Are there more than 3 objects?"
                    cf_params = {}
        
        cf_questions.append((cf_q, cf_params))
    
    return cf_questions

def answer_question_for_scene(question, scene):
    objects = scene.get('objects', [])
    question_lower = question.lower()
    
    if "more than" in question_lower:
        match = re.search(r'more than (\d+)', question_lower)
        if match:
            threshold = int(match.group(1))
            count = count_matching_objects(question_lower, objects)
            
            return "yes" if count > threshold else "no"
    
    if "fewer than" in question_lower:
        match = re.search(r'fewer than (\d+)', question_lower)
        if match:
            threshold = int(match.group(1))
            count = count_matching_objects(question_lower, objects)
            return "yes" if count < threshold else "no"
    
    if " not " in question_lower:
        count = 0
        colors = ['red', 'blue', 'green', 'brown', 'purple', 'cyan', 'yellow', 'gray', 'grey']
        shapes = ['cube', 'sphere', 'cylinder', 'cubes', 'spheres', 'cylinders']
        materials = ['metal', 'rubber', 'metals', 'rubbers']
        sizes = ['small', 'large']
        
        excluded_attr = None
        excluded_type = None
        
        for c in colors:
            if c in question_lower:
                excluded_attr = c.rstrip('s')
                excluded_type = 'color'
                break
        
        if excluded_attr is None:
            for s in shapes:
                if s in question_lower:
                    excluded_attr = s.rstrip('s')
                    excluded_type = 'shape'
                    break
        
        if excluded_attr is None:
            for m in materials:
                if m in question_lower:
                    excluded_attr = m.rstrip('s')
                    excluded_type = 'material'
                    break
        
        if excluded_attr is None:
            for s in sizes:
                if s in question_lower:
                    excluded_attr = s
                    excluded_type = 'size'
                    break
        
        if excluded_attr and excluded_type:
            for obj in objects:
                obj_attr = obj.get(excluded_type, '').lower()
                if obj_attr != excluded_attr:
                    count += 1
        else:
            count = len(objects)
        
        return str(count)
    
    if " than " in question_lower and " more " in question_lower:
        parts = question_lower.split(" than ")
        if len(parts) == 2:
            first_part = parts[0]
            second_part = parts[1].replace('?', '').strip()
            
            count1 = count_matching_objects(first_part, objects)
            count2 = count_matching_objects(second_part, objects)
            
            return "yes" if count1 > count2 else "no"
    
    if question_lower.startswith("how many"):
        if "objects are in the scene" in question_lower or "total number of objects" in question_lower:
            return str(len(objects))
        
        count = count_matching_objects(question_lower, objects)
        return str(count)
    
    elif question_lower.startswith("are there") or question_lower.startswith("is there"):
        count = count_matching_objects(question_lower, objects)
        return "yes" if count > 0 else "no"
    
    elif question_lower.startswith("what"):
        if "colors" in question_lower:
            colors = list(set(obj.get('color', '') for obj in objects if obj.get('color')))
            return ", ".join(colors) if colors else "none"
        elif "shapes" in question_lower:
            shapes = list(set(obj.get('shape', '') for obj in objects if obj.get('shape')))
            return ", ".join(shapes) if shapes else "none"
        elif "total number" in question_lower:
            count = count_matching_objects(question_lower, objects)
            return str(count)
        else:
            return str(len(objects))
    
    if "matte or shiny" in question_lower or ("or" in question_lower and ("matte" in question_lower or "shiny" in question_lower)):
        colors = ['red', 'blue', 'green', 'brown', 'purple', 'cyan', 'yellow', 'gray', 'grey']
        shapes = ['cube', 'sphere', 'cylinder', 'cubes', 'spheres', 'cylinders']
        
        color_match = None
        shape_match = None
        
        for c in colors:
            if c in question_lower:
                color_match = c.rstrip('s')
                break
        
        for s in shapes:
            if s in question_lower:
                shape_match = s.rstrip('s')
                break
        
        for obj in objects:
            obj_color = obj.get('color', '').lower()
            obj_shape = obj.get('shape', '').lower()
            obj_material = obj.get('material', '').lower()
            
            matches = True
            if color_match and obj_color != color_match:
                matches = False
            if shape_match and obj_shape != shape_match:
                matches = False
            
            if matches:
                if obj_material == 'metal':
                    return "shiny"
                elif obj_material == 'rubber':
                    return "matte"
                else:
                    return "unknown"
        
        return "not found"
    
    return "unknown"

def count_matching_objects(question_lower, objects):
    count = 0
    
    colors = ['red', 'blue', 'green', 'brown', 'purple', 'cyan', 'yellow', 'gray', 'grey']
    shapes = ['cube', 'sphere', 'cylinder', 'cubes', 'spheres', 'cylinders']
    materials = ['metal', 'rubber', 'metals', 'rubbers']
    sizes = ['small', 'large']
    
    color_match = None
    for c in colors:
        if c in question_lower:
            color_match = c.rstrip('s')
            break
    
    shape_match = None
    for s in shapes:
        if s in question_lower:
            shape_match = s.rstrip('s')
            break
    
    material_match = None
    if "metallic" in question_lower:
        material_match = "metal"
    else:
        for m in materials:
            if m in question_lower:
                material_match = m.rstrip('s')
                break
    
    size_match = None
    for s in sizes:
        if s in question_lower:
            size_match = s
            break
    
    for obj in objects:
        obj_color = obj.get('color', '').lower()
        obj_shape = obj.get('shape', '').lower()
        obj_material = obj.get('material', '').lower()
        obj_size = obj.get('size', '').lower()
        
        matches = True
        
        if color_match and obj_color != color_match:
            matches = False
        if shape_match and obj_shape != shape_match:
            matches = False
        if material_match and obj_material != material_match:
            matches = False
        if size_match and obj_size != size_match:
            matches = False
        
        if matches:
            count += 1
    
    return count

def generate_mapping_with_questions(run_dir, csv_filename='image_mapping_with_questions.csv',
                                   generate_questions=False, with_links=False, base_url=None):
    images_dir = os.path.join(run_dir, 'images')
    scenes_dir = os.path.join(run_dir, 'scenes')
    
    if not os.path.exists(images_dir):
        print(f"ERROR: Images directory not found: {images_dir}")
        return
    
    if not os.path.exists(scenes_dir):
        print(f"ERROR: Scenes directory not found: {scenes_dir}")
        return
    
    image_files = [f for f in os.listdir(images_dir) if f.endswith('.png')]
    
    scene_sets = {}
    for img_file in image_files:
        if img_file.startswith('scene_'):
            parts = img_file.replace('.png', '').split('_')
            if len(parts) >= 3:
                scene_num = parts[1]
                scene_type = parts[2]
                
                if scene_num not in scene_sets:
                    scene_sets[scene_num] = {}
                scene_sets[scene_num][scene_type] = img_file
    
    rows = []
    if with_links:
        header = ['scene_id', 'original_image_link', 'original_scene_link',
                  'counterfactual1_image_link', 'counterfactual1_scene_link', 
                  'counterfactual2_image_link', 'counterfactual2_scene_link']
        if generate_questions:
            header.extend([
                'original_question', 'counterfactual1_question', 'counterfactual2_question',
                'original_question_difficulty', 'counterfactual1_question_difficulty', 'counterfactual2_question_difficulty',
                'original_image_answer_to_original_question', 
                'original_image_answer_to_counterfactual1_question', 
                'original_image_answer_to_counterfactual2_question',
                'counterfactual1_image_answer_to_original_question', 
                'counterfactual1_image_answer_to_counterfactual1_question', 
                'counterfactual1_image_answer_to_counterfactual2_question',
                'counterfactual2_image_answer_to_original_question', 
                'counterfactual2_image_answer_to_counterfactual1_question', 
                'counterfactual2_image_answer_to_counterfactual2_question'
            ])
        rows.append(header)
    elif generate_questions:
        rows.append([
            'original_image', 'counterfactual1_image', 'counterfactual2_image',
            'original_question', 'counterfactual1_question', 'counterfactual2_question',
            'original_question_difficulty', 'counterfactual1_question_difficulty', 'counterfactual2_question_difficulty',
            'original_image_answer_to_original_question', 
            'original_image_answer_to_cf1_question', 
            'original_image_answer_to_cf2_question',
            'cf1_image_answer_to_original_question', 
            'cf1_image_answer_to_cf1_question', 
            'cf1_image_answer_to_cf2_question',
            'cf2_image_answer_to_original_question', 
            'cf2_image_answer_to_cf1_question', 
            'cf2_image_answer_to_cf2_question'
        ])
    else:
        rows.append(['original_image', 'counterfactual1_image', 'counterfactual2_image'])
    
    total_scenes = len(scene_sets)
    
    for idx, scene_num in enumerate(sorted(scene_sets.keys())):
        scene_data = scene_sets[scene_num]
        
        # Check if we have all three versions
        if 'original' not in scene_data or 'cf1' not in scene_data or 'cf2' not in scene_data:
            print(f"WARNING: Scene {scene_num} missing images")
            continue
        
        original_id = scene_data['original']
        cf1_id = scene_data['cf1']
        cf2_id = scene_data['cf2']
        
        if generate_questions:
            original_scene_file = find_scene_file(scenes_dir, original_id)
            cf1_scene_file = find_scene_file(scenes_dir, cf1_id)
            cf2_scene_file = find_scene_file(scenes_dir, cf2_id)
            
            if not all([original_scene_file, cf1_scene_file, cf2_scene_file]):
                print(f"WARNING: Scene {scene_num} missing scene files")
                continue
            
            print(f"Processing scene {idx+1}/{total_scenes}: {scene_num}")
            
            original_scene = load_scene(original_scene_file)
            cf1_scene = load_scene(cf1_scene_file)
            cf2_scene = load_scene(cf2_scene_file)
            
            original_question, params = generate_question_for_scene(original_scene_file)
            cf_questions = create_counterfactual_questions(original_question, params, original_scene)
            cf1_question, cf1_params = cf_questions[0]
            cf2_question, cf2_params = cf_questions[1]
            
            original_difficulty = calculate_question_difficulty(original_question, params)
            cf1_difficulty = calculate_question_difficulty(cf1_question, cf1_params)
            cf2_difficulty = calculate_question_difficulty(cf2_question, cf2_params)
            
            original_ans_orig_q = answer_question_for_scene(original_question, original_scene)
            original_ans_cf1_q = answer_question_for_scene(cf1_question, original_scene)
            original_ans_cf2_q = answer_question_for_scene(cf2_question, original_scene)
            
            cf1_ans_orig_q = answer_question_for_scene(original_question, cf1_scene)
            cf1_ans_cf1_q = answer_question_for_scene(cf1_question, cf1_scene)
            cf1_ans_cf2_q = answer_question_for_scene(cf2_question, cf1_scene)
            
            cf2_ans_orig_q = answer_question_for_scene(original_question, cf2_scene)
            cf2_ans_cf1_q = answer_question_for_scene(cf1_question, cf2_scene)
            cf2_ans_cf2_q = answer_question_for_scene(cf2_question, cf2_scene)
            
            if with_links:
                def make_link(filename, file_type='image'):
                    if base_url:
                        return f"{base_url.rstrip('/')}/{file_type}s/{filename}"
                    else:
                        return f"{file_type}s/{filename}"
                
                original_image_link = make_link(original_id, 'image')
                original_scene_link = make_link(original_id.replace('.png', '.json'), 'scene')
                cf1_image_link = make_link(cf1_id, 'image')
                cf1_scene_link = make_link(cf1_id.replace('.png', '.json'), 'scene')
                cf2_image_link = make_link(cf2_id, 'image')
                cf2_scene_link = make_link(cf2_id.replace('.png', '.json'), 'scene')
                
                rows.append([
                    scene_num,
                    original_image_link, original_scene_link,
                    cf1_image_link, cf1_scene_link,
                    cf2_image_link, cf2_scene_link,
                    original_question, cf1_question, cf2_question,
                    original_difficulty, cf1_difficulty, cf2_difficulty,
                    original_ans_orig_q, original_ans_cf1_q, original_ans_cf2_q,
                    cf1_ans_orig_q, cf1_ans_cf1_q, cf1_ans_cf2_q,
                    cf2_ans_orig_q, cf2_ans_cf1_q, cf2_ans_cf2_q
                ])
            else:
                rows.append([
                    original_id, cf1_id, cf2_id,
                    original_question, cf1_question, cf2_question,
                    original_difficulty, cf1_difficulty, cf2_difficulty,
                    original_ans_orig_q, original_ans_cf1_q, original_ans_cf2_q,
                    cf1_ans_orig_q, cf1_ans_cf1_q, cf1_ans_cf2_q,
                    cf2_ans_orig_q, cf2_ans_cf1_q, cf2_ans_cf2_q
                ])
        else:
            if with_links:
                def make_link(filename, file_type='image'):
                    if base_url:
                        return f"{base_url.rstrip('/')}/{file_type}s/{filename}"
                    else:
                        return f"{file_type}s/{filename}"
                
                original_image_link = make_link(original_id, 'image')
                original_scene_link = make_link(original_id.replace('.png', '.json'), 'scene')
                cf1_image_link = make_link(cf1_id, 'image')
                cf1_scene_link = make_link(cf1_id.replace('.png', '.json'), 'scene')
                cf2_image_link = make_link(cf2_id, 'image')
                cf2_scene_link = make_link(cf2_id.replace('.png', '.json'), 'scene')
                
                rows.append([
                    scene_num,
                    original_image_link, original_scene_link,
                    cf1_image_link, cf1_scene_link,
                    cf2_image_link, cf2_scene_link
                ])
            else:
                rows.append([original_id, cf1_id, cf2_id])
    
    csv_path = os.path.join(run_dir, csv_filename)
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
        writer.writerows(rows)
    
    print(f"\n[OK] Generated mapping CSV: {csv_path}")
    print(f"  Total scene sets: {len(rows) - 1}")
    
    print("\nSample entry:")
    if len(rows) > 1:
        row = rows[1]
        if with_links:
            if generate_questions:
                print(f"  Scene ID: {row[0]}")
                print(f"  Links:")
                print(f"    Original image: {row[1]}")
                print(f"    Original scene: {row[2]}")
                print(f"    CF1 image: {row[3]}")
                print(f"    CF1 scene: {row[4]}")
                print(f"    CF2 image: {row[5]}")
                print(f"    CF2 scene: {row[6]}")
                print(f"  Questions:")
                print(f"    Original: {row[7]}")
                print(f"    CF1: {row[8]}")
                print(f"    CF2: {row[9]}")
            else:
                print(f"  Scene ID: {row[0]}")
                print(f"  Links:")
                print(f"    Original image: {row[1]}, scene: {row[2]}")
                print(f"    CF1 image: {row[3]}, scene: {row[4]}")
                print(f"    CF2 image: {row[5]}, scene: {row[6]}")
        elif generate_questions and len(row) > 6:
            print(f"  Images:")
            print(f"    Original: {row[0]}")
            print(f"    Counterfactual 1: {row[1]}")
            print(f"    Counterfactual 2: {row[2]}")
            print(f"  Questions:")
            print(f"    Original question: {row[3]}")
            print(f"    CF1 question: {row[4]}")
            print(f"    CF2 question: {row[5]}")
            print(f"  Answer Matrix (scene × question):")
            print(f"    Original image:")
            print(f"      → Original Q: {row[6]}")
            print(f"      → CF1 Q: {row[7]}")
            print(f"      → CF2 Q: {row[8]}")
            print(f"    CF1 image:")
            print(f"      → Original Q: {row[9]}")
            print(f"      → CF1 Q: {row[10]}")
            print(f"      → CF2 Q: {row[11]}")
            print(f"    CF2 image:")
            print(f"      → Original Q: {row[12]}")
            print(f"      → CF1 Q: {row[13]}")
            print(f"      → CF2 Q: {row[14]}")

def main():
    parser = argparse.ArgumentParser(
        description='Generate CSV with original and VARIED counterfactual questions applied to all scenes'
    )
    parser.add_argument('--output_dir', default='output',
                       help='Run directory or base output directory (default: output)')
    parser.add_argument('--auto_latest', action='store_true',
                       help='Automatically find and use the latest run in output_dir')
    parser.add_argument('--csv_name', default='image_mapping_with_questions.csv',
                       help='Output CSV filename')
    parser.add_argument('--generate_questions', action='store_true',
                       help='Generate questions and answers for each scene set')
    
    args = parser.parse_args()
    
    if args.auto_latest:
        run_dir = find_latest_run(args.output_dir)
        if run_dir is None:
            print(f"ERROR: Could not find any run directories in {args.output_dir}")
            return
            print(f"Using latest run: {run_dir}")
    else:
        if os.path.exists(os.path.join(args.output_dir, 'images')) and \
           os.path.exists(os.path.join(args.output_dir, 'scenes')):
            run_dir = args.output_dir
        else:
            run_dir = find_latest_run(args.output_dir)
            if run_dir is None:
                print(f"ERROR: {args.output_dir} does not contain images/scenes directories")
                print(f"       and no run directories found in {args.output_dir}")
                return
            print(f"Auto-detected run directory: {run_dir}")
    
    generate_mapping_with_questions(
        run_dir,
        args.csv_name,
        args.generate_questions
    )

if __name__ == '__main__':
    main()