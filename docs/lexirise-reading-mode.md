# Lexirise reading mode for Proxy Transcript

Status: implemented locally, 28 September 2026. The reading selector offers **Migaku** and **Lexirise**. The existing manual **Send to Lexirise** buttons remain separate.

## What is built

- `backend/reading.py` uses the Windows-only Lexirise credential, analyzes saved lines by ID, validates ordered UTF-16 ranges, and caches sentence analysis for 10 minutes. Lexirise's `occurrences` supply tone marked Pinyin and tones; `entryMetaById.gloss` supplies English meanings for known and unknown words. Analysis returns without waiting for missing dictionary glosses. Up to four missing unknown words are looked up in the background and cached. Zhuyin spelling is converted locally with `pypinyin`, using Lexirise's tone values.
- `GET /api/lines/{id}/reading` returns normalized tokens without exposing the key. `GET /api/lines/{id}/reading/lookup?start=…` looks up the word at that position only when pressed. It returns Lexirise English translations and examples, CC-CEDICT definitions, HSK level when present, frequency rank and score, alternate readings, and character components when present. The parser converts supplemental dictionary HTML to plain text before sending it to the browser. Dictionary data is cached locally for 30 days; an older cache format is ignored.
- `GET /api/lines/{id}/reading/context?start=…` asks Lexirise to explain the selected occurrence in its full saved sentence. This request starts only after opening the Context tab. `GET /api/lines/{id}/reading/characters?start=…` fetches each unique Hanzi in a multi-character word only when its Components tab opens; individual character metadata is cached for 30 days. `POST /api/lines/{id}/reading/proficiency` updates a selected word to tracked, learning, fresh, or known only after a user presses its state button. The route accepts a line ID and token offset, validates the word server-side, and requires the companion's custom header. A saved Lexirise item is patched; an unsaved one is created through the vocabulary endpoint. No captured line automatically creates vocabulary.
- `app/reading-text.tsx` renders selectable Hanzi with Pinyin, Zhuyin, tone marks, and glosses as soon as sentence analysis returns. When dictionary glosses are still pending, the visible line refreshes briefly in the background. Tapping a word opens a responsive sheet with **Definition**, **Translation**, **Context**, and **Components** tabs. Its T/L/F/K controls reflect Lexirise levels 1/2/3/4, and a successful update refreshes all visible instances of the word immediately. The pronunciation button uses this device's browser speech voice (`zh-CN`); Lexirise does not document a word-audio endpoint. Yomitan can still scan the underlying text in browsers where its touch setting is enabled. Browser localStorage remembers each display scope and the five tone colors.
- The **Reading options** dialog offers unknown/all/off independently for Pinyin, Zhuyin, separate tone marks, inline translation, and tone colors. The default colors follow [Migaku's tone mapping](https://migaku.com/blog/chinese/chinese-language-tones): first red, second yellow, third green, fourth blue, neutral gray. Each color is editable and can be reset. When Lexirise supplies one tone per Hanzi, a text gradient colors each character while preserving one selectable word node for Yomitan. Other words fall back to their first tone color.
- Migaku keeps its fresh-node current-line behavior and remains the default. The mode selector can be changed at any time without changing transcript records.

Live API verification on a saved ZZZ sentence returned 36 tokens with Pinyin, Zhuyin, tone data, and English glosses. A live lookup for `是` returned rank 2, HSK 1, two CC-CEDICT entries, two components, and an alternate reading. The context endpoint returned the selected word's meaning in the sentence. A multi-character `出来` component request returned both characters. A live proficiency request preserved the already-known state of `是` through Lexirise's PATCH endpoint. The word sheet was checked in the running local browser at a narrow portrait viewport. The actual iPad and Yomitan touch behavior still need a device check.

## Target experience

Keep the current English line and official Chinese line. In Lexirise mode, segment the Chinese sentence into tappable words as in the supplied screenshot. Color words by Mandarin tone with an editable Migaku-like palette, place an optional short English meaning below words, and show optional Pinyin, Zhuyin, or tone marks above them. Each display setting supports unknown words, all words, or off. Preserve the exact official Chinese text, punctuation, and word order. A word tap opens the cached definition. Current line and History use the same annotations; the narrow iPad layout wraps word groups cleanly without shrinking Hanzi.

This is a **display and lookup** option, not an automatic vocabulary export. Never automatically create saved words or send captured audio because a line appears on screen.

## Relevant API contracts

Lexirise's [API reference](https://lexirise.app/api-reference) documents Pro-account authentication with `Authorization: Bearer …` or `x-api-key`, base URL `https://api.lexirise.app`, and 1,200 requests per hour. This PC stores the user's key with Windows DPAPI in Local AppData; the existing backend also supports its ignored `data/lexirise/key.dpapi` path. No key belongs in React, localStorage, a URL, a log, or this document.

| Need | Endpoint | Use |
| --- | --- | --- |
| Sentence segmentation, Pinyin, tones, gloss, entry IDs, learner state | `POST /v1/analyze/text` | Send `{ "text": "…", "language": "zh", "fast": true }` from the Python backend. Response includes `occurrences` with `word`, `charStart`, `charEnd`, `entryId`, `transliteration`, and tones; `entryMetaById` includes glosses and tones; `stateByEntryId` gives proficiency. |
| Full analysis when fast result is provisional | `POST /v1/analyze/text` | Repeat with `fast: false` after a short delay only when needed. `morphoPending: true` says refined segmentation is pending. Do not poll each render. |
| Fallback meaning when analysis has no gloss | `POST /v1/dictionary/lookup` | Look up distinct unknown words with missing glosses, cache the English dictionary translation, and reuse it across lines. |
| Optional later contextual meaning | `POST /v1/analyze/context` | Send a sentence and token offsets for a meaning specific to that occurrence. This is researched but not called in the current renderer because it would multiply latency and API usage. |
| Explicit vocabulary state selection | `POST /v1/vocabulary`, `PATCH /v1/vocabulary/{id}` | Tracked 1, learning 2, fresh 3, known 4. Only a status button calls these endpoints. |

The [Yomitan scanning settings](https://github.com/yomidevs/yomitan/blob/master/ext/templates-modals.html) support mouse, touch, and pen inputs. Yomitan can already scan selectable text in the Windows Chrome window, including one shown on the iPad through Duet. Its [local API](https://github.com/yomidevs/yomitan-api/blob/master/README.md) is optional and device-local. It is unnecessary for the first version of this feature.

## Lookup interaction

Press a Hanzi word to open the Lexirise sheet. The word stays as real DOM text so Yomitan can also scan it when touch scanning is enabled in the Chrome profile shown through Duet. Test an actual press on the iPad; browser automation at a narrow viewport cannot prove how Duet sends touch events. The inline glosses, pinyin, and colors come from Lexirise analysis.

The built-in tap sheet provides lookup without relying on Yomitan. The dictionary call runs only when a word is pressed and is cached locally. The sentence and analysis gloss stay visible if a dictionary request is slow or fails, with a retry control. `/v1/analyze/context` makes a separate request only when the Context tab is opened, which preserves API quota and keeps the initial sheet quick.

## Data and rendering design

The local endpoint accepts a transcript line ID and loads its official Chinese text from SQLite. The backend validates monotonic, non-overlapping Lexirise ranges before returning tokens. Lexirise offsets count **JavaScript UTF-16 units**: a probe of `你好🙂朋友朋友` placed the emoji at `2..4` and the two `朋友` tokens at `4..6` and `6..8`. The React renderer uses those ranges with JavaScript `slice`, preserving punctuation and gaps as plain text. An invalid token is omitted while the official sentence remains visible.

`stateByEntryId` determines the documented proficiency levels: 0 unknown, 1 tracked, 2 learning, 3 fresh, and 4 known. Proficiency controls which words count as unknown for display settings. Lexirise supplies the Pinyin and tones; the local `pypinyin` converter supplies Zhuyin phonetic symbols, and Lexirise's tones override local tone guesses. The word component stacks whichever annotations are enabled around one selectable Hanzi text node. The Migaku branch keeps its existing fresh DOM node, while the Lexirise branch uses normal React text. All reader settings persist per browser.

Potential refinements: deduplicate simultaneous requests for the same uncached sentence across browser tabs, add a rate-budget indicator, and source word audio from Lexirise if a documented API endpoint becomes available. A browser session currently avoids refetching the same line, and the backend caches analysis, meanings, dictionary data, and context across sessions.

## Checks before release

- The real `zh` analysis and dictionary response have been verified on a saved ZZZ sentence. Confirm that read-only analysis does not alter the user's vocabulary count if that becomes a concern.
- Test unknown, tracked, learning, fresh, known, and missing `stateByEntryId`; duplicated words; punctuation; emoji; no dictionary result; `morphoPending`; 401/429/timeouts; and a line that changes while analysis is pending.
- Inspect at the current Duet viewport and the home portrait monitor. Test touch target size, word wrapping, scroll, popup placement, and Yomitan scanning in the actual Chrome profile.
- Check that API credentials do not appear in network responses, HTML, browser storage, logs, or Git; verify the 1,200/hour budget with cache metrics.

## Open contract questions

- A live read-only probe returned tone-marked Chinese pinyin (`nǐhǎo`, `péngyou`) and `POST /v1/analyze/context` returned `conciseMeaning: "friend"` with `reading: "péngyou"`. Less common names, polyphonic words, and provisional `morphoPending` responses still need review.
- The API docs do not show a batch context endpoint. The current implementation uses cached dictionary meanings, which may be less precise for polysemous words. A future context pass should be limited to selected words to protect the 1,200/hour quota.
