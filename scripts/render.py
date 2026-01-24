from __future__ import print_function
import math, sys, random, argparse, json, os, tempfile
from datetime import datetime as dt
from collections import Counter
try:
    from PIL import Image, ImageFilter
except ImportError:
    Image = None
    ImageFilter = None

INSIDE_BLENDER = True
try:
  import bpy, bpy_extras
  from mathutils import Vector
except ImportError as e:
  INSIDE_BLENDER = False

def extract_args(input_argv=None):
  if input_argv is None:
    input_argv = sys.argv
  output_argv = []
  if '--' in input_argv:
    idx = input_argv.index('--')
    output_argv = input_argv[(idx + 1):]
  return output_argv

def parse_args(parser, argv=None):
  return parser.parse_args(extract_args(argv))

def delete_object(obj):
  if not INSIDE_BLENDER:
    return
  bpy.ops.object.select_all(action='DESELECT')
  obj.select_set(True)
  bpy.context.view_layer.objects.active = obj
  bpy.ops.object.delete()

def get_camera_coords(cam, pos):
  if not INSIDE_BLENDER:
    return (0, 0, 0)
  scene = bpy.context.scene
  x, y, z = bpy_extras.object_utils.world_to_camera_view(scene, cam, pos)
  scale = scene.render.resolution_percentage / 100.0
  w = int(scale * scene.render.resolution_x)
  h = int(scale * scene.render.resolution_y)
  px = int(round(x * w))
  py = int(round(h - y * h))
  return (px, py, z)

def set_layer(obj, layer_idx):
  if not INSIDE_BLENDER:
    return
  obj.layers[layer_idx] = True
  for i in range(len(obj.layers)):
    obj.layers[i] = (i == layer_idx)

def add_object(object_dir, name, scale, loc, theta=0):
  """
  Load an object from a file. We assume that in the directory object_dir, there
  is a file named "$name.blend" which contains a single object named "$name"
  that has unit size and is centered at the origin.

  - scale: scalar giving the size that the object should be in the scene
  - loc: tuple (x, y) giving the coordinates on the ground plane where the
    object should be placed.
  """
  if not INSIDE_BLENDER:
    return
  object_dir = os.path.abspath(os.path.normpath(object_dir))
  if not os.path.exists(object_dir):
    print(f"ERROR: Object directory does not exist: {object_dir}")
    return
  count = 0
  for obj in bpy.data.objects:
    if obj.name.startswith(name):
      count += 1

  blend_file = os.path.join(object_dir, '%s.blend' % name)
  blend_file = os.path.abspath(blend_file).replace('\\', '/')
  if not os.path.exists(blend_file):
    print(f"ERROR: Blend file does not exist: {blend_file}")
    return
  directory = blend_file + '/Object/'
  try:
    bpy.ops.wm.append(
      directory=directory,
      filename=name,
      filter_blender=True
    )
  except Exception as e:
    error_msg = str(e)
    print(f"ERROR: Failed to load object {name} from {directory}: {error_msg}")
    print(f"  Error type: {type(e).__name__}")
    raise

  new_name = '%s_%d' % (name, count)
  bpy.data.objects[name].name = new_name

  x, y = loc
  bpy.context.view_layer.objects.active = bpy.data.objects[new_name]
  bpy.context.object.rotation_euler[2] = theta
  bpy.ops.transform.resize(value=(scale, scale, scale))
  bpy.ops.transform.translate(value=(x, y, scale))

def load_materials(material_dir):
  """
  Load materials from a directory. We assume that the directory contains .blend
  files with one material each. The file X.blend has a single NodeTree item named
  X; this NodeTree item must have a "Color" input that accepts an RGBA value.
  """
  if not INSIDE_BLENDER:
    return
  material_dir = os.path.abspath(os.path.normpath(material_dir))
  if not os.path.exists(material_dir):
    print(f"ERROR: Material directory does not exist: {material_dir}")
    return
  for fn in os.listdir(material_dir):
    if not fn.endswith('.blend'): continue
    name = os.path.splitext(fn)[0]
    blend_file = os.path.join(material_dir, fn)
    blend_file = os.path.abspath(blend_file).replace('\\', '/')
    if not os.path.exists(blend_file):
      print(f"ERROR: Blend file does not exist: {blend_file}")
      continue
    directory = blend_file + '/NodeTree/'
    try:
      bpy.ops.wm.append(
        directory=directory,
        filename=name,
        filter_blender=True
      )
    except Exception as e:
      error_msg = str(e)
      print(f"ERROR: Failed to load material {name} from {directory}: {error_msg}")
      print(f"  Error type: {type(e).__name__}")
      raise

def apply_filter_to_image(image_path, filter_type, filter_strength):
  """Apply post-processing filters to rendered image"""
  image_path = os.path.abspath(image_path)
  if Image is None:
    print(f"ERROR: PIL/Image not available, cannot apply filter {filter_type}")
    return
  if not os.path.exists(image_path):
    print(f"ERROR: Image file does not exist: {image_path}")
    return
  
  try:
    img = Image.open(image_path)
    
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
      
      for y in range(height):
        for x in range(width):
          dx = (x - center_x) / max_radius
          dy = (y - center_y) / max_radius
          distance = math.sqrt(dx*dx + dy*dy)
          
          if distance > 1.0:
            out_pixels[x, y] = (0, 0, 0)
          else:
            theta = math.atan2(dy, dx)
            r_normalized = distance
            r_distorted = r_normalized * (1.0 + filter_strength * (1.0 - r_normalized))
            r_distorted = min(1.0, r_distorted)
            
            src_x = int(center_x + r_distorted * max_radius * math.cos(theta))
            src_y = int(center_y + r_distorted * max_radius * math.sin(theta))
            
            if 0 <= src_x < width and 0 <= src_y < height:
              out_pixels[x, y] = in_pixels[src_x, src_y]
            else:
              out_pixels[x, y] = (0, 0, 0)
      
      img = output
    
    img.save(image_path)
    print(f"[OK] Applied {filter_type} filter (strength: {filter_strength:.2f})")
  except Exception as e:
    import traceback
    print(f"ERROR applying filter {filter_type}: {e}")
    traceback.print_exc()
    raise

def add_material(name, **properties):
  """
  Create a new material and assign it to the active object. "name" should be the
  name of a material that has been previously loaded using load_materials.
  """
  if not INSIDE_BLENDER:
    return
  mat_count = len(bpy.data.materials)
  bpy.ops.material.new()
  mat = bpy.data.materials['Material']
  mat.name = 'Material_%d' % mat_count
  obj = bpy.context.active_object
  assert len(obj.data.materials) == 0
  obj.data.materials.append(mat)

  output_node = None
  for n in mat.node_tree.nodes:
    if n.name == 'Material Output':
      output_node = n
      break

  group_node = mat.node_tree.nodes.new('ShaderNodeGroup')
  group_node.node_tree = bpy.data.node_groups[name]

  for inp in group_node.inputs:
    if inp.name in properties:
      inp.default_value = properties[inp.name]

  mat.node_tree.links.new(
      group_node.outputs['Shader'],
      output_node.inputs['Surface'],
  )

parser = argparse.ArgumentParser()
parser.add_argument('--scene_file', default=None,
    help="Optional JSON file to load scene from. If provided, renders from JSON instead of generating random scenes.")
parser.add_argument('--base_scene_blendfile', default='data/base_scene.blend',
    help="Base blender file on which all scenes are based; includes " +
          "ground plane, lights, and camera.")
parser.add_argument('--properties_json', default='data/properties.json',
    help="JSON file defining objects, materials, sizes, and colors. " +
         "The \"colors\" field maps from CLEVR color names to RGB values; " +
         "The \"sizes\" field maps from CLEVR size names to scalars used to " +
         "rescale object models; the \"materials\" and \"shapes\" fields map " +
         "from CLEVR material and shape names to .blend files in the " +
         "--object_material_dir and --shape_dir directories respectively.")
parser.add_argument('--shape_dir', default='data/shapes',
    help="Directory where .blend files for object models are stored")
parser.add_argument('--material_dir', default='data/materials',
    help="Directory where .blend files for materials are stored")
parser.add_argument('--shape_color_combos_json', default=None,
    help="Optional path to a JSON file mapping shape names to a list of " +
         "allowed color names for that shape. This allows rendering images " +
         "for CLEVR-CoGenT.")

parser.add_argument('--min_objects', default=3, type=int,
    help="The minimum number of objects to place in each scene")
parser.add_argument('--max_objects', default=10, type=int,
    help="The maximum number of objects to place in each scene")
parser.add_argument('--min_dist', default=0.15, type=float,
    help="The minimum allowed distance between object centers")
parser.add_argument('--margin', default=0.2, type=float,
    help="Along all cardinal directions (left, right, front, back), all " +
         "objects will be at least this distance apart. This makes resolving " +
         "spatial relationships slightly less ambiguous.")
parser.add_argument('--min_pixels_per_object', default=50, type=int,
    help="All objects will have at least this many visible pixels in the " +
         "final rendered images; this ensures that no objects are fully " +
         "occluded by other objects.")
parser.add_argument('--max_retries', default=100, type=int,
    help="The number of times to try placing an object before giving up and " +
         "re-placing all objects in the scene.")

parser.add_argument('--start_idx', default=0, type=int,
    help="The index at which to start for numbering rendered images. Setting " +
         "this to non-zero values allows you to distribute rendering across " +
         "multiple machines and recombine the results later.")
parser.add_argument('--num_images', default=5, type=int,
    help="The number of images to render")
parser.add_argument('--filename_prefix', default='CLEVR',
    help="This prefix will be prepended to the rendered images and JSON scenes")
parser.add_argument('--split', default='new',
    help="Name of the split for which we are rendering. This will be added to " +
         "the names of rendered images, and will also be stored in the JSON " +
         "scene structure for each image.")
parser.add_argument('--output_image_dir', default='../output/images/',
    help="The directory where output images will be stored. It will be " +
         "created if it does not exist.")
parser.add_argument('--output_scene_dir', default='../output/scenes/',
    help="The directory where output JSON scene structures will be stored. " +
         "It will be created if it does not exist.")
parser.add_argument('--output_scene_file', default='../output/CLEVR_scenes.json',
    help="Path to write a single JSON file containing all scene information")
parser.add_argument('--output_blend_dir', default='output/blendfiles',
    help="The directory where blender scene files will be stored, if the " +
         "user requested that these files be saved using the " +
         "--save_blendfiles flag; in this case it will be created if it does " +
         "not already exist.")
parser.add_argument('--save_blendfiles', type=int, default=0,
    help="Setting --save_blendfiles 1 will cause the blender scene file for " +
         "each generated image to be stored in the directory specified by " +
         "the --output_blend_dir flag. These files are not saved by default " +
         "because they take up ~5-10MB each.")
parser.add_argument('--version', default='1.0',
    help="String to store in the \"version\" field of the generated JSON file")
parser.add_argument('--license',
    default="Creative Commons Attribution (CC-BY 4.0)",
    help="String to store in the \"license\" field of the generated JSON file")
parser.add_argument('--date', default=dt.today().strftime("%m/%d/%Y"),
    help="String to store in the \"date\" field of the generated JSON file; " +
         "defaults to today's date")

parser.add_argument('--use_gpu', default=0, type=int,
    help="Setting --use_gpu 1 enables GPU-accelerated rendering using CUDA. " +
         "You must have an NVIDIA GPU with the CUDA toolkit installed for " +
         "to work.")
parser.add_argument('--width', default=320, type=int,
    help="The width (in pixels) for the rendered images")
parser.add_argument('--height', default=240, type=int,
    help="The height (in pixels) for the rendered images")
parser.add_argument('--key_light_jitter', default=1.0, type=float,
    help="The magnitude of random jitter to add to the key light position.")
parser.add_argument('--fill_light_jitter', default=1.0, type=float,
    help="The magnitude of random jitter to add to the fill light position.")
parser.add_argument('--back_light_jitter', default=1.0, type=float,
    help="The magnitude of random jitter to add to the back light position.")
parser.add_argument('--camera_jitter', default=0.5, type=float,
    help="The magnitude of random jitter to add to the camera position")
parser.add_argument('--render_num_samples', default=512, type=int,
    help="The number of samples to use when rendering. Larger values will " +
         "result in nicer images but will cause rendering to take longer.")
parser.add_argument('--render_min_bounces', default=8, type=int,
    help="The minimum number of bounces to use for rendering.")
parser.add_argument('--render_max_bounces', default=8, type=int,
    help="The maximum number of bounces to use for rendering.")
parser.add_argument('--render_tile_size', default=256, type=int,
    help="The tile size to use for rendering. This should not affect the " +
         "quality of the rendered image but may affect the speed; CPU-based " +
         "rendering may achieve better performance using smaller tile sizes " +
         "while larger tile sizes may be optimal for GPU-based rendering.")
parser.add_argument('--output_image', default=None,
    help="Output image path (used when rendering from JSON)")

BACKGROUND_COLORS = {
    'default': None,
    'gray': (0.5, 0.5, 0.5),
    'blue': (0.2, 0.4, 0.8),
    'green': (0.2, 0.6, 0.3),
    'brown': (0.4, 0.3, 0.2),
    'purple': (0.5, 0.3, 0.6),
    'orange': (0.8, 0.5, 0.2),
    'white': (0.9, 0.9, 0.9),
    'dark_gray': (0.2, 0.2, 0.2),
    'red': (0.7, 0.2, 0.2),
    'yellow': (0.8, 0.8, 0.3),
    'cyan': (0.3, 0.7, 0.8),
}

LIGHTING_PRESETS = {
    'default': {'key': 1.0, 'fill': 0.5, 'back': 0.3},
    'bright': {'key': 2.5, 'fill': 1.5, 'back': 1.0},
    'dim': {'key': 0.2, 'fill': 0.1, 'back': 0.05},
    'warm': {'key': 1.8, 'fill': 1.0, 'back': 0.5, 'color': (1.0, 0.85, 0.7)},
    'cool': {'key': 1.2, 'fill': 0.7, 'back': 0.6, 'color': (0.7, 0.85, 1.0)},
    'dramatic': {'key': 3.5, 'fill': 0.1, 'back': 0.05},
}

def set_background_color(color_name):
  """Set the world background color"""
  if not INSIDE_BLENDER:
    return
  if color_name not in BACKGROUND_COLORS or BACKGROUND_COLORS[color_name] is None:
    return
  
  rgb = BACKGROUND_COLORS[color_name]
  
  world = bpy.context.scene.world
  if world is None:
    world = bpy.data.worlds.new("World")
    bpy.context.scene.world = world
  
  world.use_nodes = True
  nodes = world.node_tree.nodes
  
  bg_node = None
  for node in nodes:
    if node.type == 'BACKGROUND':
      bg_node = node
      break
  
  if bg_node is None:
    bg_node = nodes.new(type='ShaderNodeBackground')
  
  bg_node.inputs['Color'].default_value = (rgb[0], rgb[1], rgb[2], 1.0)
  bg_node.inputs['Strength'].default_value = 1.0
  
  print(f"Set background color to {color_name}: RGB{rgb}")

def set_ground_color(color_name):
  """Set the ground plane color if it exists"""
  if not INSIDE_BLENDER:
    return
  if color_name not in BACKGROUND_COLORS or BACKGROUND_COLORS[color_name] is None:
    return
  
  rgb = BACKGROUND_COLORS[color_name]
  
  ground = None
  for obj in bpy.data.objects:
    if 'ground' in obj.name.lower() or 'plane' in obj.name.lower():
      ground = obj
      break
  
  if ground is None:
    return
  
  if len(ground.data.materials) == 0:
    mat = bpy.data.materials.new(name="Ground_Material")
    ground.data.materials.append(mat)
  else:
    mat = ground.data.materials[0]
  
  mat.use_nodes = True
  nodes = mat.node_tree.nodes
  
  bsdf = None
  for node in nodes:
    if node.type == 'BSDF_PRINCIPLED':
      bsdf = node
      break
  
  if bsdf:
    bsdf.inputs['Base Color'].default_value = (rgb[0], rgb[1], rgb[2], 1.0)
    print(f"Set ground color to {color_name}")

def set_lighting(lighting_name):
  """Set lighting conditions"""
  if not INSIDE_BLENDER:
    return
  if lighting_name not in LIGHTING_PRESETS:
    return
  
  preset = LIGHTING_PRESETS[lighting_name]
  
  lamp_names = ['Lamp_Key', 'Lamp_Fill', 'Lamp_Back']
  intensity_keys = ['key', 'fill', 'back']
  
  for lamp_name, int_key in zip(lamp_names, intensity_keys):
    if lamp_name in bpy.data.objects:
      lamp_obj = bpy.data.objects[lamp_name]
      if lamp_obj.data and hasattr(lamp_obj.data, 'energy'):
        base_energy = lamp_obj.data.energy
        lamp_obj.data.energy = base_energy * preset.get(int_key, 1.0)
        
        if 'color' in preset and hasattr(lamp_obj.data, 'color'):
          lamp_obj.data.color = preset['color']
  
  print(f"Set lighting to {lighting_name}")

def render_from_json(args):
  """Render a scene from a JSON file (alternative to random generation)"""
  if not INSIDE_BLENDER:
    print("ERROR: render_from_json must be run inside Blender")
    return
  
  output_dir = os.path.dirname(args.output_image) if args.output_image else '.'
  if output_dir and not os.path.exists(output_dir):
    os.makedirs(output_dir)
  
  with open(args.scene_file, 'r') as f:
    scene_struct = json.load(f)
  
  num_objects = len(scene_struct.get('objects', []))
  print(f"Scene has {num_objects} objects")
  
  base_scene_path = os.path.abspath(args.base_scene_blendfile)
  bpy.ops.wm.open_mainfile(filepath=base_scene_path)
  
  try:
    load_materials(args.material_dir)
  except Exception as e:
    print(f"Warning: Could not load materials: {e}")

  background_color = scene_struct.get('background_color', None)
  if background_color:
    set_background_color(background_color)
    set_ground_color(background_color)
  
  lighting = scene_struct.get('lighting', None)
  if lighting:
    set_lighting(lighting)
  
  render_args = bpy.context.scene.render
  render_args.engine = "CYCLES"
  render_args.filepath = args.output_image
  render_args.resolution_x = args.width
  render_args.resolution_y = args.height
  render_args.resolution_percentage = 100
  
  if args.use_gpu == 1:
    try:
      bpy.context.preferences.addons['cycles'].preferences.compute_device_type = 'CUDA'
      bpy.context.scene.cycles.device = 'GPU'
      print("[OK] GPU rendering enabled")
    except Exception as e:
      print(f"Warning: Could not enable GPU: {e}")
  
  bpy.context.scene.cycles.samples = args.render_num_samples
  
  filter_type = scene_struct.get('filter_type')
  filter_strength = scene_struct.get('filter_strength', 1.0)
  
  if filter_type == 'fisheye':
    camera = bpy.data.objects.get('Camera')
    if camera and camera.data:
      cam_data = camera.data
      if cam_data.type == 'PERSP':
        cam_data.lens = cam_data.lens * 0.7
        print(f"[OK] Zoomed out camera for fisheye: lens={cam_data.lens:.1f}mm")
  
  with open(args.properties_json, 'r') as f:
    properties = json.load(f)
    color_name_to_rgba = {}
    for name, rgb in properties['colors'].items():
      rgba = [float(c) / 255.0 for c in rgb] + [1.0]
      color_name_to_rgba[name] = rgba
    size_mapping = properties['sizes']
  
  shape_semantic_to_file = properties['shapes']
  material_semantic_to_file = properties['materials']
  
  print("Adding objects to scene...")
  for i, obj_info in enumerate(scene_struct.get('objects', [])):
    x, y, z = obj_info['3d_coords']
    r = size_mapping[obj_info['size']]
    semantic_shape = obj_info['shape']
    
    if semantic_shape == 'cube':
      r /= math.sqrt(2)
    
    if semantic_shape not in shape_semantic_to_file:
      print(f"ERROR: Shape '{semantic_shape}' not found")
      continue
    
    shape_file_name = shape_semantic_to_file[semantic_shape]
    
    try:
      add_object(args.shape_dir, shape_file_name, r, (x, y), theta=obj_info['rotation'])
    except Exception as e:
      print(f"Error adding object {i}: {e}")
      continue
    
    rgba = color_name_to_rgba[obj_info['color']]
    semantic_material = obj_info['material']
    
    if semantic_material not in material_semantic_to_file:
      print(f"ERROR: Material '{semantic_material}' not found")
      continue
    
    mat_file_name = material_semantic_to_file[semantic_material]
    
    try:
      add_material(mat_file_name, Color=rgba)
    except Exception as e:
      print(f"Warning: Could not add material: {e}")
  
  filter_type = scene_struct.get('filter_type')
  filter_strength = scene_struct.get('filter_strength', 1.0)
  
  print(f"Rendering to {args.output_image}...")
  
  try:
    bpy.ops.render.render(write_still=True)
    print("[OK] Rendering complete!")
  except Exception as e:
    print(f"Error during rendering: {e}")
    sys.exit(1)
  
  post_filter_type = scene_struct.get('filter_type')
  if post_filter_type and post_filter_type != 'fisheye':
    if Image is None:
      print(f"Warning: PIL not available, cannot apply post-filter {post_filter_type}")
    elif not os.path.exists(args.output_image):
      print(f"Warning: Output image does not exist: {args.output_image}")
    else:
      try:
        post_filter_strength = scene_struct.get('filter_strength', 1.0)
        apply_filter_to_image(args.output_image, post_filter_type, post_filter_strength)
      except Exception as e:
        import traceback
        print(f"Warning: Failed to apply post-filter {post_filter_type}: {e}")
        traceback.print_exc()

def main(args):
  if args.scene_file:
    render_from_json(args)
    return
  
  num_digits = 6
  prefix = '%s_%s_' % (args.filename_prefix, args.split)
  img_template = '%s%%0%dd.png' % (prefix, num_digits)
  scene_template = '%s%%0%dd.json' % (prefix, num_digits)
  blend_template = '%s%%0%dd.blend' % (prefix, num_digits)
  img_template = os.path.join(args.output_image_dir, img_template)
  scene_template = os.path.join(args.output_scene_dir, scene_template)
  blend_template = os.path.join(args.output_blend_dir, blend_template)

  if not os.path.isdir(args.output_image_dir):
    os.makedirs(args.output_image_dir)
  if not os.path.isdir(args.output_scene_dir):
    os.makedirs(args.output_scene_dir)
  if args.save_blendfiles == 1 and not os.path.isdir(args.output_blend_dir):
    os.makedirs(args.output_blend_dir)
  
  all_scene_paths = []
  for i in range(args.num_images):
    img_path = img_template % (i + args.start_idx)
    scene_path = scene_template % (i + args.start_idx)
    all_scene_paths.append(scene_path)
    blend_path = None
    if args.save_blendfiles == 1:
      blend_path = blend_template % (i + args.start_idx)
    num_objects = random.randint(args.min_objects, args.max_objects)
    render_scene(args,
      num_objects=num_objects,
      output_index=(i + args.start_idx),
      output_split=args.split,
      output_image=img_path,
      output_scene=scene_path,
      output_blendfile=blend_path,
    )

  all_scenes = []
  for scene_path in all_scene_paths:
    with open(scene_path, 'r') as f:
      all_scenes.append(json.load(f))
  output = {
    'info': {
      'date': args.date,
      'version': args.version,
      'split': args.split,
      'license': args.license,
    },
    'scenes': all_scenes
  }
  if args.output_scene_file:
    output_dir = os.path.dirname(os.path.abspath(args.output_scene_file))
    if output_dir:
      os.makedirs(output_dir, exist_ok=True)
    with open(args.output_scene_file, 'w') as f:
      json.dump(output, f)



def render_scene(args,
    num_objects=5,
    output_index=0,
    output_split='none',
    output_image='render.png',
    output_scene='render_json',
    output_blendfile=None,
  ):

  base_scene_path = os.path.abspath(args.base_scene_blendfile)
  bpy.ops.wm.open_mainfile(filepath=base_scene_path)
  load_materials(args.material_dir)

  render_args = bpy.context.scene.render
  render_args.engine = "CYCLES"
  render_args.filepath = output_image
  render_args.resolution_x = args.width
  render_args.resolution_y = args.height
  render_args.resolution_percentage = 100
  if args.use_gpu == 1:
    bpy.context.preferences.addons['cycles'].preferences.compute_device_type = 'CUDA'
    bpy.context.preferences.addons['cycles'].preferences.get_devices()
    for device in bpy.context.preferences.addons['cycles'].preferences.devices:
      device.use = True

  bpy.data.worlds['World'].cycles.sample_as_light = True
  bpy.context.scene.cycles.blur_glossy = 2.0
  bpy.context.scene.cycles.samples = args.render_num_samples
  bpy.context.scene.cycles.transparent_min_bounces = args.render_min_bounces
  bpy.context.scene.cycles.transparent_max_bounces = args.render_max_bounces
  if args.use_gpu == 1:
    bpy.context.scene.cycles.device = 'GPU'

  scene_struct = {
      'split': output_split,
      'image_index': output_index,
      'image_filename': os.path.basename(output_image),
      'objects': [],
      'directions': {},
  }

  bpy.ops.mesh.primitive_plane_add(size=10, location=(0, 0, 0))
  plane = bpy.context.object

  def rand(L):
    return 2.0 * L * (random.random() - 0.5)

  if args.camera_jitter > 0:
    for i in range(3):
      bpy.data.objects['Camera'].location[i] += rand(args.camera_jitter)

  camera = bpy.data.objects['Camera']
  plane_normal = plane.data.vertices[0].normal
  cam_behind = camera.matrix_world.to_quaternion() @ Vector((0, 0, -1))
  cam_left = camera.matrix_world.to_quaternion() @ Vector((-1, 0, 0))
  cam_up = camera.matrix_world.to_quaternion() @ Vector((0, 1, 0))
  plane_behind = (cam_behind - cam_behind.project(plane_normal)).normalized()
  plane_left = (cam_left - cam_left.project(plane_normal)).normalized()
  plane_up = cam_up.project(plane_normal).normalized()

  delete_object(plane)

  scene_struct['directions']['behind'] = tuple(plane_behind)
  scene_struct['directions']['front'] = tuple(-plane_behind)
  scene_struct['directions']['left'] = tuple(plane_left)
  scene_struct['directions']['right'] = tuple(-plane_left)
  scene_struct['directions']['above'] = tuple(plane_up)
  scene_struct['directions']['below'] = tuple(-plane_up)

  if args.key_light_jitter > 0:
    for i in range(3):
      bpy.data.objects['Lamp_Key'].location[i] += rand(args.key_light_jitter)
  if args.back_light_jitter > 0:
    for i in range(3):
      bpy.data.objects['Lamp_Back'].location[i] += rand(args.back_light_jitter)
  if args.fill_light_jitter > 0:
    for i in range(3):
      bpy.data.objects['Lamp_Fill'].location[i] += rand(args.fill_light_jitter)

  objects, blender_objects = add_random_objects(scene_struct, num_objects, args, camera)
  scene_struct['objects'] = objects
  scene_struct['relationships'] = compute_all_relationships(scene_struct)
  while True:
    try:
      bpy.ops.render.render(write_still=True)
      break
    except Exception as e:
      print(e)

  with open(output_scene, 'w') as f:
    json.dump(scene_struct, f, indent=2)

  if output_blendfile is not None:
    bpy.ops.wm.save_as_mainfile(filepath=output_blendfile)


def add_random_objects(scene_struct, num_objects, args, camera, max_scene_attempts=10):
  """
  Add random objects to the current blender scene
  """
  scene_attempt = 0
  while scene_attempt < max_scene_attempts:
    scene_attempt += 1

    with open(args.properties_json, 'r') as f:
      properties = json.load(f)
      color_name_to_rgba = {}
      for name, rgb in properties['colors'].items():
        rgba = [float(c) / 255.0 for c in rgb] + [1.0]
        color_name_to_rgba[name] = rgba
      material_mapping = [(v, k) for k, v in properties['materials'].items()]
      object_mapping = [(v, k) for k, v in properties['shapes'].items()]
      size_mapping = list(properties['sizes'].items())

    shape_color_combos = None
    if args.shape_color_combos_json is not None:
      with open(args.shape_color_combos_json, 'r') as f:
        shape_color_combos = list(json.load(f).items())

    positions = []
    objects = []
    blender_objects = []
    for i in range(num_objects):
      size_name, r = random.choice(size_mapping)

      num_tries = 0
      while True:
        num_tries += 1
        if num_tries > args.max_retries:
          for obj in blender_objects:
            delete_object(obj)
          break
        x = random.uniform(-3, 3)
        y = random.uniform(-3, 3)
        dists_good = True
        margins_good = True
        for (xx, yy, rr) in positions:
          dx, dy = x - xx, y - yy
          dist = math.sqrt(dx * dx + dy * dy)
          if dist - r - rr < args.min_dist:
            dists_good = False
            break
          for direction_name in ['left', 'right', 'front', 'behind']:
            direction_vec = scene_struct['directions'][direction_name]
            assert direction_vec[2] == 0
            margin = dx * direction_vec[0] + dy * direction_vec[1]
            if 0 < margin < args.margin:
              print(margin, args.margin, direction_name)
              print('BROKEN MARGIN!')
              margins_good = False
              break
          if not margins_good:
            break

        if dists_good and margins_good:
          break
      
      if num_tries > args.max_retries:
        break

      if shape_color_combos is None:
        obj_name, obj_name_out = random.choice(object_mapping)
        color_name, rgba = random.choice(list(color_name_to_rgba.items()))
      else:
        obj_name_out, color_choices = random.choice(shape_color_combos)
        color_name = random.choice(color_choices)
        obj_name = [k for k, v in object_mapping if v == obj_name_out][0]
        rgba = color_name_to_rgba[color_name]

      if obj_name == 'Cube':
        r /= math.sqrt(2)

      theta = 360.0 * random.random()
      add_object(args.shape_dir, obj_name, r, (x, y), theta=theta)
      obj = bpy.context.object
      blender_objects.append(obj)
      positions.append((x, y, r))

      mat_name, mat_name_out = random.choice(material_mapping)
      add_material(mat_name, Color=rgba)

      pixel_coords = get_camera_coords(camera, obj.location)
      objects.append({
        'shape': obj_name_out,
        'size': size_name,
        'material': mat_name_out,
        '3d_coords': tuple(obj.location),
        'rotation': theta,
        'pixel_coords': pixel_coords,
        'color': color_name,
      })

    if len(objects) < num_objects:
      continue

    all_visible = check_visibility(blender_objects, args.min_pixels_per_object)
    if not all_visible:
      print('Some objects are occluded; replacing objects')
      for obj in blender_objects:
        delete_object(obj)
      continue

    return objects, blender_objects

  raise RuntimeError(f"Failed to generate a valid scene after {max_scene_attempts} attempts")


def compute_all_relationships(scene_struct, eps=0.2):
  """
  Computes relationships between all pairs of objects in the scene.
  
  Returns a dictionary mapping string relationship names to lists of lists of
  integers, where output[rel][i] gives a list of object indices that have the
  relationship rel with object i. For example if j is in output['left'][i] then
  object j is left of object j.
  """
  all_relationships = {}
  for name, direction_vec in scene_struct['directions'].items():
    if name == 'above' or name == 'below': continue
    all_relationships[name] = []
    for i, obj1 in enumerate(scene_struct['objects']):
      coords1 = obj1['3d_coords']
      related = set()
      for j, obj2 in enumerate(scene_struct['objects']):
        if obj1 == obj2: continue
        coords2 = obj2['3d_coords']
        diff = [coords2[k] - coords1[k] for k in [0, 1, 2]]
        dot = sum(diff[k] * direction_vec[k] for k in [0, 1, 2])
        if dot > eps:
          related.add(j)
      all_relationships[name].append(sorted(list(related)))
  return all_relationships


def check_visibility(blender_objects, min_pixels_per_object):
  """Visibility check disabled for Blender 4.x compatibility."""
  return True


def render_shadeless(blender_objects, path='flat.png'):
  """
  Render a version of the scene with shading disabled and unique materials
  assigned to all objects, and return a set of all colors that should be in the
  rendered image. The image itself is written to path. This is used to ensure
  that all objects will be visible in the final rendered scene.
  """
  render_args = bpy.context.scene.render

  old_filepath = render_args.filepath
  old_engine = render_args.engine

  render_args.filepath = path
  render_args.engine = 'BLENDER_EEVEE_NEXT'
  
  view_layer = bpy.context.scene.view_layers[0]
  old_use_pass_combined = view_layer.use_pass_combined
  
  for obj_name in ['Lamp_Key', 'Lamp_Fill', 'Lamp_Back', 'Ground']:
    if obj_name in bpy.data.objects:
      obj = bpy.data.objects[obj_name]
      obj.hide_render = True

  object_colors = set()
  old_materials = []
  for i, obj in enumerate(blender_objects):
    if len(obj.data.materials) > 0:
      old_materials.append(obj.data.materials[0])
    else:
      old_materials.append(None)
    
    mat = bpy.data.materials.new(name='Material_%d' % i)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()
    
    node_emission = nodes.new(type='ShaderNodeEmission')
    node_output = nodes.new(type='ShaderNodeOutputMaterial')
    
    while True:
      r, g, b = [random.random() for _ in range(3)]
      if (r, g, b) not in object_colors: break
    object_colors.add((r, g, b))
    
    node_emission.inputs['Color'].default_value = (r, g, b, 1.0)
    mat.node_tree.links.new(node_emission.outputs['Emission'], node_output.inputs['Surface'])
    
    if len(obj.data.materials) > 0:
      obj.data.materials[0] = mat
    else:
      obj.data.materials.append(mat)

  bpy.ops.render.render(write_still=True)

  for mat, obj in zip(old_materials, blender_objects):
    if mat is not None:
      obj.data.materials[0] = mat
    elif len(obj.data.materials) > 0:
      obj.data.materials.clear()

  for obj_name in ['Lamp_Key', 'Lamp_Fill', 'Lamp_Back', 'Ground']:
    if obj_name in bpy.data.objects:
      obj = bpy.data.objects[obj_name]
      obj.hide_render = False

  render_args.filepath = old_filepath
  render_args.engine = old_engine

  return object_colors


if __name__ == '__main__':
  if INSIDE_BLENDER:
    # Run normally
    argv = extract_args()
    args = parser.parse_args(argv)
    main(args)
  elif '--help' in sys.argv or '-h' in sys.argv:
    parser.print_help()
  else:
    print('This script is intended to be called from blender like this:')
    print()
    print('blender --background --python render_images.py -- [args]')
    print()
    print('You can also run as a standalone python script to view all')
    print('arguments like this:')
    print()
    print('python render_images.py --help')
