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
PHRASES_TO_RELATION_KEYS = {'left of': 'left', 'right of': 'right', 'in front of': 'front', 'behind': 'behind'}
DEFAULT_RELATIONS = ['left of', 'right of', 'in front of', 'behind']

# Token sets for parsing questions
_COLORS = ['red', 'blue', 'green', 'brown', 'purple', 'cyan', 'yellow', 'gray', 'grey']
_SHAPES = ['cube', 'sphere', 'cylinder', 'cubes', 'spheres', 'cylinders']
_MATERIALS = ['metal', 'rubber', 'metals', 'rubbers']
_SIZES = ['small', 'large']


def _find_objects_matching(objects, color=None, shape=None, material=None, size=None):
    """Return list of object indices that match all specified attributes (None means any)."""
    out = []
    for i, obj in enumerate(objects):
        if color is not None and (obj.get('color') or '').lower() != color:
            continue
        if shape is not None:
            s = (obj.get('shape') or '').lower()
            if s != shape and s != shape.rstrip('s') and s + 's' != shape:
                continue
        if material is not None and (obj.get('material') or '').lower() != material:
            continue
        if size is not None and (obj.get('size') or '').lower() != size:
            continue
        out.append(i)
    return out


def _first_value_in_question(question_lower, values, strip_s=True):
    for v in values:
        if v in question_lower:
            return v.rstrip('s') if strip_s and v.endswith('s') else v
    return None


def _objects_in_relation_to_reference(scene, relation_phrase, ref_color=None, ref_shape=None, ref_material=None, ref_size=None):
    """Return set of object indices that stand in relation_phrase to the reference object (e.g. 'left of' the red cube)."""
    objects = scene.get('objects', [])
    rel_key = PHRASES_TO_RELATION_KEYS.get(relation_phrase)
    if not rel_key:
        return set()
    rels = scene.get('relationships') or {}
    rel_list = rels.get(rel_key)
    if not rel_list or len(rel_list) != len(objects):
        return set()
    ref_indices = _find_objects_matching(
        objects, color=ref_color, shape=ref_shape, material=ref_material, size=ref_size
    )
    if not ref_indices:
        return set()
    ref_idx = ref_indices[0]
    return set(rel_list[ref_idx])


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


def generate_question_for_counterfactual(cf_type, original_scene, cf_scene, retry_index=0, original_question=None, original_params=None):
    """
    Generate a counterfactual question. If original_question and original_params are provided,
    uses strict targeting: (1) try original question, (2) try mutated questions that target
    the change, (3) return (None, None) to signal rejection/retry if no question yields an answer change.
    """
    # --- Strict counterfactual targeting when original question is provided ---
    if original_question is not None and original_params is not None:
        a_orig = answer_question_for_scene(original_question, original_scene)
        a_cf = answer_question_for_scene(original_question, cf_scene)
        a_orig_n = normalize_answer(a_orig)
        a_cf_n = normalize_answer(a_cf)
        if a_orig_n != a_cf_n:
            return (original_question, original_params)
        for mut_q, mut_params in create_counterfactual_questions(original_question, original_params, original_scene):
            a_mut_cf = answer_question_for_scene(mut_q, cf_scene)
            if normalize_answer(a_mut_cf) != a_orig_n:
                return (mut_q, mut_params)
        return (None, None)

    random.seed(hash((str(cf_type), retry_index, str(id(original_scene)), str(id(cf_scene)))))
    change = get_change_details(original_scene, cf_scene)
    orig_objs = original_scene.get('objects', [])
    cf_objs = cf_scene.get('objects', [])
    props_orig = get_scene_properties(original_scene)
    props_cf = get_scene_properties(cf_scene)

    def _pick_spatial_question(props):
        """Strict spatial/relational templates only; never simple attribute count."""
        relations = props.get('relations') or DEFAULT_RELATIONS
        colors = list(props.get('colors') or props.get('all_colors') or ['red', 'blue', 'green'])
        shapes = list(props.get('shapes') or props.get('all_shapes') or ['cube', 'sphere', 'cylinder'])
        materials = list(props.get('materials') or props.get('all_materials') or ['metal', 'rubber'])
        sizes = list(props.get('sizes') or props.get('all_sizes') or ['small', 'large'])
        templates = [
            ("What color is the object {relation} the {color} {shape}?", {
                'relation': random.choice(relations), 'color': random.choice(colors), 'shape': random.choice(shapes)
            }),
            ("What shape is the object {relation} the {material} object?", {
                'relation': random.choice(relations), 'material': random.choice(materials)
            }),
            ("How many objects are {relation} the {color} {shape}?", {
                'relation': random.choice(relations), 'color': random.choice(colors), 'shape': random.choice(shapes)
            }),
            ("How many {material} objects are {relation} the {shape}?", {
                'material': random.choice(materials), 'relation': random.choice(relations), 'shape': random.choice(shapes)
            }),
            ("Is there a {color} object {relation} the {shape}?", {
                'color': random.choice(colors), 'relation': random.choice(relations), 'shape': random.choice(shapes)
            }),
            ("What is the total number of {size} objects {relation} the {color} object?", {
                'size': random.choice(sizes), 'relation': random.choice(relations), 'color': random.choice(colors)
            }),
            ("What is the total number of {material} objects {relation} the {color} {shape}?", {
                'material': random.choice(materials), 'relation': random.choice(relations),
                'color': random.choice(colors), 'shape': random.choice(shapes)
            }),
            ("Is there a {size} {material} object {relation} the {shape}?", {
                'size': random.choice(sizes), 'material': random.choice(materials),
                'relation': random.choice(relations), 'shape': random.choice(shapes)
            }),
        ]
        template, params = random.choice(templates)
        return template.format(**params), params

    def _pick_compositional_question(props):
        """Strict compositional (≥2 attributes) templates only; never single-attribute count."""
        colors = list(props.get('colors') or props.get('all_colors') or ['red', 'blue', 'green'])
        shapes = list(props.get('shapes') or props.get('all_shapes') or ['cube', 'sphere', 'cylinder'])
        materials = list(props.get('materials') or props.get('all_materials') or ['metal', 'rubber'])
        sizes = list(props.get('sizes') or props.get('all_sizes') or ['small', 'large'])
        templates = [
            ("How many {color} {shape}s are there?", {
                'color': random.choice(colors), 'shape': random.choice(shapes)
            }),
            ("Are there any {color} {shape}s?", {
                'color': random.choice(colors), 'shape': random.choice(shapes)
            }),
            ("Is there a {color} {shape}?", {
                'color': random.choice(colors), 'shape': random.choice(shapes)
            }),
            ("Is there a {material} {shape}?", {
                'material': random.choice(materials), 'shape': random.choice(shapes)
            }),
            ("How many {size} {color} objects are there?", {
                'size': random.choice(sizes), 'color': random.choice(colors)
            }),
            ("What is the total number of {color} {material} objects?", {
                'color': random.choice(colors), 'material': random.choice(materials)
            }),
            ("Are there any {material} {shape}s?", {
                'material': random.choice(materials), 'shape': random.choice(shapes)
            }),
            ("How many {size} {shape}s are there?", {
                'size': random.choice(sizes), 'shape': random.choice(shapes)
            }),
        ]
        template, params = random.choice(templates)
        return template.format(**params), params

    # --- change_position: STRICTLY spatial/relational only; never simple attribute count ---
    if cf_type == 'change_position':
        props = props_cf if (props_cf.get('relations') or props_cf.get('colors') or props_cf.get('shapes')) else props_orig
        question, params = _pick_spatial_question(props)
        return question, params

    # --- relational_flip: STRICTLY spatial/relational only ---
    if cf_type == 'relational_flip':
        props = props_cf if (props_cf.get('relations') or props_cf.get('colors') or props_cf.get('shapes')) else props_orig
        question, params = _pick_spatial_question(props)
        return question, params

    # --- swap_attribute: STRICTLY compositional (≥2 attributes) only; never single-attribute count ---
    if cf_type == 'swap_attribute':
        props = props_cf if (props_cf.get('colors') or props_cf.get('shapes')) else props_orig
        question, params = _pick_compositional_question(props)
        return question, params

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

    if cf_type in ('change_size', 'change_material'):
        key = 'sizes' if cf_type == 'change_size' else 'materials'
        attr = key.rstrip('s')
        vals = list(props_cf.get(key) or props_orig.get(key) or [])
        if vals:
            val = random.choice(vals)
            if cf_type == 'change_size':
                template, _ = random.choice(CF_SIZE_QUESTION_TEMPLATES)
            else:
                template, _ = random.choice(CF_MATERIAL_QUESTION_TEMPLATES)
            question = template.format(val=val)
            return question, {attr: val}

    # Fallback: never use generic "How many objects?" for change_position, relational_flip, swap_attribute.
    if cf_type in ('change_position', 'relational_flip', 'swap_attribute'):
        props = props_cf if (props_cf.get('relations') or props_cf.get('colors')) else props_orig
        if cf_type == 'swap_attribute':
            question, params = _pick_compositional_question(props)
        else:
            question, params = _pick_spatial_question(props)
        return question, params
    question = random.choice(CF_COUNT_QUESTION_TEMPLATES)
    return question, {}

def generate_question_for_scene(scene_file, retry_index=None):
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
        # --- Attribute Equivalence (Same/Different) ---
        ("Is the color of the {shape1} the same as the {shape2}?", {
            'shape1': random.choice(props['shapes']),
            'shape2': random.choice(props['shapes'])
        }),
        ("Is the material of the {color} object the same as the {size} object?", {
            'color': random.choice(props['colors']),
            'size': random.choice(props['sizes'])
        }),
        ("Do the {size} object and the {material} object have the same shape?", {
            'size': random.choice(props['sizes']),
            'material': random.choice(props['materials'])
        }),
        # --- Logical Disjunction (OR) ---
        ("How many objects are either {color} or {shape}?", {
            'color': random.choice(props['colors']),
            'shape': random.choice(props['shapes'])
        }),
        ("Are there any objects that are either {material} or {color}?", {
            'material': random.choice(props['materials']),
            'color': random.choice(props['colors'])
        }),
        ("What is the total number of objects that are either {size} or {shape}?", {
            'size': random.choice(props['sizes']),
            'shape': random.choice(props['shapes'])
        }),
        # --- Exact Numerical Comparison ---
        ("Is the number of {color} objects equal to the number of {shape}s?", {
            'color': random.choice(props['colors']),
            'shape': random.choice(props['shapes'])
        }),
        ("Are there exactly as many {material} objects as {size} objects?", {
            'material': random.choice(props['materials']),
            'size': random.choice(props['sizes'])
        }),
        ("Does the scene contain an equal number of {color1} objects and {color2} objects?", dict(zip(
            ['color1', 'color2'],
            random.sample(props['colors'], 2) if len(props['colors']) >= 2 else [props['colors'][0]] * 2
        ))),
        # --- Complex Spatial & Attribute Composition ---
        ("What is the total number of {material} objects {relation} the {color} {shape}?", {
            'material': random.choice(props['materials']),
            'relation': random.choice(props['relations']),
            'color': random.choice(props['colors']),
            'shape': random.choice(props['shapes'])
        }),
        ("Is there a {size} {material} object {relation} the {shape}?", {
            'size': random.choice(props['sizes']),
            'material': random.choice(props['materials']),
            'relation': random.choice(props['relations']),
            'shape': random.choice(props['shapes'])
        }),
    ]
    # Add matte/shin only when the scene has a metal/rubber object; caller should accept only when CF is attribute-swap (not add/remove).
    matte_shiny_objects = [o for o in objects if (o.get('material') or '').lower() in ('metal', 'rubber') and o.get('color') and o.get('shape')]
    if matte_shiny_objects:
        obj = random.choice(matte_shiny_objects)
        templates.append(("Is the {color} {shape} matte or shiny?", {'color': obj.get('color'), 'shape': obj.get('shape')}))
    if retry_index is not None:
        random.seed(hash((scene_file, retry_index)))
    else:
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

def _apply_param_replacements(question, params, cf_params):
    """Replace param values in question with cf_params, from last to first by position, to avoid double-replacing when the same value appears for different placeholders."""
    if not params or not cf_params:
        return question
    # Order keys by first occurrence of their value in the question (so we replace in document order)
    positions = []
    for k, v in params.items():
        if k not in cf_params or cf_params[k] == v:
            continue
        pos = question.find(v)
        if pos >= 0:
            positions.append((pos, k, v, cf_params[k]))
    # Replace from end to start so indices stay valid
    positions.sort(key=lambda x: -x[0])
    for pos, k, old_val, new_val in positions:
        question = question[:pos] + new_val + question[pos + len(old_val):]
    return question


def create_counterfactual_questions(original_question, params, scene):
    props = get_scene_properties(scene)
    cf_questions = []
    
    strategies = ['attribute_swap', 'question_type', 'scope_change',
                  'negation', 'comparative', 'multi_attribute',
                  'same_different', 'either_or', 'equal_comparison']
    
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
                current = params.get(param_to_change)

                def pick_alternative(attr_key, all_vals_getter):
                    alts = [v for v in all_vals_getter() if v != current]
                    if alts:
                        cf_params[param_to_change] = random.choice(alts)
                        return True
                    return False

                if param_to_change in ('color', 'color1', 'color2'):
                    if not pick_alternative('color', lambda: props['all_colors']):
                        strategy = 'negation'
                        continue
                elif param_to_change in ('shape', 'shape1', 'shape2'):
                    if not pick_alternative('shape', lambda: props['all_shapes']):
                        strategy = 'negation'
                        continue
                elif param_to_change == 'material':
                    if not pick_alternative('material', lambda: props['all_materials']):
                        strategy = 'negation'
                        continue
                elif param_to_change == 'size':
                    if not pick_alternative('size', lambda: props['all_sizes']):
                        strategy = 'negation'
                        continue
                elif param_to_change == 'relation':
                    if not pick_alternative('relation', lambda: props['relations']):
                        strategy = 'negation'
                        continue
                else:
                    retry_count += 1
                    continue

                cf_q = _apply_param_replacements(original_question, params, cf_params)
            
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

            elif strategy == 'same_different':
                # Attribute equivalence: "same as" / "same shape/color/material" -> swap one compared attribute or "same" -> "different"
                q = original_question
                q_lower = q.lower()
                if "the same as" in q_lower or "same shape" in q_lower or "same color" in q_lower or "same material" in q_lower:
                    if random.choice([True, False]) and params:
                        # Swap one of the compared attributes (reuse attribute_swap logic for one key)
                        swap_keys = [k for k in params if k in ('shape1', 'shape2', 'color', 'size', 'material', 'shape')]
                        if swap_keys:
                            key = random.choice(swap_keys)
                            current = params.get(key)
                            if key in ('shape1', 'shape2', 'shape'):
                                alts = [s for s in props['all_shapes'] if s != current]
                                val = random.choice(alts) if alts else current
                            elif key in ('color', 'color1', 'color2'):
                                alts = [c for c in props['all_colors'] if c != current]
                                val = random.choice(alts) if alts else current
                            elif key == 'material':
                                alts = [m for m in props['all_materials'] if m != current]
                                val = random.choice(alts) if alts else current
                            elif key == 'size':
                                alts = [s for s in props['all_sizes'] if s != current]
                                val = random.choice(alts) if alts else current
                            else:
                                val = current
                            if val != current:
                                cf_params = params.copy()
                                cf_params[key] = val
                                cf_q = _apply_param_replacements(q, params, cf_params)
                            else:
                                cf_q = None
                        else:
                            cf_q = None
                    else:
                        # Replace "same as" with "different from" / "same" with "different"
                        if "the same as" in q_lower:
                            cf_q = q.replace("the same as", "different from").replace("The same as", "Different from")
                        elif "same shape" in q_lower:
                            cf_q = q.replace("same shape", "different shape").replace("same shape", "different shape")
                        elif "same color" in q_lower:
                            cf_q = q.replace("same color", "different color")
                        elif "same material" in q_lower:
                            cf_q = q.replace("same material", "different material")
                        else:
                            cf_q = q.replace("the same as", "different from")
                        cf_params = params.copy() if params else {}
                else:
                    cf_q = None

            elif strategy == 'either_or':
                # "either X or Y" -> swap X or Y, or "either X or Y" -> "both X and Y"
                q_lower = original_question.lower()
                if "either" in q_lower and " or " in q_lower and params:
                    if random.choice([True, False]):
                        # Swap one of the two attributes
                        swap_keys = [k for k in params if k in ('color', 'shape', 'material', 'size')]
                        if swap_keys:
                            key = random.choice(swap_keys)
                            current = params.get(key)
                            if key == 'shape':
                                alts = [s for s in props['all_shapes'] if s != current]
                                val = random.choice(alts) if alts else current
                            elif key == 'color':
                                alts = [c for c in props['all_colors'] if c != current]
                                val = random.choice(alts) if alts else current
                            elif key == 'material':
                                alts = [m for m in props['all_materials'] if m != current]
                                val = random.choice(alts) if alts else current
                            elif key == 'size':
                                alts = [s for s in props['all_sizes'] if s != current]
                                val = random.choice(alts) if alts else current
                            else:
                                val = current
                            if val != current:
                                cf_params = params.copy()
                                cf_params[key] = val
                                cf_q = _apply_param_replacements(original_question, params, cf_params)
                            else:
                                cf_q = None
                        else:
                            cf_q = None
                    else:
                        # "either ... or" -> "both ... and"
                        cf_q = original_question.replace("either", "both").replace(" or ", " and ")
                        cf_params = params.copy() if params else {}
                else:
                    cf_q = None

            elif strategy == 'equal_comparison':
                # "equal to" / "exactly as many" -> swap one target or change to "greater than" / "fewer than"
                q = original_question
                q_lower = q.lower()
                if ("equal to" in q_lower or "exactly as many" in q_lower or "equal number" in q_lower) and params:
                    if random.choice([True, False]):
                        # Swap one of the compared properties (color, shape, material, size, color1, color2)
                        swap_keys = [k for k in params if k in ('color', 'color1', 'color2', 'shape', 'material', 'size')]
                        if swap_keys:
                            key = random.choice(swap_keys)
                            current = params.get(key)
                            if key in ('color', 'color1', 'color2'):
                                alts = [c for c in props['all_colors'] if c != current]
                                val = random.choice(alts) if alts else current
                            elif key == 'shape':
                                alts = [s for s in props['all_shapes'] if s != current]
                                val = random.choice(alts) if alts else current
                            elif key == 'material':
                                alts = [m for m in props['all_materials'] if m != current]
                                val = random.choice(alts) if alts else current
                            elif key == 'size':
                                alts = [s for s in props['all_sizes'] if s != current]
                                val = random.choice(alts) if alts else current
                            else:
                                val = current
                            if val != current:
                                cf_params = params.copy()
                                cf_params[key] = val
                                cf_q = _apply_param_replacements(q, params, cf_params)
                            else:
                                cf_q = None
                        else:
                            cf_q = None
                    else:
                        # "equal to" -> "greater than" or "fewer than"; "equal number" -> "greater/fewer number"
                        # ("exactly as many" left to swap-only path to avoid ungrammatical "more X as Y")
                        if "equal to" in q_lower:
                            direction = random.choice(["greater than", "fewer than"])
                            cf_q = q.replace("equal to", direction).replace("Equal to", direction.capitalize())
                            cf_params = params.copy() if params else {}
                        elif "equal number" in q_lower:
                            cf_q = q.replace("equal number", random.choice(["greater number", "fewer number"]))
                            cf_params = params.copy() if params else {}
                        else:
                            cf_q = None
                            cf_params = {}
                else:
                    cf_q = None

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

    def _str_answer(val):
        if val is None:
            return "unknown"
        return str(val).strip().lower()

    # --- Attribute Equivalence ("same as" / "same shape/color/material") ---
    if "the same as" in question_lower or "different from" in question_lower or "same shape" in question_lower or "same color" in question_lower or "same material" in question_lower:
        expect_same = "different from" not in question_lower and "different shape" not in question_lower and "different color" not in question_lower and "different material" not in question_lower
        shape1 = _first_value_in_question(question_lower, _SHAPES)
        shape2 = None
        for s in _SHAPES:
            if s in question_lower and s != shape1:
                shape2 = s.rstrip('s')
                break
        if shape2 is None and shape1:
            shape2 = shape1.rstrip('s')
        color1 = _first_value_in_question(question_lower, _COLORS)
        size1 = _first_value_in_question(question_lower, _SIZES, strip_s=False)
        material1 = _first_value_in_question(question_lower, _MATERIALS)

        if "have the same shape" in question_lower:
            cand_a = _find_objects_matching(objects, size=size1) if size1 else []
            cand_b = _find_objects_matching(objects, material=material1) if material1 else []
            if not cand_a or not cand_b:
                return _str_answer("no" if expect_same else "yes")
            v1 = (objects[cand_a[0]].get('shape') or '').lower()
            v2 = (objects[cand_b[0]].get('shape') or '').lower()
            same = (v1 == v2)
            return _str_answer("yes" if (same == expect_same) else "no")

        if "material of" in question_lower:
            attr = 'material'
            cand1 = _find_objects_matching(objects, color=color1) if color1 else []
            cand2 = _find_objects_matching(objects, size=size1) if size1 else []
        elif "color of" in question_lower or ("same as" in question_lower and shape1):
            attr = 'color'
            cand1 = _find_objects_matching(objects, shape=shape1.rstrip('s') if shape1 else None) if shape1 else []
            cand2 = _find_objects_matching(objects, shape=shape2) if shape2 else []
        else:
            attr = 'color'
            cand1 = _find_objects_matching(objects, shape=shape1.rstrip('s') if shape1 else None) if shape1 else _find_objects_matching(objects, color=color1) if color1 else []
            cand2 = _find_objects_matching(objects, shape=shape2) if shape2 else _find_objects_matching(objects, size=size1) if size1 else []
        if not cand1 or not cand2:
            return _str_answer("no" if expect_same else "yes")
        v1 = (objects[cand1[0]].get(attr) or '').lower()
        v2 = (objects[cand2[0]].get(attr) or '').lower()
        if not v1 or not v2:
            return _str_answer("unknown")
        same = (v1 == v2)
        return _str_answer("yes" if (same == expect_same) else "no")

    # --- Logical Disjunction ("either X or Y") ---
    if "either" in question_lower and " or " in question_lower:
        color_val = _first_value_in_question(question_lower, _COLORS)
        shape_val = _first_value_in_question(question_lower, _SHAPES)
        material_val = _first_value_in_question(question_lower, _MATERIALS)
        size_val = _first_value_in_question(question_lower, _SIZES, strip_s=False)
        count = 0
        for obj in objects:
            c = (obj.get('color') or '').lower()
            s = (obj.get('shape') or '').lower()
            m = (obj.get('material') or '').lower()
            z = (obj.get('size') or '').lower()
            match = False
            if color_val and c == color_val.rstrip('s'):
                match = True
            if shape_val and (s == shape_val.rstrip('s') or s + 's' == shape_val):
                match = True
            if material_val and m == material_val.rstrip('s'):
                match = True
            if size_val and z == size_val:
                match = True
            if match:
                count += 1
        if "are there any" in question_lower:
            return _str_answer("yes" if count > 0 else "no")
        return _str_answer(str(count))

    # --- Exact Numerical Comparison ("equal to", "exactly as many", "equal number") ---
    if "equal to" in question_lower or "exactly as many" in question_lower or "equal number" in question_lower:
        def _count_for_value(attr_kind, val):
            if not val:
                return None
            if attr_kind == 'color':
                return sum(1 for o in objects if (o.get('color') or '').lower() == val.rstrip('s'))
            if attr_kind == 'shape':
                return sum(1 for o in objects if (o.get('shape') or '').lower() == val.rstrip('s'))
            if attr_kind == 'material':
                return sum(1 for o in objects if (o.get('material') or '').lower() == val.rstrip('s'))
            if attr_kind == 'size':
                return sum(1 for o in objects if (o.get('size') or '').lower() == val)
            return None

        def _parse_one_category(phrase):
            for c in _COLORS:
                if c in phrase:
                    return ('color', c.rstrip('s'))
            for s in _SHAPES:
                if s in phrase:
                    return ('shape', s.rstrip('s'))
            for m in _MATERIALS:
                if m in phrase:
                    return ('material', m.rstrip('s'))
            for z in _SIZES:
                if z in phrase:
                    return ('size', z)
            return (None, None)

        if "number of" in question_lower and "objects and" in question_lower:
            parts = question_lower.split("and")
            if len(parts) >= 2:
                kind1, v1 = _parse_one_category(parts[0])
                kind2, v2 = _parse_one_category(parts[1])
                if kind1 and kind2:
                    n1 = _count_for_value(kind1, v1)
                    n2 = _count_for_value(kind2, v2)
                    if n1 is not None and n2 is not None:
                        return _str_answer("yes" if n1 == n2 else "no")
        if "equal to" in question_lower:
            left, _, right = question_lower.partition("equal to")
            kind1, v1 = _parse_one_category(left)
            kind2, v2 = _parse_one_category(right)
            if kind1 and kind2:
                n1 = _count_for_value(kind1, v1)
                n2 = _count_for_value(kind2, v2)
                if n1 is not None and n2 is not None:
                    return _str_answer("yes" if n1 == n2 else "no")
        if "exactly as many" in question_lower:
            parts = re.split(r'exactly as many\s+', question_lower)
            if len(parts) >= 2:
                rest = parts[1]
                parts2 = re.split(r'\s+as\s+', rest, maxsplit=1)
                if len(parts2) >= 2:
                    kind1, v1 = _parse_one_category(parts2[0])
                    kind2, v2 = _parse_one_category(parts2[1])
                    if kind1 and kind2:
                        n1 = _count_for_value(kind1, v1)
                        n2 = _count_for_value(kind2, v2)
                        if n1 is not None and n2 is not None:
                            return _str_answer("yes" if n1 == n2 else "no")
        return _str_answer("unknown")

    # --- Complex Spatial (X objects {relation} the Y) ---
    for rel_phrase in PHRASES_TO_RELATION_KEYS:
        if rel_phrase in question_lower and ("objects " in question_lower or "object " in question_lower):
            before_rel, _, after_rel = question_lower.partition(rel_phrase)
            ref_color = _first_value_in_question(after_rel, _COLORS)
            ref_shape = _first_value_in_question(after_rel, _SHAPES)
            ref_material = _first_value_in_question(after_rel, _MATERIALS)
            ref_size = _first_value_in_question(after_rel, _SIZES, strip_s=False)
            in_rel = _objects_in_relation_to_reference(scene, rel_phrase, ref_color=ref_color, ref_shape=ref_shape, ref_material=ref_material, ref_size=ref_size)
            filter_color = _first_value_in_question(before_rel, _COLORS)
            filter_shape = _first_value_in_question(before_rel, _SHAPES)
            filter_material = _first_value_in_question(before_rel, _MATERIALS)
            filter_size = _first_value_in_question(before_rel, _SIZES, strip_s=False)
            filtered = 0
            for idx in in_rel:
                if idx >= len(objects):
                    continue
                o = objects[idx]
                if filter_color and (o.get('color') or '').lower() != filter_color.rstrip('s'):
                    continue
                if filter_shape and (o.get('shape') or '').lower() != filter_shape.rstrip('s'):
                    continue
                if filter_material and (o.get('material') or '').lower() != filter_material.rstrip('s'):
                    continue
                if filter_size and (o.get('size') or '').lower() != filter_size:
                    continue
                filtered += 1
            if "how many" in question_lower or "total number" in question_lower:
                return _str_answer(str(filtered))
            if "is there a" in question_lower or "are there any" in question_lower:
                return _str_answer("yes" if filtered > 0 else "no")
            break

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
            obj_color = (obj.get('color') or '').lower()
            obj_shape = (obj.get('shape') or '').lower()
            obj_material = (obj.get('material') or '').lower()
            matches = True
            if color_match and obj_color != color_match:
                matches = False
            if shape_match and obj_shape != shape_match:
                matches = False
            if matches:
                if obj_material == 'metal':
                    return "shiny"
                if obj_material == 'rubber':
                    return "matte"
        # Object not in this scene (e.g. CF removed it); answer without "none" or "not found"
        return _str_answer("unknown")
    
    return _str_answer("unknown")

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
                                   strict_question_validation=True, single_cf_per_row=False):
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
    
    if single_cf_per_row:
        if with_links:
            h = ['scene_id', 'original_image_link', 'original_scene_link', 'counterfactual_image_link', 'counterfactual_scene_link', 'counterfactual_type', 'counterfactual_description']
            if generate_questions:
                h.extend(['original_question', 'counterfactual_question', 'original_question_difficulty', 'counterfactual_question_difficulty',
                         'original_image_answer_to_original_question', 'original_image_answer_to_cf_question',
                         'cf_image_answer_to_original_question', 'cf_image_answer_to_cf_question'])
            rows = [h]
        elif generate_questions:
            rows = [['original_image', 'counterfactual_image', 'counterfactual_type', 'counterfactual_description',
                     'original_question', 'counterfactual_question', 'original_question_difficulty', 'counterfactual_question_difficulty',
                     'original_image_answer_to_original_question', 'original_image_answer_to_cf_question',
                     'cf_image_answer_to_original_question', 'cf_image_answer_to_cf_question']]
        else:
            rows = [['original_image', 'counterfactual_image', 'counterfactual_type', 'counterfactual_description']]
    
    total_scenes = len(scene_sets)
    
    for idx, scene_num in enumerate(sorted(scene_sets.keys())):
        scene_data = scene_sets[scene_num]
        cf_keys = sorted([k for k in scene_data if k.startswith('cf') and len(k) > 2 and k[2:].isdigit()], key=lambda x: int(x[2:]))
        
        if single_cf_per_row:
            if 'original' not in scene_data or len(cf_keys) < 1:
                continue
            original_id = scene_data['original']
            for cf_key in cf_keys:
                cf_id = scene_data[cf_key]
                original_scene_file = find_scene_file(scenes_dir, original_id)
                cf_scene_file = find_scene_file(scenes_dir, cf_id)
                if not original_scene_file or not cf_scene_file:
                    continue
                try:
                    original_scene = load_scene(original_scene_file)
                    cf_scene = load_scene(cf_scene_file)
                    cf_type = get_cf_type_from_scene(cf_scene) or ''
                    cf_description = get_cf_description_from_scene(cf_scene) or ''
                except Exception:
                    continue
                if generate_questions:
                    appended = False
                    for cf_retry in range(MAX_CF_ANSWER_RETRIES):
                        try:
                            original_question, params = generate_question_for_scene(original_scene_file, retry_index=cf_retry)
                            original_ans_orig = answer_question_for_scene(original_question, original_scene)
                            cf_question, cf_params = generate_question_for_counterfactual(
                                cf_type, original_scene, cf_scene, retry_index=cf_retry,
                                original_question=original_question, original_params=params
                            )
                            if cf_question is None or cf_params is None:
                                continue
                            # Matte/shin can yield "unknown" when the object is removed; only allow for attribute-swap CFs.
                            if "matte or shiny" in (original_question or "").lower() and cf_type in ("add_object", "remove_object"):
                                continue
                            original_ans_cf_q = answer_question_for_scene(cf_question, original_scene)
                            cf_ans_orig_q = answer_question_for_scene(original_question, cf_scene)
                            cf_ans_cf_q = answer_question_for_scene(cf_question, cf_scene)
                            orig_diff = calculate_question_difficulty(original_question, params)
                            cf_diff = calculate_question_difficulty(cf_question, cf_params)
                        except Exception:
                            continue
                        # Answers must change between original and counterfactual images for both questions.
                        if normalize_answer(original_ans_orig) == normalize_answer(cf_ans_orig_q):
                            continue
                        if strict_question_validation:
                            validity = classify_question_validity(cf_question, original_scene, cf_scene)
                            required = 'Semantic-Valid' if (cf_type and cf_type in IMAGE_CF_TYPES) else 'Negative-Valid'
                            if validity != required:
                                continue
                        else:
                            if normalize_answer(original_ans_cf_q) == normalize_answer(cf_ans_cf_q):
                                continue
                        if with_links:
                            def _link(fn, ft='image'):
                                return f"{base_url.rstrip('/')}/{ft}s/{fn}" if base_url else f"{ft}s/{fn}"
                            rows.append([
                                scene_num,
                                _link(original_id, 'image'), _link(original_id.replace('.png', '.json'), 'scene'),
                                _link(cf_id, 'image'), _link(cf_id.replace('.png', '.json'), 'scene'),
                                cf_type, cf_description,
                                original_question, cf_question, orig_diff, cf_diff,
                                original_ans_orig, original_ans_cf_q, cf_ans_orig_q, cf_ans_cf_q
                            ])
                        else:
                            rows.append([
                                original_id, cf_id, cf_type, cf_description,
                                original_question, cf_question, orig_diff, cf_diff,
                                original_ans_orig, original_ans_cf_q, cf_ans_orig_q, cf_ans_cf_q
                            ])
                        appended = True
                        break
                    if not appended and generate_questions:
                        pass  # skip this (original, CF) pair after MAX_CF_ANSWER_RETRIES
                else:
                    if with_links:
                        def _link(fn, ft='image'):
                            return f"{base_url.rstrip('/')}/{ft}s/{fn}" if base_url else f"{ft}s/{fn}"
                        rows.append([
                            scene_num,
                            _link(original_id, 'image'), _link(original_id.replace('.png', '.json'), 'scene'),
                            _link(cf_id, 'image'), _link(cf_id.replace('.png', '.json'), 'scene'),
                            cf_type, cf_description
                        ])
                    else:
                        rows.append([original_id, cf_id, cf_type, cf_description])
            continue
        
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
                        cf1_question, cf1_params = generate_question_for_counterfactual(
                            cf1_type, original_scene, cf1_scene, retry_index=cf_retry,
                            original_question=original_question, original_params=params
                        )
                        if cf1_question is None or cf1_params is None:
                            continue
                    else:
                        cf1_question, cf1_params = cf_questions[0] if cf_questions and len(cf_questions) > 0 else ("How many objects are in the scene?", {})
                    if cf2_type:
                        cf2_question, cf2_params = generate_question_for_counterfactual(
                            cf2_type, original_scene, cf2_scene, retry_index=cf_retry,
                            original_question=original_question, original_params=params
                        )
                        if cf2_question is None or cf2_params is None:
                            continue
                    else:
                        cf2_question, cf2_params = cf_questions[1] if cf_questions and len(cf_questions) > 1 else (cf_questions[0] if cf_questions else ("How many objects are in the scene?", {}))
                    # Matte/shin can yield "unknown" when the object is removed; only allow for attribute-swap CFs.
                    if "matte or shiny" in (original_question or "").lower() and (cf1_type in ("add_object", "remove_object") or cf2_type in ("add_object", "remove_object")):
                        continue
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
                # Original question answer must change between original and each counterfactual image.
                orig_n = normalize_answer(original_ans_orig_q)
                if orig_n == normalize_answer(cf1_ans_orig_q) or orig_n == normalize_answer(cf2_ans_orig_q):
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
                    # change_position, swap_attribute, relational_flip now use strict spatial/compositional routing and must pass Semantic-Valid.
                    cf1_differs = (cf1_type not in IMAGE_CF_TYPES) or (normalize_answer(original_ans_cf1_q) != normalize_answer(cf1_ans_cf1_q))
                    cf2_differs = (cf2_type not in IMAGE_CF_TYPES) or (normalize_answer(original_ans_cf2_q) != normalize_answer(cf2_ans_cf2_q))
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
    print(f"  Total rows: {len(rows) - 1}")
    
    print("\nSample entry:")
    if len(rows) > 1:
        row = rows[1]
        if single_cf_per_row:
            if generate_questions and len(row) >= 12:
                print(f"  Images: Original: {row[0]}, Counterfactual: {row[1]}")
                print(f"  CF type / description: {row[2]}, {row[3]!r}")
                print(f"  Questions: Original: {row[4]}, CF: {row[5]}")
                print(f"  Answers: orig→orig_q: {row[8]}, orig→cf_q: {row[9]}, cf→orig_q: {row[10]}, cf→cf_q: {row[11]}")
            elif len(row) >= 4:
                print(f"  Images: Original: {row[0]}, Counterfactual: {row[1]}")
                print(f"  CF type / description: {row[2]}, {row[3]!r}")
        elif with_links:
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
    parser.add_argument('--single_cf_per_row', action='store_true',
                       help='Emit one row per (original, single counterfactual) instead of one row per (original, cf1, cf2). CSV columns: original_image, counterfactual_image, counterfactual_type, counterfactual_description [, + Q&A if --generate_questions].')
    
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
        strict_question_validation=not args.no_strict_validation,
        single_cf_per_row=getattr(args, 'single_cf_per_row', False)
    )

if __name__ == '__main__':
    main()