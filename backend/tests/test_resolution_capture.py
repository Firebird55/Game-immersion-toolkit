
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
