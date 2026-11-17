"""Physical crop geometry shared by desktop capture and native frame adapters."""


def picture_bounds(bounds, area):
    if area != '16:9':
        return bounds
    x, y, width, height = bounds
    picture_width = min(width, round(height * 16 / 9))
    picture_height = min(height, round(width * 9 / 16))
    return (x + (width - picture_width) // 2, y + (height - picture_height) // 2,
        picture_width, picture_height)


def region_bounds(bounds, region):
    x, y, width, height = bounds
    left = x + min(width - 1, round(width * region.left))
    top = y + min(height - 1, round(height * region.top))
    return (left, top,
        max(1, min(x + width - left, max(50, round(width * region.width)))),
        max(1, min(y + height - top, max(50, round(height * region.height)))))
