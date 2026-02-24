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

RELATION_KEYS_TO_PHRASES = {'left': 'left of', 'right': 'right of', 'front': 'in front of', 'behind': 'behind'}
DEFAULT_RELATIONS = ['left of', 'right of', 'in front of', 'behind']


def get_scene_properties(scene):
    objects = scene.get('objects', [])
    if not objects:
        return {
            'colors': ['red', 'blue', 'green'],
            'shapes': ['cube', 'sphere', 'cylinder'],
            'materials': ['metal', 'rubber'],
            'sizes': ['small', 'large'],
            'relations': DEFAULT_RELATIONS
        }
    
    colors = list(set(obj.get('color') for obj in objects if obj.get('color')))
    shapes = list(set(obj.get('shape') for obj in objects if obj.get('shape')))
    materials = list(set(obj.get('material') for obj in objects if obj.get('material')))
    sizes = list(set(obj.get('size') for obj in objects if obj.get('size')))
    relationships = scene.get('relationships') or {}
    relations = [RELATION_KEYS_TO_PHRASES[k] for k in relationships if k in RELATION_KEYS_TO_PHRASES]
    if not relations:
        relations = DEFAULT_RELATIONS
    
    all_colors = ['gray', 'red', 'blue', 'green', 'brown', 'purple', 'cyan', 'yellow']
    all_shapes = ['cube', 'sphere', 'cylinder']
    all_materials = ['metal', 'rubber']
    all_sizes = ['small', 'large']
    
    return {
        'colors': colors if colors else all_colors,
        'shapes': shapes if shapes else all_shapes,
        'materials': materials if materials else all_materials,
        'sizes': sizes if sizes else all_sizes,
        'relations': relations,
        'all_colors': all_colors,
        'all_shapes': all_shapes,
        'all_materials': all_materials,
        'all_sizes': all_sizes
    }

IMAGE_CF_TYPES = {
    'change_color', 'change_shape', 'change_size', 'change_material',
    'change_position', 'add_object', 'remove_object', 'replace_object',
    'swap_attribute', 'relational_flip'
}
NEGATIVE_CF_TYPES = {
    'change_background', 'change_lighting', 'add_noise',
    'apply_fisheye', 'apply_blur', 'apply_vignette', 'apply_chromatic_aberration',
    'occlusion_change'
}

MAX_CF_ANSWER_RETRIES = 150

def get_cf_type_from_scene(scene):
    meta = scene.get('cf_metadata') or {}
    if not meta.get('is_counterfactual'):
        return None
    return meta.get('cf_type')

def get_cf_description_from_scene(scene):
    meta = scene.get('cf_metadata') or {}
    if not meta.get('is_counterfactual'):
        return None
    return meta.get('cf_description')

def get_change_details(original_scene, cf_scene):
    orig_objs = original_scene.get('objects', [])
    cf_objs = cf_scene.get('objects', [])
    if len(orig_objs) != len(cf_objs):
        return {'attribute': 'count', 'orig_count': len(orig_objs), 'cf_count': len(cf_objs)}
    attrs = ['color', 'shape', 'material', 'size']
    for i, (o, c) in enumerate(zip(orig_objs, cf_objs)):
        for attr in attrs:
            ov = (o.get(attr) or '').lower().strip()
            cv = (c.get(attr) or '').lower().strip()
            if ov != cv:
                return {'attribute': attr, 'orig_val': ov or 'unknown', 'cf_val': cv or 'unknown', 'object_index': i}
    return None

CF_COUNT_QUESTION_TEMPLATES = [
    "How many objects are in the scene?",
    "What is the total number of objects in the scene?",
]
CF_COLOR_QUESTION_TEMPLATES = [
    ("How many {val} objects are there?", 'color'),
    ("Are there any {val} objects?", 'color'),
    ("What is the total number of {val} objects?", 'color'),
]
CF_SHAPE_QUESTION_TEMPLATES = [
    ("How many {val} are there?", 'shape'),
    ("Are there any {val}?", 'shape'),
    ("What is the total number of {val}?", 'shape'),
]
CF_MATERIAL_QUESTION_TEMPLATES = [
    ("How many {val} objects are there?", 'material'),
    ("Are there any {val} objects?", 'material'),
    ("What is the total number of {val} objects?", 'material'),
]
CF_SIZE_QUESTION_TEMPLATES = [
    ("How many {val} objects are there?", 'size'),
    ("Are there any {val} objects?", 'size'),
    ("What is the total number of {val} objects?", 'size'),
]


def _pluralize_shape(shape):
    if not shape:
        return shape
    s = shape.strip().lower()
    if s.endswith('s'):
        return s
    return s + 's'


def _count_by_attribute(objects, attr):
    counts = {}
    for obj in objects:
        val = (obj.get(attr) or '').lower().strip()
        if val:
            counts[val] = counts.get(val, 0) + 1
    return counts


def _get_attributes_with_different_counts(original_scene, cf_scene):
    orig_objs = original_scene.get('objects', [])
    cf_objs = cf_scene.get('objects', [])
    differing = []
    for attr in ['color', 'shape', 'material', 'size']:
        orig_counts = _count_by_attribute(orig_objs, attr)
        cf_counts = _count_by_attribute(cf_objs, attr)
        all_vals = set(orig_counts) | set(cf_counts)
        for val in all_vals:
            o = orig_counts.get(val, 0)
            c = cf_counts.get(val, 0)
            if o != c:
                differing.append((attr, val, o, c))
    return differing


def generate_question_for_counterfactual(cf_type, original_scene, cf_scene, retry_index=0):
    random.seed(hash((str(cf_type), retry_index, str(id(original_scene)), str(id(cf_scene)))))
    change = get_change_details(original_scene, cf_scene)
    orig_objs = original_scene.get('objects', [])
    cf_objs = cf_scene.get('objects', [])
    props_orig = get_scene_properties(original_scene)
    props_cf = get_scene_properties(cf_scene)

    if cf_type and cf_type in IMAGE_CF_TYPES:
        differing = _get_attributes_with_different_counts(original_scene, cf_scene)
        if differing:
            idx = retry_index % len(differing) if differing else 0
            attr, val, orig_count, cf_count = differing[idx]
            if attr == 'color':
                template, _ = random.choice(CF_COLOR_QUESTION_TEMPLATES)
                question = template.format(val=val)
            elif attr == 'shape':
                plural = _pluralize_shape(val)
                template, _ = random.choice(CF_SHAPE_QUESTION_TEMPLATES)
                question = template.format(val=plural)
            elif attr == 'material':
                template, _ = random.choice(CF_MATERIAL_QUESTION_TEMPLATES)
                question = template.format(val=val)
            elif attr == 'size':
                template, _ = random.choice(CF_SIZE_QUESTION_TEMPLATES)
                question = template.format(val=val)
            else:
                question = None
            if question:
                return question, {attr: val.rstrip('s') if attr == 'shape' else val}

    if cf_type and cf_type in NEGATIVE_CF_TYPES:
        templates = [
            ("How many objects are in the scene?", {}),
            ("How many {color} objects are there?", {'color': random.choice(props_orig['colors'])} if props_orig['colors'] else None),
            ("Are there any {shape} objects?", {'shape': random.choice(props_orig['shapes'])} if props_orig['shapes'] else None),
            ("How many {material} objects are there?", {'material': random.choice(props_orig['materials'])} if props_orig['materials'] else None),
            ("What is the total number of {size} objects?", {'size': random.choice(props_orig['sizes'])} if props_orig['sizes'] else None),
        ]
        valid = [(t, p) for t, p in templates if p is not None or t.startswith("How many objects are in")]
        if not valid:
            valid = [("How many objects are in the scene?", {})]
        template, params = random.choice(valid)
        params = params or {}
        question = template.format(**params) if params else template
        return question, params

    if change and change.get('attribute') == 'count':
        orig_count = change.get('orig_count', len(orig_objs))
        cf_count = change.get('cf_count', len(cf_objs))
        templates_with_params = []
        templates_with_params.append((random.choice(CF_COUNT_QUESTION_TEMPLATES), {}))
        if cf_count > orig_count:
            templates_with_params.append((f"Are there more than {orig_count} objects?", {}))
            templates_with_params.append((f"Are there at least {cf_count} objects?", {}))
        if cf_count < orig_count:
            templates_with_params.append((f"Are there fewer than {orig_count} objects?", {}))
            templates_with_params.append((f"Are there more than {cf_count} objects?", {}))
        template, params = random.choice(templates_with_params)
        return template, params

    if change and change.get('attribute') in ('color', 'shape', 'material', 'size'):
        attr = change['attribute']
        cf_val = (change.get('cf_val') or '').strip().lower()
        if not cf_val:
            cf_val = 'unknown'
        params = {attr: cf_val}
        if attr == 'color':
            template, _ = random.choice(CF_COLOR_QUESTION_TEMPLATES)
            question = template.format(val=cf_val)
        elif attr == 'shape':
            template, _ = random.choice(CF_SHAPE_QUESTION_TEMPLATES)
            plural = _pluralize_shape(cf_val)
            question = template.format(val=plural)
            params['shape'] = cf_val.rstrip('s')
        elif attr == 'material':
            template, _ = random.choice(CF_MATERIAL_QUESTION_TEMPLATES)
            question = template.format(val=cf_val)
        elif attr == 'size':
            template, _ = random.choice(CF_SIZE_QUESTION_TEMPLATES)
            question = template.format(val=cf_val)
        else:
            question = "How many objects are in the scene?"
            params = {}
        return question, params

    if cf_type in ('add_object', 'remove_object'):
        templates = list(CF_COUNT_QUESTION_TEMPLATES)
        if len(orig_objs) != len(cf_objs):
            if len(cf_objs) > len(orig_objs):
                templates.extend([f"Are there more than {len(orig_objs)} objects?", f"Are there at least {len(cf_objs)} objects?"])
            else:
                templates.extend([f"Are there fewer than {len(orig_objs)} objects?", f"Are there more than {len(cf_objs)} objects?"])
        template = random.choice(templates)
        return template, {}

    if cf_type in ('change_color', 'change_shape', 'replace_object'):
        for attr, key in [('color', 'colors'), ('shape', 'shapes'), ('material', 'materials'), ('size', 'sizes')]:
            vals = list(props_cf.get(key) or props_orig.get(key) or [])
            if vals:
                val = random.choice(vals)
                if attr == 'shape':
                    plural = _pluralize_shape(val)
                    templates = CF_SHAPE_QUESTION_TEMPLATES
                    template, _ = random.choice(templates)
                    question = template.format(val=plural)
                elif attr == 'color':
                    template, _ = random.choice(CF_COLOR_QUESTION_TEMPLATES)
                    question = template.format(val=val)
                elif attr == 'material':
                    template, _ = random.choice(CF_MATERIAL_QUESTION_TEMPLATES)
                    question = template.format(val=val)
                else:
                    template, _ = random.choice(CF_SIZE_QUESTION_TEMPLATES)
                    question = template.format(val=val)
                return question, {attr: val.rstrip('s') if attr == 'shape' else val}

    if cf_type in ('change_size', 'change_material', 'change_position', 'swap_attribute', 'relational_flip'):
        key = 'sizes' if cf_type == 'change_size' else ('materials' if cf_type == 'change_material' else 'colors')
        attr = key.rstrip('s')
        vals = list(props_cf.get(key) or props_orig.get(key) or [])
        if vals:
            val = random.choice(vals)
            if cf_type == 'change_size':
                template, _ = random.choice(CF_SIZE_QUESTION_TEMPLATES)
            elif cf_type == 'change_material':
                template, _ = random.choice(CF_MATERIAL_QUESTION_TEMPLATES)
            else:
                template, _ = random.choice(CF_COLOR_QUESTION_TEMPLATES)
            question = template.format(val=val)
            return question, {attr: val}

    question = random.choice(CF_COUNT_QUESTION_TEMPLATES)
    return question, {}

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
        ("What color is the object {relation} the {color} {shape}?", {
            'relation': random.choice(props['relations']),
            'color': random.choice(props['colors']),
            'shape': random.choice(props['shapes'])
        }),
        ("What shape is the object {relation} the {material} object?", {
            'relation': random.choice(props['relations']),
            'material': random.choice(props['materials'])
        }),
        ("What material is the {size} object {relation} the {shape}?", {
            'size': random.choice(props['sizes']),
            'relation': random.choice(props['relations']),
            'shape': random.choice(props['shapes'])
        }),
        ("How many objects are {relation} the {color} {shape}?", {
            'relation': random.choice(props['relations']),
            'color': random.choice(props['colors']),
            'shape': random.choice(props['shapes'])
        }),
        ("How many {material} objects are {relation} the {shape}?", {
            'material': random.choice(props['materials']),
            'relation': random.choice(props['relations']),
            'shape': random.choice(props['shapes'])
        }),
        ("What is the total number of {size} objects {relation} the {color} object?", {
            'size': random.choice(props['sizes']),
            'relation': random.choice(props['relations']),
            'color': random.choice(props['colors'])
        }),
        ("Is there a {color} object {relation} the {shape}?", {
            'color': random.choice(props['colors']),
            'relation': random.choice(props['relations']),
            'shape': random.choice(props['shapes'])
        }),
        ("Are there any {material} {shape}s {relation} the {size} object?", {
            'material': random.choice(props['materials']),
            'shape': random.choice(props['shapes']),
            'relation': random.choice(props['relations']),
            'size': random.choice(props['sizes'])
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
    else:
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
                elif param_to_change == 'relation':
                    alternatives = [r for r in props['relations'] if r != params.get('relation')]
                    if alternatives:
                        cf_params['relation'] = random.choice(alternatives)
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
            if not cf_params:
                cf_params = {}
            
            if cf_q and cf_q.strip() != original_question.strip():
                break
            
            retry_count += 1
            if retry_count < max_retries:
                available_strategies = [s for s in strategies if s != strategy]
                if available_strategies:
                    strategy = random.choice(available_strategies)
                else:
                    strategy = 'negation'
        
        if cf_q is None or cf_q.strip() == original_question.strip():
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

def normalize_answer(a):
    if a is None:
        return ""
    return str(a).strip().lower()


def answer_question_for_scene(question, scene):
    objects = scene.get('objects', [])
    question_lower = question.lower()
    
    if "at least" in question_lower:
        match = re.search(r'at least (\d+)', question_lower)
        if match:
            threshold = int(match.group(1))
            count = count_matching_objects(question_lower, objects)
            return "yes" if count >= threshold else "no"
    
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


def classify_question_validity(question, base_scene_graph, counterfactual_scene_graph):
    answer_base = answer_question_for_scene(question, base_scene_graph)
    answer_cf = answer_question_for_scene(question, counterfactual_scene_graph)
    norm_base = normalize_answer(answer_base)
    norm_cf = normalize_answer(answer_cf)
    if norm_base != norm_cf:
        return 'Semantic-Valid'
    return 'Negative-Valid'


def generate_mapping_with_questions(run_dir, csv_filename='image_mapping_with_questions.csv',
                                   generate_questions=False, with_links=False, base_url=None,
                                   strict_question_validation=True):
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
                  'counterfactual2_image_link', 'counterfactual2_scene_link',
                  'counterfactual1_type', 'counterfactual2_type',
                  'counterfactual1_description', 'counterfactual2_description']
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
            'counterfactual1_type', 'counterfactual2_type',
            'counterfactual1_description', 'counterfactual2_description',
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
        rows.append(['original_image', 'counterfactual1_image', 'counterfactual2_image',
                    'counterfactual1_type', 'counterfactual2_type',
                    'counterfactual1_description', 'counterfactual2_description'])
    
    total_scenes = len(scene_sets)
    
    for idx, scene_num in enumerate(sorted(scene_sets.keys())):
        scene_data = scene_sets[scene_num]
        
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
            
            try:
                original_scene = load_scene(original_scene_file)
                cf1_scene = load_scene(cf1_scene_file)
                cf2_scene = load_scene(cf2_scene_file)
            except Exception as e:
                import traceback
                traceback.print_exc()
                continue
            
            try:
                original_question, params = generate_question_for_scene(original_scene_file)
                original_ans_orig_q = answer_question_for_scene(original_question, original_scene)
                cf1_type = get_cf_type_from_scene(cf1_scene)
                cf2_type = get_cf_type_from_scene(cf2_scene)
                cf1_description = get_cf_description_from_scene(cf1_scene)
                cf2_description = get_cf_description_from_scene(cf2_scene)
            except Exception as e:
                import traceback
                traceback.print_exc()
                continue
            
            cf1_question = cf2_question = None
            cf1_params = cf2_params = {}
            original_difficulty = cf1_difficulty = cf2_difficulty = None
            original_ans_cf1_q = original_ans_cf2_q = None
            cf1_ans_orig_q = cf1_ans_cf1_q = cf1_ans_cf2_q = None
            cf2_ans_orig_q = cf2_ans_cf1_q = cf2_ans_cf2_q = None
            orig_norm = normalize_answer(original_ans_orig_q)
            
            for cf_retry in range(MAX_CF_ANSWER_RETRIES):
                try:
                    random.seed(hash((scene_num, idx, cf_retry)))
                    cf_questions = create_counterfactual_questions(original_question, params, original_scene) if (not cf1_type or not cf2_type) else None
                    if cf1_type:
                        cf1_question, cf1_params = generate_question_for_counterfactual(cf1_type, original_scene, cf1_scene, retry_index=cf_retry)
                    else:
                        cf1_question, cf1_params = cf_questions[0] if cf_questions and len(cf_questions) > 0 else ("How many objects are in the scene?", {})
                    if cf2_type:
                        cf2_question, cf2_params = generate_question_for_counterfactual(cf2_type, original_scene, cf2_scene, retry_index=cf_retry)
                    else:
                        cf2_question, cf2_params = cf_questions[1] if cf_questions and len(cf_questions) > 1 else (cf_questions[0] if cf_questions else ("How many objects are in the scene?", {}))
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    continue
                
                try:
                    original_difficulty = calculate_question_difficulty(original_question, params)
                    cf1_difficulty = calculate_question_difficulty(cf1_question, cf1_params)
                    cf2_difficulty = calculate_question_difficulty(cf2_question, cf2_params)
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    continue
                
                try:
                    original_ans_cf1_q = answer_question_for_scene(cf1_question, original_scene)
                    original_ans_cf2_q = answer_question_for_scene(cf2_question, original_scene)
                    cf1_ans_orig_q = answer_question_for_scene(original_question, cf1_scene)
                    cf1_ans_cf1_q = answer_question_for_scene(cf1_question, cf1_scene)
                    cf1_ans_cf2_q = answer_question_for_scene(cf2_question, cf1_scene)
                    cf2_ans_orig_q = answer_question_for_scene(original_question, cf2_scene)
                    cf2_ans_cf1_q = answer_question_for_scene(cf1_question, cf2_scene)
                    cf2_ans_cf2_q = answer_question_for_scene(cf2_question, cf2_scene)
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    continue
                
                if strict_question_validation:
                    cf1_validity = classify_question_validity(cf1_question, original_scene, cf1_scene)
                    cf2_validity = classify_question_validity(cf2_question, original_scene, cf2_scene)
                    cf1_required = 'Semantic-Valid' if (cf1_type and cf1_type in IMAGE_CF_TYPES) else 'Negative-Valid'
                    cf2_required = 'Semantic-Valid' if (cf2_type and cf2_type in IMAGE_CF_TYPES) else 'Negative-Valid'
                    cf1_ok = (cf1_required == cf1_validity)
                    cf2_ok = (cf2_required == cf2_validity)
                    if cf1_ok and cf2_ok:
                        break
                else:
                    CF_TYPES_ACCEPT_WITHOUT_CHECK = {'change_position', 'swap_attribute', 'relational_flip'}
                    cf1_differs = (cf1_type not in IMAGE_CF_TYPES) or (cf1_type in CF_TYPES_ACCEPT_WITHOUT_CHECK) or (normalize_answer(original_ans_cf1_q) != normalize_answer(cf1_ans_cf1_q))
                    cf2_differs = (cf2_type not in IMAGE_CF_TYPES) or (cf2_type in CF_TYPES_ACCEPT_WITHOUT_CHECK) or (normalize_answer(original_ans_cf2_q) != normalize_answer(cf2_ans_cf2_q))
                    if cf1_differs or cf2_differs:
                        break
            else:
                print(f"WARNING: Scene {scene_num}: could not find questions with different answers for both CFs after {MAX_CF_ANSWER_RETRIES} retries (scene included with best-effort questions)")
            
            try:
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
                        cf1_type, cf2_type, cf1_description, cf2_description,
                        original_question, cf1_question, cf2_question,
                        original_difficulty, cf1_difficulty, cf2_difficulty,
                        original_ans_orig_q, original_ans_cf1_q, original_ans_cf2_q,
                        cf1_ans_orig_q, cf1_ans_cf1_q, cf1_ans_cf2_q,
                        cf2_ans_orig_q, cf2_ans_cf1_q, cf2_ans_cf2_q
                    ])
                else:
                    rows.append([
                        original_id, cf1_id, cf2_id,
                        cf1_type, cf2_type, cf1_description, cf2_description,
                        original_question, cf1_question, cf2_question,
                        original_difficulty, cf1_difficulty, cf2_difficulty,
                        original_ans_orig_q, original_ans_cf1_q, original_ans_cf2_q,
                        cf1_ans_orig_q, cf1_ans_cf1_q, cf1_ans_cf2_q,
                        cf2_ans_orig_q, cf2_ans_cf1_q, cf2_ans_cf2_q
                    ])
            except Exception as e:
                import traceback
                traceback.print_exc()
                continue
        else:
            cf1_type = cf2_type = cf1_description = cf2_description = ''
            cf1_scene_file = find_scene_file(scenes_dir, cf1_id)
            cf2_scene_file = find_scene_file(scenes_dir, cf2_id)
            if cf1_scene_file and cf2_scene_file:
                try:
                    cf1_scene = load_scene(cf1_scene_file)
                    cf2_scene = load_scene(cf2_scene_file)
                    cf1_type = get_cf_type_from_scene(cf1_scene) or ''
                    cf2_type = get_cf_type_from_scene(cf2_scene) or ''
                    cf1_description = get_cf_description_from_scene(cf1_scene) or ''
                    cf2_description = get_cf_description_from_scene(cf2_scene) or ''
                except Exception:
                    pass
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
                    cf1_type, cf2_type, cf1_description, cf2_description
                ])
            else:
                rows.append([original_id, cf1_id, cf2_id, cf1_type, cf2_type, cf1_description, cf2_description])
    
    csv_path = os.path.join(run_dir, csv_filename)
    try:
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f, quoting=csv.QUOTE_ALL)
            writer.writerows(rows)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return
    
    print(f"\n[OK] Generated mapping CSV: {csv_path}")
    print(f"  Total scene sets: {len(rows) - 1}")
    
    print("\nSample entry:")
    if len(rows) > 1:
        row = rows[1]
        if with_links:
            if generate_questions:
                print(f"  Scene ID: {row[0]}")
                print(f"  Links:")
                print(f"    Original image: {row[1]}, scene: {row[2]}")
                print(f"    CF1 image: {row[3]}, scene: {row[4]}")
                print(f"    CF2 image: {row[5]}, scene: {row[6]}")
                print(f"  CF type / description: CF1 type={row[7]}, CF2 type={row[8]}; CF1 desc={row[9]!r}, CF2 desc={row[10]!r}")
                print(f"  Questions: Original: {row[11]}, CF1: {row[12]}, CF2: {row[13]}")
            else:
                print(f"  Scene ID: {row[0]}")
                print(f"  Links:")
                print(f"    Original image: {row[1]}, scene: {row[2]}")
                print(f"    CF1 image: {row[3]}, scene: {row[4]}")
                print(f"    CF2 image: {row[5]}, scene: {row[6]}")
                print(f"  CF type / description: CF1 type={row[7]}, CF2 type={row[8]}; CF1 desc={row[9]!r}, CF2 desc={row[10]!r}")
        elif generate_questions and len(row) > 14:
            print(f"  Images: Original: {row[0]}, CF1: {row[1]}, CF2: {row[2]}")
            print(f"  CF type / description: CF1 type={row[3]}, CF2 type={row[4]}; CF1 desc={row[5]!r}, CF2 desc={row[6]!r}")
            print(f"  Questions: Original: {row[7]}, CF1: {row[8]}, CF2: {row[9]}")
            print(f"  Answer Matrix (scene × question):")
            print(f"    Original image -> Orig Q: {row[10]}, CF1 Q: {row[11]}, CF2 Q: {row[12]}")
            print(f"    CF1 image -> Orig Q: {row[13]}, CF1 Q: {row[14]}, CF2 Q: {row[15]}")
            print(f"    CF2 image -> Orig Q: {row[16]}, CF1 Q: {row[17]}, CF2 Q: {row[18]}")
        elif len(row) >= 7:
            print(f"  Images: Original: {row[0]}, CF1: {row[1]}, CF2: {row[2]}")
            print(f"  CF type / description: CF1 type={row[3]}, CF2 type={row[4]}; CF1 desc={row[5]!r}, CF2 desc={row[6]!r}")

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
    parser.add_argument('--no_strict_validation', action='store_true',
                       help='Disable strict question validation (Semantic-Valid / Negative-Valid classifier); use legacy accept logic')
    
    args = parser.parse_args()
    
    if args.auto_latest:
        run_dir = find_latest_run(args.output_dir)
        if run_dir is None:
            print(f"ERROR: Could not find any run directories in {args.output_dir}")
            return
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
        args.generate_questions,
        strict_question_validation=not args.no_strict_validation
    )

if __name__ == '__main__':
    main()