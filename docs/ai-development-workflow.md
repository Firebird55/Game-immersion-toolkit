# AI-development voor de rework

Deze werkwijze hoort bij de [rework-roadmap](rework-roadmap.md). Status op
2026-10-24: uitvoeringsvoorstel; geen applicatie-implementatie gestart.
[AGENTS.md](../AGENTS.md) en [RELEASE.md](../RELEASE.md) blijven de repositoryregels.
Het lezen van deze documenten start geen werk en autoriseert geen publicatie.

## Wat verandert door AI-development?

Plan op afgebakende resultaten en bewijs, niet op hoeveel code agents kunnen
genereren. AI kan onderzoek, implementatie, fixtures en reviews parallel versnellen.
Integratie, betrouwbare verwachtingen, Windows-/apparaattoegang en releasebewijs
blijven de beperkende factoren. Gebruik geen vaste AI-snelheidsfactor of
ongefundeerde kalenderbelofte.

| Gewone roadmapformulering | Uitvoerbaar AI-werkpakket |
| --- | --- |
| Verbeter verbindingen | Behoud bronstatus tot de badge en bewijs de juiste uitleg bij stilstaande frames, pauze en reconnect |
| Refactor OCR | Laat dezelfde onafhankelijke sequentiefixtures eerst legacy/meertalige verschillen tonen; verander daarna één verantwoordelijkheid |
| Maak een installer | Lever een geïnstalleerd artifact dat op schone Windows de afgesproken functionele probes doorloopt |
| Onderzoek Rust | Vergelijk één workergrens met vaste input, meetplan, correctheidscriteria en expliciete behoud/migratiebeslissing |

Een pakket is klein genoeg als een reviewer het gedrag kan beoordelen en de
wijziging afzonderlijk kan worden teruggedraaid. Aantallen regels, bestanden of
agents zijn geen kwaliteitsmaat. Splits een roadmap-ID zo nodig in bijvoorbeeld
R15a/R15b; leg hun interfaces en integratievolgorde vast en behoud het hoofdcriterium.

## Rollen en parallelle banen

- **Integrator:** bewaakt scope, afhankelijkheden, contracten, migraties en het
  gezamenlijke eindresultaat. Houdt pakketstatus en ontbrekend bewijs bij.
- **Implementerende agent:** onderzoekt en realiseert één begrensd pakket,
  voert relevante checks uit en levert een exacte diff/commit met bewijs.
- **Reviewer:** onderzoekt criteria, broncode, diff en checkuitvoer onafhankelijk
  van de implementatiesamenvatting. Zoekt naar concrete fouten en ontbrekende gevallen.
- **Apparaattester/maintainer:** levert fysieke verificatie en productbesluiten
  waarvoor echte hardware of menselijke beoordeling nodig is.

Begin met hoogstens drie onafhankelijke implementatiebanen: UX, OCR en
installatie/discovery. Meer agents toevoegen is alleen nuttig bij gescheiden
scope en beschikbare reviewcapaciteit. Een agent die fixtures of review doet
hoeft geen parallelle schrijver te zijn.

| Gebied | Parallel mogelijk | Integratie-eigenaar vereist voor |
| --- | --- | --- |
| UX | Copy/hulpontwerp, onafhankelijke browserchecks | `mobile/companion.jsx`, `app/companion.tsx`, gedeelde statuscontracten |
| OCR | Corpusannotatie, replayvalidatie, afzonderlijke gamefixtures | `backend/capture.py`, matchercontracten, `public/mobile-capture/mobile-ui.mjs` |
| Installatie | Launcheradapters, per-game packprobes, runtime-inventaris | `backend/game_paths.py`, `backend/installation.py`, `app/toolkit-setup.tsx`, storage-layout |
| Platform | Packagingproef, testontwerp voor upgrade/rollback | `backend/api.py`, launcher/updater, releaseworkflow |
| Shared reader | Onderzoek/tests in consumers | Source in Lexirise-shared-components; versie en beide consumerupdates |

Twee agents schrijven niet tegelijk aan hetzelfde gedeelde bestand of contract.
Leg eerst de grens vast, integreer de kleine voorbereidende wijziging en laat
afhankelijke taken daarna daarop starten. Gebruik geïsoleerde branches/worktrees
waar schrijvers anders dezelfde checkout zouden wijzigen; inspecteer bestaande
worktrees en hergebruik geschikte exemplaren. Een worktree lost semantische
conflicten niet op. Eén eigenaar integreert en controleert het gezamenlijke resultaat.

## Taakcontract

Bewaar dit contract en de voortgang in de taak-/PR-beschrijving of een beknopt
uitvoeringsdocument gekoppeld aan het roadmap-ID. Maak geen taakdatabase of
verzameling lege statusbestanden. Neem alleen gesaniteerde conclusies in Git op.

```text
Pakket: Rxx — concreet resultaat
Status: planned | ready | active | implemented | verified | blocked
Baseline: branch + commit; relevante veranderingen sinds het onderzoek
Doel: zichtbaar gedrag of meetbaar onderhoudsresultaat
Afhankelijkheden: pakket/contract-ID's en beschikbaar bewijs
Context: AGENTS.md, RELEASE.md, roadmapfase, relevante bronnen/tests
Scope/eigenaar: toegestane modules; integratie-eigenaar bij overlap
Buiten scope: expliciete aangrenzende wijzigingen die een aparte taak zijn
Invarianten: relevante data-, taal-, account-, capture- en compatibiliteitsregels
Acceptatie: observeerbare succes- én foutgevallen; bron van de verwachting
Verificatie: gerichte commands, runtime/hardware, fixture- of corpusversie
Ontbrekende middelen: wat lokaal ontbreekt en welke claim daardoor open blijft
Rollback: hoe deze wijziging veilig kan worden teruggenomen
Oplevering: commit, checkresultaten, review, resterend apparaatbewijs
Volgende stap: exact vervolg binnen scope of concreet besluitpunt
```

`ready` betekent dat de benodigde contracts en toetsbare criteria duidelijk zijn;
het is geen nieuwe toestemming. `implemented` betekent dat code klaarstaat maar
verplicht bewijs nog kan ontbreken. `verified` vereist alle relevante criteria,
review en apparaatchecks. `blocked` noemt een specifieke ontbrekende voorwaarde
en welk onafhankelijk werk nog door kan. Een fase is pas voltooid wanneer alle
verplichte pakketten en gates zijn bewezen; een geslaagde docs-check voltooit geen
implementatiefase.

## Uitvoeringslus

1. **Lees en begrens.** Controleer instructies, Git-status, baseline en actuele
   broncode. Behoud andermans werk. Begin een `codex/`-taakbranch. Leg scope en
   afhankelijkheden vast; maak geen brede opruiming onderdeel van een reparatie.
2. **Leg de verwachting vast.** Bij een bug: een reproducerend geval met correcte
   verwachting. Bij risicovolle refactoring: relevante behoudsinvarianten. Nieuwe
   tests zijn niet verplicht voor eenvoudige copy-/stijlwijzigingen.
3. **Implementeer de kleinste samenhangende stap.** Gebruik bestaande contracts.
   Nieuwe gameheuristiek, storage-migratie of runtimekeuze krijgt eigen bewijs.
4. **Verifieer.** Draai de geselecteerde checks en alleen noodzakelijke aanvullende
   scenario's. Onderzoek fouten; verander geen verwachting of drempel om uitsluitend
   een groen resultaat te krijgen.
5. **Laat gericht reviewen.** Voor capture, accounts, migratie en lifecycle leest
   een tweede agent de actuele diff en relevante code, naast de criteria. Voor
   eenvoudige documentatie/copy volstaat review passend bij het risico.
6. **Integreer en lever op.** Verifieer bevindingen, herstel geldige fouten, voer
   geraakte checks opnieuw uit en commit de logische wijziging met GitHub-noreply
   author/committer. Controleer na integratie het gezamenlijke resultaat.

Agents kunnen binnen een toegewezen en geautoriseerd pakket zelfstandig
onderzoeken, implementeren, verifiëren en een reviewbaar resultaat voorbereiden.
Vraag niet opnieuw toestemming voor iedere routinehandeling. Bij een echte
scopewijziging of ontbrekende externe voorwaarde: lever eerst het onafhankelijke
werk op en leg een concrete keuze met gevolgen voor. Publicatie, releases en
echte accountwrites krijgen geen impliciete toestemming uit deze roadmap.

## Een betrouwbare testverwachting

De implementatie mag niet zijn eigen bewijs produceren. Voor ZZZ mogen verwachte
regels/volgorde niet worden afgeleid van de huidige sorteermethode. Laat het
fixtureontwerp steunen op handmatig bepaalde sequenties, geldige authored metadata
of onafhankelijke annotaties. Een AI-reviewer met dezelfde ongecontroleerde
aanname is geen onafhankelijke waarheid.

- Bewijs dat tests de bedoelde fout detecteren: bijvoorbeeld omgekeerde events,
  een dubbele publicatie of een verouderde bronrespons invoeren en de assertion
  zien falen. Geen algemene mutation-testcampagne voor eenvoudige wijzigingen.
- Meet recall naast precisie; alles weigeren mag geen groene OCR-score geven.
  Houd onbekende volgorde apart van correct bewezen volgorde.
- Voer replay door de echte productiecontroller uit. Test ook de routekeuze voor
  ZZZ en onderscheid legacy/meertalig/mobile. Reproduceer timing met bron- en
  sample-identiteit; door resampling gekopieerde frames zijn geen extra bewijs.
  Twee werkelijk nieuwe observaties met identieke pixels mogen wel bevestigen.
  Meet publicatielatentie vanaf het geannoteerde bronmoment met voldoende bewijs,
  met expliciete klokcorrelatie; meten vanaf OCR-completion verbergt vertraging.
- Houd ongebruikte hold-outscènes apart. Als een hold-out een nieuwe regressiecase
  wordt, voeg ook nieuwe onafhankelijke evaluatiescènes toe en versioneer de set.
- Leg noodzakelijke wijzigingen van criteria expliciet vast met reden en nieuw
  bewijs. Een agent mag geen test schrappen, skip toevoegen of threshold verlagen
  als vervanging voor het oplossen van de gemelde fout.

## Verificatie en bewijs

Gebruik het bestaande selectiesysteem; zie [development checks](development-checks.md).

| Moment | Controle |
| --- | --- |
| Tijdens een wijziging | `npm run check:changed` |
| Volledige taakbranch | `npm run check:changed -- --base origin/main` |
| Criteria niet gedekt door selector | Benoemde aanvullende scenario's; noteer waarom |
| Kandidaat/release | Bestaande volledige browser-/packaginggates in GitHub-hosted CI volgens RELEASE.md |
| Claim over native Windows of iPhone/iPad | Relevante fysieke proef op het daadwerkelijke kandidaatartifact |

Stage nieuwe documentatie vóór de docs-check zodat de huidige linkchecker,
die `git ls-files` gebruikt, die bestanden meeneemt. Timingrapporten blijven in
genegeerde `output/checks`. Herhaal geslaagde brede suites alleen na relevante
wijzigingen, fouten of onopgeloste risico's.

Iedere overdracht vermeldt per controle **pass**, **fail**, **not run** of
**unavailable**, met commit, command, omgeving en reden. Een unavailable
Windowscheck op macOS is geen pass. Leg een dependency-/hostprobleem apart vast
van een productfout; omzeil het niet door tests te verwijderen.

De minimale gesaniteerde bewijskaart bevat pakket-ID, commit, resultaat van elk
acceptatiecriterium, gebruikte fixtureversie, commands/uitkomsten, reviewbevindingen,
rollback en exact resterend werk. Private media, accounts, paden en ruwe logs
blijven buiten Git. Na contextverlies leest een volgende agent deze kaart en de
actuele repository; die begint niet automatisch opnieuw of verklaart ontbrekend
bewijs alsnog geslaagd.

### Wat AI niet met synthetische checks kan bewijzen

Een test met mocked OCR bewijst geen werkende native OCR-installatie. Desktop
WebKit bewijst geen iOS-achtergrondgedrag. Een source-build bewijst geen werkende
installer op schone Windows. Een gewijzigde DOM-fixture bewijst geen werkelijke
Migaku/Yomitan-compatibiliteit.

Lever voor fysieke verificatie eerst een installeerbare kandidaat, concrete stappen,
verwacht resultaat en een gesaniteerd registratieformat. Gebruik het bestaande
[mobiele verificatieprotocol](mobile-capture-verification.md). Het resultaat
geldt alleen voor de genoemde hardware/OS/browser/gameversies. Vraag de tester
pas om actie wanneer die kandidaat klaarstaat; bereid intussen onafhankelijk werk voor.

## Praktische uitvoeropdracht

Gebruik dit pas wanneer een werkpakket daadwerkelijk is toegewezen:

> Voer pakket Rxx uit de rework-roadmap uit. Lees AGENTS.md, RELEASE.md en het
> relevante taakcontract. Controleer baseline en Git-status, behoud de genoemde
> invarianten en blijf binnen de afgesproken modules. Gebruik onafhankelijke
> verwachtingen en voer de relevante checks uit. Laat risicovol gedrag gericht
> reviewen en lever een gecontroleerde commit met bewijs en rollback. Rapporteer
> ontbrekende platformchecks eerlijk en werk zelfstandig door aan niet-geblokkeerde
> onderdelen. Vergroot de scope niet stilzwijgend; deze opdracht omvat geen release.

## Onderbouwing

De algemene opzet met doel, context, grenzen, verificatie en review sluit aan op
de officiële [Codex best practices](https://learn.chatgpt.com/docs/learn/best-practices)
en [outcome-/bewijsgerichte taken](https://developers.openai.com/cookbook/examples/codex/using_goals_in_codex).
De pakketindeling, integratieregels en gates hierboven zijn een voorstel voor
deze repository, geen algemene garantie over AI-prestaties. Er is geen specifiek
model, nieuw abonnement of automatische doorlopende taak vereist.
