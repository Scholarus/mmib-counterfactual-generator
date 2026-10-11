import os
import argparse
import csv
import json
import math
import random
import re
import tempfile
from itertools import product
from pathlib import Path

# NEGATIVE_TEXT_TEMPLATES: paraphrase pools for the CSV linguistic-control (negative-text CF) column;
# each key is a generate_question_for_scene template string with the same .format(**params) names.
NEGATIVE_TEXT_TEMPLATES = {'How many objects are in the scene?': ['How many objects are in the scene in total?',
                                        'What is the total number of objects in the scene?',
                                        'How many objects are in the scene right now?',
                                        'What is the count of objects in the scene?',
                                        'How many objects are present in the scene?',
                                        'How many objects are visible in the scene?'],
 'What is the total number of objects in the scene?': ['How many objects are in the scene?',
                                                       'How many objects are in the scene in total?',
                                                       'What is the count of objects in the scene?',
                                                       'What is the count of objects that are in the scene?',
                                                       'What is the number of objects that are in the scene?',
                                                       'What is the number of objects in the scene?'],
 'How many {color} objects are there?': ['What is the total number of {color} objects?',
                                         'How many {color} objects are in the scene?',
                                         'How many {color} objects can be found in the scene?',
                                         'What is the count of {color} objects in the scene?',
                                         'What is the count of {color} objects?',
                                         'What is the number of {color} objects in the scene?'],
 'Are there any {shape} objects?': ['Are there any {shape} objects in the scene?',
                                    'Is there at least one {shape} object?',
                                    'Are there any {shape} objects in total?',
                                    'Is there at least one {shape} object in the scene?',
                                    'Are there any {shape} objects present in the scene?',
                                    'Are there any {shape} objects visible in this scene?'],
 'Are there any {shape}s present?': ['Are there any {shape}s in the scene?',
                                     'Is there at least one {shape}?',
                                     'Are there any {shape}s in total?',
                                     'Is there at least one {shape} in the scene?',
                                     'Are there any {shape}s present in the scene?',
                                     'Are there any {shape}s visible in this scene?'],
 'Is there a {color} {shape}?': ['Are there any {color} {shape}s?',
                                 'Is there at least one {color} {shape}?',
                                 'Are there any {color} {shape}s in the scene?',
                                 'Is there at least one {color} {shape} in the scene?',
                                 'Is there a {color} {shape} present in this scene?',
                                'Is it true in this scene that there is a {color} {shape}?'],
 'How many {material} objects are there?': ['What is the total number of {material} objects?',
                                            'How many {material} objects are in the scene?',
                                            'How many {material} objects can be found in the scene?',
                                            'What is the count of {material} objects in the scene?',
                                            'How many {material} objects are present in the scene?',
                                            'What is the number of {material} objects in the scene?'],
 'What is the total number of {material} objects?': ['How many {material} objects are there in total?',
                                                     'How many {material} objects are there?',
                                                     'What is the count of {material} objects?',
                                                     'What is the number of {material} objects?',
                                                     'What is the count of {material} objects in the scene?',
                                                     'How many {material} objects are present in the scene?'],
 'What is the total number of metallic objects?': ['How many metallic objects are in the scene?',
                                                   'How many metal objects are there?',
                                                   'How many metallic objects can be found in the scene?',
                                                   'What is the count of metallic objects in the scene?',
                                                   'What is the count of metallic objects?',
                                                   'How many metallic objects are present in the scene?'],
 'What is the total number of {size} objects?': ['How many {size} objects are there altogether?',
                                                 'How many {size} objects are in the scene?',
                                                 'How many {size} objects can be found in the scene?',
                                                 'What is the count of {size} objects in the scene?',
                                                 'What is the count of {size} objects?',
                                                 'How many {size} objects are present in the scene?'],
 'Is there a {material} {shape}?': ['Are there any {material} {shape}s?',
                                    'Is there at least one {material} {shape}?',
                                    'Are there any {material} {shape}s in the scene?',
                                    'Is there at least one {material} {shape} in the scene?',
                                    'Is there a {material} {shape} present in this scene?',
                                    'Is it true in this scene that there is a {material} {shape}?'],
 'How many {size} {color} objects are there?': ['What is the total number of {size} {color} objects?',
                                                'How many {size} {color} objects are in the scene?',
                                                'How many {size} {color} objects can be found in the scene?',
                                                'What is the count of {size} {color} objects in the scene?',
                                                'What is the count of {size} {color} objects?',
                                                'What is the number of {size} {color} objects in the scene?'],
 'Are there any {color} {shape}s?': ['Are there any {color} {shape}s in the scene?',
                                     'Is there a {color} {shape}?',
                                     'Is there at least one {color} {shape}?',
                                     'Is there at least one {color} {shape} in the scene?',
                                     'Are there any {color} {shape}s present in the scene?',
                                     'Are there any {color} {shape}s visible in this scene?'],
 'What is the total number of {color} {material} objects?': ['How many {color} {material} objects are there in total?',
                                                             'How many {color} {material} objects are in the scene?',
                                                             'How many {color} {material} objects can be found in the '
                                                             'scene?',
                                                             'What is the count of {color} {material} objects in the '
                                                             'scene?',
                                                             'What is the count of {color} {material} objects?',
                                                             'How many {color} {material} objects are present in the '
                                                             'scene?'],
 'What color is the object {relation} the {color} {shape}?': ['What is the color of the object {relation} the {color} '
                                                              '{shape}?',
                                                              'What color is the object that is {relation} the {color} '
                                                              '{shape}?',
                                                              'What is the color of the object that is {relation} the '
                                                              '{color} {shape}?',
                                                              'What color does the object {relation} the {color} '
                                                              '{shape} have?',
                                                              'Can you identify the color of the object {relation} the '
                                                              '{color} {shape}?',
                                                              'What color can be identified for the object {relation} '
                                                              'the {color} {shape}?'],
 'What shape is the object {relation} the {material} object?': ['What is the shape of the object {relation} the '
                                                                '{material} object?',
                                                                'What shape is the object that is {relation} the '
                                                                '{material} object?',
                                                                'What is the shape of the object that is {relation} '
                                                                'the {material} object?',
                                                                'What shape does the object {relation} the {material} '
                                                                'object have?',
                                                                'Can you identify the shape of the object {relation} '
                                                                'the {material} object?',
                                                                'What shape can be identified for the object '
                                                                '{relation} the {material} object?'],
 'What material is the {size} object {relation} the {shape}?': ['What is the material of the {size} object {relation} '
                                                                'the {shape}?',
                                                                'What material is the {size} object that is {relation} '
                                                                'the {shape}?',
                                                                'What is the material of the {size} object that is '
                                                                '{relation} the {shape}?',
                                                                'What material does the {size} object {relation} the '
                                                                '{shape} have?',
                                                                'Can you identify the material of the {size} object '
                                                                '{relation} the {shape}?',
                                                                'What material can be identified for the {size} object '
                                                                '{relation} the {shape}?'],
 'How many objects are {relation} the {color} {shape}?': ['What is the total number of objects {relation} the {color} '
                                                          '{shape}?',
                                                          'How many objects are positioned {relation} the {color} '
                                                          '{shape}?',
                                                          'What is the total number of objects positioned {relation} '
                                                          'the {color} {shape}?',
                                                          'How many objects can be found {relation} the {color} '
                                                          '{shape}?',
                                                          'What is the count of objects that are {relation} the '
                                                          '{color} {shape}?',
                                                          'What is the number of objects that are {relation} the '
                                                          '{color} {shape} in the scene?'],
 'How many {material} objects are {relation} the {shape}?': ['What is the total number of {material} objects '
                                                             '{relation} the {shape}?',
                                                             'How many {material} objects are positioned {relation} '
                                                             'the {shape}?',
                                                             'What is the total number of {material} objects '
                                                             'positioned {relation} the {shape}?',
                                                             'How many {material} objects can be found {relation} the '
                                                             '{shape}?',
                                                             'What is the count of {material} objects that are '
                                                             '{relation} the {shape}?',
                                                             'What is the number of {material} objects that are '
                                                             '{relation} the {shape} in the scene?'],
 'What is the total number of {size} objects {relation} the {color} object?': ['How many {size} objects are {relation} '
                                                                               'the {color} object?',
                                                                               'How many {size} objects are positioned '
                                                                               '{relation} the {color} object?',
                                                                               'What is the total number of {size} '
                                                                               'objects positioned {relation} the '
                                                                               '{color} object?',
                                                                               'How many {size} objects can be found '
                                                                               '{relation} the {color} object?',
                                                                               'What is the count of {size} objects '
                                                                               '{relation} the {color} object?',
                                                                               'How many {size} objects {relation} the '
                                                                               '{color} object are present in the '
                                                                               'scene?'],
 'Is there a {color} object {relation} the {shape}?': ['Are there any {color} objects {relation} the {shape}?',
                                                       'Is there at least one {color} object {relation} the {shape}?',
                                                       'Are there any {color} objects positioned {relation} the '
                                                       '{shape}?',
                                                       'Is there at least one {color} object positioned {relation} the '
                                                       '{shape}?',
                                                       'Is there at least one {color} object {relation} the {shape} in '
                                                       'the scene?',
                                                       'Is there a {color} object {relation} the {shape} present in '
                                                       'this scene?'],
 'Are there any {material} {shape}s {relation} the {size} object?': ['Are there any {material} {shape}s positioned '
                                                                     '{relation} the {size} object?',
                                                                     'Is there a {material} {shape} {relation} the '
                                                                     '{size} object?',
                                                                     'Is there at least one {material} {shape} '
                                                                     '{relation} the {size} object?',
                                                                     'Is there at least one {material} {shape} '
                                                                     'positioned {relation} the {size} object?',
                                                                     'Are there any {material} {shape}s {relation} the '
                                                                     '{size} object present in the scene?',
                                                                     'Are there any {material} {shape}s {relation} the '
                                                                     '{size} object visible in this scene?'],
 'Is the color of the {shape1} the same as the {shape2}?': ['Is the color of the {shape1} the same as the color of the '
                                                            '{shape2}?',
                                                            'Do the {shape1} and the {shape2} have the same color?',
                                                            'Is the {shape1} the same color as the {shape2}?',
                                                            'Are the {shape1} and the {shape2} the same color?',
                                                            'Is it true that the color of the {shape1} is the same as '
                                                            'the {shape2}?',
                                                            'In this scene, is the color of the {shape1} the same as '
                                                            'the {shape2}?'],
 'Is the material of the {color} object the same as the {size} object?': ['Is the material of the {color} object the '
                                                                          'same as the material of the {size} object?',
                                                                          'Do the {color} object and the {size} object '
                                                                          'have the same material?',
                                                                          'Is the {color} object the same material as '
                                                                          'the {size} object?',
                                                                          'Are the {color} object and the {size} '
                                                                          'object the same material?',
                                                                          'Is it true that the material of the '
                                                                          '{color} object is the same as the {size} '
                                                                          'object?',
                                                                          'In this scene, is the material of the '
                                                                          '{color} object the same as the {size} '
                                                                          'object?'],
 'Do the {size} object and the {material} object have the same shape?': ['Are the {size} object and the {material} '
                                                                         'object the same shape?',
                                                                         'Is the shape of the {size} object the same '
                                                                         'as the {material} object?',
                                                                         'Is the {size} object the same shape as the '
                                                                         '{material} object?',
                                                                         'Is the shape of the {size} object the same '
                                                                         'as the shape of the {material} object?',
                                                                         'Is it true that the {size} object and the '
                                                                         '{material} object have the same shape?',
                                                                         'In this scene, do the {size} object and the '
                                                                         '{material} object have the same shape?'],
 'How many objects are either {color} or {shape}?': ['What is the total number of objects that are either {color} or '
                                                     '{shape}?',
                                                     'How many objects are {color} or {shape}?',
                                                     'What is the total number of objects that are {color} or {shape}?',
                                                     'How many objects in the scene are either {color} or {shape}?',
                                                     'What is the count of objects that are either {color} or {shape}?',
                                                     'What is the number of objects that are either {color} or {shape} '
                                                     'in the scene?'],
 'Are there any objects that are either {material} or {color}?': ['Are there any {material} objects or {color} '
                                                                  'objects?',
                                                                  'Is there at least one {material} or {color} object?',
                                                                  'Are there any {material} objects or any {color} '
                                                                  'objects?',
                                                                  'Is there a {material} object or a {color} object?',
                                                                  'Are there any objects that are either {material} or '
                                                                  '{color} present in the scene?',
                                                                  'Are there any objects that are either {material} or '
                                                                  '{color} visible in this scene?'],
 'What is the total number of objects that are either {size} or {shape}?': ['How many objects are either {size} or '
                                                                            '{shape}?',
                                                                            'How many objects are {size} or {shape}?',
                                                                            'What is the total number of objects that '
                                                                            'are {size} or {shape}?',
                                                                            'How many objects in the scene are either '
                                                                            '{size} or {shape}?',
                                                                            'What is the count of objects that are '
                                                                            'either {size} or {shape}?',
                                                                            'How many objects that are either {size} '
                                                                            'or {shape} are present in the scene?'],
 'Is the number of {color} objects equal to the number of {shape}s?': ['Is the number of {color} objects equal to the '
                                                                       'number of {shape} objects?',
                                                                       'Is the count of {color} objects equal to the '
                                                                       'count of {shape}s?',
                                                                       'Is the count of {color} objects equal to the '
                                                                       'count of {shape} objects?',
                                                                       'Is the number of {shape}s equal to the number '
                                                                       'of {color} objects?',
                                                                       'Is it true that the number of {color} '
                                                                       'objects is equal to the number of {shape}s?',
                                                                       'In this scene, is the number of {color} '
                                                                       'objects equal to the number of {shape}s?'],
 'Are there exactly as many {material} objects as {size} objects?': ['Is the number of {material} objects exactly '
                                                                     'equal to the number of {size} objects?',
                                                                     'Is the number of {size} objects exactly equal to '
                                                                     'the number of {material} objects?',
                                                                     'Is the count of {material} objects exactly equal '
                                                                     'to the count of {size} objects?',
                                                                     'Is the count of {size} objects exactly equal to '
                                                                     'the count of {material} objects?',
                                                                     'Is it true that there are exactly as many '
                                                                     '{material} objects as {size} objects?',
                                                                     'In this scene, are there exactly as many '
                                                                     '{material} objects as {size} objects?'],
 'Does the scene contain an equal number of {color1} objects and {color2} objects?': ['Is the number of {color1} '
                                                                                      'objects equal to the number of '
                                                                                      '{color2} objects?',
                                                                                      'Is the count of {color1} '
                                                                                      'objects equal to the count of '
                                                                                      '{color2} objects?',
                                                                                      'Is the number of {color2} '
                                                                                      'objects equal to the number of '
                                                                                      '{color1} objects?',
                                                                                      'Is the count of {color2} '
                                                                                      'objects equal to the count of '
                                                                                      '{color1} objects?',
                                                                                      'Is it true that the scene '
                                                                                      'contains an equal number of '
                                                                                      '{color1} objects and {color2} '
                                                                                      'objects?',
                                                                                      'In this scene, does it '
                                                                                      'contain an equal number of '
                                                                                      '{color1} objects and {color2} '
                                                                                      'objects?'],
 'What is the total number of {material} objects {relation} the {color} {shape}?': ['How many {material} objects are '
                                                                                    '{relation} the {color} {shape}?',
                                                                                    'How many {material} objects are '
                                                                                    'positioned {relation} the {color} '
                                                                                    '{shape}?',
                                                                                    'What is the total number of '
                                                                                    '{material} objects positioned '
                                                                                    '{relation} the {color} {shape}?',
                                                                                    'How many {material} objects can '
                                                                                    'be found {relation} the {color} '
                                                                                    '{shape}?',
                                                                                    'What is the count of {material} '
                                                                                    'objects {relation} the {color} '
                                                                                    '{shape}?',
                                                                                    'How many {material} objects '
                                                                                    '{relation} the {color} {shape} '
                                                                                    'are present in the scene?'],
 'Is there a {size} {material} object {relation} the {shape}?': ['Are there any {size} {material} objects {relation} '
                                                                 'the {shape}?',
                                                                 'Is there at least one {size} {material} object '
                                                                 '{relation} the {shape}?',
                                                                 'Are there any {size} {material} objects positioned '
                                                                 '{relation} the {shape}?',
                                                                 'Is there at least one {size} {material} object '
                                                                 'positioned {relation} the {shape}?',
                                                                 'Is there at least one {size} {material} object '
                                                                 '{relation} the {shape} in the scene?',
                                                                 'Is there a {size} {material} object {relation} the '
                                                                 '{shape} present in this scene?'],
 'Is the {color} {shape} matte or shiny?': ['For the {color} {shape}, is it matte or shiny?',
                                            'Is the {color} {shape} shiny or matte?',
                                            'What finish does the {color} {shape} have — matte or shiny?',
                                            'Is the {color} {shape} a matte or shiny object?',
                                            'What is the finish of the {color} {shape} — matte or shiny?',
                                            'What is the surface appearance of the {color} {shape}: matte or shiny?'],
 'How many {color} {shape}s are there?': ['What is the total number of {color} {shape}s?',
                                          'How many {color} {shape}s are in the scene?',
                                          'How many {color} {shape}s can be found in the scene?',
                                          'What is the count of {color} {shape}s in the scene?',
                                          'What is the count of {color} {shape}s?',
                                          'What is the number of {color} {shape}s in the scene?'],
 'Are there any {material} {shape}s?': ['Are there any {material} {shape}s in the scene?',
                                        'Is there at least one {material} {shape}?',
                                        'Are there any {material} {shape}s in total?',
                                        'Is there at least one {material} {shape} in the scene?',
                                        'Are there any {material} {shape}s present in the scene?',
                                        'Are there any {material} {shape}s visible in this scene?'],
 'How many {size} {shape}s are there?': ['What is the total number of {size} {shape}s?',
                                         'How many {size} {shape}s are in the scene?',
                                         'How many {size} {shape}s can be found in the scene?',
                                         'What is the count of {size} {shape}s in the scene?',
                                         'What is the count of {size} {shape}s?',
                                         'What is the number of {size} {shape}s in the scene?'],
 'What color is the shiny {shape}?': ['What is the color of the shiny {shape}?',
                                      'What color is the metallic {shape}?',
                                      'What is the color of the metallic {shape}?',
                                      'What color does the shiny {shape} have?',
                                      'Can you identify the color of the shiny {shape}?',
                                      'What color can be identified for the shiny {shape}?'],
 'What color is the matte {shape}?': ['What is the color of the matte {shape}?',
                                      'What color is the rubber {shape}?',
                                      'What is the color of the rubber {shape}?',
                                      'What color does the matte {shape} have?',
                                      'Can you identify the color of the matte {shape}?',
                                      'What color can be identified for the matte {shape}?'],
 'What color is the object closest to the {t_shape}?': ['What is the color of the object closest to the {t_shape}?',
                                                        'What color is the nearest object to the {t_shape}?',
                                                        'What is the color of the nearest object to the {t_shape}?',
                                                        'What color is the object nearest to the {t_shape}?',
                                                        'Can you identify the color of the object closest to the '
                                                        '{t_shape}?',
                                                        'What color does the object closest to the {t_shape} have?'],
 'What color is the object closest to the {target_shape}?': ['What is the color of the object closest to the '
                                                             '{target_shape}?',
                                                             'What color is the nearest object to the {target_shape}?',
                                                             'What is the color of the nearest object to the '
                                                             '{target_shape}?',
                                                             'What color is the object nearest to the {target_shape}?',
                                                             'Can you identify the color of the object closest to the '
                                                             '{target_shape}?',
                                                             'What color does the object closest to the {target_shape} '
                                                             'have?'],
 'Are there more than {orig_count} objects?': ['Are there more than {orig_count} objects in total?',
                                               'Are there more than {orig_count} objects in the scene?',
                                               'Is the number of objects in the scene more than {orig_count}?'],
 'Are there at least {cf_count} objects?': ['Are there at least {cf_count} objects in the scene?',
                                            'Is the total number of objects at least {cf_count}?',
                                            'Are there at least {cf_count} objects in total?',
                                            'Is the number of objects in the scene at least {cf_count}?'],
 'Are there fewer than {orig_count} objects?': ['Is the total number of objects less than {orig_count}?',
                                                'Are there fewer than {orig_count} objects in the scene?',
                                                'Is the number of objects fewer than {orig_count}?',
                                                'Is the number of objects in the scene less than {orig_count}?'],
 'Are there more than {cf_count} objects?': ['Are there more than {cf_count} objects in total?',
                                             'Are there more than {cf_count} objects in the scene?',
                                             'Is the number of objects in the scene more than {cf_count}?']}

def _question_answer_type(q):
    """Answer-type bucket for paraphrase compatibility: same bucket as original_question required."""
    ql = (q or '').strip().lower()
    if 'matte or shiny' in ql or ('finish' in ql and 'matte' in ql and 'shiny' in ql):
        return 'matte_shiny'
    if (
        ql.startswith('how many')
        or 'total number' in ql
        or ql.startswith('what is the total')
        or 'what is the count' in ql
    ):
        return 'count'
    if (
        ql.startswith('is ')
        or ql.startswith('are ')
        or ql.startswith('do ')
        or ql.startswith('does ')
        or 'equal to' in ql
        or 'equal number' in ql
        or 'exactly as many' in ql
        or 'at least' in ql
        or 'fewer than' in ql
        or 'more than' in ql
    ):
        return 'yesno'
    if ql.startswith('what '):
        return 'what'
        return 'other'


def _csv_answer_type(q):
    """Export bucket: count, yes/no, or attribute. Matches the audit notebook classifier."""
    internal = _question_answer_type(q)
    if internal == 'count':
        return 'count'
    if internal == 'yesno':
        return 'yes/no'
    if internal in ('what', 'matte_shiny'):
        return 'attribute'
    return 'other'


def _iter_ordered_negative_paraphrases(original_template, params, original_question, retry_index):
    """Yield distinct paraphrase strings (excluding original_question) in deterministic seeded order; same answer-type as original only."""
    pool = NEGATIVE_TEXT_TEMPLATES.get(original_template)
    if not pool:
        return
    expected_type = _question_answer_type(original_question)
    seed = hash((str(original_template), int(retry_index)))
    rng = random.Random(seed)
    order = list(range(len(pool)))
    rng.shuffle(order)
    seen = set()
    for i in order:
        tmpl = pool[i]
        try:
            s = tmpl.format(**(params or {}))
        except (KeyError, ValueError, TypeError):
            continue
        if _question_answer_type(s) != expected_type:
            continue
        if s == original_question or s in seen:
            continue
        seen.add(s)
        yield s


def _answers_invariant_on_scenes(question, scenes):
    if not scenes or question is None:
        return False
    first = normalize_answer(answer_question_for_scene(question, scenes[0]))
    if not first:
        return False
    for sc in scenes[1:]:
        if normalize_answer(answer_question_for_scene(question, sc)) != first:
            return False
    return True


def pick_negative_counterfactual_paraphrase(
    original_template, params, original_question, original_scene, cf_scene, retry_index
):
    """
    First paraphrase from NEGATIVE_TEXT_TEMPLATES (seeded by template + retry_index) that differs
    from original_question and has the same answer on original_scene and cf_scene.
    Returns (question, params_dict) or (None, None).
    """
    if not original_template or original_question is None or params is None:
        return None, None
    scenes = [original_scene, cf_scene]
    for q in _iter_ordered_negative_paraphrases(original_template, params, original_question, retry_index):
        if _answers_invariant_on_scenes(q, scenes):
            return q, dict(params)
    return None, None


def pick_negative_text_cf_question(
    original_template,
    params,
    original_question,
    retry_index,
    *,
    first_paraphrase=None,
    scenes_invariant=None,
):
    """
    Second distinct paraphrase from the same seeded pool as negative_counterfactual_question_1,
    answer-invariant on all scenes in scenes_invariant. Falls back to original_question if
    only one usable paraphrase exists or template is missing.
    """
    if not original_template or original_question is None or params is None:
        return None
    if not scenes_invariant:
        scenes_invariant = []
    first = first_paraphrase or original_question
    second = None
    for q in _iter_ordered_negative_paraphrases(original_template, params, original_question, retry_index):
        if q == first:
            continue
        if _answers_invariant_on_scenes(q, scenes_invariant):
            second = q
            break
    if second is None:
        print(
            f"[NEG_TEXT_CF_WARNING] No distinct answer-invariant second paraphrase; "
            f"template={original_template!r} retry_index={retry_index}"
        )
        return None
    return second


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
        scene = json.load(f)

    objects = scene.get('objects', [])
    visible_indices = []
    for i, obj in enumerate(objects):
        is_occluded = bool(obj.get('is_occluded', False))
        visible_flag = obj.get('visible', None)
        visibility_fraction = obj.get('visibility_fraction', None)
        visible_pixels = obj.get('visible_pixel_count', None)
        full_pixels = obj.get('full_pixel_count', None)

        if visible_flag is False or is_occluded:
            pass
        elif visibility_fraction is not None and full_pixels and full_pixels > 0 and visibility_fraction <= 0:
            pass
        elif visible_pixels is not None and int(visible_pixels) <= 0:
            pass
        else:
            visible_indices.append(i)

    scene['_visible_object_indices'] = visible_indices
    scene['_visible_objects'] = [objects[i] for i in visible_indices if 0 <= i < len(objects)]

    return scene


def _scene_visible_objects(scene):
    objs = scene.get('_visible_objects')
    if objs is not None:
        return objs
    return scene.get('objects', [])

RELATION_KEYS_TO_PHRASES = {'left': 'left of', 'right': 'right of', 'front': 'in front of', 'behind': 'behind'}
PHRASES_TO_RELATION_KEYS = {'left of': 'left', 'right of': 'right', 'in front of': 'front', 'behind': 'behind'}
DEFAULT_RELATIONS = ['left of', 'right of', 'in front of', 'behind']
# Relation opposites for minimal spatial text mutations in create_counterfactual_questions.
RELATION_OPPOSITES = {'left of': 'right of', 'right of': 'left of', 'in front of': 'behind', 'behind': 'in front of'}

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
    visible_indices = set(scene.get('_visible_object_indices', range(len(objects))))
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
    ref_idx = None
    for idx in ref_indices:
        if idx in visible_indices:
            ref_idx = idx
            break
    if ref_idx is None:
        return set()
    return {i for i in rel_list[ref_idx] if i in visible_indices}


def get_scene_properties(scene):
    """Aggregate colors, shapes, materials, sizes, and relation phrases present or defaulted for template sampling."""
    objects = _scene_visible_objects(scene)
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


def _attr_token(value):
    return (value or '').strip().lower().rstrip('s')


def _absent_values(present, universe):
    present_n = {_attr_token(x) for x in (present or []) if x}
    return [x for x in universe if _attr_token(x) not in present_n]


def _pick_exist_value(rng, present, universe, force_absent):
    if force_absent:
        absent = _absent_values(present, universe)
        if absent:
            return rng.choice(absent)
    pool = [x for x in (present or []) if x] or list(universe)
    return rng.choice(pool)


def _present_combos(objects, keys):
    combos = []
    for obj in objects:
        combo = tuple((obj.get(k) or '').strip().lower() for k in keys)
        if all(combo):
            combos.append(combo)
    return combos


def _pick_exist_combo(rng, objects, keys, universes, force_absent):
    present = _present_combos(objects, keys)
    present_n = {tuple(_attr_token(v) for v in c) for c in present}
    if force_absent:
        candidates = [c for c in product(*universes) if tuple(_attr_token(v) for v in c) not in present_n]
        if candidates:
            picked = rng.choice(candidates)
            return {k: v for k, v in zip(keys, picked)}
    if present:
        picked = rng.choice(present)
        return {k: v for k, v in zip(keys, picked)}
    return {k: rng.choice(u) for k, u in zip(keys, universes)}


def _pick_exist_either_material_color(rng, props, force_absent):
    if force_absent:
        absent_m = _absent_values(props['materials'], props['all_materials'])
        absent_c = _absent_values(props['colors'], props['all_colors'])
        if absent_m and absent_c:
            return {'material': rng.choice(absent_m), 'color': rng.choice(absent_c)}
    return {
        'material': rng.choice(props['materials']),
        'color': rng.choice(props['colors']),
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
INTRODUCING_CF_TYPES = {'add_object', 'change_color', 'replace_object'}

# Maps original VQA templates to groups 1–5 for cf_type compatibility (which semantic IMAGE_CF_TYPES may pair with which question families).
QUESTION_TEMPLATE_TO_GROUP = {
    "How many objects are in the scene?": 1,
    "What is the total number of objects in the scene?": 1,
    "How many {color} objects are there?": 2,
    "Are there any {shape} objects?": 2,
    "Are there any {shape}s present?": 2,
    "How many {material} objects are there?": 2,
    "What is the total number of {material} objects?": 2,
    "What is the total number of metallic objects?": 2,
    "What is the total number of {size} objects?": 2,
    "Is there a {color} {shape}?": 3,
    "Is there a {material} {shape}?": 3,
    "How many {size} {color} objects are there?": 3,
    "Are there any {color} {shape}s?": 3,
    "What is the total number of {color} {material} objects?": 3,
    "Is the {color} {shape} matte or shiny?": 3,
    "What color is the object {relation} the {color} {shape}?": 4,
    "What shape is the object {relation} the {material} object?": 4,
    "What material is the {size} object {relation} the {shape}?": 4,
    "How many objects are {relation} the {color} {shape}?": 4,
    "How many {material} objects are {relation} the {shape}?": 4,
    "What is the total number of {size} objects {relation} the {color} object?": 4,
    "Is there a {color} object {relation} the {shape}?": 4,
    "Are there any {material} {shape}s {relation} the {size} object?": 4,
    "What is the total number of {material} objects {relation} the {color} {shape}?": 4,
    "Is there a {size} {material} object {relation} the {shape}?": 4,
    "Is the color of the {shape1} the same as the {shape2}?": 5,
    "Is the material of the {color} object the same as the {size} object?": 5,
    "Do the {size} object and the {material} object have the same shape?": 5,
    "How many objects are either {color} or {shape}?": 5,
    "Are there any objects that are either {material} or {color}?": 5,
    "What is the total number of objects that are either {size} or {shape}?": 5,
    "Is the number of {color} objects equal to the number of {shape}s?": 5,
    "Are there exactly as many {material} objects as {size} objects?": 5,
    "Does the scene contain an equal number of {color1} objects and {color2} objects?": 5,
}

SEMANTIC_CF_TYPES_BY_QUESTION_GROUP = {
    1: frozenset({'add_object', 'remove_object'}),
    2: frozenset({
        'change_color', 'change_shape', 'change_material', 'change_size',
        'replace_object', 'swap_attribute', 'add_object', 'remove_object',
    }),
    3: frozenset({
        'change_color', 'change_shape', 'change_size', 'change_material',
        'replace_object', 'swap_attribute',
    }),
    4: frozenset({'change_position', 'relational_flip', 'add_object', 'remove_object'}),
    5: frozenset({'swap_attribute', 'change_color', 'change_shape', 'add_object', 'remove_object'}),
}

QUESTION_GROUP_TEXT_MUTATION_NOTES = {
    1: "No parameters: minimal mutations yield none; type-targeted CF must be add/remove.",
    2: "Single-parameter swap to another CLEVR value (color/shape/material/size).",
    3: "Single-parameter swap breaks one leg of compositional binding.",
    4: "Relation opposite (left↔right, etc.) and/or anchor attribute swap.",
    5: "Paired-argument swap (color1↔color2, shape1↔shape2) and single-attribute edits.",
}


def get_question_group_for_template(template):
    """Return 1–5 for known original VQA templates, else None."""
    if not template:
        return None
    return QUESTION_TEMPLATE_TO_GROUP.get(template)


def semantic_cf_type_allowed_for_template(cf_type, template):
    """Return whether image cf_type is allowed for template's question group; unknown templates and non-image cf_types are not blocked here."""
    if not cf_type or cf_type not in IMAGE_CF_TYPES:
        return True
    g = get_question_group_for_template(template)
    if g is None:
        return True
    allowed = SEMANTIC_CF_TYPES_BY_QUESTION_GROUP.get(g)
    if not allowed:
        return True
    return cf_type in allowed


def _count_fallback_allowed(original_template, original_question):
    """
    Allow add/remove count fallback only for unknown template paths or known group-1 templates.
    Known groups 2/3/4/5 are blocked so CF must stay in the original template family.
    """
    if not original_template:
        return True
    return get_question_group_for_template(original_template) == 1


def _reference_is_unique(scene, **attrs):
    """True iff exactly one visible object matches all given attributes (None = any)."""
    objects = _scene_visible_objects(scene)
    matches = _find_objects_matching(objects, **attrs)
    return len(matches) == 1


def _shape_kw(params, key):
    v = (params or {}).get(key)
    if v is None:
        return None
    return str(v).lower().rstrip('s')


# Definite singular-reference templates: (template -> checker(scene, params)).
SINGLE_REF_TEMPLATE_CHECKERS = {
    "What color is the object {relation} the {color} {shape}?": lambda p, s: _reference_is_unique(
        s, color=(p or {}).get('color'), shape=_shape_kw(p, 'shape')
    ),
    "What shape is the object {relation} the {material} object?": lambda p, s: _reference_is_unique(
        s, material=(p or {}).get('material')
    ),
    "What material is the {size} object {relation} the {shape}?": lambda p, s: _reference_is_unique(
        s, shape=_shape_kw(p, 'shape')
    ),
    "Is there a {color} object {relation} the {shape}?": lambda p, s: _reference_is_unique(
        s, shape=_shape_kw(p, 'shape')
    ),
    "Are there any {material} {shape}s {relation} the {size} object?": lambda p, s: _reference_is_unique(
        s, size=(p or {}).get('size')
    ),
    "Is the {color} {shape} matte or shiny?": lambda p, s: _reference_is_unique(
        s, color=(p or {}).get('color'), shape=_shape_kw(p, 'shape')
    ),
    "What color is the shiny {shape}?": lambda p, s: _reference_is_unique(
        s, material='metal', shape=_shape_kw(p, 'shape')
    ),
    "What color is the matte {shape}?": lambda p, s: _reference_is_unique(
        s, material='rubber', shape=_shape_kw(p, 'shape')
    ),
}


def original_question_single_ref_valid(original_template, params, scene):
    fn = SINGLE_REF_TEMPLATE_CHECKERS.get(original_template)
    if not fn:
        return True
    try:
        return bool(fn(params, scene))
    except (TypeError, ValueError, AttributeError):
        return False


# Rejection sampling: resample original questions up to this many times per row until answer parity and optional validity checks pass.
# Increased to reduce dropped rows for hard scene/counterfactual combinations.
MAX_CF_ANSWER_RETRIES = 2000

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
    orig_objs = _scene_visible_objects(original_scene)
    cf_objs = _scene_visible_objects(cf_scene)
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


def _parse_cf_attribute_change(original_scene, cf_scene):
    """
    Return (attribute, old_value, new_value) from cf_metadata.cf_description and scene deltas.
    Handles patterns like 'changed gray cube to green', 'changed large sphere to small', etc.
    Returns (None, None, None) if not parseable.
    """
    meta = (cf_scene.get('cf_metadata') or {})
    desc = (meta.get('cf_description') or '').lower()
    cf_type = meta.get('cf_type') or ''

    attr_map = {
        'change_color': ('color', _COLORS),
        'change_shape': ('shape', _SHAPES),
        'change_material': ('material', _MATERIALS),
        'change_size': ('size', _SIZES),
    }
    if cf_type not in attr_map:
        return None, None, None

    attr, vocab = attr_map[cf_type]
    change = get_change_details(original_scene, cf_scene)
    if change and change.get('attribute') == attr:
        return attr, change.get('orig_val'), change.get('cf_val')

    if ' to ' in desc:
        left, _, right = desc.rpartition(' to ')
        left = left.replace('changed', '').strip()
        right = right.strip().rstrip('.')

        def _extract_vocab_value(clause, vocab_list):
            clause_l = clause.lower()
            best = None
            best_len = -1
            for v in vocab_list:
                base = v.rstrip('s').lower()
                if not base:
                    continue
                if re.search(r'\b' + re.escape(base) + r's?\b', clause_l):
                    if len(base) > best_len:
                        best_len = len(base)
                        best = base
            return best

        old_v = _extract_vocab_value(left, vocab)
        new_v = _extract_vocab_value(right, vocab)
        if old_v and new_v and old_v != new_v:
            return attr, old_v, new_v

    found = []
    seen = set()
    for v in vocab:
        base = v.rstrip('s').lower()
        if base and base in desc and base not in seen:
            seen.add(base)
            found.append(base)
    if len(found) >= 2:
        return attr, found[0], found[-1]
    return None, None, None


CF_COUNT_QUESTION_TEMPLATES = [
    "How many objects are in the scene?",
    "What is the total number of objects in the scene?",
    "How many objects are in the scene in total?",
    "Are there more than 2 objects?",
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
    orig_objs = _scene_visible_objects(original_scene)
    cf_objs = _scene_visible_objects(cf_scene)
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


def _minimal_text_mutations(original_params, scene):
    """Yield deep-copied param dicts: paired color/shape swaps first, then relation opposites and single-attribute flips to other taxonomy values."""
    import copy

    if 'color1' in original_params and 'color2' in original_params:
        c1, c2 = original_params['color1'], original_params['color2']
        if (c1 or '').lower() != (c2 or '').lower():
            swapped = copy.deepcopy(original_params)
            swapped['color1'], swapped['color2'] = c2, c1
            yield swapped
    if 'shape1' in original_params and 'shape2' in original_params:
        s1, s2 = original_params['shape1'], original_params['shape2']
        n1 = (s1 or '').lower().rstrip('s')
        n2 = (s2 or '').lower().rstrip('s')
        if n1 != n2:
            swapped = copy.deepcopy(original_params)
            swapped['shape1'], swapped['shape2'] = s2, s1
            yield swapped

    props = get_scene_properties(scene)
    for key in original_params:
        current = original_params[key]
        mutated = copy.deepcopy(original_params)
        if key == 'relation' and current in RELATION_OPPOSITES:
            mutated[key] = RELATION_OPPOSITES[current]
            yield mutated
        elif key in ('color', 'color1', 'color2'):
            for v in props.get('all_colors', _COLORS):
                if (v or '').lower() != (current or '').lower():
                    mutated[key] = v
                    yield mutated
        elif key in ('shape', 'shape1', 'shape2'):
            for v in props.get('all_shapes', _SHAPES):
                v = v.rstrip('s') if v else v
                cur = (current or '').lower().rstrip('s')
                if v and v.lower() != cur:
                    mutated[key] = v
                    yield mutated
        elif key == 'material':
            for v in props.get('all_materials', _MATERIALS):
                if (v or '').lower() != (current or '').lower():
                    mutated[key] = v
                    yield mutated
        elif key == 'size':
            for v in props.get('all_sizes', _SIZES):
                if (v or '').lower() != (current or '').lower():
                    mutated[key] = v
                    yield mutated


def _semantic_image_cf_pair_passes_pipeline(original_question, cf_question, original_scene, cf_scene):
    """Flip checks for IMAGE_CF_TYPES: both questions flip across images; CF Q must differ from original Q on the original image (rejects commutative / logically equivalent mutations)."""
    if cf_question == original_question:
        return False
    o_o = normalize_answer(answer_question_for_scene(original_question, original_scene))
    o_c = normalize_answer(answer_question_for_scene(original_question, cf_scene))
    c_o = normalize_answer(answer_question_for_scene(cf_question, original_scene))
    c_c = normalize_answer(answer_question_for_scene(cf_question, cf_scene))
    if not (o_o != o_c and c_o != c_c):
        return False
    if c_o == o_o:
        return False
    return True


def _norm_attr_token(v):
    return (v or '').strip().lower().rstrip('s')


def _param_keys_for_semantic_attr(params, attr):
    if not params:
        return []
    if attr == 'color':
        return [k for k in params if k in ('color', 'color1', 'color2')]
    if attr == 'shape':
        return [k for k in params if k in ('shape', 'shape1', 'shape2', 'target_shape', 't_shape')]
    if attr == 'material':
        return [k for k in params if k == 'material']
    if attr == 'size':
        return [k for k in params if k == 'size']
    return []


def _replace_attr_value_in_params(mutated, attr, old_val, new_val):
    """Replace param values matching old_val with new_val for keys tied to attr. Returns whether any key was updated."""
    old_n = _norm_attr_token(old_val)
    new_n = _norm_attr_token(new_val)
    if not old_n or not new_n:
        return False
    keys = _param_keys_for_semantic_attr(mutated, attr)
    replaced = False
    for k in keys:
        if _norm_attr_token(mutated.get(k)) == old_n:
            mutated[k] = new_val.strip().lower().rstrip('s') if attr == 'shape' else new_val.strip().lower()
            replaced = True
    return replaced


def _try_count_cf_questions(original_question, original_scene, cf_scene, orig_objs, cf_objs):
    """add_object / remove_object: count-based questions only."""
    orig_n = len(orig_objs)
    cf_n = len(cf_objs)
    candidates = list(CF_COUNT_QUESTION_TEMPLATES)
    if cf_n > orig_n:
        candidates.extend([
            f"Are there more than {orig_n} objects?",
            f"Are there at least {cf_n} objects?",
        ])
    elif cf_n < orig_n:
        candidates.extend([
            f"Are there fewer than {orig_n} objects?",
            f"Are there more than {cf_n} objects?",
        ])
    for tq in candidates:
        if _semantic_image_cf_pair_passes_pipeline(original_question, tq, original_scene, cf_scene):
            return tq, {}
    return None, None


def generate_question_for_counterfactual(cf_type, original_scene, cf_scene, retry_index=0, original_question=None, original_params=None, original_template=None):
    """IMAGE_CF: minimal .format param mutations on the original template under flip parity; NEGATIVE_CF: first answer-invariant paraphrase from NEGATIVE_TEXT_TEMPLATES."""
    random.seed(hash((str(cf_type), retry_index, str(id(original_scene)), str(id(cf_scene)))))

    if cf_type in NEGATIVE_CF_TYPES and original_question is not None and original_params is not None:
        if not original_template:
            return None, None
        q, p = pick_negative_counterfactual_paraphrase(
            original_template, original_params, original_question, original_scene, cf_scene, retry_index
        )
        if q is not None and p is not None:
            return q, p
        return None, None

    import copy

    orig_objs = _scene_visible_objects(original_scene)
    cf_objs = _scene_visible_objects(cf_scene)

    if cf_type in IMAGE_CF_TYPES and original_question is not None and original_params is not None:
        if not original_template:
            if cf_type in ('add_object', 'remove_object') and _count_fallback_allowed(
                None, original_question
            ):
                tq, tp = _try_count_cf_questions(original_question, original_scene, cf_scene, orig_objs, cf_objs)
                if tq is not None:
                    return tq, tp
            return None, None

        if cf_type in ('add_object', 'remove_object'):
            if _count_fallback_allowed(original_template, original_question):
                tq, tp = _try_count_cf_questions(original_question, original_scene, cf_scene, orig_objs, cf_objs)
                if tq is not None:
                    return tq, tp
        else:
            mutated = copy.deepcopy(original_params)
            applied = False

            if cf_type in ('change_position', 'relational_flip'):
                if mutated.get('relation') in RELATION_OPPOSITES:
                    mutated['relation'] = RELATION_OPPOSITES[mutated['relation']]
                    applied = True

            elif cf_type == 'swap_attribute':
                chg = get_change_details(original_scene, cf_scene)
                if chg and chg.get('attribute') in ('color', 'shape', 'material', 'size'):
                    applied = _replace_attr_value_in_params(mutated, chg['attribute'], chg['orig_val'], chg['cf_val'])
                if not applied:
                    differing = _get_attributes_with_different_counts(original_scene, cf_scene)
                    by_attr = {}
                    for attr, val, o, c in differing:
                        by_attr.setdefault(attr, []).append((val, o, c))
                    for attr, lst in by_attr.items():
                        dec = [x for x in lst if x[1] > x[2]]
                        inc = [x for x in lst if x[2] > x[1]]
                        if len(dec) == 1 and len(inc) == 1:
                            if _replace_attr_value_in_params(mutated, attr, dec[0][0], inc[0][0]):
                                applied = True
                                break

            elif cf_type == 'replace_object':
                chg = get_change_details(original_scene, cf_scene)
                if chg and chg.get('attribute') in ('color', 'shape', 'material', 'size'):
                    applied = _replace_attr_value_in_params(mutated, chg['attribute'], chg['orig_val'], chg['cf_val'])
                    if not applied:
                        applied = _replace_attr_value_in_params(mutated, chg['attribute'], chg['cf_val'], chg['orig_val'])

            elif cf_type in ('change_color', 'change_shape', 'change_material', 'change_size'):
                attr, old_v, new_v = _parse_cf_attribute_change(original_scene, cf_scene)
                if not attr or not old_v or not new_v:
                    chg = get_change_details(original_scene, cf_scene)
                    if chg and chg.get('attribute') in ('color', 'shape', 'material', 'size'):
                        attr, old_v, new_v = chg['attribute'], chg['orig_val'], chg['cf_val']
                if attr and old_v and new_v:
                    applied = _replace_attr_value_in_params(mutated, attr, old_v, new_v)
                    if not applied:
                        applied = _replace_attr_value_in_params(mutated, attr, new_v, old_v)

            if applied:
                try:
                    cf_q = original_template.format(**mutated)
                except (KeyError, ValueError, TypeError):
                    cf_q = None
                if cf_q and _semantic_image_cf_pair_passes_pipeline(original_question, cf_q, original_scene, cf_scene):
                    return cf_q, dict(mutated)

        for mutated_params in _minimal_text_mutations(original_params, original_scene):
            try:
                cf_question = original_template.format(**mutated_params)
            except (KeyError, ValueError, TypeError):
                continue
            if _semantic_image_cf_pair_passes_pipeline(original_question, cf_question, original_scene, cf_scene):
                return cf_question, mutated_params
        return None, None


def _obj_attr_tuple(obj):
    return (
        (obj.get('color') or '').strip().lower(),
        (obj.get('shape') or '').strip().lower().rstrip('s'),
        (obj.get('material') or '').strip().lower(),
        (obj.get('size') or '').strip().lower(),
    )


def _introduced_attrs(original_scene, cf_scene, cf_type):
    """Attribute combo the introducing CF added or changed to, if any."""
    if cf_type not in INTRODUCING_CF_TYPES or not cf_scene:
        return None
    orig_objs = _scene_visible_objects(original_scene)
    cf_objs = _scene_visible_objects(cf_scene)
    orig_set = {_obj_attr_tuple(o) for o in orig_objs}

    if cf_type == 'change_color':
        attr, _old_v, new_v = _parse_cf_attribute_change(original_scene, cf_scene)
        color = (new_v or '').strip().lower() if attr == 'color' else ''
        if not color:
            chg = get_change_details(original_scene, cf_scene)
            if chg and chg.get('attribute') == 'color':
                color = (chg.get('cf_val') or '').strip().lower()
                idx = chg.get('object_index')
            else:
                return None
        else:
            chg = get_change_details(original_scene, cf_scene)
            idx = chg.get('object_index') if chg else None
        shape = None
        if idx is not None and 0 <= idx < len(cf_objs):
            shape = (cf_objs[idx].get('shape') or '').strip().lower().rstrip('s')
        if not color:
            return None
        return {'color': color, 'shape': shape}

    cf_set = {_obj_attr_tuple(o) for o in cf_objs}
    new = cf_set - orig_set
    if not new and cf_type == 'add_object' and len(cf_objs) > len(orig_objs):
        new = {_obj_attr_tuple(cf_objs[-1])}
    if not new:
        return None
    color, shape, material, size = next(iter(new))
    return {'color': color, 'shape': shape, 'material': material, 'size': size}


def _paired_exist_question(rng, original_scene, intro, cf_type=None):
    """Exist/yes-no question that is 'no' on the original because the introduced combo is absent."""
    color = (intro.get('color') or '').strip()
    shape = (intro.get('shape') or '').strip().rstrip('s')
    material = (intro.get('material') or '').strip()
    specs = []
    if color and shape:
        specs.extend([
            ("Is there a {color} {shape}?", {'color': color, 'shape': shape}),
            ("Are there any {color} {shape}s?", {'color': color, 'shape': shape}),
        ])
    if shape:
        specs.extend([
            ("Are there any {shape} objects?", {'shape': shape}),
            ("Are there any {shape}s present?", {'shape': shape}),
        ])
    if material and shape:
        specs.append(("Is there a {material} {shape}?", {'material': material, 'shape': shape}))
    if material and color:
        specs.append(("Are there any objects that are either {material} or {color}?", {'material': material, 'color': color}))
    rng.shuffle(specs)
    for template, params in specs:
        if cf_type and not semantic_cf_type_allowed_for_template(cf_type, template):
            continue
        try:
            question = template.format(**params)
        except (KeyError, ValueError, TypeError):
            continue
        if not original_question_single_ref_valid(template, params, original_scene):
            continue
        ans = normalize_answer(answer_question_for_scene(question, original_scene))
        if ans == 'no':
            return question, params, template
    return None


class AcceptanceQuotas:
    """Keep original yes/no near 50% and cap any count value at 25% of count rows."""

    def __init__(self, count_cap=0.25, min_count_cap=3):
        self.n_yes = 0
        self.n_no = 0
        self.n_count = 0
        self.count_values = {}
        self.count_cap = count_cap
        self.min_count_cap = min_count_cap

    def allow(self, answer_type, original_answer):
        a = normalize_answer(original_answer)
        if answer_type == 'yes/no':
            if a == 'yes':
                return self.n_yes <= self.n_no
            if a == 'no':
                return self.n_no <= self.n_yes
            return True
        if answer_type == 'count':
            next_n = self.n_count + 1
            next_c = self.count_values.get(a, 0) + 1
            cap = max(self.min_count_cap, math.ceil(self.count_cap * next_n))
            return next_c <= cap
        return True

    def record(self, answer_type, original_answer):
        a = normalize_answer(original_answer)
        if answer_type == 'yes/no':
            if a == 'yes':
                self.n_yes += 1
            elif a == 'no':
                self.n_no += 1
        elif answer_type == 'count':
            self.n_count += 1
            self.count_values[a] = self.count_values.get(a, 0) + 1

    def snapshot(self):
        return {
            'n_yes': self.n_yes,
            'n_no': self.n_no,
            'n_count': self.n_count,
            'count_values': dict(self.count_values),
        }


def _new_acceptance_stats():
    return {
        'attempts': 0,
        'accepted': 0,
        'reject_reasons': {},
        'quota_rejects': 0,
        'quota_fallbacks': 0,
        'precheck_attempts': 0,
        'precheck_accepted': 0,
        'precheck_failed_draws': 0,
        'mapping_attempts': 0,
        'mapping_accepted': 0,
        'quota_snapshot': {},
        'instrumented': True,
    }


_ACCEPTANCE_STATS = _new_acceptance_stats()
_PRECHECK_QUOTA = AcceptanceQuotas()


def reset_acceptance_stats():
    global _ACCEPTANCE_STATS, _PRECHECK_QUOTA
    _ACCEPTANCE_STATS = _new_acceptance_stats()
    _PRECHECK_QUOTA = AcceptanceQuotas()


def _bump_reject(reason):
    reasons = _ACCEPTANCE_STATS.setdefault('reject_reasons', {})
    reasons[reason] = reasons.get(reason, 0) + 1


def write_acceptance_stats(run_dir, mapping_quota=None, verbose=True):
    payload = dict(_ACCEPTANCE_STATS)
    payload['precheck_quota_snapshot'] = _PRECHECK_QUOTA.snapshot()
    if mapping_quota is not None:
        payload['mapping_quota_snapshot'] = mapping_quota.snapshot()
        payload['quota_snapshot'] = mapping_quota.snapshot()
    else:
        payload['quota_snapshot'] = _PRECHECK_QUOTA.snapshot()
    precheck_attempts = int(payload.get('precheck_attempts') or 0)
    mapping_attempts = int(payload.get('mapping_attempts') or 0)
    accepted = int(payload.get('accepted') or payload.get('mapping_accepted') or 0)
    attempts = precheck_attempts or mapping_attempts
    payload['attempts'] = attempts
    payload['accepted'] = accepted
    payload['acceptance_rate'] = (accepted / attempts) if attempts else None
    payload['triplets_attempted_per_kept'] = (attempts / accepted) if accepted else None
    path = os.path.join(run_dir, 'acceptance_stats.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, indent=2)
    if verbose:
        print(f'[OK] Wrote acceptance stats: {path}')
    return path


def generate_question_for_scene(scene_file, retry_index=None, cf_scene=None, cf_type=None):
    """Sample one VQA template for a scene JSON; returns (question, params, template_string).

    Diversity-preserving version. Three changes from the legacy implementation:
      1. Uses a LOCAL random.Random instance instead of seeding the global RNG.
         The legacy version called random.seed(hash(scene_file)) which (a) made
         downstream calls in this module deterministic in surprising ways and
         (b) baked one parameter set per template at function entry.
      2. Each template carries a params *factory* that resamples parameters on
         every call. So when a template is rejected by the validity check
         because of unlucky params (e.g. "How many red objects?" in a scene
         with no red), retrying that template can now succeed with new params
         instead of being doomed to fail forever.
      3. The fallback path no longer collapses every difficult scene onto
         templates[0] ("How many objects are in the scene?"). Instead it
         shuffles the template list and tries each template with several
         fresh param rolls. Only if every template fails does it return the
         universal count question. In the legacy version this collapse was
         responsible for ~10% of all rows being identical.
    """
    scene = load_scene(scene_file)
    objects = _scene_visible_objects(scene)

    if len(objects) == 0:
        return "How many objects are in the scene?", {}, "How many objects are in the scene?"

    props = get_scene_properties(scene)

    # Local RNG -- reproducible per (scene_file, retry_index) without polluting global state.
    seed = hash((scene_file, retry_index)) if retry_index is not None else hash(scene_file)
    rng = random.Random(seed)

    # Absent yes/no exist questions only survive if an introducing CF can flip no→yes.
    if cf_type in INTRODUCING_CF_TYPES and cf_scene is not None and rng.random() < 0.5:
        intro = _introduced_attrs(scene, cf_scene, cf_type)
        if intro:
            paired = _paired_exist_question(rng, scene, intro, cf_type=cf_type)
            if paired is not None:
                return paired

    # force_absent is False: non-introducing CFs must not sample absent exist targets.
    template_specs = [
        ("How many objects are in the scene?", lambda r: {}),
        ("How many {color} objects are there?", lambda r: {'color': r.choice(props['colors'])}),
        ("Are there any {shape} objects?", lambda r: {
            'shape': _pick_exist_value(r, props['shapes'], props['all_shapes'], False)
        }),
        ("Are there any {shape}s present?", lambda r: {
            'shape': _pick_exist_value(r, props['shapes'], props['all_shapes'], False)
        }),
        ("Is there a {color} {shape}?", lambda r: _pick_exist_combo(
            r, objects, ('color', 'shape'),
            (props['all_colors'], [s.rstrip('s') for s in props['all_shapes']]),
            False
        )),
        ("How many {material} objects are there?", lambda r: {'material': r.choice(props['materials'])}),
        ("What is the total number of {material} objects?", lambda r: {'material': r.choice(props['materials'])}),
        ("What is the total number of metallic objects?", lambda r: {}),
        ("What is the total number of {size} objects?", lambda r: {'size': r.choice(props['sizes'])}),
        ("Is there a {material} {shape}?", lambda r: _pick_exist_combo(
            r, objects, ('material', 'shape'),
            (props['all_materials'], [s.rstrip('s') for s in props['all_shapes']]),
            False
        )),
        ("How many {size} {color} objects are there?", lambda r: {
            'size': r.choice(props['sizes']),
            'color': r.choice(props['colors'])
        }),
        ("Are there any {color} {shape}s?", lambda r: _pick_exist_combo(
            r, objects, ('color', 'shape'),
            (props['all_colors'], [s.rstrip('s') for s in props['all_shapes']]),
            False
        )),
        ("What is the total number of {color} {material} objects?", lambda r: {
            'color': r.choice(props['colors']),
            'material': r.choice(props['materials'])
        }),
        ("What color is the object {relation} the {color} {shape}?", lambda r: {
            'relation': r.choice(props['relations']),
            'color': r.choice(props['colors']),
            'shape': r.choice(props['shapes'])
        }),
        ("What shape is the object {relation} the {material} object?", lambda r: {
            'relation': r.choice(props['relations']),
            'material': r.choice(props['materials'])
        }),
        ("What material is the {size} object {relation} the {shape}?", lambda r: {
            'size': r.choice(props['sizes']),
            'relation': r.choice(props['relations']),
            'shape': r.choice(props['shapes'])
        }),
        ("How many objects are {relation} the {color} {shape}?", lambda r: {
            'relation': r.choice(props['relations']),
            'color': r.choice(props['colors']),
            'shape': r.choice(props['shapes'])
        }),
        ("How many {material} objects are {relation} the {shape}?", lambda r: {
            'material': r.choice(props['materials']),
            'relation': r.choice(props['relations']),
            'shape': r.choice(props['shapes'])
        }),
        ("What is the total number of {size} objects {relation} the {color} object?", lambda r: {
            'size': r.choice(props['sizes']),
            'relation': r.choice(props['relations']),
            'color': r.choice(props['colors'])
        }),
        ("Is there a {color} object {relation} the {shape}?", lambda r: {
            'color': _pick_exist_value(r, props['colors'], props['all_colors'], False),
            'relation': r.choice(props['relations']),
            'shape': r.choice(props['shapes'])
        }),
        ("Are there any {material} {shape}s {relation} the {size} object?", lambda r: {
            **_pick_exist_combo(
                r, objects, ('material', 'shape'),
                (props['all_materials'], [s.rstrip('s') for s in props['all_shapes']]),
                False
            ),
            'relation': r.choice(props['relations']),
            'size': r.choice(props['sizes'])
        }),
        ("Is the color of the {shape1} the same as the {shape2}?", lambda r: dict(zip(
            ['shape1', 'shape2'],
            r.sample(props['shapes'], 2) if len(props['shapes']) >= 2 else [props['shapes'][0]] * 2
        ))),
        ("Is the material of the {color} object the same as the {size} object?", lambda r: {
            'color': r.choice(props['colors']),
            'size': r.choice(props['sizes'])
        }),
        ("Do the {size} object and the {material} object have the same shape?", lambda r: {
            'size': r.choice(props['sizes']),
            'material': r.choice(props['materials'])
        }),
        ("How many objects are either {color} or {shape}?", lambda r: {
            'color': r.choice(props['colors']),
            'shape': r.choice(props['shapes'])
        }),
        ("Are there any objects that are either {material} or {color}?", lambda r: _pick_exist_either_material_color(
            r, props, False
        )),
        ("What is the total number of objects that are either {size} or {shape}?", lambda r: {
            'size': r.choice(props['sizes']),
            'shape': r.choice(props['shapes'])
        }),
        ("Is the number of {color} objects equal to the number of {shape}s?", lambda r: {
            'color': r.choice(props['colors']),
            'shape': r.choice(props['shapes'])
        }),
        ("Are there exactly as many {material} objects as {size} objects?", lambda r: {
            'material': r.choice(props['materials']),
            'size': r.choice(props['sizes'])
        }),
        ("Does the scene contain an equal number of {color1} objects and {color2} objects?", lambda r: dict(zip(
            ['color1', 'color2'],
            r.sample(props['colors'], 2) if len(props['colors']) >= 2 else [props['colors'][0]] * 2
        ))),
        ("What is the total number of {material} objects {relation} the {color} {shape}?", lambda r: {
            'material': r.choice(props['materials']),
            'relation': r.choice(props['relations']),
            'color': r.choice(props['colors']),
            'shape': r.choice(props['shapes'])
        }),
        ("Is there a {size} {material} object {relation} the {shape}?", lambda r: {
            **_pick_exist_combo(
                r, objects, ('size', 'material'),
                (props['all_sizes'], props['all_materials']),
                False
            ),
            'relation': r.choice(props['relations']),
            'shape': r.choice(props['shapes'])
        }),
    ]

    matte_shiny_objects = [
        o for o in objects
        if (o.get('material') or '').lower() in ('metal', 'rubber')
        and o.get('color') and o.get('shape')
    ]
    if matte_shiny_objects:
        def _matte_shiny_params(r, _objs=matte_shiny_objects):
            obj = r.choice(_objs)
            return {'color': obj.get('color'), 'shape': obj.get('shape')}
        template_specs.append(("Is the {color} {shape} matte or shiny?", _matte_shiny_params))

    def _try_once(template, param_fn):
        try:
            params = param_fn(rng)
        except (IndexError, ValueError):
            return None
        if not original_question_single_ref_valid(template, params, scene):
            return None
        try:
            question = template.format(**params) if params else template
        except (KeyError, ValueError, TypeError):
            return None
        return question, params

    # Enumerate viable (template, params) combinations: try each template up
    # to PARAM_ATTEMPTS_PER_TEMPLATE times with FRESH params on each attempt,
    # and record the FIRST successful (question, params) for each template
    # that has any viable params at all.
    #
    # Then sample uniformly from this set of viable templates. This is the
    # crucial difference vs the legacy algorithm: random.choice over ALL
    # templates is biased toward templates that always pass validity (the
    # parameter-free count templates), causing them to dominate when scenes
    # have many failing validity checks. Sampling over viable templates only
    # gives every viable template equal probability regardless of how many
    # of its sibling templates failed.
    PARAM_ATTEMPTS_PER_TEMPLATE = 6
    candidates = []
    for template, param_fn in template_specs:
        for _ in range(PARAM_ATTEMPTS_PER_TEMPLATE):
            result = _try_once(template, param_fn)
            if result is not None:
                question, params = result
                candidates.append((question, params, template))
                break  # one viable params roll per template is enough

    if candidates:
        return rng.choice(candidates)

    # Absolute last resort: every template failed validity for this scene.
    # The parameter-free count question is always valid for non-empty scenes.
    template = "How many objects are in the scene?"
    return template, {}, template


# Canonical-template -> reasoning-operation tag, GQA-style.
# Tags use dotted notation: <primary>[.<modifier>]*
# Primary ops:
#   count                    - returns a number
#   exist                    - yes/no on whether matching objects exist
#   query.color              - returns a color value
#   query.shape              - returns a shape value
#   query.material           - returns a material value
#   query.material_binary    - returns matte/shiny (CLEVR convention)
#   compare.attribute        - yes/no on whether two attribute values match
#   compare.count            - yes/no on whether two counts are equal
# Modifiers (appended in canonical order: filter, relate, logical_or):
#   filter                   - has attribute predicates (color, shape, etc.)
#   relate                   - involves spatial relation between objects
#   logical_or               - involves OR composition of predicates
TEMPLATE_REASONING_OPS = {
    # Pure count
    "How many objects are in the scene?":                                                          "count",
    "What is the total number of objects in the scene?":                                           "count",
    # Count with implicit material filter (CLEVR's "metallic" alias for metal)
    "What is the total number of metallic objects?":                                               "count.filter",
    # Count with explicit single filter
    "How many {color} objects are there?":                                                         "count.filter",
    "How many {material} objects are there?":                                                      "count.filter",
    "What is the total number of {material} objects?":                                             "count.filter",
    "What is the total number of {size} objects?":                                                 "count.filter",
    # Count with multiple filters
    "How many {size} {color} objects are there?":                                                  "count.filter",
    "What is the total number of {color} {material} objects?":                                     "count.filter",
    # Exist
    "Are there any {shape} objects?":                                                              "exist.filter",
    "Are there any {shape}s present?":                                                             "exist.filter",
    "Is there a {color} {shape}?":                                                                 "exist.filter",
    "Is there a {material} {shape}?":                                                              "exist.filter",
    "Are there any {color} {shape}s?":                                                             "exist.filter",
    # Query material binary (CLEVR's matte/shiny convention)
    "Is the {color} {shape} matte or shiny?":                                                      "query.material_binary",
    # Query attribute via spatial relation
    "What color is the object {relation} the {color} {shape}?":                                   "query.color.relate",
    "What shape is the object {relation} the {material} object?":                                 "query.shape.relate",
    "What material is the {size} object {relation} the {shape}?":                                 "query.material.relate",
    # Count with relation
    "How many objects are {relation} the {color} {shape}?":                                       "count.relate",
    "How many {material} objects are {relation} the {shape}?":                                    "count.filter.relate",
    "What is the total number of {size} objects {relation} the {color} object?":                  "count.filter.relate",
    "What is the total number of {material} objects {relation} the {color} {shape}?":             "count.filter.relate",
    # Exist with relation
    "Is there a {color} object {relation} the {shape}?":                                          "exist.filter.relate",
    "Are there any {material} {shape}s {relation} the {size} object?":                            "exist.filter.relate",
    "Is there a {size} {material} object {relation} the {shape}?":                                "exist.filter.relate",
    # Compare attribute values
    "Is the color of the {shape1} the same as the {shape2}?":                                     "compare.attribute",
    "Is the material of the {color} object the same as the {size} object?":                       "compare.attribute",
    "Do the {size} object and the {material} object have the same shape?":                        "compare.attribute",
    # Logical OR
    "How many objects are either {color} or {shape}?":                                            "count.filter.logical_or",
    "Are there any objects that are either {material} or {color}?":                               "exist.filter.logical_or",
    "What is the total number of objects that are either {size} or {shape}?":                     "count.filter.logical_or",
    # Compare counts
    "Is the number of {color} objects equal to the number of {shape}s?":                          "compare.count",
    "Are there exactly as many {material} objects as {size} objects?":                            "compare.count",
    "Does the scene contain an equal number of {color1} objects and {color2} objects?":           "compare.count",
}


def calculate_question_difficulty(question, params, template=None):
    """Return a GQA-style reasoning-operation tag for the question.

    Replaces the previous easy/medium/hard heuristic, which (a) was never
    calibrated against actual model performance and (b) special-cased a few
    string patterns inconsistently (e.g. "matte or shiny" was hardcoded as
    hard while "either small or cube" was routed through param-count).

    Reasoning-operation tags are the standard taxonomy used by GQA and
    follow-up VQA benchmarks. They're descriptive (each tag names what
    skill the question tests) rather than prescriptive (claiming a difficulty
    ordering that hasn't been empirically validated). Downstream analysis
    can group by primary op (everything starting with 'count.') or filter
    by modifier (everything containing '.relate') to get per-skill breakdowns
    without committing to a difficulty ranking.

    Tag format: <primary>[.<modifier>]* in dotted notation.

    Args:
        question: the rendered question string (used as fallback when
            `template` is unavailable, e.g. for paraphrased CFs).
        params: question parameters dict, used to detect filter modifiers.
        template: canonical template string (optional). When provided and
            recognized, returns the precomputed tag from TEMPLATE_REASONING_OPS
            without any string parsing. Pass this whenever you have it.

    Examples:
        "How many objects?"                          -> "count"
        "How many red cubes?"                        -> "count.filter"
        "How many objects left of the cube?"         -> "count.relate"
        "How many red objects left of the cube?"     -> "count.filter.relate"
        "Is there a red sphere?"                     -> "exist.filter"
        "What color is the object left of the cube?" -> "query.color.relate"
        "Is the color of X the same as Y?"           -> "compare.attribute"
        "How many objects are red or sphere?"        -> "count.filter.logical_or"
    """
    # Fast path: canonical template hits the lookup table.
    if template and template in TEMPLATE_REASONING_OPS:
        return TEMPLATE_REASONING_OPS[template]

    # Fallback: parse the question text. Used when template is None or the
    # template was rewritten by create_counterfactual_questions paraphrasing.
    q = (question or "").lower()

    # Determine primary operation. Order matters: comparison phrases must be
    # checked before "how many" because compare.count contains "number of".
    if "matte or shiny" in q:
        primary = "query.material_binary"
    elif (("color of" in q or "material of" in q) and ("same as" in q or "the same" in q)):
        primary = "compare.attribute"
    elif "have the same shape" in q or "the same shape" in q:
        primary = "compare.attribute"
    elif ("equal number" in q or "exactly as many" in q
          or ("number of" in q and "equal to" in q)):
        primary = "compare.count"
    elif q.startswith("how many") or "total number" in q or "count of" in q:
        primary = "count"
    elif (q.startswith("are there") or q.startswith("is there")
          or q.startswith("does the scene contain") or q.startswith("do ")):
        primary = "exist"
    elif "what color" in q:
        primary = "query.color"
    elif "what shape" in q:
        primary = "query.shape"
    elif "what material" in q:
        primary = "query.material"
    elif "what size" in q:
        primary = "query.size"
    else:
        primary = "unknown"

    modifiers = []

    # filter: any non-relation params, OR detect implicit filter keywords in
    # the question text (covers paraphrases that don't have params attached).
    has_filter = bool(params) and any(k != "relation" for k in params.keys())
    if not has_filter:
        filter_keywords = (
            "red", "blue", "green", "yellow", "purple", "gray", "brown", "cyan",
            "cube", "sphere", "cylinder", "metal", "rubber", "metallic",
            "small", "large", "matte", "shiny",
        )
        has_filter = any(kw in q for kw in filter_keywords)
    if has_filter and primary in ("count", "exist"):
        modifiers.append("filter")

    # relate: spatial-relation phrases.
    if any(rel in q for rel in ("left of", "right of", "behind", "in front of")):
        modifiers.append("relate")

    # logical_or: OR composition. Strip the matte/shiny disjunction first
    # since that's already captured by query.material_binary.
    q_no_matteshiny = q.replace("matte or shiny", "")
    if "either" in q_no_matteshiny or " or " in q_no_matteshiny:
        if "logical_or" not in modifiers:
            modifiers.append("logical_or")

    if modifiers:
        return primary + "." + ".".join(modifiers)
    return primary

def _apply_param_replacements(question, params, cf_params):
    """Replace placeholder values in order of first occurrence, applying edits from end to start so spans stay valid when values repeat."""
    if not params or not cf_params:
        return question
    positions = []
    for k, v in params.items():
        if k not in cf_params or cf_params[k] == v:
            continue
        pos = question.find(v)
        if pos >= 0:
            positions.append((pos, k, v, cf_params[k]))
    positions.sort(key=lambda x: -x[0])
    for pos, k, old_val, new_val in positions:
        question = question[:pos] + new_val + question[pos + len(old_val):]
    return question


def create_counterfactual_questions(original_question, params, scene):
    """Legacy text CF generator: two random strategies producing alternate wordings from the same scene graph."""
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
                q = original_question
                q_lower = q.lower()
                if "the same as" in q_lower or "same shape" in q_lower or "same color" in q_lower or "same material" in q_lower:
                    if random.choice([True, False]) and params:
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
                q_lower = original_question.lower()
                if "either" in q_lower and " or " in q_lower and params:
                    if random.choice([True, False]):
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
                        cf_q = original_question.replace("either", "both").replace(" or ", " and ")
                        cf_params = params.copy() if params else {}
                else:
                    cf_q = None

            elif strategy == 'equal_comparison':
                q = original_question
                q_lower = q.lower()
                if ("equal to" in q_lower or "exactly as many" in q_lower or "equal number" in q_lower) and params:
                    if random.choice([True, False]):
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

            if cf_q and cf_q.strip() != original_question.strip():
                if not cf_params:
                    cf_params = {}
                break
            
            retry_count += 1
            if retry_count < max_retries:
                available_strategies = [s for s in strategies if s != strategy]
                if available_strategies:
                    strategy = random.choice(available_strategies)
                else:
                    strategy = 'negation'
        
        if cf_q is None or cf_q.strip() == original_question.strip():
            continue

        cf_questions.append((cf_q, cf_params or {}))
    
    return cf_questions


def normalize_answer(a):
    """Lowercase stripped string for answer comparison; None becomes empty."""
    if a is None:
        return ""
    return str(a).strip().lower()


UNRESOLVED_ANSWER_TOKENS = frozenset({'', 'unknown', 'not found', 'none'})


def _is_unresolved_answer(a):
    return normalize_answer(a) in UNRESOLVED_ANSWER_TOKENS


def answer_question_for_scene(question, scene):
    """Deterministic VQA over scene JSON: specialized parsers for relational, counting, and compositional templates, then CLEVR-style fallbacks."""
    objects = _scene_visible_objects(scene)
    full_objects = scene.get('objects', [])
    question_lower = question.lower()

    def _str_answer(val):
        if val is None:
            return "unknown"
        return str(val).strip().lower()

    # Relational yes/no: use 2D projected coords (not adjacency lists) so left/right/front/behind match camera-fixed geometry.
    if question_lower.startswith("is the"):
        for phrase, rel_key in PHRASES_TO_RELATION_KEYS.items():
            if phrase in question_lower:
                before, _, after = question_lower.partition(phrase)
                a_color = _first_value_in_question(before, _COLORS)
                a_shape = _first_value_in_question(before, _SHAPES)
                a_mat = _first_value_in_question(before, _MATERIALS)
                a_size = _first_value_in_question(before, _SIZES, strip_s=False)
                cand_a = _find_objects_matching(objects, color=a_color, shape=a_shape, material=a_mat, size=a_size)
                b_color = _first_value_in_question(after, _COLORS)
                b_shape = _first_value_in_question(after, _SHAPES)
                b_mat = _first_value_in_question(after, _MATERIALS)
                b_size = _first_value_in_question(after, _SIZES, strip_s=False)
                cand_b = _find_objects_matching(objects, color=b_color, shape=b_shape, material=b_mat, size=b_size)
                if not cand_a or not cand_b:
                    return _str_answer("unknown")
                a = objects[cand_a[0]] or {}
                b = objects[cand_b[0]] or {}
                ca = (a.get('3d_coords') or [])[:2]
                cb = (b.get('3d_coords') or [])[:2]
                if len(ca) < 2 or len(cb) < 2:
                    return _str_answer("unknown")
                ax, ay = ca
                bx, by = cb
                eps = 1e-4
                if phrase == 'left of':
                    cond = ax < bx - eps
                elif phrase == 'right of':
                    cond = ax > bx + eps
                elif phrase == 'in front of':
                    cond = ay < by - eps
                elif phrase == 'behind':
                    cond = ay > by + eps
                else:
                    cond = False
                return _str_answer("yes" if cond else "no")

    # Nearest-neighbor identity (Euclidean 3D); front/behind uses -y as view axis in relational branch above.
    if "closest to the" in question_lower:
        _, _, tail = question_lower.partition("closest to the")
        t_color = _first_value_in_question(tail, _COLORS)
        t_shape = _first_value_in_question(tail, _SHAPES)
        t_mat = _first_value_in_question(tail, _MATERIALS)
        t_size = _first_value_in_question(tail, _SIZES, strip_s=False)
        cand_t = _find_objects_matching(objects, color=t_color, shape=t_shape, material=t_mat, size=t_size)
        if not cand_t:
            return _str_answer("unknown")
        t_idx = cand_t[0]
        t_coords = objects[t_idx].get('3d_coords') or []
        if len(t_coords) < 3:
            return _str_answer("unknown")
        tx, ty, tz = t_coords[:3]
        best_idx = None
        best_d2 = None
        for i, obj in enumerate(objects):
            if i == t_idx:
                continue
            coords = obj.get('3d_coords') or []
            if len(coords) < 3:
                continue
            x, y, z = coords[:3]
            d2 = (x - tx) ** 2 + (y - ty) ** 2 + (z - tz) ** 2
            if best_d2 is None or d2 < best_d2:
                best_d2 = d2
                best_idx = i
        if best_idx is None:
            return _str_answer("unknown")
        neigh_color = (objects[best_idx].get('color') or '').lower()
        return _str_answer(neigh_color if neigh_color else "unknown")

    # Shiny/matte → metal/rubber disambiguation for single-object color queries.
    if question_lower.startswith("what color is the") and ("shiny" in question_lower or "matte" in question_lower):
        mat = None
        if "shiny" in question_lower:
            mat = "metal"
        elif "matte" in question_lower:
            mat = "rubber"
        target_shape = _first_value_in_question(question_lower, _SHAPES)
        cand = _find_objects_matching(objects, shape=target_shape, material=mat)
        if not cand:
            return _str_answer("unknown")
        obj = objects[cand[0]] or {}
        color = (obj.get('color') or '').lower()
        return _str_answer(color if color else "unknown")

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
        elif "same material" in question_lower or ("material" in question_lower and "same" in question_lower):
            attr = 'material'
            cand1 = _find_objects_matching(objects, color=color1) if color1 else []
            cand2 = _find_objects_matching(objects, size=size1) if size1 else []
        elif "color of" in question_lower or ("same as" in question_lower and shape1):
            attr = 'color'
            cand1 = _find_objects_matching(objects, shape=shape1.rstrip('s') if shape1 else None) if shape1 else []
            cand2 = _find_objects_matching(objects, shape=shape2) if shape2 else []
        elif "same color" in question_lower or ("color" in question_lower and "same" in question_lower):
            attr = 'color'
            cand1 = _find_objects_matching(objects, shape=shape1.rstrip('s') if shape1 else None) if shape1 else []
            cand2 = _find_objects_matching(objects, shape=shape2) if shape2 else []
        elif "same size" in question_lower or ("size" in question_lower and "same" in question_lower):
            attr = 'size'
            cand1 = _find_objects_matching(objects, color=color1) if color1 else []
            cand2 = _find_objects_matching(objects, size=size1) if size1 else []
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
            matched = []
            for idx in in_rel:
                if idx >= len(full_objects):
                    continue
                o = full_objects[idx]
                if filter_color and (o.get('color') or '').lower() != filter_color.rstrip('s'):
                    continue
                if filter_shape and (o.get('shape') or '').lower() != filter_shape.rstrip('s'):
                    continue
                if filter_material and (o.get('material') or '').lower() != filter_material.rstrip('s'):
                    continue
                if filter_size and (o.get('size') or '').lower() != filter_size:
                    continue
                filtered += 1
                matched.append(idx)
            if "how many" in question_lower or "total number" in question_lower:
                return _str_answer(str(filtered))
            if "is there a" in question_lower or "are there any" in question_lower:
                return _str_answer("yes" if filtered > 0 else "no")
            if matched:
                preamble = before_rel
                target = full_objects[matched[0]] if matched[0] < len(full_objects) else {}
                if "color" in preamble:
                    return _str_answer((target.get('color') or 'unknown').lower())
                if "shape" in preamble:
                    return _str_answer((target.get('shape') or 'unknown').lower())
                if "material" in preamble:
                    return _str_answer((target.get('material') or 'unknown').lower())
                if "size" in preamble:
                    return _str_answer((target.get('size') or 'unknown').lower())
            elif question_lower.startswith("what"):
                return _str_answer("unknown")
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

    if question_lower.startswith("how many") and "either" in question_lower and " or " in question_lower:
        _, _, tail = question_lower.partition("either")
        left, _, right = tail.partition(" or ")
        right = right.replace("?", "").strip()

        def _parse_token(phrase):
            phrase = (phrase or "").strip()
            for c in _COLORS:
                base = c.rstrip('s')
                if re.search(r'\b' + re.escape(base) + r's?\b', phrase):
                    return ('color', base)
            for s in _SHAPES:
                base = s.rstrip('s')
                if re.search(r'\b' + re.escape(base) + r's?\b', phrase):
                    return ('shape', base)
            for m in _MATERIALS:
                base = m.rstrip('s')
                if re.search(r'\b' + re.escape(base) + r's?\b', phrase):
                    return ('material', base)
            for z in _SIZES:
                if re.search(r'\b' + re.escape(z) + r'\b', phrase):
                    return ('size', z)
            return (None, None)

        k1, v1 = _parse_token(left)
        k2, v2 = _parse_token(right)
        if k1 and k2:
            count = 0
            for o in objects:
                o_color = (o.get('color') or '').lower()
                o_shape = (o.get('shape') or '').lower()
                o_material = (o.get('material') or '').lower()
                o_size = (o.get('size') or '').lower()

                m1 = (
                    (k1 == 'color' and o_color == v1)
                    or (k1 == 'shape' and o_shape == v1)
                    or (k1 == 'material' and o_material == v1)
                    or (k1 == 'size' and o_size == v1)
                )
                m2 = (
                    (k2 == 'color' and o_color == v2)
                    or (k2 == 'shape' and o_shape == v2)
                    or (k2 == 'material' and o_material == v2)
                    or (k2 == 'size' and o_size == v2)
                )
                if m1 or m2:
                    count += 1
            return _str_answer(str(count))

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
            if any(p in question_lower for p in PHRASES_TO_RELATION_KEYS):
                return _str_answer("unknown")
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
    """Count objects whose attributes match color/shape/material/size tokens inferred from the lowered question string."""
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
    """Label 'Semantic-Valid' vs 'Negative-Valid' from whether the same question flips answers across paired scene graphs."""
    answer_base = answer_question_for_scene(question, base_scene_graph)
    answer_cf = answer_question_for_scene(question, counterfactual_scene_graph)
    norm_base = normalize_answer(answer_base)
    norm_cf = normalize_answer(answer_cf)
    if norm_base != norm_cf:
        return 'Semantic-Valid'
    return 'Negative-Valid'


def precheck_dual_cf_questions_viable(
    original_scene,
    cf1_scene,
    cf2_scene,
    *,
    scene_index=0,
    strict_question_validation=True,
    enforce_cf_question_group=True,
    max_retries=None,
):
    """
    Return (True, None) if some original + cf1 + cf2 question triple passes the same rejection
    sampling used when building image_mapping_with_questions.csv (dual-CF rows).

    Writes temporary JSON so generate_question_for_scene (path-based) can run unchanged.
    Keep logic aligned with generate_mapping_with_questions (dual-CF branch).
    """
    mr = max_retries if max_retries is not None else MAX_CF_ANSWER_RETRIES
    scene_key = f'{int(scene_index):04d}'
    idx = int(scene_index)

    try:
        with tempfile.TemporaryDirectory(prefix='mmb_cf_precheck_') as tmp:
            orig_path = os.path.join(tmp, 'original.json')
            cf1_path = os.path.join(tmp, 'cf1.json')
            cf2_path = os.path.join(tmp, 'cf2.json')
            with open(orig_path, 'w', encoding='utf-8') as fo:
                json.dump(original_scene, fo)
            with open(cf1_path, 'w', encoding='utf-8') as f1:
                json.dump(cf1_scene, f1)
            with open(cf2_path, 'w', encoding='utf-8') as f2:
                json.dump(cf2_scene, f2)

            try:
                original_scene_d = load_scene(orig_path)
                cf1_scene_d = load_scene(cf1_path)
                cf2_scene_d = load_scene(cf2_path)
            except Exception:
                return False, 'failed to load temp scene JSON'

            try:
                cf1_type = get_cf_type_from_scene(cf1_scene_d)
                cf2_type = get_cf_type_from_scene(cf2_scene_d)
            except Exception:
                return False, 'failed to read cf_metadata from counterfactual scenes'

            for cf_retry in range(mr):
                _ACCEPTANCE_STATS['attempts'] += 1
                _ACCEPTANCE_STATS['precheck_attempts'] += 1
                try:
                    original_question, params, original_template = generate_question_for_scene(
                        orig_path, retry_index=cf_retry, cf_scene=cf1_scene_d, cf_type=cf1_type
                    )
                    if not original_question_single_ref_valid(original_template, params, original_scene_d):
                        _bump_reject('orig_q_invalid')
                        continue
                    if enforce_cf_question_group:
                        if cf1_type in IMAGE_CF_TYPES and not semantic_cf_type_allowed_for_template(cf1_type, original_template):
                            _bump_reject('cf1_template_group')
                            continue
                        if cf2_type in IMAGE_CF_TYPES and not semantic_cf_type_allowed_for_template(cf2_type, original_template):
                            _bump_reject('cf2_template_group')
                            continue
                    original_ans_orig_q = answer_question_for_scene(original_question, original_scene_d)
                    random.seed(hash((scene_key, idx, cf_retry)))
                    cf_questions = (
                        create_counterfactual_questions(original_question, params, original_scene_d)
                        if (not cf1_type or not cf2_type)
                        else None
                    )
                    if cf1_type:
                        cf1_question, cf1_params = generate_question_for_counterfactual(
                            cf1_type,
                            original_scene_d,
                            cf1_scene_d,
                            retry_index=cf_retry,
                            original_question=original_question,
                            original_params=params,
                            original_template=original_template,
                        )
                        if cf1_question is None or cf1_params is None:
                            _bump_reject('cf1_question_none')
                            continue
                    else:
                        if not cf_questions or len(cf_questions) == 0:
                            _bump_reject('cf_questions_empty')
                            continue
                        cf1_question, cf1_params = cf_questions[0]
                    if cf2_type:
                        cf2_question, cf2_params = generate_question_for_counterfactual(
                            cf2_type,
                            original_scene_d,
                            cf2_scene_d,
                            retry_index=cf_retry,
                            original_question=original_question,
                            original_params=params,
                            original_template=original_template,
                        )
                        if cf2_question is None or cf2_params is None:
                            _bump_reject('cf2_question_none')
                            continue
                    else:
                        if not cf_questions:
                            _bump_reject('cf_questions_empty')
                            continue
                        if len(cf_questions) > 1:
                            cf2_question, cf2_params = cf_questions[1]
                        else:
                            cf2_question, cf2_params = cf_questions[0]
                    if "matte or shiny" in (original_question or "").lower() and (
                        cf1_type in ("add_object", "remove_object")
                        or cf2_type in ("add_object", "remove_object")
                    ):
                        _bump_reject('matte_shiny_add_remove')
                        continue
                except Exception:
                    _bump_reject('exception_sample')
                    continue

                try:
                    calculate_question_difficulty(original_question, params)
                    calculate_question_difficulty(cf1_question, cf1_params)
                    calculate_question_difficulty(cf2_question, cf2_params)
                except Exception:
                    _bump_reject('difficulty')
                    continue

                try:
                    original_ans_cf1_q = answer_question_for_scene(cf1_question, original_scene_d)
                    original_ans_cf2_q = answer_question_for_scene(cf2_question, original_scene_d)
                    cf1_ans_orig_q = answer_question_for_scene(original_question, cf1_scene_d)
                    cf1_ans_cf1_q = answer_question_for_scene(cf1_question, cf1_scene_d)
                    cf1_ans_cf2_q = answer_question_for_scene(cf2_question, cf1_scene_d)
                    cf2_ans_orig_q = answer_question_for_scene(original_question, cf2_scene_d)
                    cf2_ans_cf1_q = answer_question_for_scene(cf1_question, cf2_scene_d)
                    cf2_ans_cf2_q = answer_question_for_scene(cf2_question, cf2_scene_d)
                except Exception:
                    _bump_reject('answer')
                    continue

                all_answers = [
                    original_ans_orig_q,
                    original_ans_cf1_q,
                    original_ans_cf2_q,
                    cf1_ans_orig_q,
                    cf1_ans_cf1_q,
                    cf1_ans_cf2_q,
                    cf2_ans_orig_q,
                    cf2_ans_cf1_q,
                    cf2_ans_cf2_q,
                ]
                if any(_is_unresolved_answer(a) for a in all_answers):
                    _bump_reject('unresolved')
                    continue

                orig_vs_cf1_orig = (
                    normalize_answer(original_ans_orig_q),
                    normalize_answer(cf1_ans_orig_q),
                )
                orig_vs_cf1_cf = (
                    normalize_answer(original_ans_cf1_q),
                    normalize_answer(cf1_ans_cf1_q),
                )
                orig_vs_cf2_orig = (
                    normalize_answer(original_ans_orig_q),
                    normalize_answer(cf2_ans_orig_q),
                )
                orig_vs_cf2_cf = (
                    normalize_answer(original_ans_cf2_q),
                    normalize_answer(cf2_ans_cf2_q),
                )

                if cf1_type in IMAGE_CF_TYPES:
                    if orig_vs_cf1_orig[0] == orig_vs_cf1_orig[1]:
                        _bump_reject('no_orig_q_flip')
                        continue
                    if orig_vs_cf1_cf[0] == orig_vs_cf1_cf[1]:
                        _bump_reject('no_cf1_q_flip')
                        continue
                    if normalize_answer(cf1_ans_cf1_q) == normalize_answer(cf1_ans_orig_q):
                        _bump_reject('cf1_questions_same_answer')
                        continue

                if cf2_type in NEGATIVE_CF_TYPES:
                    if orig_vs_cf2_orig[0] != orig_vs_cf2_orig[1]:
                        _bump_reject('no_orig_q_hold')
                        continue
                    if orig_vs_cf2_cf[0] != orig_vs_cf2_cf[1]:
                        _bump_reject('no_cf2_q_hold')
                        continue

                if strict_question_validation:
                    cf1_validity = classify_question_validity(cf1_question, original_scene_d, cf1_scene_d)
                    cf2_validity = classify_question_validity(cf2_question, original_scene_d, cf2_scene_d)
                    cf1_required = 'Semantic-Valid' if (cf1_type and cf1_type in IMAGE_CF_TYPES) else 'Negative-Valid'
                    cf2_required = 'Semantic-Valid' if (cf2_type and cf2_type in IMAGE_CF_TYPES) else 'Negative-Valid'
                    if not (cf1_required == cf1_validity and cf2_required == cf2_validity):
                        _bump_reject('validity_class')
                        continue

                atype = _csv_answer_type(original_question)
                orig_ans = normalize_answer(original_ans_orig_q)
                if not _PRECHECK_QUOTA.allow(atype, orig_ans):
                    _ACCEPTANCE_STATS['quota_rejects'] += 1
                    _bump_reject('quota')
                    continue
                _PRECHECK_QUOTA.record(atype, orig_ans)
                _ACCEPTANCE_STATS['precheck_accepted'] += 1
                return True, None
    except Exception as e:
        return False, str(e)

    _ACCEPTANCE_STATS['precheck_failed_draws'] += 1
    return False, f'no valid question triple in {mr} attempts'


def generate_mapping_with_questions(run_dir, csv_filename='image_mapping_with_questions.csv',
                                   generate_questions=True, with_links=False, base_url=None,
                                   strict_question_validation=True, single_cf_per_row=False,
                                   enforce_cf_question_group=True):
    """Write run_dir mapping CSV; by default includes original_question, semantic_counterfactual_question_1, negative_counterfactual_question_1, rejection-sampled answers, optional validity stress test, and linguistic-control negatives."""
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
                  'semantic_counterfactual_image_link', 'semantic_counterfactual_scene_link',
                  'negative_counterfactual_image_link', 'negative_counterfactual_scene_link',
                  'semantic_counterfactual_type', 'negative_counterfactual_type',
                  'semantic_counterfactual_description', 'negative_counterfactual_description']
        if generate_questions:
            header.extend([
                'original_question', 'semantic_counterfactual_question_1', 'negative_counterfactual_question_1',
                'original_question_answer_type', 'semantic_counterfactual_question_1_answer_type', 'negative_counterfactual_question_1_answer_type',
                'original_question_reasoning_op', 'semantic_counterfactual_question_1_reasoning_op', 'negative_counterfactual_question_1_reasoning_op',
                'original_image_answer_to_original_question',
                'original_image_answer_to_semantic_counterfactual_question_1',
                'original_image_answer_to_negative_counterfactual_question_1',
                'semantic_counterfactual_image_answer_to_original_question',
                'semantic_counterfactual_image_answer_to_semantic_counterfactual_question_1',
                'semantic_counterfactual_image_answer_to_negative_counterfactual_question_1',
                'negative_counterfactual_image_answer_to_original_question',
                'negative_counterfactual_image_answer_to_semantic_counterfactual_question_1',
                'negative_counterfactual_image_answer_to_negative_counterfactual_question_1',
            ])
        rows.append(header)
    elif generate_questions:
        rows.append([
            'original_image', 'semantic_counterfactual_image', 'negative_counterfactual_image',
            'semantic_counterfactual_type', 'negative_counterfactual_type',
            'semantic_counterfactual_description', 'negative_counterfactual_description',
            'original_question', 'semantic_counterfactual_question_1', 'negative_counterfactual_question_1',
            'original_question_answer_type', 'semantic_counterfactual_question_1_answer_type', 'negative_counterfactual_question_1_answer_type',
            'original_question_reasoning_op', 'semantic_counterfactual_question_1_reasoning_op', 'negative_counterfactual_question_1_reasoning_op',
            'original_image_answer_to_original_question',
            'original_image_answer_to_semantic_counterfactual_question_1',
            'original_image_answer_to_negative_counterfactual_question_1',
            'semantic_counterfactual_image_answer_to_original_question',
            'semantic_counterfactual_image_answer_to_semantic_counterfactual_question_1',
            'semantic_counterfactual_image_answer_to_negative_counterfactual_question_1',
            'negative_counterfactual_image_answer_to_original_question',
            'negative_counterfactual_image_answer_to_semantic_counterfactual_question_1',
            'negative_counterfactual_image_answer_to_negative_counterfactual_question_1',
        ])
    else:
        rows.append(['original_image', 'semantic_counterfactual_image', 'negative_counterfactual_image',
                    'semantic_counterfactual_type', 'negative_counterfactual_type',
                    'semantic_counterfactual_description', 'negative_counterfactual_description'])
    
    if single_cf_per_row:
        if with_links:
            h = ['scene_id', 'original_image_link', 'original_scene_link', 'counterfactual_image_link', 'counterfactual_scene_link', 'counterfactual_type', 'counterfactual_description']
            if generate_questions:
                h.extend(['original_question', 'counterfactual_question',
                         'original_question_answer_type', 'counterfactual_question_answer_type',
                         'original_question_reasoning_op', 'counterfactual_question_reasoning_op',
                         'original_image_answer_to_original_question', 'original_image_answer_to_cf_question',
                         'cf_image_answer_to_original_question', 'cf_image_answer_to_cf_question',
                        ])
            rows = [h]
        elif generate_questions:
            rows = [['original_image', 'counterfactual_image', 'counterfactual_type', 'counterfactual_description',
                     'original_question', 'counterfactual_question',
                     'original_question_answer_type', 'counterfactual_question_answer_type',
                     'original_question_reasoning_op', 'counterfactual_question_reasoning_op',
                     'original_image_answer_to_original_question', 'original_image_answer_to_cf_question',
                     'cf_image_answer_to_original_question', 'cf_image_answer_to_cf_question']]
        else:
            rows = [['original_image', 'counterfactual_image', 'counterfactual_type', 'counterfactual_description']]
    
    total_scenes = len(scene_sets)
    mapping_quota = AcceptanceQuotas()
    
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
                    for cf_retry in range(MAX_CF_ANSWER_RETRIES):
                        try:
                            original_question, params, original_template = generate_question_for_scene(
                                original_scene_file, retry_index=cf_retry, cf_scene=cf_scene, cf_type=cf_type
                            )
                            if not original_question_single_ref_valid(original_template, params, original_scene):
                                continue
                            if enforce_cf_question_group and cf_type in IMAGE_CF_TYPES and not semantic_cf_type_allowed_for_template(cf_type, original_template):
                                continue
                            original_ans_orig = answer_question_for_scene(original_question, original_scene)
                            cf_question, cf_params = generate_question_for_counterfactual(
                                cf_type, original_scene, cf_scene, retry_index=cf_retry,
                                original_question=original_question, original_params=params,
                                original_template=original_template
                            )
                            if cf_question is None or cf_params is None:
                                continue
                            if "matte or shiny" in (original_question or "").lower() and cf_type in ("add_object", "remove_object"):
                                continue
                            original_ans_cf_q = answer_question_for_scene(cf_question, original_scene)
                            cf_ans_orig_q = answer_question_for_scene(original_question, cf_scene)
                            cf_ans_cf_q = answer_question_for_scene(cf_question, cf_scene)
                            orig_diff = calculate_question_difficulty(original_question, params, template=original_template)
                            cf_diff = calculate_question_difficulty(cf_question, cf_params)
                        except Exception:
                            continue
                        all_answers = [
                            original_ans_orig,
                            original_ans_cf_q,
                            cf_ans_orig_q,
                            cf_ans_cf_q,
                        ]
                        if any(_is_unresolved_answer(a) for a in all_answers):
                            continue
                        # Rejection sampling: IMAGE_CF_TYPES require answer flips on both scenes (semantic parity); NEGATIVE_CF_TYPES forbid flips (stress-test invariance).
                        orig_vs_cf_orig = (
                            normalize_answer(original_ans_orig),
                            normalize_answer(cf_ans_orig_q),
                        )
                        orig_vs_cf_cf = (
                            normalize_answer(original_ans_cf_q),
                            normalize_answer(cf_ans_cf_q),
                        )
                        if cf_type in IMAGE_CF_TYPES:
                            if orig_vs_cf_orig[0] == orig_vs_cf_orig[1]:
                                continue
                            if orig_vs_cf_cf[0] == orig_vs_cf_cf[1]:
                                continue
                        elif cf_type in NEGATIVE_CF_TYPES:
                            if orig_vs_cf_orig[0] != orig_vs_cf_orig[1]:
                                continue
                            if orig_vs_cf_cf[0] != orig_vs_cf_cf[1]:
                                continue
                        if strict_question_validation:
                            validity = classify_question_validity(cf_question, original_scene, cf_scene)
                            required = 'Semantic-Valid' if (cf_type and cf_type in IMAGE_CF_TYPES) else 'Negative-Valid'
                            if validity != required:
                                continue
                        if with_links:
                            def _link(fn, ft='image'):
                                return f"{base_url.rstrip('/')}/{ft}s/{fn}" if base_url else f"{ft}s/{fn}"
                            rows.append([
                                scene_num,
                                _link(original_id, 'image'), _link(original_id.replace('.png', '.json'), 'scene'),
                                _link(cf_id, 'image'), _link(cf_id.replace('.png', '.json'), 'scene'),
                                cf_type, cf_description,
                                original_question, cf_question,
                                _csv_answer_type(original_question), _csv_answer_type(cf_question),
                                orig_diff, cf_diff,
                                original_ans_orig, original_ans_cf_q, cf_ans_orig_q, cf_ans_cf_q,
                            ])
                        else:
                            rows.append([
                                original_id, cf_id, cf_type, cf_description,
                                original_question, cf_question,
                                _csv_answer_type(original_question), _csv_answer_type(cf_question),
                                orig_diff, cf_diff,
                                original_ans_orig, original_ans_cf_q, cf_ans_orig_q, cf_ans_cf_q,
                            ])
                        break
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

            # Rejection sampling: previously the loop break-on-first-success let
            # any template that passed validation+answer-flip checks dominate.
            # For add_object/remove_object CFs in particular, "How many objects
            # are in the scene?" passes 100% of the time (count always flips by
            # ±1) while attribute-specific count questions like "How many red
            # objects?" only pass when the changed object happens to be red,
            # so the unconditional count question dominated count-CF rows
            # (~38% concentration on a single template). To fix this we
            # collect MANY viable candidates across retries, then sample
            # uniformly over DISTINCT TEMPLATES from the collected set. This
            # caps any single template's contribution to 1/(distinct templates
            # passing for this scene) regardless of per-template pass rates.
            CANDIDATE_TARGET = 24
            viable_candidates = []
            for cf_retry in range(MAX_CF_ANSWER_RETRIES):
                _ACCEPTANCE_STATS['mapping_attempts'] += 1
                try:
                    original_question, params, original_template = generate_question_for_scene(
                        original_scene_file, retry_index=cf_retry, cf_scene=cf1_scene, cf_type=cf1_type
                    )
                    if not original_question_single_ref_valid(original_template, params, original_scene):
                        continue
                    if enforce_cf_question_group:
                        if cf1_type in IMAGE_CF_TYPES and not semantic_cf_type_allowed_for_template(cf1_type, original_template):
                            continue
                        if cf2_type in IMAGE_CF_TYPES and not semantic_cf_type_allowed_for_template(cf2_type, original_template):
                            continue
                    original_ans_orig_q = answer_question_for_scene(original_question, original_scene)
                    random.seed(hash((scene_num, idx, cf_retry)))
                    cf_questions = create_counterfactual_questions(original_question, params, original_scene) if (not cf1_type or not cf2_type) else None
                    if cf1_type:
                        cf1_question, cf1_params = generate_question_for_counterfactual(
                            cf1_type, original_scene, cf1_scene, retry_index=cf_retry,
                            original_question=original_question, original_params=params,
                            original_template=original_template
                        )
                        if cf1_question is None or cf1_params is None:
                            continue
                    else:
                        if not cf_questions or len(cf_questions) == 0:
                            continue
                        cf1_question, cf1_params = cf_questions[0]
                    if cf2_type:
                        cf2_question, cf2_params = generate_question_for_counterfactual(
                            cf2_type, original_scene, cf2_scene, retry_index=cf_retry,
                            original_question=original_question, original_params=params,
                            original_template=original_template
                        )
                        if cf2_question is None or cf2_params is None:
                            continue
                    else:
                        if not cf_questions:
                            continue
                        if len(cf_questions) > 1:
                            cf2_question, cf2_params = cf_questions[1]
                        else:
                            cf2_question, cf2_params = cf_questions[0]
                    if "matte or shiny" in (original_question or "").lower() and (cf1_type in ("add_object", "remove_object") or cf2_type in ("add_object", "remove_object")):
                        continue
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    continue
                
                try:
                    # Pass the canonical original_template so the lookup-table
                    # fast path is used for the original question. cf1/cf2
                    # questions are paraphrases without canonical templates
                    # so they fall back to text-based parsing.
                    original_difficulty = calculate_question_difficulty(original_question, params, template=original_template)
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
                all_answers = [
                    original_ans_orig_q,
                    original_ans_cf1_q,
                    original_ans_cf2_q,
                    cf1_ans_orig_q,
                    cf1_ans_cf1_q,
                    cf1_ans_cf2_q,
                    cf2_ans_orig_q,
                    cf2_ans_cf1_q,
                    cf2_ans_cf2_q,
                ]
                if any(_is_unresolved_answer(a) for a in all_answers):
                    continue
                # Rejection sampling: cf1 semantic flips required; cf2 negative-CF invariance; strict_question_validation adds cross-scene classifier stress test.
                orig_vs_cf1_orig = (
                    normalize_answer(original_ans_orig_q),
                    normalize_answer(cf1_ans_orig_q),
                )
                orig_vs_cf1_cf = (
                    normalize_answer(original_ans_cf1_q),
                    normalize_answer(cf1_ans_cf1_q),
                )
                orig_vs_cf2_orig = (
                    normalize_answer(original_ans_orig_q),
                    normalize_answer(cf2_ans_orig_q),
                )
                orig_vs_cf2_cf = (
                    normalize_answer(original_ans_cf2_q),
                    normalize_answer(cf2_ans_cf2_q),
                )

                if cf1_type in IMAGE_CF_TYPES:
                    if orig_vs_cf1_orig[0] == orig_vs_cf1_orig[1]:
                        continue
                    if orig_vs_cf1_cf[0] == orig_vs_cf1_cf[1]:
                        continue
                    cf1_img_orig_q = normalize_answer(cf1_ans_orig_q)
                    cf1_img_cf1_q = normalize_answer(cf1_ans_cf1_q)
                    if cf1_img_orig_q == cf1_img_cf1_q:
                        continue

                if cf2_type in NEGATIVE_CF_TYPES:
                    if orig_vs_cf2_orig[0] != orig_vs_cf2_orig[1]:
                        continue
                    if orig_vs_cf2_cf[0] != orig_vs_cf2_cf[1]:
                        continue

                if strict_question_validation:
                    cf1_validity = classify_question_validity(cf1_question, original_scene, cf1_scene)
                    cf2_validity = classify_question_validity(cf2_question, original_scene, cf2_scene)
                    cf1_required = 'Semantic-Valid' if (cf1_type and cf1_type in IMAGE_CF_TYPES) else 'Negative-Valid'
                    cf2_required = 'Semantic-Valid' if (cf2_type and cf2_type in IMAGE_CF_TYPES) else 'Negative-Valid'
                    cf1_ok = (cf1_required == cf1_validity)
                    cf2_ok = (cf2_required == cf2_validity)
                    if not (cf1_ok and cf2_ok):
                        continue

                # All rejection criteria passed: stash the candidate and keep
                # collecting until we hit CANDIDATE_TARGET or run out of retries.
                viable_candidates.append({
                    'template': original_template,
                    'original_question': original_question,
                    'params': params,
                    'cf1_question': cf1_question, 'cf1_params': cf1_params,
                    'cf2_question': cf2_question, 'cf2_params': cf2_params,
                    'original_difficulty': original_difficulty,
                    'cf1_difficulty': cf1_difficulty, 'cf2_difficulty': cf2_difficulty,
                    'original_ans_orig_q': original_ans_orig_q,
                    'original_ans_cf1_q': original_ans_cf1_q,
                    'original_ans_cf2_q': original_ans_cf2_q,
                    'cf1_ans_orig_q': cf1_ans_orig_q,
                    'cf1_ans_cf1_q': cf1_ans_cf1_q,
                    'cf1_ans_cf2_q': cf1_ans_cf2_q,
                    'cf2_ans_orig_q': cf2_ans_orig_q,
                    'cf2_ans_cf1_q': cf2_ans_cf1_q,
                    'cf2_ans_cf2_q': cf2_ans_cf2_q,
                })
                if len(viable_candidates) >= CANDIDATE_TARGET:
                    break

            # Pick one candidate by sampling uniformly across DISTINCT templates,
            # then uniformly within the chosen template's bucket. This caps any
            # single template's share to 1 / (number of distinct templates that
            # passed for this scene), instead of letting templates with high
            # validation pass-rates dominate.
            if viable_candidates:
                fitting = []
                for c in viable_candidates:
                    atype = _csv_answer_type(c['original_question'])
                    orig_ans = normalize_answer(c['original_ans_orig_q'])
                    if mapping_quota.allow(atype, orig_ans):
                        fitting.append(c)
                if fitting:
                    pick_pool = fitting
                else:
                    _ACCEPTANCE_STATS['quota_fallbacks'] += 1
                    _bump_reject('quota_fallback')
                    pick_pool = viable_candidates
                _ACCEPTANCE_STATS['quota_rejects'] += max(0, len(viable_candidates) - len(fitting))
                by_template = {}
                for c in pick_pool:
                    by_template.setdefault(c['template'], []).append(c)
                _pick_rng = random.Random(hash((scene_num, idx, 'pick_canonical', original_id)))
                chosen_template_key = _pick_rng.choice(sorted(by_template.keys()))
                chosen = _pick_rng.choice(by_template[chosen_template_key])

                original_question = chosen['original_question']
                params = chosen['params']
                original_template = chosen['template']
                cf1_question = chosen['cf1_question']
                cf1_params = chosen['cf1_params']
                cf2_question = chosen['cf2_question']
                cf2_params = chosen['cf2_params']
                original_difficulty = chosen['original_difficulty']
                cf1_difficulty = chosen['cf1_difficulty']
                cf2_difficulty = chosen['cf2_difficulty']
                original_ans_orig_q = chosen['original_ans_orig_q']
                original_ans_cf1_q = chosen['original_ans_cf1_q']
                original_ans_cf2_q = chosen['original_ans_cf2_q']
                cf1_ans_orig_q = chosen['cf1_ans_orig_q']
                cf1_ans_cf1_q = chosen['cf1_ans_cf1_q']
                cf1_ans_cf2_q = chosen['cf1_ans_cf2_q']
                cf2_ans_orig_q = chosen['cf2_ans_orig_q']
                cf2_ans_cf1_q = chosen['cf2_ans_cf1_q']
                cf2_ans_cf2_q = chosen['cf2_ans_cf2_q']
                mapping_quota.record(_csv_answer_type(original_question), original_ans_orig_q)
                _ACCEPTANCE_STATS['mapping_accepted'] += 1
                _ACCEPTANCE_STATS['accepted'] += 1

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
                            _csv_answer_type(original_question), _csv_answer_type(cf1_question), _csv_answer_type(cf2_question),
                            original_difficulty, cf1_difficulty, cf2_difficulty,
                            original_ans_orig_q, original_ans_cf1_q, original_ans_cf2_q,
                            cf1_ans_orig_q, cf1_ans_cf1_q, cf1_ans_cf2_q,
                            cf2_ans_orig_q, cf2_ans_cf1_q, cf2_ans_cf2_q,
                        ])
                    else:
                        rows.append([
                            original_id, cf1_id, cf2_id,
                            cf1_type, cf2_type, cf1_description, cf2_description,
                            original_question, cf1_question, cf2_question,
                            _csv_answer_type(original_question), _csv_answer_type(cf1_question), _csv_answer_type(cf2_question),
                            original_difficulty, cf1_difficulty, cf2_difficulty,
                            original_ans_orig_q, original_ans_cf1_q, original_ans_cf2_q,
                            cf1_ans_orig_q, cf1_ans_cf1_q, cf1_ans_cf2_q,
                            cf2_ans_orig_q, cf2_ans_cf1_q, cf2_ans_cf2_q,
                        ])
                except Exception as e:
                    import traceback
                    traceback.print_exc()
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
    try:
        write_acceptance_stats(run_dir, mapping_quota=mapping_quota)
    except Exception:
        import traceback
        traceback.print_exc()
    
    print("\nSample entry:")
    if len(rows) > 1:
        row = rows[1]
        if single_cf_per_row:
            if generate_questions and len(row) >= 15:
                print(f"  Images: Original: {row[0]}, Counterfactual: {row[1]}")
                print(f"  CF type / description: {row[2]}, {row[3]!r}")
                print(f"  Questions: Original: {row[4]}, CF: {row[5]}; Neg text: {row[12]}")
                print(f"  Answers: orig->orig_q: {row[8]}, orig->cf_q: {row[9]}, cf->orig_q: {row[10]}, cf->cf_q: {row[11]}")
                print(f"  Neg-text (copied from orig Q on each scene): orig: {row[13]}, cf: {row[14]}")
            elif len(row) >= 4:
                print(f"  Images: Original: {row[0]}, Counterfactual: {row[1]}")
                print(f"  CF type / description: {row[2]}, {row[3]!r}")
        elif with_links:
            if generate_questions:
                print(f"  Scene ID: {row[0]}")
                print(f"  Links:")
                print(f"    Original image: {row[1]}, scene: {row[2]}")
                print(f"    Semantic CF image: {row[3]}, scene: {row[4]}")
                print(f"    Negative CF image: {row[5]}, scene: {row[6]}")
                print(f"  CF type / description: semantic={row[7]}, negative={row[8]}; semantic desc={row[9]!r}, negative desc={row[10]!r}")
                print(f"  Questions: Original: {row[11]}, semantic Q1: {row[12]}, negative Q1: {row[13]}")
            else:
                print(f"  Scene ID: {row[0]}")
                print(f"  Links:")
                print(f"    Original image: {row[1]}, scene: {row[2]}")
                print(f"    Semantic CF image: {row[3]}, scene: {row[4]}")
                print(f"    Negative CF image: {row[5]}, scene: {row[6]}")
                print(f"  CF type / description: semantic={row[7]}, negative={row[8]}; semantic desc={row[9]!r}, negative desc={row[10]!r}")
        elif generate_questions and len(row) >= 26:
            print(f"  Images: Original: {row[0]}, semantic CF: {row[1]}, negative CF: {row[2]}")
            print(f"  CF type / description: semantic={row[3]}, negative={row[4]}; semantic desc={row[5]!r}, negative desc={row[6]!r}")
            print(f"  Questions: Original: {row[7]}, semantic Q1: {row[8]}, negative Q1: {row[9]}; Neg text: {row[22]}")
            print(f"  Answer Matrix (scene × question):")
            print(f"    Original image -> Orig Q: {row[13]}, semantic Q1: {row[14]}, negative Q1: {row[15]}")
            print(f"    Semantic CF image -> Orig Q: {row[16]}, semantic Q1: {row[17]}, negative Q1: {row[18]}")
            print(f"    Negative CF image -> Orig Q: {row[19]}, semantic Q1: {row[20]}, negative Q1: {row[21]}")
            print(f"  Neg-text answers (same as orig Q on each scene): orig: {row[23]}, semantic CF: {row[24]}, negative CF: {row[25]}")
        elif len(row) >= 7:
            print(f"  Images: Original: {row[0]}, semantic CF: {row[1]}, negative CF: {row[2]}")
            print(f"  CF type / description: semantic={row[3]}, negative={row[4]}; semantic desc={row[5]!r}, negative desc={row[6]!r}")

def main():
    parser = argparse.ArgumentParser(
        description='Generate mapping CSV: original_question, semantic_counterfactual_question_1, negative_counterfactual_question_1, answer grid, negative_text_cf_question.'
    )
    parser.add_argument('--output_dir', default='output',
                       help='Run directory or base output directory (default: output)')
    parser.add_argument('--auto_latest', action='store_true',
                       help='Automatically find and use the latest run in output_dir')
    parser.add_argument('--csv_name', default='image_mapping_with_questions.csv',
                       help='Output CSV filename')
    parser.set_defaults(generate_questions=True)
    parser.add_argument('--generate_questions', dest='generate_questions', action='store_true',
                       help='Include Q&A columns (default: on)')
    parser.add_argument('--no_generate_questions', dest='generate_questions', action='store_false',
                       help='Filename-only CSV: omit questions, answers, and neg-text columns')
    parser.add_argument('--no_strict_validation', action='store_true',
                       help='Disable strict question validation (Semantic-Valid / Negative-Valid classifier); use legacy accept logic')
    parser.add_argument('--no_cf_question_group_filter', action='store_true',
                       help='Allow any semantic CF type with any original VQA template (disable Group 1–5 ↔ CF-type compatibility filter)')
    parser.add_argument('--single_cf_per_row', action='store_true',
                       help='Emit one row per (original, single CF) instead of (original, semantic CF, negative CF). Q&A columns still follow --generate_questions / --no_generate_questions (default: Q&A on).')
    
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
        single_cf_per_row=getattr(args, 'single_cf_per_row', False),
        enforce_cf_question_group=not getattr(args, 'no_cf_question_group_filter', False),
    )

if __name__ == '__main__':
    main()