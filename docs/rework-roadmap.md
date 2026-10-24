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

## Prioriteiten en afhankelijkheden

**P0:** correctheid of bewijs dat nodig is vóór de betreffende wijziging/release.
**P1:** directe productverbetering en vereenvoudiging. **P2:** voorwaardelijk
experiment; geen blokkade voor eerdere verbeteringen. Prioriteit is geen
kalenderplanning. Per pakket volgt een raming zodra de vereiste omgeving,
fixtures en scope bekend zijn; AI-capaciteit vervangt geen apparaatvalidatie.

Alle fasen staan aanvankelijk op **planned**. Pakket-ID's hieronder zijn het
backlog; houd voortgang en bewijs per pakket bij volgens de AI-werkwijze.

| Fase | Prioriteit | Resultaat | Afhankelijkheden |
| --- | --- | --- | --- |
| F0 | P0 | Vertrouwde baseline, testverwachtingen en meetplan | Geen |
| F1 | P1; statuscorrectheid P0 | Begrijpelijke, compacte companions | R00; relevante checks per pakket |
| F2 | P0 | Betrouwbare temporele ZZZ-OCR en replay | R00–R01; R02 voor performancecriteria; R07 vóór parserwijzigingen |
| F3 | P1 | Expliciete contracts en kleinere verantwoordelijkheden | R00; gedragsbewijs van het te verplaatsen onderdeel |
| F4 | P1 | Gedeelde discovery, voicepackinventaris en onboarding | R00; lokaal installatie-/voorkeurencontract vastleggen in R14 |
| F5 | P1 | Zelfstandige Windows-installer en herstelbare migratie | R02, R18; R14–R17 voor integratie; geen afhankelijkheid van F6 |
| F6 | P2 | Onderbouwde keuze voor een native onderdeel | R02, R07–R10 en de relevante contracts uit F3/F5 |
| G | P0, doorlopend | Bewijs voor elk opgeleverd pakket en releaseartifact | Relevante pakketcriteria; geen eindfase waarin testen wordt uitgesteld |

### F0 — Baseline en onafhankelijke verwachtingen

**Werkpakketten**

| ID | Afgebakende oplevering | Voorwaarde |
| --- | --- | --- |
| R00 | Actuele route-/capabilitykaart, behoudsinvarianten en reproducties voor de gerapporteerde UX-problemen | Geen |
| R01 | Eigen synthetische temporele comicfixtures, onafhankelijk geannoteerde verwachte events en manifest voor lokale videoclips | R00 |
| R02 | Meetplan en baseline voor kwaliteit (recall/precisie, duplicaten, inversies, trackfragmentatie) en prestaties (cold/warm start, capture/OCR/matching/UI-tijd, p50/p95, CPU/RSS, mobiele sessieduur) | R00; R01-annotaties voor kwaliteitsgrenzen; relevante lokale testmiddelen beschikbaar |

**Acceptatie**

- [ ] Elke oorspronkelijke wens is gekoppeld aan een pakket in de traceertabel.
- [ ] Routes onderscheiden legacy desktop, meertalige desktop, mobiele OCR en
  paired-PC. Gameondersteuning, taalondersteuning en apparaatbewijs zijn apart.
- [ ] Verwachte transcript-events komen uit annotaties/vereisten, niet uit de
  uitvoer of sorteerfunctie die straks wordt getest. Geometrische sortering,
  dubbele publicatie en een late oude-bronrespons laten de bijbehorende fixture falen.
- [ ] Videomanifesten onderscheiden bronframes, decodeertimestamps, sampling,
  scene, occurrence, taal, resolutie, rechten/provenance en onzekere volgorde.
  Duplicatie door resampling telt niet als nieuw onafhankelijk bewijs. Twee
  werkelijk nieuwe waarnemingen met identieke pixels mogen wel bevestigen;
  gekoppelde regressies voorkomen dat pixelhash-deduplicatie dit onmogelijk maakt.
- [ ] Het meetrapport vermeldt commit, model/engine, catalogusversie en hardware.
  Ontbrekende metingen staan als niet uitgevoerd. In R02 leggen integrator en
  onafhankelijke reviewer kwaliteits- en performancegrenzen per testmatrix vast
  op basis van R01-annotaties en de gemeten baseline, vóór matchingtuning of
  optimalisatie. Ontbrekende baseline houdt die eindbeoordeling open; grenzen
  worden niet achteraf aangepast aan de gerealiseerde uitkomst.

R00 kan F1 en F4 vrijgeven terwijl R01/R02 verdergaan. Een ontbrekend fysiek
apparaat blokkeert uitsluitend de pakketten of claims die dat bewijs nodig hebben.

### F1 — Status, leesmodus en rustige bediening

| ID | Afgebakende oplevering | Voorwaarde |
| --- | --- | --- |
| R03 | Bronstatus behouden tot in de header; aanklikbare diagnose per subsystem | R00 |
| R04 | Labels Browser Extension/Lexirise API; leesopties alleen bij Lexirise API | R00 |
| R05 | Updatebanner verwijderen, offline cache en veilige activatie behouden | R00; bestaande updatechecks als vertrekpunt |
| R06 | Permanente uitleg beperken; hulp via focus/hover/tap en herstelacties | R03–R04 voor de betreffende controls |

**Acceptatie**

- [ ] Ontvangen beeld, beeldactualiteit, OCR, bibliotheek en accountstatus zijn
  afzonderlijk te verklaren. Een ongewijzigd beeld wordt niet als bewezen
  netwerkfout weergegeven. Een geselecteerde game wordt niet als gedetecteerd
  draaiend proces gepresenteerd. Ontvangsttijd heet geen end-to-end latency.
- [ ] Klik/tap op status geeft de reden en een passende vervolgstap voor:
  verbinden, eerste frame, stilstaand beeld, onderbreking, pauze, ontbrekende
  bibliotheek, geen match en accountvergrendeling. Geen privé-link in diagnostiek.
- [ ] Oude `migaku`-voorkeuren blijven werken. Browser Extension biedt
  selecteerbare tekst zonder Lexirise-account; extensies zijn voorbeelden met
  platformbeperkingen, geen ongeverifieerde compatibiliteitsgarantie.
- [ ] Beide mobiele ingangen naar Reading options zijn verborgen buiten
  Lexirise API. Algemene tekstgrootte/vertalingsweergave blijven beschikbaar.
- [ ] Geen updatebanner of automatische reload tijdens spelen. Een wachtende
  update kan bij een veilige volgende start of expliciete Settings-actie
  activeren; offline heropenen behoudt historie, favorieten en kalibratie.
- [ ] Hulp werkt via toetsenbord en touch, is sluitbaar en houdt focus logisch.
  Blokkerende fouten en noodzakelijke gebruikerskeuzes blijven zichtbaar.
- [ ] Relevante Chromium/Firefox/WebKit-, smalle scherm-, zoom- en
  Shadow DOM-scenario's slagen. Fysieke iOS-conclusies vereisen apparaatbewijs.

### F2 — ZZZ, temporele herkenning en productie-replay

| ID | Afgebakende oplevering | Voorwaarde |
| --- | --- | --- |
| R07 | Replay door de echte controllers, injecteerbare klok/bron; bewijs dat ZZZ het speciale pad gebruikt; volgorde/duplicatie/tijd als assertions | R01 |
| R08 | Gedeeld gedragscontract en gerichte reparatie van vastgestelde legacy/meertalige fragmentverschillen, met behoud van ambiguïteitscontrole | R07; R02-kwaliteitsgrenzen vóór matchingtuning |
| R09 | Desktop-bubble-identiteit en volgorde over frames, inclusief onbekende volgorde binnen een eerste batch | R08 |
| R10 | Mobiele verwerking van meerdere ZZZ-bubbles en behoud van identiteit bij scroll/verplaatsing | R07–R09 contract; geserialiseerde integratie met R03 |
| R11 | ZZZ-videocorpus en hold-outscènes evalueren, plus regressiematrix voor overige actieve adapters | R07; eindbeoordeling na R08–R10 en R02 |

**Acceptatie**

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
  blijven juist; ongemapte dialoog algemeen toelaten is geen onderdeel van deze fase.
- [ ] Verplaatsing maakt geen nieuwe utterance; een latere echte herhaling kan
  wel een nieuwe occurrence zijn. Meerdere zichtbare bubbles verdringen elkaar niet.
- [ ] Gevalideerde authored volgorde gaat vóór betrouwbare eerste waarneming.
  Zonder beide blijft onderlinge volgorde onbekend; coördinaten, dictionaryvolgorde
  en taalmodellen vullen die niet in. Geen verzonnen audio of automatische
  playbackvolgorde voor een onzekere batch.
- [ ] Kritieke synthetische sequenties hebben nul verkeerde identiteiten,
  onbedoelde duplicaten, verouderde publicaties en volgorde-inversies, én alle
  vereiste regels. Negatieve fixtures publiceren geen onterechte regels/voices.
- [ ] Videoresultaten rapporteren recall, precisie, duplicaten, inversies,
  trackfragmentatie en p50/p95-vertraging per game/presentatie/taal/resolutie.
  Bevroren drempels uit R02 worden gehaald; dekking mag niet worden gered door
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

### F3 — Contracts en gerichte modularisering

| ID | Afgebakende oplevering | Voorwaarde |
| --- | --- | --- |
| R12 | Versieerbare transcript-, bron-, status- en gamecontracts; TS-types afleiden en inputgrenzen valideren waar nuttig | R00; gedragstests van het betrokken pad |
| R13 | Per use-case orchestration uit grote modules halen; gamebeleid in expliciete adapters houden | Betrokken R12-contract; relevante F2-fixtures vóór OCR-verplaatsing |

**Acceptatie**

- [ ] Eén betekenis per gedeeld veld; ontbrekende/onbekende versie of capability
  wordt afgehandeld. UI-local state hoeft niet in een universeel schema.
- [ ] Bron/session/account/language-generations blijven oude resultaten weren.
  Afgebroken voorbereiding publiceert geen halve index; oud gedrag blijft getest.
- [ ] Elke extractie behoudt extern gedrag en heeft een afzonderlijke rollback.
  Een functionele reparatie en brede bestandsverplaatsing komen in aparte changes.
- [ ] Game-specifieke verschillen blijven expliciet. Geen universele heuristiek
  die bestaande uitzonderingen stilzwijgend verwijdert.
- [ ] De gerefactorde module heeft een concrete verantwoordelijkheid en minder
  impliciete afhankelijkheden. Regelcount is geen acceptatiecriterium.

F3 is incrementeel: geen repositorybrede refactor als voorwaarde voor UX of installer.

### F4 — Discovery, voicepacks en gezamenlijke onboarding

| ID | Afgebakende oplevering | Voorwaarde |
| --- | --- | --- |
| R14 | Installatiekandidaat-, packstatus- en voorkeurencontract; één service voor beide UI's | R00 |
| R15 | Steam-appmanifests, Epic/GOG-adapters, HoYoPlay na formaatvalidatie, begrensde fallback en handmatige paden | R14; adapters afzonderlijk testbaar |
| R16 | Per-game/per-taal fysieke voicepackprobes, los van voorbereide index | R14; probes per game parallel mogelijk |
| R17 | Games → talen/packs → Browser Extension/Lexirise API → gereed; opnieuw openen in WebUI | R04, R15–R16; afgestemde R14/R18-opslaggrens |

R14 en R18 leggen samen vast wie voorkeuren schrijft, waar ze worden opgeslagen
en welke migratie-/precedentieregels gelden vóór R17/R19/R21 die grens gebruiken.
R15-launcherdetectie kan ondertussen onafhankelijk doorgaan.

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

### F5 — Windows-bundel, installer en migratie

| ID | Afgebakende oplevering | Voorwaarde |
| --- | --- | --- |
| R18 | Runtime-/tool-/redistributie-inventaris, Windows-versies/architecturen en systeemvoorwaarden; app/data/cache/credentials-layout en prototypebesluit | R00; parallel met F1/F2/F4, opslaggrens samen met R14 |
| R19 | Windows-runtimebundel met functionele probes; statisch serveren van frontend onderzoeken | R18, R02; afgestemde R14/R18-opslaggrens |
| R20 | Per-user installer met geïntegreerde onboarding, repair en uninstall | R17, R19 |
| R21 | ZIP→installer-migratie, upgrade, annulering en rollback met synthetische gebruikersdata | Afgestemde R14/R18-opslaggrens; integraal bewijs met R20 |
| R22 | Kandidaatbuild/artifactvalidatie in bestaande CI integreren; downloads verifiëren en ondertekeningbesluit vastleggen | R20–R21; daarna G uitvoeren voor afronding vóór publicatie |

Voorkeur voor het eerste prototype: Inno Setup plus gebundelde bestaande runtime,
met een PyInstaller-directorybundel als te toetsen optie. MSI/MSIX/Tauri zijn
alternatieven bij een concrete producteis of bewezen blokkade. De native
OCR-componenten uit Snipping Tool zijn geen vrij herdistribueerbare aanname.

**Acceptatie**

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
- [ ] Update laat maximaal één capture-eigenaar actief; voorbereidingsfout houdt
  de vorige runtime bruikbaar. Uninstall behoudt gebruikersdata standaard.
- [ ] GitHub-hosted CI controleert het echte installerartifact; een schone gewone
  Windowsomgeving controleert daarnaast native OCR/capture, actuele launcherrecords,
  meerdere monitors, crop-bounds en 125–200% DPI. Claims noemen de geteste matrix.
- [ ] Downloads hebben geverifieerde checksums en commitkoppeling. JSON-provenance,
  Authenticode en cryptografische buildattestaties zijn onderscheiden. R22 legt
  vast welke aanwezig zijn; ondertekening wordt uitsluitend geclaimd na verificatie
  van signature/timestamp. Sleutels volgen de beschermde-opslagregels.

### F6 — Voorwaardelijke native experimenten

| ID | Afgebakende oplevering | Voorwaarde |
| --- | --- | --- |
| R23 | Eén probleem vergelijken met Python-workerproces, Rust of C# achter dezelfde grens | R02; relevante F2/F3-contracten; R19-bundelingservaring |
| R24 | Beslisdocument met metingen, onderhoudskosten, compatibiliteit en behoud/migratiekeuze | R23 |

**Acceptatie**

- [ ] Het experiment heeft vooraf één hypothese en grens: bijvoorbeeld herstel
  van een hangende native OCR-call of procesbeheer. Geen volledige rewrite als taak.
- [ ] Vergelijk dezelfde hardware, frames, engine/model, catalogus en buildmodus.
  Scheid capture-, OCR-, matching- en publicatietijd; rapporteer cold/warm start,
  RSS, fouten en hersteltijd. Gebruik de vooraf vastgelegde R02-grenzen.
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

## Volgorde voor AI-development

Begin met R00. Daarna kunnen drie afgebakende banen starten: **UX R03–R06**,
**OCR R01→R07→R08→R09→R10**, en **installatie R14–R16 plus R18**. Eén integrator
beheert gedeelde bestanden en legt interfaceafspraken vast vóór parallelle
implementatie. R02 bereidt parallel het meetplan voor en legt met R01 de
kwaliteitsgrenzen vast vóór tuning; ontbrekende baseline blokkeert de relevante
eindbeoordeling van R11/R19/R23. R11 verzamelt onafhankelijk videobewijs zodra R07 werkt. R17 en
R19 komen samen in R20; migratie/layout wordt al in R18 ontworpen. F3 volgt per
onderdeel na voldoende gedragstests. F6 ligt buiten het kritieke pad.

De eerste uitvoeropdrachten zijn dus R00, vervolgens R01/R02/R03/R14/R18 naar
beschikbare capaciteit; niet één opdracht om de hele roadmap te implementeren.
De [taaktemplate](ai-development-workflow.md#taakcontract) maakt elk pakket
overdraagbaar zonder deze hele onderzoeksdiscussie te hoeven reconstrueren.

## Traceerbaarheid naar de wensen

| Wens of risico | Pakketten |
| --- | --- |
| Windows-installer | R18–R22 |
| Games autodetecteren en handmatig kiezen in installer/WebUI | R14–R15, R17, R20 |
| Geïnstalleerde voicepacks tonen | R16–R17 |
| Browser Extension/Lexirise API kiezen tijdens installatie en later | R04, R14, R17, R20 |
| Minder tekst; bereikbare hulp | R06 |
| Game-specifieke OCR beschermen, ZZZ-comics en YouTube-replay | R01, R07–R11 |
| Verbindingsmelding uitleggen en herstel bieden | R03 |
| Leesopties alleen voor Lexirise API | R04 |
| Updatebanner verwijderen | R05 |
| Python/Rust/alternatieven onderbouwd kiezen | R02, R18–R19, R23–R24 |
| AI kan veilig parallel werken en bewijs overdragen | R00, R12–R13, gate G, AI-werkwijze |

## Besluiten die bewijs vereisen

| Besluit | Voorlopige richting | Beslismoment |
| --- | --- | --- |
| Kernruntime | Python behouden; Rust/C# alleen gericht | R24, geen blokkade voor installer |
| Desktopfrontend | Onderzoeken of statische build Node/Wrangler op gebruikers-pc kan vervangen | R19 |
| Installer | Per-user Inno Setup met runtimebundel | R18–R20, schone-Windows-proef |
| OCR-volgorde | Authored metadata indien geverifieerd, anders tijd; onzeker blijft onzeker | R01/R07–R09 |
| Performancegrenzen | Nog geen onderbouwde absolute doelen | R02 vóór optimalisatie/eindbeoordeling |
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
