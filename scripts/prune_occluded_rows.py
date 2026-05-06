import argparse
import csv
import json
import os
import re
from typing import Dict, List, Optional, Sequence, Tuple


COLORS = ("gray", "grey", "red", "blue", "green", "brown", "purple", "cyan", "yellow")
SHAPES = ("cube", "cubes", "sphere", "spheres", "cylinder", "cylinders")
MATERIALS = ("metal", "metals", "rubber", "rubbers")
SIZES = ("small", "large")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prune mapping CSV rows if any scene object is occluded. "
            "Default behavior is absolute-safety mode: drop row if occlusion metadata "
            "is missing or any object fails visibility threshold."
        )
    )
    parser.add_argument(
        "--run_dir",
        required=True,
        help="Path to a run directory containing the CSV and scenes/ folder.",
    )
    parser.add_argument(
        "--input_csv",
        default="image_mapping_with_questions_strict_cf.csv",
        help="Input CSV filename inside run_dir.",
    )
    parser.add_argument(
        "--output_csv",
        default="image_mapping_with_questions_pruned.csv",
        help="Output CSV filename inside run_dir.",
    )
    parser.add_argument(
        "--scenes_dir",
        default=None,
        help="Optional explicit scenes directory (defaults to <run_dir>/scenes).",
    )
    parser.add_argument(
        "--min_visible_pixels",
        type=int,
        default=50,
        help="Minimum visible pixels threshold for an object to be considered visible.",
    )
    parser.add_argument(
        "--min_visibility_fraction",
        type=float,
        default=None,
        help="Optional minimum visibility fraction threshold.",
    )
    parser.add_argument(
        "--question_conditioned",
        action="store_true",
        help=(
            "Only prune when a failing object matches attributes mentioned in question columns. "
            "Default (off) is safer: prune if any object fails."
        ),
    )
    parser.add_argument(
        "--keep_missing_visibility",
        action="store_true",
        help=(
            "Keep rows where no usable visibility metadata is found. "
            "Default (off) is safer: drop rows with missing visibility metadata."
        ),
    )
    return parser.parse_args()


def load_json(path: str) -> Optional[Dict]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[WARN] Failed to read JSON: {path} ({e})")
        return None


def looks_like_scene_image(name: str) -> bool:
    return bool(name) and name.endswith(".png") and name.startswith("scene_")


def scene_json_from_row(row: Dict[str, str], scenes_dir: str) -> Optional[str]:
    candidate_fields = (
        "original_scene_link",
        "original_scene",
        "original_image",
        "original_image_link",
    )

    for field in candidate_fields:
        val = (row.get(field) or "").strip()
        if not val:
            continue
        if val.endswith(".json"):
            base = os.path.basename(val)
            return os.path.join(scenes_dir, base)
        if looks_like_scene_image(os.path.basename(val)):
            base = os.path.basename(val).replace(".png", ".json")
            return os.path.join(scenes_dir, base)

    for _, val in row.items():
        sval = (val or "").strip()
        base = os.path.basename(sval)
        if looks_like_scene_image(base) and "_original.png" in base:
            return os.path.join(scenes_dir, base.replace(".png", ".json"))
    return None


def normalize_token(s: str) -> str:
    return (s or "").strip().lower()


def object_fails_visibility(
    obj: Dict,
    min_visible_pixels: int,
    min_visibility_fraction: Optional[float],
) -> Tuple[bool, bool]:
    """
    Returns:
      (fails_threshold, has_any_visibility_metadata)
    """
    is_occluded = bool(obj.get("is_occluded", False))
    visible_flag = obj.get("visible", None)
    visible_pixels = obj.get("visible_pixel_count", None)
    visibility_fraction = obj.get("visibility_fraction", None)

    has_metadata = any(
        k in obj for k in ("is_occluded", "visible", "visible_pixel_count", "visibility_fraction")
    )

    if is_occluded:
        return True, has_metadata
    if visible_flag is False:
        return True, has_metadata

    if visible_pixels is not None:
        try:
            if int(visible_pixels) < int(min_visible_pixels):
                return True, True
        except Exception:
            pass

    if min_visibility_fraction is not None and visibility_fraction is not None:
        try:
            if float(visibility_fraction) < float(min_visibility_fraction):
                return True, True
        except Exception:
            pass

    return False, has_metadata


def mentioned_attributes(question_text: str) -> Dict[str, set]:
    q = normalize_token(question_text)
    tokens = re.findall(r"[a-z]+", q)
    tok_set = set(tokens)
    return {
        "color": {c.rstrip("s") for c in COLORS if c in tok_set},
        "shape": {s.rstrip("s") for s in SHAPES if s in tok_set},
        "material": {m.rstrip("s") for m in MATERIALS if m in tok_set},
        "size": {z for z in SIZES if z in tok_set},
    }


def row_question_text(row: Dict[str, str]) -> str:
    parts: List[str] = []
    for k, v in row.items():
        if "question" in (k or "").lower():
            vv = (v or "").strip()
            if vv:
                parts.append(vv.lower())
    return " ".join(parts)


def obj_matches_mentioned_attrs(obj: Dict, mentioned: Dict[str, set]) -> bool:
    c = normalize_token(obj.get("color", ""))
    s = normalize_token(obj.get("shape", "")).rstrip("s")
    m = normalize_token(obj.get("material", "")).rstrip("s")
    z = normalize_token(obj.get("size", ""))
    if mentioned["color"] and c in mentioned["color"]:
        return True
    if mentioned["shape"] and s in mentioned["shape"]:
        return True
    if mentioned["material"] and m in mentioned["material"]:
        return True
    if mentioned["size"] and z in mentioned["size"]:
        return True
    return False


def should_prune_row(
    row: Dict[str, str],
    scene: Dict,
    min_visible_pixels: int,
    min_visibility_fraction: Optional[float],
    question_conditioned: bool,
    keep_missing_visibility: bool,
) -> Tuple[bool, str]:
    objects = scene.get("objects", []) or []
    if not isinstance(objects, list) or not objects:
        return True, "empty_or_invalid_scene_objects"

    failing_objects: List[Dict] = []
    any_metadata = False
    for obj in objects:
        fails, has_meta = object_fails_visibility(obj, min_visible_pixels, min_visibility_fraction)
        any_metadata = any_metadata or has_meta
        if fails:
            failing_objects.append(obj)

    if not any_metadata and not keep_missing_visibility:
        return True, "missing_visibility_metadata"
    if not failing_objects:
        return False, "ok"

    if not question_conditioned:
        return True, f"occluded_objects={len(failing_objects)}"

    q_text = row_question_text(row)
    mentioned = mentioned_attributes(q_text)
    for obj in failing_objects:
        if obj_matches_mentioned_attrs(obj, mentioned):
            return True, "occluded_object_matches_question_attributes"
    return False, "occluded_but_no_question_attribute_overlap"


def main() -> None:
    args = parse_args()

    run_dir = os.path.abspath(args.run_dir)
    scenes_dir = os.path.abspath(args.scenes_dir) if args.scenes_dir else os.path.join(run_dir, "scenes")
    input_csv_path = os.path.join(run_dir, args.input_csv)
    output_csv_path = os.path.join(run_dir, args.output_csv)

    if not os.path.isfile(input_csv_path):
        raise FileNotFoundError(f"Input CSV not found: {input_csv_path}")
    if not os.path.isdir(scenes_dir):
        raise FileNotFoundError(f"Scenes directory not found: {scenes_dir}")

    total = 0
    kept = 0
    pruned = 0
    reasons: Dict[str, int] = {}
    out_rows: List[Dict[str, str]] = []

    with open(input_csv_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        if not fieldnames:
            raise RuntimeError("Input CSV has no header.")

        for row in reader:
            total += 1
            scene_json = scene_json_from_row(row, scenes_dir)
            if not scene_json or not os.path.isfile(scene_json):
                pruned += 1
                reasons["scene_file_missing"] = reasons.get("scene_file_missing", 0) + 1
                if total % 50 == 0:
                    print(f"[PROGRESS] processed={total} kept={kept} pruned={pruned}")
                continue

            scene = load_json(scene_json)
            if scene is None:
                pruned += 1
                reasons["scene_json_unreadable"] = reasons.get("scene_json_unreadable", 0) + 1
                if total % 50 == 0:
                    print(f"[PROGRESS] processed={total} kept={kept} pruned={pruned}")
                continue

            drop, reason = should_prune_row(
                row=row,
                scene=scene,
                min_visible_pixels=args.min_visible_pixels,
                min_visibility_fraction=args.min_visibility_fraction,
                question_conditioned=args.question_conditioned,
                keep_missing_visibility=args.keep_missing_visibility,
            )

            if drop:
                pruned += 1
                reasons[reason] = reasons.get(reason, 0) + 1
            else:
                kept += 1
                out_rows.append(row)

            if total % 50 == 0:
                print(f"[PROGRESS] processed={total} kept={kept} pruned={pruned}")

    with open(output_csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(out_rows)

    print("\n[DONE] Pruning complete")
    print(f"Input CSV:  {input_csv_path}")
    print(f"Output CSV: {output_csv_path}")
    print(f"Total rows: {total}")
    print(f"Kept rows:  {kept}")
    print(f"Pruned:     {pruned}")
    if reasons:
        print("Prune reasons:")
        for k in sorted(reasons.keys()):
            print(f"  - {k}: {reasons[k]}")


if __name__ == "__main__":
    main()
