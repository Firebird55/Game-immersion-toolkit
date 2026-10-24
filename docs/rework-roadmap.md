# Roadmap voor de rework

Status: **voorstel; implementatie niet gestart**. Opgesteld op 2026-10-24 op basis
van onderzoek aan versie **0.19.1**, commit
`16d17f782e3e1d2fbfbd45c624cfe9613e78363a`. Dit document en de
[AI-werkwijze](ai-development-workflow.md) veranderen geen applicatiegedrag en
geven op zichzelf geen opdracht om implementatie of publicatie te starten.

## Richting en scope

Vernieuw de toolkit in afzonderlijk toetsbare stappen: betrouwbare gameherkenning
en transcriptvolgorde, begrijpelijke companions, gezamenlijke onboarding en een
zelfstandige Windows-installer. Behoud voorlopig Python als desktopkern en de
gewone browser voor Browser Extension. Onderzoek Rust of C# alleen voor een
afgebakend onderdeel met een meetbaar probleem.

De roadmap blijft in deze repository, dicht bij implementatie en releasechecks.
Gedeelde leescomponenten blijven eigendom van Lexirise-shared-components.
Er komt geen extra repository, taakdatabase of orchestrationplatform als
voorwaarde voor deze rework.

Lees bij uitvoering eerst [AGENTS.md](../AGENTS.md), [RELEASE.md](../RELEASE.md),
[runtimecontracten](runtime-context.md) en [gerichte checks](development-checks.md).
De AI-werkwijze beschrijft taakgrenzen, review, bewijs en overdracht.
Het [architectuuronderzoek](rework-architecture.md) toetst de actuele code op
upstream `387631f`, beschrijft huidige en gewenste grenzen en onderbouwt de
concrete R12/R13-migratietaken hieronder. Het vervangt geen apparaatvalidatie.

### Invarianten

- Bestaande Chinese transcripten, favorieten, kalibratie, gamepaden, gearchiveerde
  gegevens, userscript-storagekeys en onafhankelijke Browser Extension-modus
  blijven behouden. Het zichtbare label mag veranderen zonder de interne
  `migaku`-waarde of bestaande voorkeuren stilzwijgend te breken.
- Bron-, runtime-, account- en taalwissels maken oude async resultaten ongeldig.
  Een update mag geen twee actieve capture-eigenaren achterlaten. Mislukte
  voorbereiding houdt de laatste complete index beschikbaar.
- Officiële tekst- en voice-identiteiten komen uit geverifieerde gamegegevens.
  Onzekere tekst, audio of verhaalvolgorde wordt niet verzonnen. Nog ontbrekende
  of mislukte audio-extractie verwijdert geen reeds bevestigde regel. Bestaande
  mapping-/toelatingsvoorwaarden blijven gelden, inclusief expliciete
  uitzonderingen voor audioloze ZZZ-comics; geen algemene verruiming naar ongemapte tekst.
- Echte accounts worden alleen read-only onderzocht; tests voor accountwrites
  gebruiken mocks. Credentials blijven in de bestaande beschermde opslag;
  geen persoonlijke sleutels in repository of workflow secrets.
- Gamebestanden worden niet gewijzigd. Opnames, gamebeelden, databases, lokale
  paden, accountdiagnostiek en privé-streamlinks worden niet gepubliceerd.
  Pages bevat uitsluitend allowlisted statische assets.
- Shared wijzigingen gebeuren upstream, met versiepublicatie, `shared:update`
  en controle/commit van beide consumers volgens AGENTS.md. Geen vendorpatches.
- Releases gebruiken GitHub-hosted Actions en het bestaande releaseproces;
  levering is niet afhankelijk van Argo of een cluster.

## Onderzoeksbasis en onzekerheden

Deze bevindingen beschrijven de genoemde baseline, geen nieuwe live verificatie.
Controleer de relevante code opnieuw wanneer een werkpakket begint.

Voor de documentatie-PR is de branch bijgewerkt naar upstream `387631f`.
Sinds de onderzoeksbaseline zijn onder meer mobiele comic-/voicewijzigingen
([PR #34](https://github.com/Firebird55/Game-immersion-toolkit/pull/34)) en
account-/taal-/gamekeuzewijzigingen
([PR #35](https://github.com/Firebird55/Game-immersion-toolkit/pull/35)) geïntegreerd.
Onderstaande bevindingen blijven historische onderzoeksgegevens. Hergebruik
bestaande oplossingen en tests; bepaal bij de taakstart welk acceptatiebewijs
al bestaat en welk werk nog nodig is. Deze documentatie valideert die nieuwe
implementaties niet opnieuw.

| Bevinding | Bewijs in de baseline | Gevolg voor de roadmap |
| --- | --- | --- |
| Desktop-ZZZ sorteert comicgroepen op `(left, top)` | `_spatial_text_groups` in [capture.py](../backend/capture.py) en [capturetests](../backend/tests/test_capture.py) | Tijd/context moet volgorde bepalen; een bestaande test kan de verkeerde aanname vastleggen |
| Legacy en meertalige ZZZ-matching verschillen | `_match_cinematic_fragment` in [textmaps.py](../backend/textmaps.py), `match_line_groups` in [multilingual_index.py](../backend/multilingual_index.py), `activate_language` in [api.py](../backend/api.py) | Gedragspariteit testen vóór refactoring; nog geen gereproduceerde native misser |
| Mobiele ZZZ-controller selecteert doorgaans één match per scan | [mobile-ui.mjs](../public/mobile-capture/mobile-ui.mjs), [library.mjs](../public/mobile-capture/library.mjs) | Meerdere bubbles en identiteit over frames expliciet modelleren |
| Replay vergelijkt vooral sets van tekst-ID's | [desktopreplay](../scripts/replay-video-ocr.py), [browserreplay](../scripts/replay-mobile-ocr.mjs) | Verkeerde volgorde, duplicatie en vertraging kunnen buiten de huidige criteria vallen |
| Mobiele badge reduceert bronstatus tot connected/niet connected | [companion.jsx](../mobile/companion.jsx), [capture.js](../public/mobile-capture/capture.js), [frame-source.mjs](../public/mobile-capture/frame-source.mjs) | Stilstaand beeld is geen bewijs van een verbroken verbinding of gesloten game |
| Mobiele leesopties zijn onvoorwaardelijk; updateknop wordt bij actieve bron geblokkeerd | [companion.jsx](../mobile/companion.jsx) | Modusafhankelijke bediening; banner verwijderen met behoud van veilig cachegedrag |
| Handmatige paden bestaan al; discovery gebruikt Steam-bibliotheken en mapnamen | [game_paths.py](../backend/game_paths.py), [toolkit-setup.tsx](../app/toolkit-setup.tsx), [folderpicker](../scripts/select-game-folders.ps1) | Eén service voor installer en WebUI; manifestadapters en echte packinventaris ontbreken |
| Distributie is bron-ZIP plus frontend, met runtimes/dependencies tijdens setup | [package-release.mjs](../scripts/package-release.mjs), [setup.ps1](../scripts/setup.ps1), [game_tools.py](../backend/game_tools.py) | Een installer vereist bundeling en functionele probes, niet alleen een wrapper |
| Frontend start met Node/Wrangler; native OCR-timeout vervangt een threadpool | [companion-runtime.ps1](../scripts/companion-runtime.ps1), [capture.py](../backend/capture.py) | Statische frontend en beëindigbaar workerproces onderzoeken; geen bewezen performancewinst of native hang |

Het onderzoek telde 36 actieve videoclips in de bestaande manifesten, zonder ZZZ.
De [historische browserreplay](mobile-library-verification.md) rapporteert 35/54
geslaagde cases; dat is geen actuele score van 0.19.1. Screenshots bewijzen
presentatie, maar zonder tijdcodes geen chronologie. Er zijn in het onderzoek
geen nieuwe native Windows-, video-OCR- of fysieke iOS-proeven uitgevoerd.
Starttijd, geheugen, energiegebruik en p95-latency zijn nog niet vergelijkbaar
gemeten. De roadmap behandelt die punten als open bewijs, niet als geslaagde gates.

## Indeling: drie parallelle werkstromen

De grote onderdelen zijn werkstromen met eigen subtaken, geen opeenvolgende
projectfasen. Eén persoon of team is eigenaar van elke werkstroom en kan daar
AI-agents inzetten. Iedere subtaak omvat onderzoek, implementatie, tests en
oplevering van haar eigen resultaat. Er is geen algemene voorbereidingsfase F0.
De werkstromen kunnen zelfstandig starten en begrensde resultaten opleveren;
ze zijn niet volledig losgekoppeld. Alleen de benoemde interfacewijzigingen en
gezamenlijke eindproeven vereisen overdracht. Een hele werkstroom afronden is
geen algemene voorwaarde om een andere te starten.

**P0:** correctheid of bewijs vóór de betreffende wijziging/release.
**P1:** directe productverbetering. **P2:** voorwaardelijk experiment.
Prioriteit is geen kalenderplanning. Raming gebeurt per subtaak zodra scope en
benodigde middelen bekend zijn; er wordt geen vaste AI-snelheidsfactor aangenomen.

| Werkstroom | Prioriteit | Verantwoordelijke | Zelfstandig resultaat | Eerste subtaken |
| --- | --- | --- | --- | --- |
| W1 — Companions en gebruikerservaring | P1; statuscorrectheid P0 | Eigenaar UX | Begrijpelijke, compacte desktop- en mobiele bediening | R03, R04 of R05; onderling rekening houden met gedeelde bestanden |
| W2 — OCR en transcriptbetrouwbaarheid | P0 | Eigenaar OCR | Correcte dialoogidentiteit en volgorde, beschermd met replay en regressies | R01; meetplan R02a parallel voorbereiden |
| W3 — Installatie en gamebeheer | P1; databehoud P0 | Eigenaar installatie | Gamedetectie, onboarding en zelfstandige Windows-installatie | R14 en R18; meetplan R02b voorbereiden |

Alle uitvoeringspakketten staan op **planned**. De R-ID's blijven herkenbaar uit
de eerdere indeling. R00 wordt een startcontrole binnen elke taak; R02 wordt
opgesplitst in R02a (OCR), R02b (Windows-bundel) en R02c (optioneel experiment).
R12/R13 zijn nu groepen met concrete architectuursubtaken per werkstroom;
alleen de geraakte grenzen blokkeren een wijziging. R07 is opgesplitst in R07a
(karakterisatie) en R07b (productie-replay) om de controllerextractie testbaar te
maken zonder een cirkelafhankelijkheid.
Voortgang staat bij het taakcontract, niet in een extra verzameling statusbestanden.
De tabelkolom **Afrondingsbewijs** bepaalt het resultaat per subtaak. De checklists
onder elke werkstroom beschrijven het gezamenlijke eindresultaat. Neem bij de
start de relevante criteria, concrete scenario's en commands over in het taakcontract.
Een voorbereidende taak vereist geen bewijs van een latere installer of consumer;
dat ontbrekende integratiebewijs blijft toegewezen aan de genoemde vervolgtaak.
Behoudsinvarianten en toepasselijke regressiechecks gelden bij iedere wijziging.

### Startcriteria per subtaak — voorheen R00

De taakeigenaar gebruikt het bestaande onderzoek en controleert alleen wat voor
de wijziging nodig is. Een nieuwe repositorybrede inventarisatie is geen voorwaarde.

- [ ] Doel, scope, eigenaar en relevante acceptatiecriteria zijn benoemd.
- [ ] Het betrokken pad is tegen de actuele commit gecontroleerd. Waar relevant
  worden legacy desktop, meertalige desktop, mobiele OCR en paired-PC onderscheiden;
  game-/taalondersteuning en apparaatbewijs worden niet gelijkgesteld.
- [ ] Bij een bug is het probleem reproduceerbaar; bij refactoring is het te
  behouden gedrag vastgelegd. Eenvoudige copywijzigingen vragen geen nieuwe testsuite.
- [ ] Alleen benodigde interfaces en harde afhankelijkheden zijn afgestemd.
  Onbekende of ontbrekende middelen blokkeren uitsluitend het afhankelijke werk.

Een bannerreparatie wacht dus niet op een OCR-baseline. Een wijziging aan de
bubblevolgorde wacht wel op haar onafhankelijke sequentiefixtures. Een experiment
met Rust wacht op een gemeten probleem en vooraf gekozen vergelijkingscriteria.

## W1 — Companions en gebruikerservaring

**Eigenaar:** UX. Levert elke afgeronde verbetering afzonderlijk op. R03–R05
hoeven niet op elkaar te wachten; één schrijver tegelijk aan de companionbestanden.
R06 kan hulpontwerp voorbereiden en integreert per afgerond control.
W1 integreert ook de comicweergave voor R09/R10 op basis van de R08-afspraak
met W2. Dat consumerbewijs hoort bij R09/R10; R03–R06 kunnen zelfstandig afronden.

| ID | Afgebakende oplevering | Voorwaarde | Afrondingsbewijs voor deze subtaak |
| --- | --- | --- | --- |
| R03 | Bronstatus behouden tot in de header; aanklikbare diagnose per subsystem | Startcontrole; R12a bij gewijzigde statusvelden, beperkte R13d-extractie waar nodig | Statusmatrix met eerste frame, stilstaand beeld, pauze, reconnect, ontbrekende bibliotheek en accountslot geeft telkens de juiste uitleg; bestaande OCR-events blijven bruikbaar. |
| R04 | Labels Browser Extension/Lexirise API; leesopties alleen bij Lexirise API | Startcontrole van het betrokken pad | Beide modi en beide mobiele leesoptie-ingangen gecontroleerd; oude voorkeuren werken na herladen; bestaande interne waarden en opslagkeys vastgelegd voor R17. |
| R05 | Updatebanner verwijderen, offline cache en veilige activatie behouden | Bestaande updatechecks en lokale reproductie | Banner weg; actieve sessie herlaadt niet; veilige activatie en offline heropening behouden data op de huidige frontendhost. |
| R06 | Permanente uitleg beperken; hulp via focus/hover/tap en herstelacties | R03–R04 voor de betreffende controls | Benoemde controls op desktop/mobiel hebben bereikbare, sluitbare vraagtekenhulp; keyboard/touch/focus gecontroleerd; noodzakelijke fouten blijven zichtbaar. |

**Acceptatie**

- [ ] Ontvangen beeld, beeldactualiteit, OCR, bibliotheek en accountstatus zijn
  afzonderlijk te verklaren. Een ongewijzigd beeld wordt niet als bewezen
  netwerkfout weergegeven. Een geselecteerde game wordt niet als gedetecteerd
  draaiend proces gepresenteerd. Ontvangsttijd heet geen end-to-end latency.
- [ ] Klik/tap op status geeft de reden en een passende vervolgstap voor:
  verbinden, eerste frame, stilstaand beeld, onderbreking, pauze, ontbrekende
  bibliotheek, geen match en accountvergrendeling. Geen privé-link in diagnostiek.
- [ ] Oude `migaku`-voorkeuren blijven werken. Browser Extension biedt
  selecteerbare tekst zonder Lexirise-account. De uitleg noemt Migaku, Yomitan,
  de Lexirise-extensie en andere extensies naar keuze als voorbeelden, met
  platformbeperkingen en zonder ongeverifieerde compatibiliteitsgarantie.
- [ ] Beide mobiele ingangen naar Reading options zijn verborgen buiten
  Lexirise API. Algemene tekstgrootte/vertalingsweergave blijven beschikbaar.
- [ ] Geen updatebanner of automatische reload tijdens spelen. Een wachtende
  update kan bij een veilige volgende start of expliciete Settings-actie
  activeren; offline heropenen behoudt historie, favorieten en kalibratie.
- [ ] Desktop en mobiel tonen compacte hoofdflows; aanvullende uitleg staat
  achter herkenbare, toegankelijk gelabelde vraagtekenknoppen, bereikbaar via
  hover, toetsenbord en tap. Hulp is sluitbaar en houdt focus logisch.
  Blokkerende fouten en noodzakelijke gebruikerskeuzes blijven zichtbaar.
- [ ] Relevante Chromium/Firefox/WebKit-, smalle scherm-, zoom- en
  Shadow DOM-scenario's slagen. Fysieke iOS-conclusies vereisen apparaatbewijs.

## W2 — OCR en transcriptbetrouwbaarheid

**Eigenaar:** OCR. Fixtures en replay zijn de eerste subtaken van deze werkstroom.
De native en mobiele uitvoering delen gedragsafspraken; een volledig afgeronde
desktopimplementatie is geen voorwaarde voor mobiele ontwikkeling. PR #34 heeft
al multi-bubbleherkenning en bevestiging toegevoegd. R10 toetst en behoudt dit;
het is geen opdracht om die functionaliteit opnieuw vanaf nul te bouwen.

| ID | Afgebakende oplevering | Voorwaarde | Afrondingsbewijs voor deze subtaak |
| --- | --- | --- | --- |
| R01 | Eigen synthetische temporele comicfixtures, onafhankelijke verwachte events en lokaal videomanifest | Startcontrole OCR; geen afhankelijkheid van W1/W3 | Geannoteerde sequenties en manifest dekken de genoemde comicgevallen; omgekeerde/dubbele/stale testevents worden afgekeurd. Productieherkenning hoeft hier nog niet te slagen. |
| R02a | Baseline en grenzen voor recall/precisie, duplicaten, inversies, trackfragmentatie, capture/OCR/matching/UI-tijd, p50/p95 en mobiele sessieduur | Meetplan direct; R01 en R07b van de betrokken route voor betrouwbare productiemetingen vóór tuning | Versieerbaar rapport met reproduceerbare meting en vooraf vastgelegde kwaliteit-/latentiegrenzen per gekozen matrix; ontbrekende resultaten expliciet open. |
| R07a | Huidige productiecontrollers karakteriseren met gecontroleerde I/O; echte mobiele pagina als vertrekpunt | R01; zo nodig eerst een minimale I/O-injectiegrens | Echte scan/confirmation/history/publicatie en ZZZ-route uitgevoerd; stop/bronwissel/stale-output vastgelegd; bekende fouten apart van gewenste verwachtingen. Geen nagebouwde testcontroller. |
| R07b | Replay via dezelfde productiecontrollers, met bron-/klokinjectie en temporele assertions | R07a; mobiel na R13c, desktop kan onafhankelijk starten | Dezelfde karakterisatie vóór/na extractie; identiteit/volgorde/duplicatie/tijd gemeten via productiecode; zelfstandige stable/set-loop uit replay vervalt. |
| R08 | Gedeeld fragment-/eventcontract (identiteit, occurrence en onzekere volgorde); gerichte reparatie van legacy/meertalige fragmentverschillen met behoud van ambiguïteitscontrole | R07b van de betrokken route; R12b-semantiek; R02a-kwaliteitsgrenzen vóór matchingtuning | Contract specificeert identiteit, occurrence, unknown order en stale events; W1/W2 leggen weergave, historie en favorietidentiteit vast. Bekende fragment-/ambiguïteitsgevallen slagen op legacy/meertalig. Consumerbewijs volgt in R09/R10; mobiele pariteit in R10/R11. |
| R09 | Desktop-bubble-identiteit en volgorde over frames, inclusief onbekende volgorde binnen een eerste batch | R08 voor desktop; R12b; R13b waar activatie/binding wijzigt | Desktopsequenties halen de kritieke nul-foutcriteria én vereiste regels; verplaatsing, echte herhaling en onbekende eerste batch onderscheiden. Met W1: desktopweergave, historie na herladen en paired-PC behouden die betekenis volgens de consumercriteria hieronder. |
| R10 | Bestaande mobiele multi-bubbleverwerking behouden en temporele identiteit bij scroll/verplaatsing aanvullen waar bewijs ontbreekt | R13c, mobiele R07b/R08 en R12b; afstemming met R03 bij statuswijzigingen | Dezelfde kritieke gevallen slagen via mobiele productiecontroller, inclusief zwarte bubbles, meer dan acht regels en meerdere gelijktijdige bubbles; bestaande bronstatus blijft werken. Met W1: mobiele weergave en historie na herladen voldoen aan dezelfde consumercriteria. |
| R11 | ZZZ-videocorpus en hold-outscènes evalueren, plus regressiematrix voor overige actieve adapters | R07b per route; eindbeoordeling na R08–R10 en R02a | Vaste video-/hold-outmatrix haalt R02a-grenzen op de geclaimde routes; andere actieve adapters behouden gedrag; corpus, clocks en modelversies bij resultaten vermeld. |

**Acceptatie**

- [ ] Verwachte transcript-events komen uit annotaties/vereisten, niet uit de
  uitvoer of sorteerfunctie die wordt getest. Omgekeerde volgorde, dubbele
  publicatie en een late oude-bronrespons laten de bijbehorende assertion falen.
- [ ] Videomanifesten onderscheiden bronframes, decodeertimestamps, sampling,
  scene, occurrence, taal, resolutie, rechten/provenance en onzekere volgorde.
  Resampling telt niet als nieuw bewijs; twee werkelijk nieuwe observaties met
  identieke pixels mogen wel bevestigen. Regressies bewaken dat onderscheid.
- [ ] R02a vermeldt commit, engine/model, catalogus, hardware en corpusversie.
  Eigenaar en onafhankelijke reviewer leggen grenzen per matrix vast vóór tuning.
  Ontbrekende metingen blijven open en grenzen worden niet achteraf passend gemaakt.
- [ ] Replay gebruikt productiecontroller/matcher, geen nagebouwde beslislus.
  Routebewijs voorkomt dat ZZZ ongemerkt het generieke gamepad volgt.
- [ ] De onafhankelijke fixtures omvatten: rechtsonder vóór linksboven,
  verplaatsen/herflow, scrollfragmenten, simultane bubbles, blijvende oude bubble,
  typewritertekst, diagonale overlap, dropout, late OCR, scènewissel en herhaling.
  Zwarte bubbles met witte tekst en meer dan acht totale regels zijn opgenomen.
- [ ] Een suffix in een smalle crop publiceert geen ongerelateerde officiële
  dialoog wanneer de brede comiccrop een andere volledige utterance identificeert.
  Na verdwijnen van die comic blijft een werkelijk zelfstandige utterance herkenbaar.
- [ ] Dezelfde betekenisvolle fragmenten worden in de drie routes correct
  behandeld; platforms mogen verschillende engines hebben. Bevestigde Chinese
  tekst blijft beschikbaar bij audio-extractiefouten; toegestane audioloze comics
  blijven leesbaar. Bestaande mappingvoorwaarden, locale en speler-/voicevariant
  blijven juist; ongemapte dialoog algemeen toelaten is geen onderdeel van deze werkstroom.
- [ ] Verplaatsing maakt geen nieuwe utterance; een latere echte herhaling kan
  wel een nieuwe occurrence zijn. Meerdere zichtbare bubbles verdringen elkaar niet.
- [ ] Gevalideerde authored volgorde gaat vóór betrouwbare eerste waarneming.
  Zonder beide blijft onderlinge volgorde onbekend; coördinaten, dictionaryvolgorde
  en taalmodellen vullen die niet in. Geen verzonnen audio of automatische
  playbackvolgorde voor een onzekere batch.
- [ ] Consumercriteria voor R09/R10: een eerste batch met gelijktijdig zichtbare
  bubbles zonder bewezen volgorde blijft herkenbaar als groep met onbekende
  volgorde in de transcriptweergave en historie. Een vaste plaatsingsvolgorde mag
  de UI stabiel houden, maar suggereert geen spreekvolgorde of laatst uitgesproken
  regel. De UI maakt geen kunstmatige tijdverschillen om die volgorde te creëren.
- [ ] Verplaatsen/scrollen behoudt dezelfde occurrence; een geannoteerde latere
  echte herhaling blijft een afzonderlijke occurrence, ook bij dezelfde tekst-ID.
  Opslaan/herladen en paired-PC-overdracht met reconnect behouden groepsverband,
  onbekende volgorde en occurrence-aantallen; opnieuw ontvangen is geen nieuwe
  occurrence. R09 bewijst desktop en paired-PC, R10 de lokale mobiele OCR-route.
- [ ] W1/W2 leggen in R08 vast of favorieten aan dialooginhoud of aan een
  occurrence hangen, met behoud van bestaande favorieten. R09/R10 toetsen de
  gekozen betekenis na herladen; favorietlogica voegt geen echte herhalingen
  samen in de transcriptgeschiedenis.
- [ ] Kritieke synthetische sequenties hebben nul verkeerde identiteiten,
  onbedoelde duplicaten, verouderde publicaties en volgorde-inversies, én alle
  vereiste regels. Negatieve fixtures publiceren geen onterechte regels/voices.
- [ ] Videoresultaten rapporteren recall, precisie, duplicaten, inversies,
  trackfragmentatie en p50/p95-vertraging per game/presentatie/taal/resolutie.
  Bevroren drempels uit R02a worden gehaald; dekking mag niet worden gered door
  lastige scènes te verwijderen of onzekerheid als succes te tellen.
- [ ] Publicatielatentie loopt vanaf het eerste geannoteerde bronmoment met
  voldoende herkenningsbewijs tot publicatie. Bron-/sampletijd en verwerkingstijd
  houden hun eigen klokdomein met expliciete correlatie; OCR-completion is niet
  het startpunt van die meting en bepaalt geen verhaalvolgorde.
- [ ] Hold-outscènes zijn niet gebruikt om thresholds af te stellen. YouTube is
  bronverwijzing; replay gebruikt vaste rechtmatig beschikbare lokale clips.
  Bronhash, tijdcodes, decodeerbeleid, gamepatch, OCR/model en annotatieversie
  zijn bekend. Opschalen naar 4K bewijst geen native 4K-layout.

Native Windows-OCR en de [fysieke mobiele proef](mobile-capture-verification.md)
blijven afzonderlijke gates. Nul fouten op een begrensd corpus is geen garantie
voor iedere toekomstige gamescène.

R07a/R07b kunnen als testinfrastructuur worden opgeleverd met vastgelegde bestaande
productfouten; dat verklaart R08–R11 niet geslaagd. De harness wordt apart
gevalideerd op routekeuze en foutdetectie. Gemelde productfouten blijven zichtbaar
met een eigenaar; de uiteindelijke gedragscriteria worden niet verlaagd.

## W3 — Installatie en gamebeheer

**Eigenaar:** installatie. Discovery/onboarding en bundeling kunnen parallel
voorbereid worden en komen samen in de installer. R14/R18 stemmen vroeg de
opslaggrens af. Deze werkstroom bundelt de bestaande Python-runtime en wacht niet
op een taalexperiment of een volledige OCR-rework; geïntegreerde regressies
blijven vereist voor de uiteindelijk gekozen release-inhoud.

### Gamebeheer en onboarding

| ID | Afgebakende oplevering | Voorwaarde | Afrondingsbewijs voor deze subtaak |
| --- | --- | --- | --- |
| R14 | Installatiekandidaat-, packstatus- en voorkeurencontract; één service voor beide UI's | Startcontrole installatie met huidige runtime-eisen; geen volledige R18-oplevering nodig | Kandidaat-/pack-/voorkeurenschema en foutgevallen vastgelegd met gedeelde servicegrens; consumercontracttests slagen. Nieuwe launcherprobes volgen in R15/R16. |
| R15 | Steam-appmanifests, Epic/GOG-adapters, HoYoPlay na formaatvalidatie, begrensde fallback en handmatige paden | R14; adapters afzonderlijk testbaar | Manifest- en mapfixtures dekken afwijkende drives, corrupt/stale/ontbrekend en cancel; geldige handmatige keuze blijft intact na ongeldige invoer. |
| R16 | Per-game/per-taal fysieke voicepackprobes, los van voorbereide index | R14; probes per game parallel mogelijk | Elke geclaimde game/locale onderscheidt aanwezig, onvolledig, ontbrekend en onbekend, apart van reader/index; geen verkeerde-taal-fallback. |
| R17 | Games → talen/packs → Browser Extension/Lexirise API → gereed; opnieuw openen in WebUI | Leesmodusafspraak uit R04; R15–R16; afgestemde R14/R18-opslaggrens | Herbruikbare onboardingflow werkt in WebUI/testhost met echte R15/R16-service; overslaan/hervatten en leesvoorkeurprecedentie bewezen. Installerhost wordt bewezen in R20. |

De W3-eigenaar levert de gedeelde opslagafspraak als eerste begrensde wijziging
binnen R14, op basis van de huidige runtime en vroeg beschikbare R18-bevindingen: schrijver, locatie, schema,
migratie en precedentie. R14 en R18 wachten dus niet op elkaars volledige oplevering.
R17/R19/R21 gebruiken deze geïntegreerde afspraak.
R15-launcherdetectie kan ondertussen op het R14-kandidaatcontract doorgaan.
R17 kan op vastgelegde interfaces worden voorbereid; volledige acceptatie volgt
pas met echte discovery/packprobes en de voorkeurenoverdracht naar W1.

**Acceptatie**

- [ ] Installer en WebUI geven dezelfde kandidaten en validatiefouten.
  Een launcherrecord of passende mapnaam zonder geldige gamebestanden is geen installatie.
- [ ] Niet-standaard schijven, Unicode/spaties, meerdere installaties, verplaatste
  games, ontbrekende drives, onleesbare/corrupte/stale records en incomplete
  downloads zijn afgedekt. Scan is begrensd en onderbreekbaar; geen volledige
  schijfscan of launcheraccount nodig.
- [ ] Handmatige keuze werkt in beide flows. Ongeldige invoer overschrijft geen
  geldige keuze. Gedetecteerde installaties kunnen expliciet worden geselecteerd
  voor toolvoorbereiding, ook zonder eerder opgeslagen override.
- [ ] Fysiek aanwezig, readerondersteuning en indexgereedheid zijn aparte waarden.
  Aanwezig/onvolledig/ontbrekend/onbekend zijn geldige uitkomsten; een oude index
  bewijst niet dat een pack nog op schijf staat. Geen verkeerde-taal-fallback.
- [ ] Overslaan/hervatten werkt. De gekozen leesmodus wordt bij eerste browserstart
  overgenomen met een vastgelegde precedentie: bestaande gebruikersvoorkeur blijft
  behouden tenzij de gebruiker expliciet een nieuwe keuze maakt.
- [ ] Er worden geen gamebestanden of voicepacks geïnstalleerd/veranderd door de
  toolkit. Ondersteunde launchers en games krijgen een concrete bewijsmatrix;
  onbekende formats vallen terug op handmatige mapkeuze.

### Windows-bundel, installer en migratie

| ID | Afgebakende oplevering | Voorwaarde | Afrondingsbewijs voor deze subtaak |
| --- | --- | --- | --- |
| R02b | Baseline en criteria voor cold/warm start, CPU/RSS, workerherstel en bundelgedrag op Windows | Meetplan direct; huidige runtime en test-Windows nodig voor metingen vóór optimalisatie | Windowsrapport met commit, machine, meetmethode en vooraf vastgelegde grenzen voor start, CPU/RSS en herstel; niet uitgevoerde meting blijft open. |
| R18 | Runtime-/tool-/redistributie-inventaris, Windows-versies/architecturen en systeemvoorwaarden; app/data/cache/credentials-layout en prototypebesluit | Runtime-inventaris kan direct; neemt de geïntegreerde R14-opslagafspraak over | Runtime/tool/licentie- en Windowsmatrix plus app/data/opslaglayout vastgelegd; voor elke verplichte component is bundeling of expliciete systeemvoorwaarde bepaald. |
| R19 | Windows-runtimebundel met functionele probes; statisch serveren van frontend onderzoeken | R18; R02b voor prestatievergelijking; afgestemde R14/R18-opslaggrens | Uitgepakte runtimebundel start zonder ontwikkelomgeving en doorloopt relevante game/OCR-probes; frontend/API/cachecontract en R02b-vergelijking bewezen. Installatiepad volgt in R20. |
| R20 | Per-user installer met geïntegreerde onboarding, repair en uninstall | R17, R19 | Werkelijk geïnstalleerde kandidaat doorloopt dezelfde probes en R17-flow als standaardgebruiker; repair/uninstall/cancel/no-space/locked-file-cases slagen. |
| R21 | ZIP→installer-migratie, upgrade, annulering en rollback met synthetische gebruikersdata | Afgestemde R14/R18-opslaggrens; integraal bewijs met R20 | ZIP-upgrade en falende migratie/update herstellen data en maximaal één capture-eigenaar; browseropslag, beschermde testcredentials en uninstall-behoud op de kandidaat gecontroleerd. |
| R22 | Kandidaatbuild/artifactvalidatie in bestaande CI integreren; downloads verifiëren en ondertekeningbesluit vastleggen | R20–R21; toepasselijk W3-bewijs uit G; volledige reworkintegratie bij M2/M3 | Hosted CI valideert kandidaatartifact; gedownloade checksums/commitkoppeling gecontroleerd; signingbesluit en native matrixbewijs vastgelegd voor W3, zonder te wachten op alle W2-verbeteringen. |

Voorkeur voor het eerste prototype: Inno Setup plus gebundelde bestaande runtime,
met een PyInstaller-directorybundel als te toetsen optie. MSI/MSIX/Tauri zijn
alternatieven bij een concrete producteis of bewezen blokkade. De native
OCR-componenten uit Snipping Tool zijn geen vrij herdistribueerbare aanname.

**Acceptatie**

- [ ] R02b legt omgeving, commit, meetmethode en grenzen vóór optimalisatie vast,
  getoetst door eigenaar en onafhankelijke reviewer;
  R19 vergelijkt de bundel hiermee. Bundeling kan beginnen terwijl metingen lopen;
  ontbrekend bewijs houdt de betrokken eindbeoordeling open, niet heel W1/W2.
- [ ] De kandidaat werkt op een schone Windows-installatie zonder voorafgaande
  Python, Node/npm of .NET SDK. Expliciete systeemvoorwaarden blijven zichtbaar
  met een herstelactie. Ook game-afhankelijke subprocessen/tools zijn meegenomen.
- [ ] De geïnstalleerde bundel doorloopt frontendstart, OCR-initialisatie,
  workerstart/-stop en functionele probes voor iedere unieke runtime-/extractor-
  toolchain van de geclaimde games. Niet-geteste combinaties blijven expliciet
  open. Alleen een succesvolle build, één gamereader, PowerShell-parse of
  broncheckouttest is onvoldoende.
- [ ] Installatie/onboarding/repair/uninstall werken als standaardgebruiker,
  inclusief onderbroken download, annulering, onvoldoende ruimte en bezette
  runtimebestanden. Browser Extension gebruikt een geschikte gewone browser.
- [ ] Applicatieversies en blijvende gegevens hebben afzonderlijk eigenaarschap.
  ZIP-migratie behoudt synthetische historie, favorieten, kalibratie, paden,
  voorkeuren en beschermde testcredentials. Geen blind kopiëren van DPAPI tussen
  Windowsgebruikers. Een mislukte migratie/update houdt herstel mogelijk.
  Browserdata (localStorage/IndexedDB) is aan de origin gekoppeld: host/poort/protocol
  blijven compatibel, of R19/R21 bewijzen een expliciete overdracht met behoud van
  voorkeuren, historie en kalibratie. Alleen bestandskopieën bewijzen dit niet.
- [ ] Update laat maximaal één capture-eigenaar actief; voorbereidingsfout houdt
  de vorige runtime bruikbaar. Uninstall behoudt gebruikersdata standaard.
- [ ] GitHub-hosted CI controleert het echte installerartifact; een schone gewone
  Windowsomgeving controleert daarnaast native OCR/capture, actuele launcherrecords,
  meerdere monitors, crop-bounds en 125–200% DPI. Claims noemen de geteste matrix.
- [ ] Downloads hebben geverifieerde checksums en commitkoppeling. JSON-provenance,
  Authenticode en cryptografische buildattestaties zijn onderscheiden. R22 legt
  vast welke aanwezig zijn; ondertekening wordt uitsluitend geclaimd na verificatie
  van signature/timestamp. Sleutels volgen de beschermde-opslagregels.

## Architectuurwerk binnen de werkstromen

Het [architectuuronderzoek](rework-architecture.md) legt zes ontwerpbeslissingen
vast. Doel is minder impliciet eigenaarschap, betere productie-replay en veilige
bundeling. Geen algemene architectuurfase of vierde brede refactorbaan.
De onderstaande taken vervangen de eerdere globale R12/R13-opdrachten.

| ID / prioriteit | Eigenaar en concrete scope | Voorwaarde | Acceptatie en rollback |
| --- | --- | --- | --- |
| R12a / P1 | W1: status-/UI-readmodel en gewijzigde HTTP/WS-grenzen; hergebruik StateVersion, StatePoll en pairingvalidatie | Startcontrole relevante R03-route; geen W2-afronding | Bestaande runtime-/accountgeneraties, late snapshots, onafhankelijke eventdomeinen en frame-/OCR-/library-status hebben eenduidige betekenis; oude consumers blijven via adapter werken. Rollback zonder opslagmigratie. |
| R12b / P0 | W2: RecognitionContext, actieve GameBinding en semantiek van observatie/content/occurrence/volgorde | R01 en relevante R07a-karakterisatie; bestaande runtime-/taalcontracten | Legacy/meertalig/mobiel hebben toetsbare voorbeelden; catalogus/locale/voice zijn coherent, onbekende volgorde expliciet. Handoff van nieuwe occurrence-state heeft behoud/reset-/versiebeleid. Geen universele vervanging van alle generationtellers. |
| R12c / P0 | W3: resource-/data-/cache-/credentiallayout, runtimehost en frontendorigincontract; concrete contractoplevering binnen R14/R18 | Huidige runtime plus vroege R18-inventaris; geen volledige R14/R18-afronding | Schrijver en migratie per gegeven vastgelegd; source/bundle-resourcepaden, origin/API/assets/serviceworker, readiness/quiesce/rollback benoemd. Behoud-/migratiebeleid voor browseropslag vastgelegd; werkelijk behoud volgt in R21. Huidige runtime blijft geldige adapter. |
| R13a / P1 | W3 met integrator: benodigde setup-use-case en composition-/hostadapter uit API halen, één grens per wijziging | Gedragstests van betrokken endpoints/lifecycle; R12c voor host-/padwijzigingen | Zelfde endpoints, statuscodes, LocalAccessMiddleware, accountpinning, standby/close en lockvolgorde; resource heeft één eigenaar. Source gebruikt de geëxtraheerde use-case; bundleadaptergrens contractueel getest, echte bundleconsumer volgt in R19. Pure extractie terugdraaibaar zonder datawijziging. |
| R13b / P0 | W2: publieke game-/taalactivatiegrens met coherente binding; vervang externe mutatie van capture-private state | R12b; R07a van betrokken desktoproutes | Geen externe `_scan_epoch`-mutatie; game/locale/index/voice wisselen via één eigenaar, stale werk publiceert niet, laatste complete index blijft; legacy en voorbereide taalroute blijven expliciet. Bestaande references eerst via facade, zonder matchingwijziging. |
| R13c / P0 | W2: mobiele controllerfactory losmaken van DOM met injecteerbare source/clock/OCR/library/store/eventoutput | Mobiele R07a; bestaande receiver-/libraryworkergrenzen | Zelfde productiescenario's vóór/na extractie, single-flight, stop/close/pagehide/bron-/taalwissel weren late success en errors; frames/workers/subscriptions vrijgegeven. Bestaande DOM-shell en directe controllerharness gebruiken dezelfde factory; volledige replayconsumer volgt in R07b. Extractiecommit terugdraaibaar, geen tweede beslisloop. |
| R13d / P1 | W1: subscriptions/transport/readmodel uit de geraakte companionpresentatie halen | R12a en huidige UI-karakterisatie; R13c alleen als nieuwe mobiele controllerinterface wordt gebruikt | Geen UI-beslislogica afleiden uit muterende DOM-tekst; reader/account/taalownership, onafhankelijk extensiongebruik en mount/unmount behouden. UI-local state blijft lokaal; adapter op huidige controller laat R03 doorgaan. |
| R13e / P1 | W2: observatie, gamebeleid en transcript-/audiopublicatie in desktopcapture scheiden, één gamepad per wijziging | R07b van die route; R12b, R13b indien binding wordt geraakt | Pure observatie schrijft geen transcript; één publicatie-eigenaar valideert context. Bestaande matching/toelating, audioloze comics, kanaal-/voicebeleid en foutpaden blijven gelijk. Functionele R08/R09-reparaties in aparte changes; rollback per gamepad. |

R12a/R13d worden binnen R03 gebruikt waar nodig; R04/R05 hoeven hier niet op te
wachten. R12c is de gedeelde afspraak die R14/R18 toch nodig hebben, geen extra
projectbrede goedkeuringsronde. Een R13a/R13e-extractie wordt alleen ingepland
als een concrete wijziging die grens nodig heeft. Alle daadwerkelijk toegewezen
architectuurtaken blijven onderdeel van het afrondingsbewijs van hun werkstroom.

**Behoud bij elke architectuurwijziging**

- [ ] Context wordt vóór payloadwerk vastgelegd; bron-/runtime-/account-/taalwissel
  weert late resultaten. Oude revisies krijgen geen nieuwe contextstempel.
- [ ] Bestaande cancellation, Windows Job Objects, lockvolgorde en atomische
  indexpublicatie blijven getest; onvolledige cleanup is geen succesvolle overname.
- [ ] Contract-/veldnaamadapters behouden bestaand wire-/storagegedrag. Wijziging
  van een grens noemt de geraakte producers/consumers en compatibiliteitsbewijs.
- [ ] Geen universeel gamebeleid, nieuwe eventbus, volledige databasevervanging
  of gedeelde Rust/WASM-engine zonder afzonderlijk onderbouwde noodzaak.
- [ ] Regelcount is geen doel. De wijziging maakt één concrete verantwoordelijkheid
  en eigenaar duidelijk; tests bewaken gedrag, niet alleen de nieuwe mapstructuur.

### Concrete volgorde en testgrenzen

R01 → R07a karakteriseert de bestaande productiecontroller. Mobiel volgt
R13c → R07b; desktopreplay kan op zijn eigen route door. Daarna volgen R02a-
metingen en R08/R09/R10-gedragswijzigingen per betrokken route. R13c wacht nooit
op afgerond R07b. Een benodigde injectiegrens in R07a blijft een kleine change.

Karakterisatie en gewenste acceptatie zijn afzonderlijk: bekende fouten mogen
in de baseline staan, maar worden geen gewenste invariant en verdwijnen niet
achter skips. R13b/R13e behouden eerst gedrag; functionele reparaties krijgen
aparte commits. Nieuwe occurrence-state moet ook over runtimehandoff zijn getest.

R19 bundelt de bestaande runtime zonder afhankelijkheid van R13b/R13c/R13e of
R23. De huidige uitgepakte-frontendcheck mockt de backend en gebruikt Wrangler
uit de checkout; R20/R22 voegen expliciet bewijs toe van de echte geïnstalleerde
runtime zonder ontwikkelcheckout/PATH-fallback. Native OCR, DPI en fysieke iOS
blijven apparaatbewijzen en worden niet door deze architectuurstudie afgevinkt.

## Optioneel — Native experiment bij een bewezen probleem

**Prioriteit P2.** Eigenaar wordt pas bij een concrete onderzoeksvraag aangewezen.
Dit onderzoek is geen voorwaarde voor de drie werkstromen of hun mijlpalen.

| ID | Afgebakende oplevering | Voorwaarde | Afrondingsbewijs voor deze subtaak |
| --- | --- | --- | --- |
| R02c | Baseline, hypothese en succesgrens voor één native probleem | Hergebruik relevante R02a/R02b-metingen; vul alleen ontbrekend bewijs aan | Eén meetbaar probleem, identieke vergelijkingsinput en succesgrens door eigenaar/reviewer vastgelegd vóór het experiment. |
| R23 | Eén probleem vergelijken met Python-workerproces, Rust of C# achter dezelfde grens | R02c; contracten en regressies van het gekozen onderdeel; R19 indien bundeling onderdeel van de proef is | Vergelijking op dezelfde omgeving heeft meetresultaten én correctheids-/herstelbewijs; geen winstclaim op basis van alleen hosttaal of build. |
| R24 | Beslisdocument met metingen, onderhoudskosten, compatibiliteit en behoud/migratiekeuze | R23 | Besluit noemt gemeten winst of behoud van Python, onderhoud, compatibiliteit en rollback; een migratie volgt niet automatisch uit het experiment. |

**Acceptatie**

- [ ] Het experiment heeft vooraf één hypothese en grens: bijvoorbeeld herstel
  van een hangende native OCR-call of procesbeheer. Geen volledige rewrite als taak.
  Eigenaar en onafhankelijke reviewer leggen die grens in R02c vast.
- [ ] Vergelijk dezelfde hardware, frames, engine/model, catalogus en buildmodus.
  Scheid capture-, OCR-, matching- en publicatietijd; rapporteer cold/warm start,
  RSS, fouten en hersteltijd. Gebruik de vooraf vastgelegde R02c-grenzen.
- [ ] Geen verlies van transcriptcorrectheid, voice-identiteit, data-integriteit
  of Browser Extension-gebruik. Een andere hosttaal verandert niet vanzelf het OCR-model.
- [ ] Een migratie vereist aantoonbare winst op het gekozen probleem en een
  onderhouds-/rollbackpad. Ook behoud van Python is een geldige afgeronde uitkomst.
- [ ] Een eventuele native webview heeft apart extensiecompatibiliteitsbewijs;
  de bestaande gewone-browserroute blijft beschikbaar.

## Gate G — Bewijs, integratie en release

Pas deze gate toe op ieder geraakt onderdeel; voer volledige packagingvalidatie
uit bij een releasekandidaat volgens RELEASE.md.

- [ ] De actuele commit voldoet aan de pakketcriteria; regressietests testen het
  gedrag en relevante foutpaden. Nieuwe tests zijn niet verplicht voor elke copy-edit.
- [ ] Gerichte checks slagen. Niet beschikbare platformchecks zijn expliciet
  open; die tellen niet als geslaagd en blokkeren de bijbehorende releaseclaim.
  Branchchecks gebruiken de actuele doelbranch van de PR; doelrepository,
  remote/ref en gecontroleerde basiscommit staan bij het bewijs. Voor een fork
  richting Boaz' `main` is dat hier `upstream/main`, niet automatisch `origin/main`;
  volg de [basiskeuze in de AI-werkwijze](ai-development-workflow.md#verificatie-en-bewijs).
- [ ] Voor OCR, accounts, migratie en lifecycle is een onafhankelijke review
  uitgevoerd tegen criteria, diff en echte testuitvoer. Bevindingen zijn opgelost
  of aantoonbaar weerlegd. Een reviewsamenvatting vervangt geen testbewijs.
- [ ] Overlappende wijzigingen zijn geïntegreerd en relevante checks lopen op
  het gezamenlijke resultaat. Parallel groen op oude baselines is onvoldoende.
- [ ] Relevante echte browserextensies en fysieke Windows/iPhone/iPad-protocollen
  zijn uitgevoerd voor de geclaimde configuraties. Synthetische CI bewijst geen
  ReplayKit-achtergrondgedrag of native capture op gebruikershardware.
- [ ] Rollback/databehoud en lokale versus externe gegevensstromen zijn actueel
  beschreven. Mobiele VDO/pairing/gateway en desktop hebben verschillende grenzen;
  stateless gateway betekent niet dat die technisch geen verzoekinhoud kan zien.
- [ ] Publicatie volgt de bestaande public audit, clean-main-release,
  GitHub-hosted checks en controle van het gedownloade artifact. Geen echte
  media, accountdiagnostiek of persoonlijke paden in bewijsstukken.

## Samenwerking, afhankelijkheden en mijlpalen

### Verdeling bij drie mensen of teams

| Eigenaar | Direct oppakken | Daarna binnen de eigen werkstroom | Overdracht aan anderen |
| --- | --- | --- | --- |
| UX | R03 of R04; R05 is ook zelfstandig uitvoerbaar | R06 per control; resterende R03–R05 | R04-leesmodus/voorkeuren aan installatie; R03-statusafspraak aan OCR |
| OCR | R01 en plan R02a | R07a → mobiel R13c → R07b per route → R02a/R08; daarna R09/R10; R11-evaluatie | Event-/statusgedrag aan UX; gevalideerde runtime en tests aan installatie |
| Installatie | R14 en R18; plan R02b | R15/R16 en R19; R17 → R20; R21/R22 | Kandidaten/packstatus en voorkeurenoverdracht aan UX; geïnstalleerde runtime voor gezamenlijke proef |

Eén van deze eigenaren vervult ook de integratorrol; een vierde persoon is niet
nodig. De integrator verdeelt alleen gedeelde grenzen, beoordeelt gecombineerde
wijzigingen en bewaakt release-inhoud. Iedere eigenaar levert zijn eigen tests
mee. Review kan tussen eigenaren plaatsvinden; niemand verifieert risicovol werk
uitsluitend aan de hand van zijn eigen implementatiesamenvatting.

### Alleen concrete afhankelijkheden blokkeren werk

| Grens | Eerst vastleggen | Wat erop wacht | Wat ondertussen doorgaat |
| --- | --- | --- | --- |
| Leesmodus/voorkeuren | R04: labels, interne waarde en leesgedrag; R14/R18: opslag en precedentie | R17-integratie met W1 | Discovery en bundeling; R03/R05 |
| Installatieopslag | R14/R18: schema, schrijver, locatie en migratie-eigenaarschap | Opslaggebruik in R17/R19/R21 | R15/R16 op afgesproken kandidaat-/packcontract |
| OCR-events en status | R12b/R08: identiteit/volgorde; R12a/R03: bronstatusvelden, samen met OCR-eigenaar | R09/R10 wachten op eventcontract; alleen geraakte statusconsumers wachten ook op R03-afspraak | Fixtures, replay en onafhankelijke UI-controls |
| Comicweergave en historie | R08: W2 levert occurrence-/groeps-/volgordesemantiek; W1 legt presentatie en favorietgedrag mee vast | W1 integreert de geraakte consumers voor het afrondingsbewijs van R09/R10; R08 zelf vereist nog geen afgeronde consumers | R03–R06, controllerwerk en fixtures op de afgesproken grens |
| Frontendhost en offline updates | W3/R19: origin, API-routes, assetpaden en cacheversie; W1/R05 toetst behoud van updategedrag | Alleen host-/cachewijzigingen en hun consumerintegratie | R05 kan op de huidige host worden afgerond; runtime/toolbundeling kan door |
| Runtime in installer | R17-onboarding en R19-bundel | R20; integraal bewijs R21/R22 | Migratiegevallen en CI-ontwerp voorbereiden |

Leg een gedeelde afspraak klein vast en integreer die voordat consumers ervan
uitgaan. Werk aan hetzelfde bestand wordt na elkaar geïntegreerd. Bij wijzigingen
in `mobile/companion.jsx`, `public/mobile-capture/capture.js` of backend-API's
stemmen de betreffende eigenaren scope en volgorde af. Worktrees voorkomen geen
inhoudelijke conflicten. Een blokkerende afhankelijkheid krijgt een naam en
vervolgstap; onafhankelijke subtaken blijven uitvoerbaar.

### Eigenaarschap bij gedeelde bestanden

Dit zijn integratie-eigenaren, geen verbod op bijdragen van anderen. Een andere
werkstroom levert een gerichte wijziging aan; de eigenaar plant integratie en
checks. Binnen één checkout schrijft steeds maar één taak aan hetzelfde bestand.

| Gebied | Integratie-eigenaar | Concrete grens |
| --- | --- | --- |
| `mobile/companion.jsx`, `app/companion.tsx` | W1 | W1 beheert presentatie, leesvoorkeuren en R09/R10-consumerbewijs voor comicweergave/historie; W2 levert de R08-semantiek en fixtures, W3 de R17-import/precedentiebrug |
| `public/mobile-capture/capture.js`, `mobile-ui.mjs`, bron-/OCR-events | W2 | W1 levert R03-statusdoorvoer gericht aan; bestaande events blijven ondersteund tot beide consumers zijn aangepast |
| `app/toolkit-setup.tsx`, setup-API, installatieopslag | W3 | R04-leesmodusafspraak gaat vóór R17; R06-hulp wordt afzonderlijk ingepland en blokkeert de onboardingimplementatie niet |
| Backend capture/matching versus runtime/launcher | W2 voor algoritme; W3 voor bundeling/lifecycle | W3 verandert geen OCR-beleid als packagingfix; worker-/API-grens gezamenlijk afspreken |
| `backend/api.py`, gedeelde schemas en releaseconfiguratie | Integrator | Per wijziging één schrijver aanwijzen; benoem welke producers/consumers of artifacts opnieuw getest worden |

Wijzigt een afspraak na overdracht, dan noemt de producer de geraakte consumers
en draagt hij adapter/migratie en regressiebewijs mee. Ontwikkeling met een stub
op een afgesproken interface kan doorgaan, maar bewijst de echte integratie niet.

### Gezamenlijke oplevermomenten

Mijlpalen beschrijven aantoonbare resultaten, geen nieuwe reeks verplichte fasen.
M1 wordt per werkstroom bereikt. Een afgerond onderdeel kan eerder worden geleverd
via het gewone releaseproces; W1 hoeft niet op een volledige installer te wachten.

| Mijlpaal | Inhoud en acceptatie | Verantwoordelijke |
| --- | --- | --- |
| M1 — Zelfstandig resultaat | W1: R03–R06 en UX-criteria bewezen. W2: R01/R02a/R07a/R07b/R08–R11 en OCR-criteria bewezen. W3: R02b/R14–R22 en installatiecriteria bewezen. Per werkstroom afzonderlijk afvinken; benodigde R12a–c/R13a–e-subtaken horen bij hun eigenaar. | Werkstroomeigenaar met reviewer |
| M2 — Geïntegreerde rework | Op dezelfde kandidaatcommit: game detecteren of handmatig kiezen → packs controleren → leesmodus kiezen → companion starten → bronstatus/OCR/transcript gebruiken. Herstart bewaart voorkeuren; game-/taalwissel weert oude resultaten. Beide modi en de geclaimde desktop-/mobiele routes zijn gecontroleerd. | Integrator met de drie eigenaren |
| M3 — Releasegereed | M1 voor alle onderdelen van de geplande reworkrelease, M2 en gate G bewezen; werkelijk installerartifact op schone Windows en relevante apparaten getest; migratie/rollback, checksums en resterende beperkingen vastgelegd. Publicatie volgt pas het geautoriseerde releaseproces. | Integrator/maintainer |

M2-proeven beginnen zodra de betrokken onderdelen beschikbaar zijn; ontbrekende
onderdelen houden de volledige mijlpaal open. M3 betekent gereed voor release,
geen automatische toestemming om te publiceren. Een kleinere tussentijdse release
krijgt dezelfde toepasselijke checks, maar geldt niet als volledige reworkoplevering.

### Starten met AI-development

Wijs per werkstroom een eigenaar en één eerste subtaak aan. Gebruik de
[taaktemplate](ai-development-workflow.md#taakcontract), inclusief tests, review
en overdracht. Begin direct met de startcontrole van die taak; er is geen
voorafgaande R00-opdracht voor het hele project. Onderzoek en meet alleen wat
de concrete wijziging nodig heeft. Geen opdracht om de volledige roadmap in één
keer uit te voeren; vervolgtaken volgen de genoemde afhankelijkheden.

## Traceerbaarheid naar de wensen

| Wens of risico | Pakketten |
| --- | --- |
| Windows-installer | R18–R22 |
| Games autodetecteren en handmatig kiezen in installer/WebUI | R14–R15, R17, R20 |
| Geïnstalleerde voicepacks tonen | R16–R17 |
| Browser Extension/Lexirise API kiezen tijdens installatie en later | R04, R14, R17, R20 |
| Minder tekst op desktop/mobiel; bereikbare vraagtekenhulp | R06 |
| Game-specifieke OCR beschermen, ZZZ-comics en YouTube-replay | R01, R07a/R07b, R08–R11, R12b, R13b/R13c/R13e |
| Verbindingsmelding uitleggen en herstel bieden | R03 |
| Leesopties alleen voor Lexirise API | R04 |
| Updatebanner verwijderen | R05 |
| Python/Rust/alternatieven onderbouwd kiezen | R02a–R02c, R18–R19, R23–R24 |
| AI kan veilig parallel werken en bewijs overdragen | Startcriteria per taak, R12a–c/R13a–e, gate G, AI-werkwijze |

De concrete architectuurverbeteringen zijn onderbouwd in
[rework-architecture.md](rework-architecture.md); het ontwerp is geen claim dat
alle benodigde implementaties of metingen al bestaan.

## Besluiten die bewijs vereisen

| Besluit | Voorlopige richting | Beslismoment |
| --- | --- | --- |
| Kernruntime | Python behouden; Rust/C# alleen gericht | R24, geen blokkade voor installer |
| Desktopfrontend | Onderzoeken of statische build Node/Wrangler op gebruikers-pc kan vervangen | R19 |
| Installer | Per-user Inno Setup met runtimebundel | R18–R20, schone-Windows-proef |
| OCR-volgorde | Authored metadata indien geverifieerd, anders tijd; onzeker blijft onzeker | R01/R07a/R07b/R12b/R08–R09 |
| Performancegrenzen | Nog geen onderbouwde absolute doelen | R02a/R02b/R02c vóór de betreffende optimalisatie/eindbeoordeling |
| Distributieondertekening | Afzonderlijk van bestaande checksums/provenance | R22, inclusief beschermde sleutelvoorziening |

Nieuwe productscope of onoplosbare externe voorwaarden worden als besluitpunt
voorgelegd met een concrete aanbeveling en bewijs. Routinewerk binnen een
toegewezen pakket vereist geen herhaalde goedkeuring.

## Externe onderbouwing

Dit zijn onderzochte opties, geen bewijs dat een prototype voor deze toolkit al werkt.

- [Inno Setup-wizardpagina's](https://jrsoftware.org/ishelp/topic_scriptpages.htm)
  en [per-user rechten](https://jrsoftware.org/ishelp/topic_setup_privilegesrequired.htm);
  [PyInstaller-bundels](https://pyinstaller.org/en/stable/operating-mode.html).
- [Tauri-sidecars](https://v2.tauri.app/develop/sidecar/),
  [Rust for Windows](https://learn.microsoft.com/en-us/windows/dev-environment/rust/rust-for-windows)
  en [C#/WinRT](https://learn.microsoft.com/en-us/windows/apps/develop/platform/csharp-winrt/).
- [Python futures/cancellation](https://docs.python.org/3.12/library/concurrent.futures.html)
  en [FFmpeg frame sampling](https://ffmpeg.org/ffmpeg-filters.html#fps).
- [W3C hulp op hover/focus](https://www.w3.org/WAI/WCAG21/Understanding/content-on-hover-or-focus.html),
  [Migaku-platformen](https://migaku.com/download) en
  [Yomitan-platformen](https://yomitan.wiki/getting-started/).
- [Authenticode-verificatie](https://learn.microsoft.com/en-us/windows/win32/seccrypto/using-signtool-to-verify-a-file-signature)
  en [GitHub artifact attestations](https://docs.github.com/en/actions/concepts/security/artifact-attestations).
