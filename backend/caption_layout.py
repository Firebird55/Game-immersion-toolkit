"""Positioned subtitle/menu geometry shared with desktop capture."""
import re
import math
from dataclasses import dataclass

from .models import CaptureRegion, TextMatch, is_comic_text_id
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


def spatial_text_groups(response: dict, bounds: tuple[int, int, int, int] | None = None) -> list[str]:
    """Reassemble OCR rows into comic bubbles using their screen geometry."""
    positioned = []
    fallback = []
    for line in response.get("lines", []):
        text = str(line.get("text", "")).strip()
        if not text:
            continue
        rectangle = line.get("bounding_rect") or {}
        try:
            xs = [float(rectangle[f"x{index}"]) for index in range(1, 5)]
            ys = [float(rectangle[f"y{index}"]) for index in range(1, 5)]
        except (KeyError, TypeError, ValueError):
            if bounds is None:
                fallback.append(text)
            continue
        left, right = min(xs), max(xs)
        top, bottom = min(ys), max(ys)
        if bounds is not None:
            x, y, width, height = bounds
            if not (x <= left < right <= x + width and y <= top < bottom <= y + height):
                continue
        fallback.append(text)
        if right > left and bottom > top:
            positioned.append({
                "text": text,
                "left": left,
                "right": right,
                "top": top,
                "bottom": bottom,
            })
    if len(positioned) != len(fallback):
        return fallback

    positioned.sort(key=lambda item: (item["top"], item["left"]))
    groups: list[dict] = []
    for item in positioned:
        item_height = item["bottom"] - item["top"]
        best_group = None
        best_distance = float("inf")
        for group in groups:
            group_height = max(1.0, group["line_height"])
            vertical_gap = item["top"] - group["bottom"]
            if vertical_gap < -max(item_height, group_height) or vertical_gap > max(
                48.0, group_height * 2.4
            ):
                continue
            overlap = min(item["right"], group["right"]) - max(
                item["left"], group["left"]
            )
            narrow_width = min(
                item["right"] - item["left"],
                group["right"] - group["left"],
            )
            aligned = abs(item["left"] - group["left"]) <= max(
                12.0, group_height * 1.25
            )
            centered = abs(
                (item["left"] + item["right"] - group["left"] - group["right"]) / 2
            ) <= max(12.0, group_height * 1.25)
            # Partial column overlap also occurs between separate bubbles.
            # Centered short final rows need substantial containment; mere
            # overlap must not join a diagonally adjacent bubble or effect.
            if not aligned and not (centered and overlap >= narrow_width * 0.8):
                continue
            distance = abs(vertical_gap) + abs(item["left"] - group["line_left"]) * 0.15
            if distance < best_distance:
                best_group = group
                best_distance = distance
        if best_group is None:
            groups.append({
                "lines": [item],
                "left": item["left"],
                "right": item["right"],
                "top": item["top"],
                "bottom": item["bottom"],
                "line_left": item["left"],
                "line_height": item_height,
            })
            continue
        best_group["lines"].append(item)
        best_group["left"] = min(best_group["left"], item["left"])
        best_group["right"] = max(best_group["right"], item["right"])
        best_group["bottom"] = max(best_group["bottom"], item["bottom"])
        best_group["line_left"] = item["left"]
        best_group["line_height"] = (best_group["line_height"] + item_height) / 2

    # Comic dialogue advances horizontally. Several bubbles may become
    # visible before one OCR pass, and ordering them by vertical position
    # would put an upper-right bubble before a lower-left bubble. Preserve
    # the game's reading sequence: columns left-to-right, then top-to-bottom
    # only when multiple bubbles occupy the same column.
    groups.sort(key=lambda group: (group["left"], group["top"]))
    return [
        " ".join(
            item["text"]
            for item in sorted(group["lines"], key=lambda row: (row["top"], row["left"]))
        )
        for group in groups
    ]

def is_cinematic_fragment(match: TextMatch | None, cinematic_matches) -> bool:
    """Give the broad scan ownership of comic matches visible in overlapping crops."""
    if match is None:
        return False
    source = normalize_subtitle(match.source_ocr)
    if not source:
        return False
    for cinematic in cinematic_matches:
        if not is_comic_text_id(cinematic.text_id):
            continue
        if match.text_id == cinematic.text_id:
            return True
        visible = normalize_subtitle(cinematic.source_ocr)
        if len(visible) <= len(source) or source not in visible:
            continue
        for fragment_text, full_text in ((match.english, cinematic.english),
                (match.chinese, cinematic.chinese), (match.source_text, cinematic.source_text)):
            fragment = normalize_subtitle(fragment_text or "")
            full = normalize_subtitle(full_text or "")
            if fragment and len(fragment) + 8 <= len(full) and fragment in full:
                return True
    return False
