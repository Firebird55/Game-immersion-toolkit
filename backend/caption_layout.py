"""Positioned subtitle/menu geometry shared with desktop capture."""
import re
import math
from dataclasses import dataclass

from .models import CaptureRegion
from .steam_games import STEAM_GAMES
from .bilingual import normalize_subtitle


@dataclass(frozen=True)
class NativeNteCaption:
    groups: tuple[str, ...]
    dialogue_menu: bool


def native_nte_caption(spans, image_size, picture, crop):
    """A native predecessor requires complete real positioned OCR evidence.

    Unknown scores/geometry disable context rather than manufacturing a clear
    menu state. Inspect genuine full-picture spans so an off-crop choice still
    resets the narrow caption context; keep recognized ordinary blocks separate.
    """
    if not isinstance(spans, list) or not spans or len(spans) > 512:
        return None
    if (not isinstance(image_size, (tuple, list)) or len(image_size) != 2
            or not isinstance(picture, (tuple, list)) or len(picture) != 4
            or not isinstance(crop, (tuple, list)) or len(crop) != 4
            or any(type(n) is not int for n in (*image_size, *picture, *crop))):
        return None
    width, height = image_size
    x, y, picture_width, picture_height = picture
    crop_x, crop_y, crop_width, crop_height = crop
    if (not 0 < width <= 4096 or not 0 < height <= 4096
            or not 0 <= x < x + picture_width <= width or not 0 <= y < y + picture_height <= height
            or not x <= crop_x < crop_x + crop_width <= x + picture_width
            or not y <= crop_y < crop_y + crop_height <= y + picture_height):
        return None
    rows = []
    for span in spans:
        if not isinstance(span, dict) or not isinstance(span.get('text'), str):
            return None
        rectangle = span.get('bounding_rect')
        if not isinstance(rectangle, dict):
            return None
        try:
            xs, ys = [rectangle['x' + str(i)] for i in range(1, 5)], [rectangle['y' + str(i)] for i in range(1, 5)]
            if any(type(n) not in (int, float) or not math.isfinite(n) for n in xs + ys):
                return None
            if not 0 <= min(xs) < max(xs) <= width or not 0 <= min(ys) < max(ys) <= height:
                return None
        except (KeyError, TypeError, ValueError, OverflowError):
            return None
        if not (x <= min(xs) < max(xs) <= x + picture_width and y <= min(ys) < max(ys) <= y + picture_height):
            continue
        score = span.get('confidence')
        if type(score) not in (float, int) or not 0.8 <= score <= 1:
            return None
        rows.append({**span, 'bounding_rect': {**{'x' + str(i): xs[i - 1] - x for i in range(1, 5)},
            **{'y' + str(i): ys[i - 1] - y for i in range(1, 5)}}})
    if not rows:
        return None
    selected = local_subtitle_rows({'lines': rows}, (picture_width, picture_height),
        CaptureRegion(left=0, top=0, width=1, height=1), 'nte')
    if not selected['dialogue_menu']:
        for row in rows:
            rectangle = row['bounding_rect']
            left = min(rectangle['x' + str(i)] for i in range(1, 5)) / picture_width
            top = min(rectangle['y' + str(i)] for i in range(1, 5)) / picture_height
            if left > .6 and top < .8:
                # The maintained filter can discard a short UI label before
                # identifying a menu. Its position alone cannot prove a clear
                # panel or ownership of a control, so disable native context.
                return None
    groups = []
    for row in selected['lines']:
        rect = row['bounding_rect']
        xs, ys = [rect['x' + str(i)] + x for i in range(1, 5)], [rect['y' + str(i)] + y for i in range(1, 5)]
        if crop_x <= min(xs) < max(xs) <= crop_x + crop_width and crop_y <= min(ys) < max(ys) <= crop_y + crop_height:
            groups.append(row['text'])
    return NativeNteCaption(tuple(groups), selected['dialogue_menu'])


def local_subtitle_rows(response: dict, size: tuple[int, int],
                         region: CaptureRegion, game: str) -> dict:
    """Exclude response choices and corner HUD from the lower subtitle lane.

    Coordinates refer to the OCR image, which may have been rescaled. Keep
    the user's crop independent of screen resolution and Windows DPI.
    """
    if game in STEAM_GAMES:
        # These readers use their independent, user-calibrated caption crop.
        # Source captions can be left aligned and Persona's text is beside a
        # portrait: older centered-caption/HUD rules would silently erase it.
        # Matching still requires the authored catalog and an eligible voice
        # or explicitly enabled text-only record. Off-lane silent content is
        # handled by the separate stable, exact full-frame pass.
        return response
    rows = []
    dialogue_menu = False
    for row in response.get("lines", []):
        # Interaction labels must not be treated as spoken subtitles.
        known_ui_label = normalize_subtitle(str(row.get("text", ""))) in {
            "talk", "open", "close", "back", "continue", "apply", "cancel",
            "sprint", "jump", "roach", "horse", "interact", "next", "skip",
            "select", "exit", "map", "inventory", "attack", "yourturn", "gatheringredients",
            "交谈", "对话", "互动", "继续", "取消", "确定", "退出", "跳跃",
            "冲刺", "攻击", "选择", "返回", "跳过", "打开", "关闭", "地图", "背包",
        }
        rectangle = row.get("bounding_rect") or {}
        try:
            left = region.left + min(float(rectangle[f"x{i}"]) for i in range(1, 5)) / size[0] * region.width
            right = region.left + max(float(rectangle[f"x{i}"]) for i in range(1, 5)) / size[0] * region.width
            top = region.top + min(float(rectangle[f"y{i}"]) for i in range(1, 5)) / size[1] * region.height
        except (KeyError, ValueError, TypeError):
            rows.append(row)
            continue
        text = str(row.get("text", ""))
        short_label = (len(re.findall(r"[a-zA-Z]+", text)) == 1 and len(normalize_subtitle(text)) < 12)
        short_label |= bool(re.search(r"[\u3400-\u9fff]", text) and len(normalize_subtitle(text)) < 4)
        caption_band = (.80, .87) if game == "witcher3" else (.85, .96) if game == "cyberpunk" else (.72, .96) if game == "honkai3" else (.79, .96)
        # HEAVY RAIN's documents and thought options can repeat the spoken
        # paragraph above its centered subtitle lane.
        if game == 'heavyrain' and not caption_band[0] <= top <= caption_band[1]:
            continue
        # Moving harvest names can match a unique voiced word exactly. Keep
        # single short words only in the observed centered caption band.
        if (short_label or known_ui_label) and not caption_band[0] <= top <= caption_band[1]:
            continue
        # Response menus sit to the right, above the centered caption.
        if left > (.52 if game == "cyberpunk" else .60) and top < (.84 if game == "cyberpunk" else .80):
            dialogue_menu = True
            continue
        if not .22 <= (left + right) / 2 <= .78:
            continue
        rows.append(row)
    return {**response, "lines": rows, "dialogue_menu": dialogue_menu}
