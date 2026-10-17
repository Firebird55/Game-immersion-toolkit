
import pytest
from backend.capture import CaptureService
from backend.models import CaptureRegion
from backend.windows import WindowInfo
from PIL import Image, ImageDraw

@pytest.mark.parametrize("resolution",[(1280,720),(1920,1080),(2560,1440),(3840,2160),(3440,1440),(800,600)])
@pytest.mark.parametrize("dpi_zoom",[1,1.25,1.5,1.75,2])
def test_capture_regions_follow_physical_client_pixels_without_double_scaling(resolution,dpi_zoom):
    # Windows returns DPI-aware physical client bounds; relative regions operate
    # on those pixels, not CSS/logical pixels or the PC's display scaling factor.
    w,h=resolution;window=WindowInfo(1,"fixture","game.exe",(-w,120,w,h))
    region=CaptureRegion(left=.1,top=.6,width=.8,height=.25)
    bounds=CaptureService._region_bounds(window,region)
    assert bounds==(-w+round(w*.1),120+round(h*.6),round(w*.8),round(h*.25))
    assert bounds[2]>0 and bounds[3]>0

@pytest.mark.parametrize("zoom",[.75,1,1.25,1.5,2])
def test_hito_dynamic_boxes_follow_resized_layout_not_saved_pc_coordinates(zoom):
    width,height=1920,1080
    panel_width=min(.8,.44*zoom);panel_height=min(.3,.15*zoom)
    left=(1-panel_width)/2;top=.93-panel_height;right=left+panel_width;bottom=.93
    image=Image.new("RGB",(width,height))
    ImageDraw.Draw(image).rectangle((round(left*width),round(top*height),round(right*width),round(bottom*height)),outline="white",width=6)
    region=CaptureService._hito_box_regions(image)["dialogue"]
    assert abs(region.top-top)<.015
    assert abs(region.top+region.height-bottom)<.015


def test_ultrawide_does_not_shrink_subtitle_height_and_small_windows_are_enlarged():
    normal = WindowInfo(1, "fixture", "game.exe", (0, 0, 2560, 1440))
    wide = WindowInfo(1, "fixture", "game.exe", (-5120, 120, 5120, 1440))
    normal_crop = Image.new("RGB", (2048, 460))
    wide_crop = Image.new("RGB", (4096, 460))
    assert CaptureService._ocr_image(normal_crop, normal).height == CaptureService._ocr_image(wide_crop, wide).height
    small = WindowInfo(1, "fixture", "game.exe", (100, 50, 1280, 720))
    assert CaptureService._ocr_image(Image.new("RGB", (1024, 230)), small).height > 230
    assert normal_crop.size == (2048, 460) and wide_crop.size == (4096, 460)


def test_tiny_calibrated_crop_stays_inside_window_at_low_resolution():
    window = WindowInfo(1, "fixture", "game.exe", (-800, 120, 800, 600))
    region = CaptureRegion(left=.99, top=.99, width=.01, height=.01)
    x, y, w, h = CaptureService._region_bounds(window, region)
    assert x >= -800 and y >= 120 and x + w <= 0 and y + h <= 720


def test_windowed_capture_uses_client_origin_without_borders(monkeypatch):
    from types import SimpleNamespace
    from backend import windows
    def client(hwnd, pointer):
        pointer._obj.right, pointer._obj.bottom = 1280, 720
        return True
    def origin(hwnd, pointer):
        pointer._obj.x, pointer._obj.y = -1920, 150
        return True
    monkeypatch.setattr(windows, "user32", SimpleNamespace(GetClientRect=client, ClientToScreen=origin), raising=False)
    assert windows._window_bounds(1) == (-1920, 150, 1280, 720)


@pytest.mark.parametrize("game", ["nte"])
@pytest.mark.parametrize("size", [(800,600), (1920,1080), (3440,1440), (3840,2160)])
def test_new_game_default_crops_agree_with_profiles_and_stay_in_client_bounds(game, size):
    from backend.models import AppSettings
    from backend.games import GAME_PROFILES
    region = getattr(AppSettings(), f"{game}_region")
    assert region == GAME_PROFILES[game].subtitle_region
    width, height = size
    window = WindowInfo(1, "Synthetic game", "game.exe", (-width, 120, width, height))
    x, y, w, h = CaptureService._region_bounds(window, region)
    assert -width <= x < x + w <= 0 and 120 <= y < y + h <= 120 + height


@pytest.mark.parametrize('size', [(800, 600), (1280, 800), (1920, 1200), (1920, 1080), (3440, 1440), (5120, 1440)])
def test_explicit_picture_area_preserves_aspect_ratio_and_physical_origin(size):
    width, height = size
    original = WindowInfo(1, 'Synthetic game', 'game.exe', (-width, 120, width, height))
    picture = CaptureService._picture_window(original, '16:9')
    x, y, w, h = picture.bounds
    assert abs(w/h-16/9) < .003
    assert -width <= x < x+w <= 0 and 120 <= y < y+h <= 120+height
    assert abs((x+width)*2+w-width) <= 1
    assert abs((y-120)*2+h-height) <= 1
    assert original.bounds == (-width, 120, width, height)
    assert CaptureService._picture_window(original, 'window') is original


def test_preview_uses_same_picture_coordinates_and_can_preview_unsaved_choice(tmp_path, monkeypatch):
    from backend.models import AppSettings
    from backend.games import GAME_PROFILES
    from backend.tests.test_subtitle_capture import fixture_service
    import backend.capture as module
    service, _, _, _ = fixture_service(tmp_path)
    service.settings.save(AppSettings(nte_picture_area='window'))
    window = WindowInfo(1, 'Synthetic game', 'HTGame.exe', (-800, 120, 800, 600))
    monkeypatch.setattr(module, 'find_active_game_window', lambda _: (GAME_PROFILES['nte'], window))
    seen = []
    service._capture = lambda bounds: seen.append(bounds) or Image.new('RGB', bounds[2:], 'white')
    try:
        region = service.settings.get().nte_region
        assert service.preview_for_region(region, '16:9')
        assert seen[-1] == CaptureService._region_bounds(CaptureService._picture_window(window, '16:9'), region)
        assert service.settings.get().nte_picture_area == 'window'
        assert service.preview_for_region(region)
        assert seen[-1] == CaptureService._region_bounds(window, region)
    finally:
        service._executor.shutdown()
