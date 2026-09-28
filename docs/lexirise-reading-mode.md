# Lexirise reading mode

Status: implemented locally, 28 September 2026. The website offers **Migaku** and **Lexirise** reading modes. Lexirise provides the built-in press-to-lookup experience; Yomitan is not required. The Translation tab from the reference images is intentionally omitted.

## Reading the transcript

- `POST /v1/analyze/text` segments a saved Chinese line, returns UTF-16 offsets, tone-marked Pinyin, tones, word IDs, English glosses, and learner state. The website renders the official text in its original order; punctuation and gaps remain selectable text. Analysis is cached for 10 minutes. Missing glosses are fetched in the background so a new line is shown without waiting for a dictionary request.
- Reading options independently set Pinyin, Zhuyin, separate tone marks, inline English glosses, and tone colors to **unknown words**, **all words**, or **off**. The five editable default tone colors follow the existing Migaku palette. Zhuyin spelling is converted locally, with Lexirise tones applied. Settings are stored in browser localStorage.
- Pressing a word opens the Lexirise sheet. **T/L/F/K** set tracked (1), learning (2), fresh (3), and known (4). A saved item is patched; an unsaved word is created only when its state button is pressed. The selected state immediately updates visible instances of that word.

## Word sheet

| View or control | Implementation | Limit |
| --- | --- | --- |
| Header and play | Hanzi, Lexirise Pinyin, alternate readings, Zhuyin, and this device's Chinese browser speech voice. | Lexirise's public API does not document a word-audio endpoint. Voice quality depends on installed browser/Windows voices. |
| Definition | Lexirise English meaning and part of speech, HSK, characters with Pinyin and gloss for multi-character words, supplemental dictionary entries, frequency rank/score. | Supplemental sections appear for whichever dictionaries the public lookup response returns. The user's other installed dictionaries did not appear in four tested live responses. |
| Context | `POST /v1/analyze/context` for the selected occurrence in its saved line, plus a question field for nuance, grammar, or tone. | On-demand model call may take several seconds or fail; the sheet provides retry. |
| Examples | Up to five Lexirise dictionary examples, with Chinese reading annotations and English translation. Play uses device speech. Bookmark explicitly saves the example sentence and translation through `POST /v1/vocabulary`. | The dictionary response has no example-audio URL. A bookmarked example is text only. |
| Similar | On-demand Lexirise context question requests nearby words; each proposed Hanzi word is checked through dictionary lookup before display. Pinyin, dictionary meaning, and the generated usage note are shown. | This is an AI suggestion, not a dedicated synonyms API. It may describe related expressions in the wider phrase rather than interchangeable words. The view reports an empty or failed result instead of inventing one. |
| Components | Lexirise character components and hints, when present. | Detail depends on the dictionary response. |

The popup loads only the selected view's extra data, and caches lookup, character, context, and Similar results. This keeps newly captured lines and the initial popup responsive. Word lookup stays in the app; there is no Yomitan dependency.

## Dictionary coverage checked

Live read-only `POST /v1/dictionary/lookup` probes for `总是`, `单词`, `词语`, and `朋友` all returned the English translation fields and only `CC-CEDICT` in `supplementalEntries`. `总是` returned HSK 3 and frequency rank 1,872. The parser renders every dictionary entry sent by that array and accepts both list and plain-paragraph HTML. Other dictionaries attached in the Lexirise app may be available only in that app or through a separate API contract; they cannot currently be displayed from these responses. This needs Lexirise confirmation or a documented endpoint before promising parity.

`单词` returned three examples, `词语` one, and `朋友` three. A live saved-line lookup for `是` showed two CC-CEDICT entries and its HSK/frequency information. Examples, Context, and Similar were opened in the running website and displayed API results. In the saved line `他们不过是找个理由…`, the Similar suggestions reflected the meaning of the **phrase** `不过是`; they should be treated as related expressions, not direct substitutions for `是`.

The live `出来` character request returned Pinyin, English glosses, and components for both characters. The actual Chrome window on the Duet iPad displayed the Lexirise reader and history without horizontal overflow. With wired Realtek headphones selected, the running app received loopback samples at nonzero levels from a Windows test sound. During live ZZZ dialogue it matched Zhu Yuan's English subtitle to the official Chinese at 100%, saved line 1712 with an original audio clip, and served a decodable 8.33-second non-silent MP3. Sending that line to Lexirise returned deck 1950 success; retrying returned `already_sent: true`.

## Captured voice and example voice

The existing **Send to Lexirise** action for a captured game sentence uploads its available original voice clip through `POST /v1/vocabulary/audio`, includes the returned public URL in the saved sentence's `audioUrls`, and adds that sentence to the game's snapshot deck. A focused mock-API test checks the uploaded bytes, URL, translation, deck membership, and retry idempotency. This is separate from the word sheet's browser speech and its text-only example bookmarks. Sending a captured sentence is still explicit; viewing a line never uploads its audio.

## API and local data

The official [Lexirise API reference](https://lexirise.app/api-reference) documents the `analyze/text`, `analyze/context`, `dictionary/lookup`, `vocabulary`, and `vocabulary/audio` calls used here. The API key is stored with Windows DPAPI in Local AppData for this PC; it is not sent to React or stored in the repository. A copied installation on another PC needs that PC's own credential setup because DPAPI is tied to a Windows user.

The backend accepts a transcript line ID and token start offset, then validates the word against the saved official Chinese line. Lexirise offsets are UTF-16 units, which match JavaScript `slice` even when the line contains emoji. State and example-save routes require the companion's custom header. The reader caches analysis for 10 minutes, dictionary/character data for 30 days, context answers for 30 days, and Similar suggestions for 7 days.

## Remaining device and service checks

- Test a real press, text wrap, popup scroll, and speech voice on the connected iPad through Duet, and on the home secondary screen. Browser layout checks do not prove Duet touch or audio behavior.
- Ask Lexirise whether user-installed dictionaries and recorded example/word audio are available through its public API. Only the response fields above have been observed.
- If a dedicated synonyms endpoint is added, replace the context-question Similar view. Its current generated notes can be slow and sometimes describe the surrounding phrase.
