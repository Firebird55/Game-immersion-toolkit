# Lexirise word lookup

Word lookups use a nonmodal popover attached to the pressed word. The popup prefers the space below the word, flips above it when needed, and shifts horizontally to remain within the screen. Its maximum size is 540 × 500 CSS pixels, reduced to fit the viewport and available space. Only its content scrolls; the transcript remains interactive. Outside clicks, Escape, the close button, and pressing the same word dismiss it. Keyboard opening restores focus to the word on close.

Definition shows all English meanings with part-of-speech badges, HSK, the returned supplemental dictionaries, character summaries, character explanations, component cards, and frequency. Other tab behavior is unchanged.

Component cards also load their pinyin, gloss, and character explanation from Lexirise. The explanation for the component's role in its parent character is kept separately from its own character explanation. This enrichment runs through the character-details endpoint after the main definition has rendered, uses the existing 30-day character cache, fetches direct components concurrently, and never recursively expands grandchildren. Missing component requests preserve the available definition and offer a retry.

## Verification — October 3, 2026

TypeScript checking and production build passed. Browser checks used real, read-only Lexirise responses for 要 and 总是, with those responses replayed through an isolated test page importing the actual ReadingText component and application stylesheet.

Verified viewport sizes/positions: 1200×900 top; 820×1180 top and bottom; 620×960 middle; 375×667 top and bottom; 1200×500 middle. All checks confirmed popup containment, vertical separation from the pressed word, no modal overlay or page scroll lock, all five meanings and four part-of-speech labels for 要, component explanations in Definition, outside dismissal, Escape, keyboard focus restoration, and switching directly to 总是. This verifies browser layout; the disconnected physical iPad was not tested during this change.

All 11 reading-service tests passed, including preservation of all senses, API-supplied component pinyin and explanations, reuse of cached parent/child lookups, and exclusion of pictographic symbols and recursive grandchildren from additional requests. Browser checks also confirmed 女 displays its returned pinyin and “woman” gloss within Definition.
