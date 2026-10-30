# Native screen PNG fixture

`mobile-native-chinese.png` is a 1280 × 720 lossless raster of the authored
synthetic subtitle card in `CHINESE_VIDEO` from `tests/mobile-media-fixtures.mjs`.
It contains the test sentence “我们可以继续走了。” and no game assets.

The PNG was captured by drawing that local fixture's decoded video frame to a
same-sized canvas after 0.1 seconds in Chromium, then calling
`canvas.toDataURL('image/png')`. The subtitle card is static throughout the clip.

The native receiver test loads this raster with `Image.decode()` and adds a
moving colored square before sending each correlated PNG response. It therefore
tests actual Chinese pixels, fresh frame delivery, cropping, OCR, catalog matching
and reader output without requiring CJK fonts or a video decoder inside the
synthetic VDO viewer. Browser video-adapter decoding is tested separately.
