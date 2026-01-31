#!/usr/bin/env python3

import json
import os
import sys
import copy
import argparse
from pathlib import Path

script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, project_root)

from pipeline import (
    generate_base_scene,
    find_blender,
    create_patched_utils,
    create_patched_render_script,
    create_render_from_json_script,
    save_scene,
    render_scene,
    IMAGE_COUNTERFACTUALS,
    NEGATIVE_COUNTERFACTUALS,
    COUNTERFACTUAL_TYPES
)

def generate_all_counterfactual_examples(output_dir='output/counterfactual_examples',
                                        num_objects=5,
                                        render=False,
                                        use_gpu=0):
    print("="*70)
    print("GENERATING COUNTERFACTUAL EXAMPLES")
    print("="*70)
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    if not os.path.isabs(output_dir):
        output_dir = os.path.join(project_root, output_dir)
    
    os.makedirs(output_dir, exist_ok=True)
    scenes_dir = os.path.join(output_dir, 'scenes')
    images_dir = os.path.join(output_dir, 'images') if render else None
    if render:
        os.makedirs(images_dir, exist_ok=True)
    os.makedirs(scenes_dir, exist_ok=True)
    
    # Setup Blender
    blender_path = find_blender()
    create_patched_utils()
    create_patched_render_script()
    if render:
        create_render_from_json_script()
    
    print(f"\n1. Generating base scene with {num_objects} objects...")
    base_scene = None
    for retry in range(3):
        base_scene = generate_base_scene(num_objects, blender_path, 0)
        if base_scene and len(base_scene.get('objects', [])) > 0:
            break
        print(f"  Retry {retry + 1}/3...")
    
    if not base_scene or len(base_scene.get('objects', [])) == 0:
        print("ERROR: Failed to generate base scene")
        return
    
    # Save original scene
    original_path = os.path.join(scenes_dir, '00_original.json')
    save_scene(base_scene, original_path)
    print(f"  [OK] Saved original scene: {original_path}")
    
    # Render original if requested
    if render:
        original_image = os.path.join(images_dir, '00_original.png')
        print(f"  Rendering original scene...")
        render_scene(blender_path, original_path, original_image, use_gpu=use_gpu)
        if os.path.exists(original_image):
            print(f"  [OK] Rendered: 00_original.png")
    
    # Generate examples for each counterfactual type
    all_cf_types = {**IMAGE_COUNTERFACTUALS, **NEGATIVE_COUNTERFACTUALS}
    total_cfs = len(all_cf_types)
    
    print(f"\n2. Generating {total_cfs} counterfactual examples...")
    
    # Process image counterfactuals
    image_cf_index = 1
    for cf_type, cf_func in sorted(IMAGE_COUNTERFACTUALS.items()):
        print(f"\n  [Image CF {image_cf_index}/{len(IMAGE_COUNTERFACTUALS)}] Applying: {cf_type}")
        
        # Apply counterfactual
        try:
            cf_scene, description = cf_func(copy.deepcopy(base_scene))
            
            # Add metadata
            cf_scene['cf_metadata'] = {
                'variant': f'image_cf_{image_cf_index}',
                'is_counterfactual': True,
                'cf_index': image_cf_index,
                'cf_category': 'image_cf',
                'cf_type': cf_type,
                'cf_description': description,
                'source_scene': '00_original'
            }
            
            # Create descriptive filename
            filename = f"01_image_{image_cf_index:02d}_{cf_type}.json"
            cf_path = os.path.join(scenes_dir, filename)
            
            save_scene(cf_scene, cf_path)
            print(f"    [OK] Saved: {filename}")
            print(f"      Description: {description}")
            
            # Render if requested
            if render:
                cf_image = os.path.join(images_dir, filename.replace('.json', '.png'))
                render_scene(blender_path, cf_path, cf_image, use_gpu=use_gpu)
                if os.path.exists(cf_image):
                    print(f"    [OK] Rendered: {filename.replace('.json', '.png')}")
            
            image_cf_index += 1
            
        except Exception as e:
            print(f"    [ERROR] ERROR applying {cf_type}: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    # Process negative counterfactuals
    negative_cf_index = 1
    for cf_type, cf_func in sorted(NEGATIVE_COUNTERFACTUALS.items()):
        print(f"\n  [Negative CF {negative_cf_index}/{len(NEGATIVE_COUNTERFACTUALS)}] Applying: {cf_type}")
        
        # Apply counterfactual
        try:
            # Use stronger noise for examples (medium or heavy)
            if cf_type == 'add_noise':
                cf_scene, description = cf_func(copy.deepcopy(base_scene), min_noise_level='medium')
            else:
                cf_scene, description = cf_func(copy.deepcopy(base_scene))
            
            # Add metadata
            cf_scene['cf_metadata'] = {
                'variant': f'negative_cf_{negative_cf_index}',
                'is_counterfactual': True,
                'cf_index': negative_cf_index,
                'cf_category': 'negative_cf',
                'cf_type': cf_type,
                'cf_description': description,
                'source_scene': '00_original'
            }
            
            # Create descriptive filename
            filename = f"02_negative_{negative_cf_index:02d}_{cf_type}.json"
            cf_path = os.path.join(scenes_dir, filename)
            
            save_scene(cf_scene, cf_path)
            print(f"    [OK] Saved: {filename}")
            print(f"      Description: {description}")
            
            # Render if requested
            if render:
                cf_image = os.path.join(images_dir, filename.replace('.json', '.png'))
                render_scene(blender_path, cf_path, cf_image, use_gpu=use_gpu)
                if os.path.exists(cf_image):
                    print(f"    [OK] Rendered: {filename.replace('.json', '.png')}")
            
            negative_cf_index += 1
            
        except Exception as e:
            print(f"    [ERROR] ERROR applying {cf_type}: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    # Create a summary file
    summary = {
        'base_scene': '00_original.json',
        'total_counterfactuals': len(all_cf_types),
        'image_counterfactuals': len(IMAGE_COUNTERFACTUALS),
        'negative_counterfactuals': len(NEGATIVE_COUNTERFACTUALS),
        'counterfactuals': {}
    }
    
    # Add image counterfactuals to summary
    image_cf_index = 1
    for cf_type in sorted(IMAGE_COUNTERFACTUALS.keys()):
        filename = f"01_image_{image_cf_index:02d}_{cf_type}.json"
        summary['counterfactuals'][cf_type] = {
            'filename': filename,
            'category': 'image_cf',
            'index': image_cf_index
        }
        image_cf_index += 1
    
    # Add negative counterfactuals to summary
    negative_cf_index = 1
    for cf_type in sorted(NEGATIVE_COUNTERFACTUALS.keys()):
        filename = f"02_negative_{negative_cf_index:02d}_{cf_type}.json"
        summary['counterfactuals'][cf_type] = {
            'filename': filename,
            'category': 'negative_cf',
            'index': negative_cf_index
        }
        negative_cf_index += 1
    
    summary_path = os.path.join(output_dir, 'summary.json')
    with open(summary_path, 'w') as f:
        json.dump(summary, f, indent=2)
    
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    print(f"Base scene: {original_path}")
    print(f"Total counterfactuals generated: {len(all_cf_types)}")
    print(f"  - Image CFs: {len(IMAGE_COUNTERFACTUALS)}")
    print(f"  - Negative CFs: {len(NEGATIVE_COUNTERFACTUALS)}")
    print(f"\nAll files saved to: {output_dir}")
    print(f"Summary saved to: {summary_path}")
    if render:
        print(f"Images saved to: {images_dir}")
    print("="*70)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Generate examples of each counterfactual type')
    parser.add_argument('--output_dir', type=str, default='output/counterfactual_examples',
                       help='Output directory for examples (default: output/counterfactual_examples)')
    parser.add_argument('--num_objects', type=int, default=5,
                       help='Number of objects in base scene (default: 5)')
    parser.add_argument('--render', action='store_true',
                       help='Render scenes to images')
    parser.add_argument('--use_gpu', type=int, default=0,
                       help='Use GPU rendering (0 = CPU, 1 = GPU, default: 0)')
    
    args = parser.parse_args()
    
    generate_all_counterfactual_examples(args.output_dir, args.num_objects, args.render, args.use_gpu)
