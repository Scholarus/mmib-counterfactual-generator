#!/usr/bin/env python3

import sys
import os

script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, project_root)

from pipeline import (
    find_blender,
    create_patched_render_script,
    create_run_directory,
    generate_base_scene,
    generate_counterfactuals,
    save_scene,
    save_checkpoint,
    load_checkpoint,
    get_completed_scenes_from_folder,
    COUNTERFACTUAL_TYPES,
    list_counterfactual_types
)
import argparse
import random
import json
import shutil
from datetime import datetime

def main():
    parser = argparse.ArgumentParser(
        description='Generate scene JSON files with counterfactuals (no rendering)'
    )
    
    parser.add_argument('--num_scenes', type=int, default=5,
                       help='Number of scene sets to generate')
    parser.add_argument('--num_objects', type=int, default=None,
                       help='Fixed number of objects per scene (overrides min/max)')
    parser.add_argument('--min_objects', type=int, default=3,
                       help='Minimum object count (if num_objects not given)')
    parser.add_argument('--max_objects', type=int, default=7,
                       help='Maximum object count (if num_objects not given)')
    parser.add_argument('--num_counterfactuals', type=int, default=2,
                       help='Number of counterfactual variants per scene')
    parser.add_argument('--blender_path', type=str, default=None,
                       help='Path to Blender executable (auto-detected if not provided)')
    parser.add_argument('--output_dir', type=str, default='output',
                       help='Base directory for all runs')
    parser.add_argument('--run_name', type=str, default=None,
                       help='Optional custom name for this run')
    parser.add_argument('--resume', action='store_true',
                       help='Resume from last checkpoint (requires --run_name)')
    parser.add_argument('--cf_types', nargs='+', 
                   choices=[
                       'change_color', 'change_shape', 'change_size', 
                       'change_material', 'change_position', 
                       'add_object', 'remove_object', 'swap_attribute', 'occlusion_change', 'relational_flip',
                       'replace_object',
                       'change_background', 
                       'change_lighting', 'add_noise',
                       'apply_fisheye', 'apply_blur', 'apply_vignette', 'apply_chromatic_aberration'
                   ],
                   help='Specific counterfactual types to use')
    parser.add_argument('--same_cf_type', action='store_true',
                   help='Use the same counterfactual type for all variants')
    parser.add_argument('--min_cf_change_score', type=float, default=1.0,
                   help='Minimum heuristic change score for counterfactuals')
    parser.add_argument('--max_cf_attempts', type=int, default=10,
                   help='Max retries per counterfactual to meet --min_cf_change_score')
    parser.add_argument('--min_noise_level', type=str, default='light',
                   choices=['light', 'medium', 'heavy'],
                   help='Minimum noise level when using add_noise counterfactual')
    parser.add_argument('--list_cf_types', action='store_true',
                   help='List all available counterfactual types and exit')
    
    args = parser.parse_args()
    
    if args.list_cf_types:
        list_counterfactual_types()
        return
    
    if args.resume and not args.run_name:
        print("ERROR: --run_name is required when using --resume")
        return
    
    blender_path = args.blender_path or find_blender()
    print(f"Using Blender: {blender_path}")
    
    print("\nPreparing scripts...")
    create_patched_render_script()
    
    run_dir = create_run_directory(args.output_dir, args.run_name)
    temp_run_id = os.path.basename(run_dir)
    print(f"\n{'='*70}")
    print(f"RUN DIRECTORY: {run_dir}")
    print(f"{'='*70}")

    scenes_dir = os.path.join(run_dir, 'scenes')
    os.makedirs(scenes_dir, exist_ok=True)
    
    checkpoint_file = os.path.join(run_dir, 'checkpoint.json')
    
    completed_scenes = set()
    if args.resume:
        completed_scenes = load_checkpoint(checkpoint_file)
        existing_scenes = get_completed_scenes_from_folder(scenes_dir)
        completed_scenes.update(existing_scenes)
        
        if completed_scenes:
            print(f"\n[RESUME] Found {len(completed_scenes)} already completed scenes")
        else:
            print("\n[WARNING] Resume flag set but no checkpoint found, starting fresh")
    
    print("\n" + "="*70)
    print(f"GENERATING {args.num_scenes} SCENE SETS (JSON ONLY)")
    print(f"Each with {args.num_counterfactuals} counterfactual variants")
    print("="*70)
    
    successful_scenes = 0
    
    for i in range(args.num_scenes):
        if i in completed_scenes:
            print(f"\n[SKIP] Skipping scene {i} (already completed)")
            successful_scenes += 1
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
            base_scene = generate_base_scene(num_objects, blender_path, i, temp_run_dir=temp_run_id)
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
            same_cf_type=args.same_cf_type,
            min_change_score=args.min_cf_change_score,
            max_cf_attempts=args.max_cf_attempts,
            min_noise_level=args.min_noise_level
        )
        
        for idx, cf in enumerate(counterfactuals):
            cf_cat = cf.get('cf_category', 'unknown')
            print(f"    CF{idx+1} [{cf_cat}] ({cf['type']}): {cf['description']}")
        
        scene_num = i + 1
        scene_prefix = f"scene_{scene_num:04d}"
        scene_paths = {'original': os.path.join(scenes_dir, f"{scene_prefix}_original.json")}
        
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
        
        completed_scenes.add(i)
        save_checkpoint(checkpoint_file, list(completed_scenes))
    
    metadata = {
        'timestamp': datetime.now().isoformat(),
        'num_scenes': args.num_scenes,
        'num_counterfactuals': args.num_counterfactuals,
        'successful_scenes': successful_scenes,
        'successful_renders': 0,
        'cf_types': args.cf_types if args.cf_types else 'default',
    }
    
    metadata_path = os.path.join(run_dir, 'run_metadata.json')
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    temp_run_path = os.path.join(os.getcwd(), 'temp_output', temp_run_id)
    if os.path.exists(temp_run_path):
        shutil.rmtree(temp_run_path)
    if os.path.exists('render_images_patched.py'):
        os.remove('render_images_patched.py')
    
    print("\n" + "="*70)
    print("SCENE COMPLETE")
    print("="*70)
    print(f"Run directory: {run_dir}")
    print(f"Successfully generated: {successful_scenes}/{args.num_scenes} scene sets")
    print(f"\nOutput:")
    print(f"  Scene files: {scenes_dir}/")
    print(f"  Metadata: {metadata_path}")
    print(f"  Checkpoint: {checkpoint_file}")
    print(f"\nNext step: Run 'python pipeline.py --render_only --run_name {args.run_name}' to render these scenes")
    print("="*70)

if __name__ == '__main__':
    main()

