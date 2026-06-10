#!/usr/bin/env python3
"""
PPT Master - PPTX Animation Module

Provides XML generation for slide transition effects and entrance animations.

Supported transition effects:
    - fade: Fade in/out
    - push: Push
    - wipe: Wipe
    - split: Split
    - strips: Strips (diagonal wipe)
    - cover: Cover
    - random: Random

Supported entrance animations (per-element):
    appear, fade, fly, cut, zoom, wipe, split, blinds, checkerboard,
    dissolve, random_bars, peek, wheel, box, circle, diamond, plus,
    strips, wedge, stretch, expand, swivel

Animation modes used by the builder:
    - single effect name (one of the above) — apply to every element
    - 'mixed'  — first element fades, the rest cycle through a curated visible pool
    - 'random' — pick a random effect from the same visible pool per element

Dependencies: None (pure XML generation)

Usage:
    python3 scripts/pptx_animations.py --demo
    python3 scripts/pptx_animations.py --list
"""

import argparse
from typing import Optional, Dict, Any


# ============================================================================
# Transition effect definitions
# ============================================================================

TRANSITIONS: Dict[str, Dict[str, Any]] = {
    'fade': {
        'name': 'Fade',
        'element': 'fade',
        'attrs': {},
    },
    'push': {
        'name': 'Push',
        'element': 'push',
        'attrs': {'dir': 'r'},
    },
    'push-left': {
        'name': 'Push Left',
        'element': 'push',
        'attrs': {'dir': 'l'},
    },
    'push-up': {
        'name': 'Push Up',
        'element': 'push',
        'attrs': {'dir': 'u'},
    },
    'push-down': {
        'name': 'Push Down',
        'element': 'push',
        'attrs': {'dir': 'd'},
    },
    'wipe': {
        'name': 'Wipe Right',
        'element': 'wipe',
        'attrs': {'dir': 'r'},
    },
    'wipe-left': {
        'name': 'Wipe Left',
        'element': 'wipe',
        'attrs': {'dir': 'l'},
    },
    'wipe-up': {
        'name': 'Wipe Up',
        'element': 'wipe',
        'attrs': {'dir': 'u'},
    },
    'wipe-down': {
        'name': 'Wipe Down',
        'element': 'wipe',
        'attrs': {'dir': 'd'},
    },
    'split': {
        'name': 'Split Horizontal Out',
        'element': 'split',
        'attrs': {'orient': 'horz', 'dir': 'out'},
    },
    'split-vertical': {
        'name': 'Split Vertical Out',
        'element': 'split',
        'attrs': {'orient': 'vert', 'dir': 'out'},
    },
    'split-in': {
        'name': 'Split Horizontal In',
        'element': 'split',
        'attrs': {'orient': 'horz', 'dir': 'in'},
    },
    'strips': {
        'name': 'Strips',
        'element': 'strips',
        'attrs': {'dir': 'rd'},
    },
    'cover': {
        'name': 'Cover Right',
        'element': 'cover',
        'attrs': {'dir': 'r'},
    },
    'cover-left': {
        'name': 'Cover Left',
        'element': 'cover',
        'attrs': {'dir': 'l'},
    },
    'cover-up': {
        'name': 'Cover Up',
        'element': 'cover',
        'attrs': {'dir': 'u'},
    },
    'cover-down': {
        'name': 'Cover Down',
        'element': 'cover',
        'attrs': {'dir': 'd'},
    },
    'uncover': {
        'name': 'Uncover Right',
        'element': 'cover',
        'attrs': {'dir': 'l'},
    },
    'random': {
        'name': 'Random',
        'element': 'random',
        'attrs': {},
    },
    'dissolve': {
        'name': 'Dissolve',
        'element': 'dissolve',
        'attrs': {},
    },
    'pan': {
        'name': 'Pan Right',
        'element': 'pan',
        'attrs': {'dir': 'r'},
    },
    'pan-left': {
        'name': 'Pan Left',
        'element': 'pan',
        'attrs': {'dir': 'l'},
    },
    'pan-up': {
        'name': 'Pan Up',
        'element': 'pan',
        'attrs': {'dir': 'u'},
    },
    'pan-down': {
        'name': 'Pan Down',
        'element': 'pan',
        'attrs': {'dir': 'd'},
    },
    'cube': {
        'name': 'Cube Right',
        'element': 'cube',
        'attrs': {'dir': 'r'},
    },
    'cube-left': {
        'name': 'Cube Left',
        'element': 'cube',
        'attrs': {'dir': 'l'},
    },
    'zoom': {
        'name': 'Zoom In',
        'element': 'zoom',
        'attrs': {'dir': 'in'},
    },
    'zoom-out': {
        'name': 'Zoom Out',
        'element': 'zoom',
        'attrs': {'dir': 'out'},
    },
    'glitter': {
        'name': 'Glitter Right',
        'element': 'glitter',
        'attrs': {'dir': 'r'},
    },
    'glitter-left': {
        'name': 'Glitter Left',
        'element': 'glitter',
        'attrs': {'dir': 'l'},
    },
    'vortex': {
        'name': 'Vortex Right',
        'element': 'vortex',
        'attrs': {'dir': 'r'},
    },
    'vortex-left': {
        'name': 'Vortex Left',
        'element': 'vortex',
        'attrs': {'dir': 'l'},
    },
    'ripple': {
        'name': 'Ripple',
        'element': 'ripple',
        'attrs': {'dir': 'c'},
    },
    'honeycomb': {
        'name': 'Honeycomb',
        'element': 'honeycomb',
        'attrs': {},
    },
    'wind': {
        'name': 'Wind Right',
        'element': 'wind',
        'attrs': {'dir': 'r'},
    },
    'wind-left': {
        'name': 'Wind Left',
        'element': 'wind',
        'attrs': {'dir': 'l'},
    },
    'ferris': {
        'name': 'Ferris Wheel',
        'element': 'ferris',
        'attrs': {},
    },
    'flash': {
        'name': 'Flash',
        'element': 'flash',
        'attrs': {},
    },
    'gallery': {
        'name': 'Gallery Right',
        'element': 'gallery',
        'attrs': {'dir': 'r'},
    },
    'gallery-left': {
        'name': 'Gallery Left',
        'element': 'gallery',
        'attrs': {'dir': 'l'},
    },
    'doors': {
        'name': 'Doors Vertical',
        'element': 'doors',
        'attrs': {'orient': 'vert'},
    },
    'doors-horizontal': {
        'name': 'Doors Horizontal',
        'element': 'doors',
        'attrs': {'orient': 'horz'},
    },
    'newsflash': {
        'name': 'Newsflash',
        'element': 'newsflash',
        'attrs': {},
    },
    'switch': {
        'name': 'Switch Right',
        'element': 'switch',
        'attrs': {'dir': 'r'},
    },
    'switch-left': {
        'name': 'Switch Left',
        'element': 'switch',
        'attrs': {'dir': 'l'},
    },
    'flythrough': {
        'name': 'Fly Through',
        'element': 'flythrough',
        'attrs': {'dir': 'in'},
    },
    'flythrough-out': {
        'name': 'Fly Through Out',
        'element': 'flythrough',
        'attrs': {'dir': 'out'},
    },
}

def create_transition_xml(
    effect: str = 'fade',
    duration: float = 0.5,
    advance_after: Optional[float] = None
) -> str:
    """
    Generate a slide transition effect XML fragment

    Args:
        effect: Transition effect name (fade/push/wipe/split/strips/cover/random)
        duration: Transition duration (seconds, precise to milliseconds)
        advance_after: Auto-advance interval (seconds); None means manual advance

    Returns:
        A <p:transition> element string insertable into slide XML
    """
    if effect not in TRANSITIONS:
        effect = 'fade'

    trans_info = TRANSITIONS[effect]
    element_name = trans_info['element']
    attrs = trans_info['attrs']

    # Build dur attribute (milliseconds, precise control via Office 2010 extension)
    dur_ms = int(duration * 1000)
    dur_attr = f' p14:dur="{dur_ms}" xmlns:p14="http://schemas.microsoft.com/office/powerpoint/2010/main"'

    # Build auto-advance attribute
    adv_attr = ''
    if advance_after is not None:
        adv_tm = int(advance_after * 1000)  # Convert to milliseconds
        adv_attr = f' advTm="{adv_tm}"'

    # Build effect element attributes
    effect_attrs = ' '.join(f'{k}="{v}"' for k, v in attrs.items())
    if effect_attrs:
        effect_attrs = ' ' + effect_attrs

    # Generate XML
    return f'''  <p:transition{dur_attr}{adv_attr}>
    <p:{element_name}{effect_attrs}/>
  </p:transition>'''


# ============================================================================
# Entrance animation definitions
# ============================================================================

#
# 'filter' values must be valid PowerPoint <p:animEffect filter=".."/> strings
# (see ECMA-376 §19.5.10 ST_TLAnimateEffectTransition / filter dictionary).
# Effects with filter=None render as plain "Appear" (visibility flip only).
#
# Map of animation type to presetClass (ECMA-376 §19.5.8)
# entr = entrance, emph = emphasis, exit = exit
ANIMATIONS: Dict[str, Dict[str, Any]] = {
    # --- Entrance ---
    'appear':   {'name': 'Appear',   'filter': None, 'presetID': 1, 'presetSubtype': 0, 'presetClass': 'entr'},
    'fade':     {'name': 'Fade',     'filter': 'fade', 'presetID': 10, 'presetSubtype': 0, 'presetClass': 'entr'},
    'fly':      {'name': 'Fly In',   'filter': 'slide(fromBottom)', 'presetID': 2, 'presetSubtype': 4, 'presetClass': 'entr'},
    'cut':      {'name': 'Cut In',   'filter': 'slide(fromLeft)', 'presetID': 42, 'presetSubtype': 8, 'presetClass': 'entr'},
    'zoom':     {'name': 'Zoom',     'filter': 'image', 'presetID': 23, 'presetSubtype': 0, 'presetClass': 'entr'},
    'wipe':     {'name': 'Wipe',     'filter': 'wipe(left)', 'presetID': 22, 'presetSubtype': 1, 'presetClass': 'entr'},
    'split':    {'name': 'Split',    'filter': 'barn(inVertical)', 'presetID': 16, 'presetSubtype': 21, 'presetClass': 'entr'},
    'blinds':   {'name': 'Blinds',   'filter': 'blinds(horizontal)', 'presetID': 3, 'presetSubtype': 10, 'presetClass': 'entr'},
    'checkerboard': {'name': 'Checkerboard', 'filter': 'checkerboard(across)', 'presetID': 5, 'presetSubtype': 6, 'presetClass': 'entr'},
    'dissolve': {'name': 'Dissolve', 'filter': 'dissolve', 'presetID': 9, 'presetSubtype': 0, 'presetClass': 'entr'},
    'random_bars': {'name': 'Random Bars', 'filter': 'randombar(horizontal)', 'presetID': 14, 'presetSubtype': 10, 'presetClass': 'entr'},
    'peek':     {'name': 'Peek',     'filter': 'wipe(down)', 'presetID': 12, 'presetSubtype': 4, 'presetClass': 'entr'},
    'wheel':    {'name': 'Wheel',    'filter': 'wheel(4)', 'presetID': 21, 'presetSubtype': 0, 'presetClass': 'entr'},
    'box':      {'name': 'Box',      'filter': 'box(in)', 'presetID': 4, 'presetSubtype': 0, 'presetClass': 'entr'},
    'circle':   {'name': 'Circle',   'filter': 'circle(in)', 'presetID': 6, 'presetSubtype': 0, 'presetClass': 'entr'},
    'diamond':  {'name': 'Diamond',  'filter': 'diamond(in)', 'presetID': 8, 'presetSubtype': 0, 'presetClass': 'entr'},
    'plus':     {'name': 'Plus',     'filter': 'plus(in)', 'presetID': 13, 'presetSubtype': 0, 'presetClass': 'entr'},
    'strips':   {'name': 'Strips',   'filter': 'strips(downRight)', 'presetID': 18, 'presetSubtype': 12, 'presetClass': 'entr'},
    'wedge':    {'name': 'Wedge',    'filter': 'wedge', 'presetID': 20, 'presetSubtype': 0, 'presetClass': 'entr'},
    'stretch':  {'name': 'Stretch',  'filter': 'stretch(across)', 'presetID': 17, 'presetSubtype': 0, 'presetClass': 'entr'},
    'expand':   {'name': 'Expand',   'filter': 'stretch(across)', 'presetID': 50, 'presetSubtype': 0, 'presetClass': 'entr'},
    'swivel':   {'name': 'Swivel',   'filter': 'wheel(1)', 'presetID': 19, 'presetSubtype': 0, 'presetClass': 'entr'},
    'flash_once': {'name': 'Flash Once', 'filter': 'flashbulb', 'presetID': 11, 'presetSubtype': 0, 'presetClass': 'entr'},
    'crawl':    {'name': 'Crawl In', 'filter': 'slide(fromLeft)', 'presetID': 7, 'presetSubtype': 0, 'presetClass': 'entr'},
    'float_in': {'name': 'Float In', 'filter': 'float(in)', 'presetID': 24, 'presetSubtype': 0, 'presetClass': 'entr'},
    # --- Emphasis ---
    'pulse':        {'name': 'Pulse',        'filter': None, 'presetID': 25, 'presetSubtype': 0, 'presetClass': 'emph'},
    'spin':         {'name': 'Spin',         'filter': None, 'presetID': 26, 'presetSubtype': 0, 'presetClass': 'emph'},
    'grow_shrink':  {'name': 'Grow/Shrink',  'filter': None, 'presetID': 27, 'presetSubtype': 0, 'presetClass': 'emph'},
    'teeter':       {'name': 'Teeter',       'filter': None, 'presetID': 33, 'presetSubtype': 0, 'presetClass': 'emph'},
    'color_pulse':  {'name': 'Color Pulse',  'filter': None, 'presetID': 31, 'presetSubtype': 0, 'presetClass': 'emph'},
    'desaturate':   {'name': 'Desaturate',   'filter': None, 'presetID': 28, 'presetSubtype': 0, 'presetClass': 'emph'},
    'darken':       {'name': 'Darken',       'filter': None, 'presetID': 29, 'presetSubtype': 0, 'presetClass': 'emph'},
    'lighten':      {'name': 'Lighten',      'filter': None, 'presetID': 30, 'presetSubtype': 0, 'presetClass': 'emph'},
    'transparency': {'name': 'Transparency', 'filter': None, 'presetID': 32, 'presetSubtype': 0, 'presetClass': 'emph'},
    'object_color': {'name': 'Object Color', 'filter': None, 'presetID': 34, 'presetSubtype': 0, 'presetClass': 'emph'},
    'complementary':{'name': 'Complementary Color', 'filter': None, 'presetID': 35, 'presetSubtype': 0, 'presetClass': 'emph'},
    'line_color':   {'name': 'Line Color',   'filter': None, 'presetID': 36, 'presetSubtype': 0, 'presetClass': 'emph'},
    'fill_color':   {'name': 'Fill Color',   'filter': None, 'presetID': 37, 'presetSubtype': 0, 'presetClass': 'emph'},
    'brush_color':  {'name': 'Brush Color',  'filter': None, 'presetID': 38, 'presetSubtype': 0, 'presetClass': 'emph'},
    'font_color':   {'name': 'Font Color',   'filter': None, 'presetID': 39, 'presetSubtype': 0, 'presetClass': 'emph'},
    'underline':    {'name': 'Underline',    'filter': None, 'presetID': 40, 'presetSubtype': 0, 'presetClass': 'emph'},
    'bold_flash':   {'name': 'Bold Flash',   'filter': None, 'presetID': 41, 'presetSubtype': 0, 'presetClass': 'emph'},
    'bold_reveal':  {'name': 'Bold Reveal',  'filter': None, 'presetID': 42, 'presetSubtype': 0, 'presetClass': 'emph'},
    'wave':         {'name': 'Wave',         'filter': None, 'presetID': 43, 'presetSubtype': 0, 'presetClass': 'emph'},
    'float':        {'name': 'Float',        'filter': None, 'presetID': 24, 'presetSubtype': 0, 'presetClass': 'emph'},
    # --- Exit ---
    'fade_out':     {'name': 'Fade Out',     'filter': 'fade', 'presetID': 10, 'presetSubtype': 0, 'presetClass': 'exit'},
    'fly_out':      {'name': 'Fly Out',      'filter': 'slide(toBottom)', 'presetID': 2, 'presetSubtype': 12, 'presetClass': 'exit'},
    'wipe_out':     {'name': 'Wipe Out',     'filter': 'wipe(right)', 'presetID': 22, 'presetSubtype': 0, 'presetClass': 'exit'},
    'zoom_out':     {'name': 'Zoom Out',     'filter': 'image', 'presetID': 23, 'presetSubtype': 0, 'presetClass': 'exit'},
    'dissolve_out': {'name': 'Dissolve Out', 'filter': 'dissolve', 'presetID': 9, 'presetSubtype': 0, 'presetClass': 'exit'},
    'shrink_out':   {'name': 'Shrink Out',   'filter': 'stretch(across)', 'presetID': 50, 'presetSubtype': 0, 'presetClass': 'exit'},
    'disappear':    {'name': 'Disappear',    'filter': None, 'presetID': 1, 'presetSubtype': 0, 'presetClass': 'exit'},
    'fly_out_left': {'name': 'Fly Out Left',  'filter': 'slide(toLeft)', 'presetID': 2, 'presetSubtype': 13, 'presetClass': 'exit'},
    'fly_out_right': {'name': 'Fly Out Right', 'filter': 'slide(toRight)', 'presetID': 2, 'presetSubtype': 14, 'presetClass': 'exit'},
    'fly_out_up':   {'name': 'Fly Out Up',   'filter': 'slide(toTop)', 'presetID': 2, 'presetSubtype': 15, 'presetClass': 'exit'},
    'fly_out_down': {'name': 'Fly Out Down', 'filter': 'slide(toBottom)', 'presetID': 2, 'presetSubtype': 12, 'presetClass': 'exit'},
    'wipe_out_left':  {'name': 'Wipe Out Left',  'filter': 'wipe(left)',  'presetID': 22, 'presetSubtype': 1, 'presetClass': 'exit'},
    'wipe_out_up':    {'name': 'Wipe Out Up',    'filter': 'wipe(up)',    'presetID': 22, 'presetSubtype': 4, 'presetClass': 'exit'},
    'wipe_out_right': {'name': 'Wipe Out Right', 'filter': 'wipe(right)', 'presetID': 22, 'presetSubtype': 0, 'presetClass': 'exit'},
    'wipe_out_down':  {'name': 'Wipe Out Down',  'filter': 'wipe(down)',  'presetID': 22, 'presetSubtype': 5, 'presetClass': 'exit'},
}

# Pool used by 'mixed' / 'random' modes. Excludes 'appear' because it has no
# visible motion; mixed handles the first title-like element as fade separately.
_MIXED_POOL = [
    'blinds', 'checkerboard', 'dissolve', 'fly', 'cut',
    'random_bars', 'box', 'split', 'strips', 'wedge', 'wheel',
    'wipe', 'expand', 'fade', 'swivel', 'zoom', 'float_in',
    'crawl', 'flash_once',
]


def create_timing_xml(
    animation: str = 'fade',
    duration: float = 1.0,
    delay: float = 0,
    shape_id: int = 2
) -> str:
    """
    Generate an entrance animation timing XML fragment

    Args:
        animation: Animation effect name (fade/fly/zoom/appear)
        duration: Animation duration (seconds)
        delay: Animation delay (seconds)
        shape_id: Target shape ID (SVG image is typically 2)

    Returns:
        A <p:timing> element string insertable into slide XML
    """
    if animation not in ANIMATIONS:
        animation = 'fade'

    anim_info = ANIMATIONS[animation]
    dur_ms = int(duration * 1000)
    delay_ms = int(delay * 1000)

    # Generate different effect XML depending on animation type
    if anim_info['filter'] is None:
        # appear animation: only sets visibility
        effect_xml = f'''                            <p:set>
                              <p:cBhvr>
                                <p:cTn id="5" dur="1" fill="hold">
                                  <p:stCondLst><p:cond delay="{delay_ms}"/></p:stCondLst>
                                </p:cTn>
                                <p:tgtEl><p:spTgt spid="{shape_id}"/></p:tgtEl>
                                <p:attrNameLst><p:attrName>style.visibility</p:attrName></p:attrNameLst>
                              </p:cBhvr>
                              <p:to><p:strVal val="visible"/></p:to>
                            </p:set>'''
    else:
        # Other animations: set visibility + animation effect
        filter_name = anim_info['filter']
        pr_attr = ''
        if 'prLst' in anim_info:
            pr_attr = f' prLst="{anim_info["prLst"]}"'

        effect_xml = f'''                            <p:set>
                              <p:cBhvr>
                                <p:cTn id="5" dur="1" fill="hold">
                                  <p:stCondLst><p:cond delay="0"/></p:stCondLst>
                                </p:cTn>
                                <p:tgtEl><p:spTgt spid="{shape_id}"/></p:tgtEl>
                                <p:attrNameLst><p:attrName>style.visibility</p:attrName></p:attrNameLst>
                              </p:cBhvr>
                              <p:to><p:strVal val="visible"/></p:to>
                            </p:set>
                            <p:animEffect transition="in" filter="{filter_name}"{pr_attr}>
                              <p:cBhvr>
                                <p:cTn id="6" dur="{dur_ms}"/>
                                <p:tgtEl><p:spTgt spid="{shape_id}"/></p:tgtEl>
                              </p:cBhvr>
                            </p:animEffect>'''

    return f'''  <p:timing>
    <p:tnLst>
      <p:par>
        <p:cTn id="1" dur="indefinite" nodeType="tmRoot">
          <p:childTnLst>
            <p:seq concurrent="1" nextAc="none">
              <p:cTn id="2" dur="indefinite" nodeType="mainSeq">
                <p:childTnLst>
                  <p:par>
                    <p:cTn id="3" fill="hold">
                      <p:stCondLst>
                        <p:cond delay="{delay_ms}"/>
                      </p:stCondLst>
                      <p:childTnLst>
                        <p:par>
                          <p:cTn id="4" fill="hold">
                            <p:childTnLst>
{effect_xml}
                            </p:childTnLst>
                          </p:cTn>
                        </p:par>
                      </p:childTnLst>
                    </p:cTn>
                  </p:par>
                </p:childTnLst>
              </p:cTn>
            </p:seq>
          </p:childTnLst>
        </p:cTn>
      </p:par>
    </p:tnLst>
  </p:timing>'''


def _build_effect_xml(
    animation: str,
    shape_id: int,
    duration_ms: int,
    set_id: int,
    eff_id: int,
) -> str:
    """Inner effect block for one target.

    Entrance effects are emitted as one animation pane row per target. Plain
    Appear uses a visibility set; motion/filter effects use animEffect directly
    to avoid duplicate rows for the same shape in PowerPoint.
    """
    anim_info = ANIMATIONS.get(animation, ANIMATIONS['fade'])
    preset_class = anim_info.get('presetClass', 'entr')
    preset_id = anim_info.get('presetID', 1)
    preset_subtype = anim_info.get('presetSubtype', 0)

    set_block = f'''<p:set>
  <p:cBhvr>
    <p:cTn id="{set_id}" dur="1" fill="hold">
      <p:stCondLst><p:cond delay="0"/></p:stCondLst>
    </p:cTn>
    <p:tgtEl><p:spTgt spid="{shape_id}"/></p:tgtEl>
    <p:attrNameLst><p:attrName>style.visibility</p:attrName></p:attrNameLst>
  </p:cBhvr>
  <p:to><p:strVal val="visible"/></p:to>
</p:set>'''
    if anim_info['filter'] is None:
        return set_block
    return set_block + f'''
<p:animEffect transition="in" filter="{anim_info["filter"]}">
  <p:cBhvr>
    <p:cTn id="{eff_id}" dur="{duration_ms}" presetClass="{preset_class}" presetID="{preset_id}" presetSubtype="{preset_subtype}"/>
    <p:tgtEl><p:spTgt spid="{shape_id}"/></p:tgtEl>
  </p:cBhvr>
</p:animEffect>'''


def create_sequence_timing_xml(
    targets: list,
    duration: float = 0.3,
    trigger: str = 'after-previous',
) -> str:
    """Generate a multi-target entrance sequence.

    Args:
        targets: list of (shape_id, delay_ms, animation_name) or
            (shape_id, delay_ms, animation_name, duration_seconds) tuples, in
            the order they should play. ``delay_ms`` is the gap before
            this element starts, measured from when the previous element
            triggers (only used in ``after-previous`` mode; ignored in
            the other two).
        duration: per-element entrance duration in seconds.
        trigger: PowerPoint-standard Start mode for each element.
            ``'after-previous'`` — first element fires on slide entry,
            rest chain after the previous one with ``delay_ms`` spacing
            (default).
            ``'on-click'`` — one presenter click per element.
            ``'with-previous'`` — all elements start together on slide
            entry.

    Returns:
        A ``<p:timing>`` element string. Returns an empty string when
        ``targets`` is empty.
    """
    if not targets:
        return ''

    if trigger not in ('on-click', 'with-previous', 'after-previous'):
        trigger = 'on-click'

    default_dur_ms = int(duration * 1000)
    next_id = 3

    def _target_parts(target: tuple) -> tuple[int, int, str, int]:
        shape_id, delay_ms, animation = target[:3]
        if animation not in ANIMATIONS:
            animation = 'fade'
        item_dur_ms = default_dur_ms
        if len(target) > 3 and target[3] is not None:
            item_dur_ms = int(float(target[3]) * 1000)
        return int(shape_id), int(delay_ms), str(animation), item_dur_ms

    if trigger == 'on-click':
        # Each element is an independent click-driven par directly under
        # mainSeq. Three-level nesting per element: outer cTn holds for
        # the click via delay="indefinite", innermost cTn owns the
        # clickEffect + animation children. Each click advances the seq.
        steps = []
        for target in targets:
            shape_id, _delay_ms, animation, item_dur_ms = _target_parts(target)
            anim_info = ANIMATIONS[animation]
            preset_id = anim_info.get('presetID', 1)
            preset_subtype = anim_info.get('presetSubtype', 0)
            preset_class = anim_info.get('presetClass', 'entr')
            wrapper_id = next_id
            inner_id = next_id + 1
            leaf_id = next_id + 2
            set_id = next_id + 3
            eff_id = next_id + 4
            next_id += 5
            effect_xml = _build_effect_xml(animation, shape_id, item_dur_ms, set_id, eff_id)
            steps.append(f'''<p:par>
  <p:cTn id="{wrapper_id}" fill="hold">
    <p:stCondLst><p:cond delay="indefinite"/></p:stCondLst>
    <p:childTnLst>
      <p:par>
        <p:cTn id="{inner_id}" fill="hold">
          <p:stCondLst><p:cond delay="0"/></p:stCondLst>
          <p:childTnLst>
            <p:par>
              <p:cTn id="{leaf_id}" presetID="{preset_id}" presetClass="{preset_class}" presetSubtype="{preset_subtype}" fill="hold" nodeType="clickEffect">
                <p:stCondLst><p:cond delay="0"/></p:stCondLst>
                <p:childTnLst>
                  {effect_xml}
                </p:childTnLst>
              </p:cTn>
            </p:par>
          </p:childTnLst>
        </p:cTn>
      </p:par>
    </p:childTnLst>
  </p:cTn>
</p:par>''')
        all_steps = '\n              '.join(steps)
    else:
        # with-previous / after-previous: wrap the entire cascade in ONE
        # par so the sequence has a real trigger anchor under mainSeq.
        #
        # Native PowerPoint after-previous export uses two timing layers for
        # each animation row: an outer wrapper owns the timeline offset, while
        # the inner effect cTn stays nodeType="afterEffect" with delay="0".
        # This keeps the animation pane editable as standard "After Previous"
        # rows instead of exposing synthetic per-effect cumulative delays.
        outer_id = next_id
        next_id += 1
        inner_steps = []
        with_wrapper_id = None
        if trigger == 'with-previous':
            with_wrapper_id = next_id
            next_id += 1
        elapsed_ms = 0
        prev_duration_ms = 0
        for i, target in enumerate(targets):
            shape_id, delay_ms, animation, item_dur_ms = _target_parts(target)
            anim_info = ANIMATIONS[animation]
            preset_id = anim_info.get('presetID', 1)
            preset_subtype = anim_info.get('presetSubtype', 0)
            preset_class = anim_info.get('presetClass', 'entr')

            if trigger == 'with-previous':
                leaf_id = next_id
                set_id = next_id + 1
                eff_id = next_id + 2
                next_id += 3
                effect_xml = _build_effect_xml(animation, shape_id, item_dur_ms, set_id, eff_id)
                inner_steps.append(f'''<p:par>
                  <p:cTn id="{leaf_id}" presetID="{preset_id}" presetClass="{preset_class}" presetSubtype="{preset_subtype}" fill="hold" nodeType="withEffect">
                    <p:stCondLst><p:cond delay="0"/></p:stCondLst>
                    <p:childTnLst>
                      {effect_xml}
                    </p:childTnLst>
                  </p:cTn>
                </p:par>''')
            else:
                if i == 0:
                    elapsed_ms = int(delay_ms)
                else:
                    elapsed_ms += prev_duration_ms + int(delay_ms)
                wrapper_id = next_id
                leaf_id = next_id + 1
                set_id = next_id + 2
                eff_id = next_id + 3
                next_id += 4
                effect_xml = _build_effect_xml(animation, shape_id, item_dur_ms, set_id, eff_id)
                inner_steps.append(f'''<p:par>
                  <p:cTn id="{wrapper_id}" fill="hold">
                    <p:stCondLst><p:cond delay="{elapsed_ms}"/></p:stCondLst>
                    <p:childTnLst>
                      <p:par>
                        <p:cTn id="{leaf_id}" presetID="{preset_id}" presetClass="{preset_class}" presetSubtype="{preset_subtype}" fill="hold" nodeType="afterEffect">
                          <p:stCondLst><p:cond delay="0"/></p:stCondLst>
                          <p:childTnLst>
                            {effect_xml}
                          </p:childTnLst>
                        </p:cTn>
                      </p:par>
                    </p:childTnLst>
                  </p:cTn>
                </p:par>''')
                prev_duration_ms = item_dur_ms

        inner_xml = '\n                '.join(inner_steps)
        if trigger == 'with-previous':
            # Match PowerPoint's native "Start: With Previous" export:
            # one delay=0 wrapper begins on slide entry, and all withEffect
            # rows live under that wrapper so they truly start in parallel.
            inner_xml = f'''<p:par>
                      <p:cTn id="{with_wrapper_id}" fill="hold">
                        <p:stCondLst><p:cond delay="0"/></p:stCondLst>
                        <p:childTnLst>
                          {inner_xml}
                        </p:childTnLst>
                      </p:cTn>
                    </p:par>'''
        if trigger in ('with-previous', 'after-previous'):
            # Match PowerPoint's native slide-entry export: the wrapper waits
            # for mainSeq to begin, then child nodes resolve their Start modes.
            outer_start_conditions = (
                '<p:cond delay="indefinite"/>'
                '<p:cond evt="onBegin" delay="0"><p:tn val="2"/></p:cond>'
            )
        else:
            outer_start_conditions = '<p:cond delay="0"/>'
        all_steps = f'''<p:par>
                <p:cTn id="{outer_id}" fill="hold">
                  <p:stCondLst>{outer_start_conditions}</p:stCondLst>
                  <p:childTnLst>
                    {inner_xml}
                  </p:childTnLst>
                </p:cTn>
              </p:par>'''

    bld_list = '\n    '.join(
        f'<p:bldP spid="{target[0]}" grpId="0"/>' for target in targets
    )
    return f'''  <p:timing>
    <p:tnLst>
      <p:par>
        <p:cTn id="1" dur="indefinite" restart="never" nodeType="tmRoot">
          <p:childTnLst>
            <p:seq concurrent="1" nextAc="seek">
              <p:cTn id="2" dur="indefinite" nodeType="mainSeq">
                <p:childTnLst>
              {all_steps}
                </p:childTnLst>
              </p:cTn>
              <p:prevCondLst><p:cond evt="onPrev" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond></p:prevCondLst>
              <p:nextCondLst><p:cond evt="onNext" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond></p:nextCondLst>
            </p:seq>
          </p:childTnLst>
        </p:cTn>
      </p:par>
    </p:tnLst>
    <p:bldLst>
    {bld_list}
    </p:bldLst>
  </p:timing>'''


def pick_animation_effect(mode: str, idx: int, offset: int = 0) -> str:
    """Resolve a per-element effect name from a mode string.

    - A specific animation name returns itself (no variation).
    - 'mixed': first element fixed to 'fade', rest cycle through ``_MIXED_POOL``
      plus ``offset`` (so titles stay calm while content varies across slides).
    - 'random': uniform random choice from ``_MIXED_POOL``.
    - Unknown mode falls back to 'fade'.
    """
    if mode in ANIMATIONS:
        return mode
    if mode == 'mixed':
        if idx == 0:
            return 'fade'
        return _MIXED_POOL[(idx - 1 + offset) % len(_MIXED_POOL)]
    if mode == 'random':
        import random
        return random.choice(_MIXED_POOL)
    return 'fade'


def get_available_transitions() -> list:
    """Get a list of all available transition effects"""
    return list(TRANSITIONS.keys())


def get_available_animations() -> list:
    """Get a list of all available entrance animations"""
    return list(ANIMATIONS.keys())


def get_transition_help() -> str:
    """Get help text for transition effects"""
    lines = ["Available transition effects:"]
    for key, info in TRANSITIONS.items():
        lines.append(f"  {key}: {info['name']}")
    return '\n'.join(lines)


def get_animation_help() -> str:
    """Get help text for entrance animations"""
    lines = ["Available entrance animations:"]
    for key, info in ANIMATIONS.items():
        lines.append(f"  {key}: {info['name']}")
    return '\n'.join(lines)


def main() -> None:
    """Run the CLI entry point."""
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--demo", action="store_true", help="print sample XML for a fade transition and animation")
    parser.add_argument("--list", action="store_true", help="list available transitions and entrance animations")
    args = parser.parse_args()

    if args.list:
        print(get_transition_help())
        print()
        print(get_animation_help())
        return

    if args.demo:
        print("=== Transition Effect XML Example (fade, 500ms) ===")
        print(create_transition_xml('fade', 0.5))
        print()
        print("=== Entrance Animation XML Example (fade) ===")
        print(create_timing_xml('fade', 1.0))
        return

    parser.print_help()


# ============================================================================
# SVG Attribute Parsing - Extract animations from data-animate attributes
# ============================================================================

import re
from dataclasses import dataclass as _dataclass
from typing import Optional as _Optional


@_dataclass
class SvgAnimSpec:
    """Animation specification extracted from SVG"""
    element_id: str
    animation_type: str  # fade, fade-up, zoom-in, etc.
    delay: float = 0.0   # delay in seconds
    duration: float = 0.8  # duration in seconds
    group_id: _Optional[str] = None  # parent <g id> group


@_dataclass
class SvgTransitionSpec:
    """Page transition specification extracted from SVG"""
    transition_type: str  # fade, push, wipe, etc.
    direction: _Optional[str] = None  # left, right, up, down
    duration: float = 0.5


# SVG animation type to PPT animation mapping
SVG_ANIM_MAP = {
    # Entrance animations
    "fade": "fade",
    "fade-up": "fly",
    "fade-down": "fly",
    "fade-left": "fly",
    "fade-right": "fly",
    "zoom-in": "zoom",
    "zoom-out": "zoom",
    "slide-up": "wipe",
    "slide-down": "wipe",
    "slide-left": "wipe",
    "slide-right": "wipe",
    "flip-x": "split",
    "flip-y": "split",
    "bounce-in": "float_in",
    "rotate-in": "wheel",
    # Emphasis animations
    "pulse": "grow",
    "shake": "shake",
    "swing": "spin",
    # Exit animations
    "fade-out": "fade",
    "zoom-out-exit": "zoom",
    "slide-out": "fly",
}


def parse_svg_animations(svg_content: str) -> list[SvgAnimSpec]:
    """Extract data-animate attributes from SVG content

    Args:
        svg_content: SVG file content

    Returns:
        List of animation specifications
    """
    specs: list[SvgAnimSpec] = []

    # Pattern to match data-animate attribute
    # Supports: data-animate="fade-up", data-animate="fade-up" data-delay="0.3"
    pattern = r'<(?:g|text|rect|circle|path|image)[^>]*?\s+data-animate="([^"]+)"[^>]*>'

    for i, match in enumerate(re.finditer(pattern, svg_content, re.DOTALL)):
        full_match = match.group(0)
        anim_type = match.group(1)

        # Extract element id
        id_match = re.search(r'id="([^"]+)"', full_match)
        element_id = id_match.group(1) if id_match else f"anim_{i}"

        # Extract delay
        delay_match = re.search(r'data-delay="([^"]+)"', full_match)
        delay = float(delay_match.group(1)) if delay_match else 0.0

        # Extract duration
        duration_match = re.search(r'data-duration="([^"]+)"', full_match)
        duration = float(duration_match.group(1)) if duration_match else 0.8

        # Find parent <g id> group
        group_id = None
        g_pattern = r'<g[^>]*id="([^"]+)"[^>]*>.*?' + re.escape(full_match)
        g_match = re.search(g_pattern, svg_content, re.DOTALL)
        if g_match:
            group_id = g_match.group(1)

        specs.append(SvgAnimSpec(
            element_id=element_id,
            animation_type=anim_type,
            delay=delay,
            duration=duration,
            group_id=group_id,
        ))

    return specs


def extract_transition_from_svg(svg_content: str) -> _Optional[SvgTransitionSpec]:
    """Extract page transition from SVG data-transition attribute

    Args:
        svg_content: SVG file content

    Returns:
        Transition specification or None if not found
    """
    # Check for data-transition attribute
    match = re.search(r'data-transition="([^"]+)"', svg_content)
    if match:
        transition_type = match.group(1)

        # Extract direction
        dir_match = re.search(r'data-transition-dir="([^"]+)"', svg_content)
        direction = dir_match.group(1) if dir_match else None

        # Extract duration
        dur_match = re.search(r'data-transition-dur="([^"]+)"', svg_content)
        duration = float(dur_match.group(1)) if dur_match else 0.5

        return SvgTransitionSpec(
            transition_type=transition_type,
            direction=direction,
            duration=duration,
        )

    return None


def svg_anim_to_ppt_anim(svg_anim_type: str) -> str:
    """Convert SVG animation type to PPT animation name

    Args:
        svg_anim_type: SVG animation type (e.g., "fade-up", "zoom-in")

    Returns:
        PPT animation name (e.g., "fly", "zoom")
    """
    return SVG_ANIM_MAP.get(svg_anim_type, "fade")


def create_animations_from_svg(svg_content: str, shape_id: int = 2) -> str:
    """Generate PPTX animation XML from SVG data-animate attributes

    Args:
        svg_content: SVG file content
        shape_id: Base shape ID for animations

    Returns:
        PPTX timing XML string
    """
    specs = parse_svg_animations(svg_content)
    if not specs:
        return ""

    # Build target list for sequence
    targets = []
    for i, spec in enumerate(specs):
        ppt_anim = svg_anim_to_ppt_anim(spec.animation_type)
        delay_ms = int(spec.delay * 1000)
        duration_s = spec.duration
        targets.append((shape_id + i, delay_ms, ppt_anim, duration_s))

    return create_sequence_timing_xml(targets, duration=0.3, trigger="with-previous")


def get_default_entrance_animation() -> str:
    """Get the default entrance animation for slides without explicit animation markers"""
    return "fade"


if __name__ == '__main__':
    main()
