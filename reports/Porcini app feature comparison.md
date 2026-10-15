# Mushroom products show choices for SporaMeteo

Research date: 11 October 2026.

This report compares 27 mushroom and outdoor products and turns their documented capabilities into 80 feature choices for SporaMeteo. F81 adds the owner's requirement for a polished interface. F82 records the later automatic model improvement discussed during the interview. The products combine growth estimates, weather maps, personal records, identification and trip tools in different ways. Their numbers do not share a common meaning or a common accuracy test. SporaMeteo's confirmed goal is a website that shows the estimated chance that porcini are growing in an area on a selected day. The MVP will cover all Italy, show today and the next seven days, and support Italian and English. It will be free without advertising. The owner selected the MVP features below and placed all remaining features in one later epic named "Features Roadmap".

During question 6, the owner selected F11, F12, F13, F14, F18, F23, F39 and F76 for the MVP. The owner also made a polished, carefully designed interface a launch requirement, even with a small initial feature set. Visual quality must be part of the MVP work and its acceptance. The interview is complete. The [product PRD](../docs/product_prd.md) records the agreed requirements before issue creation.

"Features Roadmap" will contain all 66 later features in its description, grouped into tables using the categories below. It will have no sub-tickets. This replaces the earlier proposal to create several later epics. MVP work will still have full epics and sub-tickets based on the PRD.

With accounts and synchronization deferred, MVP favorites stay in the current browser. Users can add, rename and remove them. They do not follow the user to another device, and clearing browser data can remove them. The broader personal-record transfer tools remain later work. F14 controls the selected MVP map layers and does not bring the separate terrain, forest or soil exploration features into scope. The MVP still requires software and input-data checks. Field validation of growth probabilities is not a launch requirement.

During question 7, the owner chose guidance for specific parts of a forest, roughly a few hundred metres across. This is the product's target for map detail. It does not establish that the weather data or prediction accuracy has the same level of detail.

During question 8, the owner accepted experimental probability estimates at launch, clearly labelled as unvalidated with their limitations explained. SporaMeteo is a companion for choosing areas to explore. It must not promise precise mushroom locations. No work may depend on the owner visiting locations to validate predictions.

During question 9, the owner selected automatic weather refresh for the MVP and deferred automatic improvement of the prediction method. F82 records that later capability. New weather keeps estimates current. It does not establish improved accuracy.

For running costs, prefer no new recurring costs and use EUR 10 a month as the planning ceiling if needed. The owner directed the plan to reuse the completed Open-Meteo allowance and cost assessment in P6. No provider purchase is authorized.

The investigation described in [planning_after_epic1.md](../docs/planning_after_epic1.md) establishes technical possibilities and limits. It does not select the product's features. This comparison is an input to the interview and final product requirements document, or PRD.

## The inventory covers public claims, with limits

The research used official websites, help pages, privacy policies and publisher app listings. It did not install apps, create accounts, buy access, test predictions in the field or independently measure identification accuracy. A documented feature below means that a publisher advertises it. An unknown feature means the inspected sources did not settle it. Unknown does not mean absent. The inventory is broad, but it does not claim to include every product or every account-only feature worldwide.

The three source notes retain the detailed findings and gaps for [Italian products](../research_notes/Porcini%20app%20feature%20comparison/italian_products.md), [international prediction products](../research_notes/Porcini%20app%20feature%20comparison/international_predictions.md), and [identification, records and outdoor products](../research_notes/Porcini%20app%20feature%20comparison/adjacent_products.md). The descriptions below keep product identity, platform differences and planned functions separate.

### P01. FungRadar

FungRadar is a website for Italy, Ticino and San Marino. It advertises species models, a 2.5 km map, seven-day indices, growth phases, explanations and reliability labels. Regional and town pages also cover berries, ticks, mosquitoes and sandflies. Website badges are available. Inputs include recent weather, soil moisture, land cover, terrain and observations. [Homepage](https://it.fungradar.com/) and [forecast directory](https://it.fungradar.com/previsioni).

Saved places remain in the current browser without an account or device synchronization. The saved-places page describes voluntary coarse public contributions, while the FAQ denies a collaborative sightings map. Recalculation runs every six hours. Detailed terrain currently covers one region. A gathering-permission layer is planned. The publisher reports evaluation failures as well as successes, but those results do not independently establish a growth probability. [Saved places](https://it.fungradar.com/i-miei-posti), [FAQ](https://it.fungradar.com/domande) and [validation](https://it.fungradar.com/come-verifichiamo).

### P02. Meteo Funghi by FungoCenter

This Italian website offers free national browsing, Google login, six monitored locations, nightly updates, threshold settings and morning email alerts. Pro adds today's local score, seven-day forecasts and a suggested best day. The public alert example is simulated. No public price was established. [Product page](https://meteofunghi.fungocenter.it/).

Its 0 to 10 score uses seven-day average temperature and weighted rain over 28 days. The documented calculation excludes forest type, altitude and slope direction. Marketing uses probability language, but the method describes a weather score. [Method](https://meteofunghi.fungocenter.it/how-it-works).

### P03. MycoMap

MycoMap is an Italy-wide website with guest, free-account and paid access. It advertises dated growth maps, a 0 to 5 score, point explanations, likely species, 40-day weather, 15-day score history, rain and hail, terrain, satellite imagery, trails, stations and downloaded areas. Saved forests have trends and alerts. Diaries record finds and unsuccessful searches, effort, quantity, maturity, larvae, other collectors, habitat and notes. Photos can supply date, elevation and position. Groups have invitations, posts, replies and shared records. Field measurements are restricted to collaborators. GPS recording and GPX transfer appear both as available and as coming later. [App page](https://mycomap.it/).

The privacy policy says displayed finds use an approximate 250 m area while the server retains exact coordinates to improve predictions. Routes remain precise and private unless shared. This conflicts with less specific homepage privacy wording. Account deletion is documented. Weekly, monthly and annual offers exist, but a September promotion was still displayed in October. [Privacy](https://mycomap.it/privacy) and [plans](https://mycomap.it/piani).

### P04. Mappa dei Porcini Premium

This Italian Android app distinguishes four porcini types. Its station map updates five times daily and uses colors for unsuitable, preparatory, productive and declining conditions. A long press gives local estimated temperature, accumulated rain and growth conditions. Stations show ten days of history. The description also mentions adapting a separate model to a user's forest. Advertising is present. The listing declares no collection or sharing of data, which was not independently checked. The publisher warns that favorable weather does not establish that a porcini species lives there. Journals, offline use and exports remain unverified. [Publisher listing](https://play.google.com/store/apps/details?hl=it&id=it.matteoperseoinformatica.mappadeiporcinipremium).

### P05. ilCercaFunghi

This Italian website advertises daily maps, more than 4,000 stations, 1 square kilometre cells, forest cover, slope direction, rain totals, filters and adjustable layer opacity. It offers forecasts three days ahead and local or station dashboards. Clicked places show separate Aereus and Edulis percentages, coordinates, Google Maps directions and charts of growth potential and useful rain remaining. The method combines weather, terrain, vegetation and species needs. [Product page](https://ilcercafunghi.it/) and [map functions](https://ilcercafunghi.it/funzionalita-mappa).

Free and paid plans exist. The extracted plan table repeated restricted functions under Free, so exact restrictions need confirmation. Public sources did not establish independent accuracy, offline use, personal journals or export.

### P06. MyBoletus

MyBoletus advertises daily maps across all 20 Italian regions for porcini, chanterelles, Caesar's mushrooms and St George's mushrooms. Users select region and species. Named inputs include rain, night temperature changes, forest type and elevation. The website also has a seasonal calendar, regional growth articles, a national bulletin, guides, a newsletter and several languages. Account, profile, community and ranking links exist, but their destinations returned only an application shell. Their behavior, access rules, privacy, alerts and offline support remain unverified. [Homepage](https://myboletus.com/it/).

### P07. Semaforo dei Funghi

Funghi Magazine's Android app has a zoomable national map updated weekly from weather and field reports. It links a detailed forecast article, includes an illustrated species atlas, and shows live station weather and accumulated rain. Users can download station history as PDF files. Push notifications announce map and article updates. The publisher calls the map indicative and does not define a numeric probability or forward forecast duration. Its store declaration says no data collection or sharing. Pricing and the remaining field tools were not established. [Publisher listing](https://play.google.com/store/apps/details?id=com.funghimagazine.semaforodeifunghi).

### P08. Catacapea

Catacapea is an Italian iPhone app with paid Base and Pro plans and a trial. It advertises scores for 26 species, ten suggested places near a selected base, explanations, recent iNaturalist reports and personal finds. Other tools include trails, terrain, contours, regional gathering rules, closed days, a species guide, dangerous lookalikes, photo suggestions and an offline return compass. Base covers today and tomorrow within a limited radius. Pro extends the radius and coverage, offers seven days, growth alerts, unlimited saved places, trip recording and downloaded maps. Publisher text was available through indexed store content after direct retrieval failed. Score meaning, retention and location-sharing rules remain unresolved. [Publisher listing](https://apps.apple.com/it/app/catacapea/id6817034469).

### P09. Mycel

Mycel is an iPhone and iPad journal with Italian content and European coverage. It advertises weather-based outing suggestions, forecasts, offline maps, finds, routes, notes, named areas, custom species and worldwide GBIF observations. It includes a species reference and dangerous lookalikes. Lock-screen and Dynamic Island controls record pinned species, while Apple Watch displays trips. Photos stay in Apple Photos. Records use local storage or private encrypted iCloud. It supports Apple Visual Look Up rather than its own photo identification. Free use includes two trips. Paid options add forecasts and bulk photo import. Annual and lifetime prices disagree between the description and purchase table. Regional packs and a web heatmap are future promises. [Publisher listing](https://apps.apple.com/it/app/mycel-mappa-dei-funghi/id6771742569).

### P10. FunghiMapp

This iPhone and iPad app saves private mushroom, truffle and berry places with photos and notes. Harvest records include automatic weather. Seasonal reminders and offline maps are advertised. It has a free download and a lifetime unlock without a subscription. The store description is Italian, while language metadata says English. Its privacy declaration includes location and user identifiers. Coverage, predictive maps, photo identification, community tools and export remain unverified. [Publisher listing](https://apps.apple.com/it/app/funghimapp/id6749822174).

### P11. MushScout

MushScout is an Android app with limited free access and annual Premium. It advertises species scores, twelve-day forecasts, reasons for missing rain or temperature, forest selection and drawn boundaries. Diaries record successful and unsuccessful trips. Trip planning includes walking estimates, return checks, prepared messages and photo suggestions. Ads and referrals expand some free limits. [Publisher listing](https://play.google.com/store/apps/details?hl=it&id=it.fungofind.app).

Documented tools include GPS recording, return-to-car guidance, nearby-find reminders, reconstructed past trips, photos, voice notes, seasonal comparisons, anniversaries, private achievements, rubbish records, friend challenges and live outings. Users can lend a forest to a friend, hide exact finds, opt into coarse community totals, correct local rain and export JSON, CSV or GPX files. [Product page](https://mushscout.eu/it/).

Premium expands species, monitored forests, history, explanations and alerts. It also adds terrain shading, drainage details, 3D routes, forest layers and fewer offline limits. The map colors and forecast have separate meanings. Actual operation and prediction accuracy were not tested. [Plan comparison](https://mushscout.eu/it/premium/).

### P12. FcP Map by Funghi che Passione

FcP Map advertises an Italian Android and web product with free and paid tiers. It combines a growth map and local 0 to 100 score with private pins, photos, habitat notes, cloud synchronization, a personal growth table and threshold alerts. Field tools include GPS, compass, altimeter, parking and return guidance, detailed IGM maps, GPX and CSV export, live group tracking, separation alerts and SOS. It also describes guided identification, diaries, seasonal statistics, shared pins, an expert badge and shop benefits. Core maps and pins work offline, while forecast updates and group tracking require a connection. Courses are planned. These are untested publisher claims. [Feature description](https://funghichepassione.shop/blog/fcp-map-la-migliore-app-per-andare-a-funghi-in-italia/) and [Android listing](https://play.google.com/store/apps/details?hl=it&id=shop.funghichepassione.fcpmap).

### P13. Mycoverse

Mycoverse has iPhone and Android apps developed in Norway for international use. Users select species, area and day, compare areas and inspect weather, woodland and terrain explanations. The publisher discloses coarse or missing data. Trip Mode records finds, distance and time. Other tools include watchlists, a species library, field exercises, tests, groups, companions, chat, blocking and reporting. Free access has limits. Premium adds longer forecasts, alerts and offline briefings. Public pages disagree on the species count. [Homepage](https://mycoverse.app/en/) and [overview](https://mycoverse.app/en/mushroom-app/).

The journal stores photos, dates, names, notes and positions, with optional photo suggestions. Findings are private by default. Public copies use approximate positions. Private links can expose approximate or exact positions and expire. Deliberate safety sharing exposes a live route, last position and expected return. Ordinary Trip Mode stays on the device. Export and account deletion are documented. Store wording that findings are never shared conflicts with these deliberate sharing options. [Privacy policy](https://mycoverse.app/en/privacy/).

### P14. ShroomCast

ShroomCast provides iOS, Android and public web forecasts. Its website advertises 15 European countries including Italy, 14 species and forecasts up to 14 days. It defines its regional percentage as the chance of active fruiting that day and describes its woodland number separately as an estimate. [Homepage](https://shroomcast.net/).

It shows regional colors, daily playback, woodland cards, weather, tree and ground details, explanations and support from past records. Users record finds and unsuccessful searches, then compare them with forecasts. Saved woods stay on the phone. Uploaded finds use their region rather than the woodland, and users can delete server records. [Method](https://shroomcast.net/about/).

The store advertises trends, community finds, alerts, a species calendar, favorites, filters, offline mode and previous-year comparisons. Species pages name lookalikes. Free access covers fewer species and days than Premium. Store copy mentions moon phases, but the research did not establish their usefulness. Older store totals differ from the website. [Publisher listing](https://apps.apple.com/es/app/shroomcast-mushroom-forecast/id6748039058).

### P15. Tattis

Tattis has iOS and Android apps for Finland. Free access includes species search, reference cards, personal place markers and notes, cloud synchronization, protected areas and submissions to laji.fi. Pro adds species maps, forest layers, species weather, offline maps and alerts. Monthly, annual and lifetime access are advertised. Its daily score combines habitat, weather and season. Forest inventory, soil, terrain, water, vegetation and observations describe habitat, while rain, temperature and frost adjust conditions. A fixed off-season gives a zero forecast even though users can record finds. The publisher says the strongest map color does not confirm mushroom presence. The forward forecast duration is unclear. [Official site](https://tattis.life/en/).

### P16. Fung.es

Fung.es provides a browser map and installable app without an account. Users choose mushrooms or edible plants, inspect colored zones and ratings, move a forecast slider, change map styles and open Google Maps directions. It also suggests nearby recipes and routes between ingredients. Named inputs include weather, soil, vegetation, host trees, elevation, water, sightings and season. Downloaded regions include maps and forecasts, with seven-day validity. Local photo identification works after downloading its model. Routes and new environmental detail need a connection. Exact coverage, the complete species list, price and forward forecast duration remain unclear. Seven-day download validity does not establish a seven-day forecast. [Instructions](https://www.fung.es/instructions/).

### P17. Chasseurs de Champignons

This French website offers colored areas, species selection, current location, accounts and habitat searches using tree type, soil acidity, altitude and slope direction. Paid Cueillette Plus adds species, seven-day growth forecasts, alerts, detailed point information, habitat mode and routes to areas. Species passes and subscriptions are sold, but public pages disagree on an initial or restart fee. Gift passes, a learning blog and an external Facebook community are also documented. Offline use, private journals and exports remain unknown. [Official site](https://www.chasseursdechampignons.com/fr/) and [gifts](https://www.chasseursdechampignons.com/fr/offrez-une-carte).

### P18. Pilzwetter

Pilzwetter is an Austrian browser tool for inspecting recent rain and temperature. Users select a period within the last 30 days, view colored rainfall areas and click charts or lists. It uses a 1 km weather grid from GeoSphere Austria radar and stations, with previous-day data fetched each morning. OpenStreetMap supplies the background map. The site describes analytics without cookies or personal data. The inspected page does not establish species probabilities, accounts, saved places, alerts, offline use or paid plans. [Official site](https://pilzwetter.at/).

### P19. Mushroom Forecast

The official page was available only as indexed content because direct fetching returned an empty page. It advertises a global interactive map across 108 regions and 81 species, location and place search, satellite and road maps, and today, three-day and seven-day choices. Markers represent approximate 5 km areas. Percentages use weather, soil moisture and sightings. Premium claims include best-day estimates, species timing, saved trip planning and monthly seasons. Prices, functioning controls, installed apps, offline use, privacy, journals and alerts were not verified. [Official site](https://mushroomforecast.com/).

### P20. Mappa dei Funghi, The Mycologist

This product works in phone, tablet and desktop browsers. The Italian site links other European country sites. It offers porcini, chanterelle and morel maps, with species and area selection, habitat probability, a daily growth index, seven-day trends, point details, thresholds, saved places and a private photo journal with weather on the find date. Named inputs include woodland, trees, geology, soil acidity, elevation and weather. A free Tuscany demo needs no account. [Italian site](https://mappadeifunghi.it/).

Paid access buys one species in one area for a year. Accounts provide device synchronization and subscription management. Different species or areas require other packages. Offline use, export, community posting and photo identification were not documented. [Map plans](https://mappadeifunghi.it/mappe-complete/).

### P21. Mondo Funghi

Mondo Funghi's Italian Android and iOS apps combine conditions maps, a private diary and learning tools. The daily 0 to 100 index compares local environmental conditions with five years of seasonal history. A value of 50 means typical conditions. It also shows forecasts, history, outings on charts, sources, missing or stale data, and terrain or woodland layers. It does not establish mushroom presence. [Feature inventory](https://mondofunghi.it/funzionalita/).

The diary stores species, outcome, place, time, notes, photos and available conditions. Offline regions retain terrain and woodland maps, but satellite imagery and porcini conditions require a connection. Downloads have size estimates, resume, repair and deletion. Sharing can include exact coordinates deliberately. Permit records retain receipts and expiry dates without expiry notifications. ZIP backup and restore include records, settings and study progress. [FAQ](https://mondofunghi.it/faq/).

The species library, lookalike comparisons, quizzes, practice exams and three-photo suggestions have free and paid options. Photo suggestions run on the phone. No account, advertising or analytics are required, and personal records stay locally. Language metadata conflicts with the FAQ's Italian content description. [Publisher listing](https://apps.apple.com/it/app/mondo-funghi/id6764337695) and [privacy](https://mondofunghi.it/privacy/).

### P22. Geoticket

Geoticket sells mushroom, fishing and outdoor permits through its website and mobile apps. It has territory selection, purchase history, notifications, saved places and a digital fishing catch record. [App page](https://geoticket.it/download-app).

Paid Geoticket+ advertises current mushroom growth predictions, weather and habitat inputs, GPS tracking, an altimeter, compass, a secret-place diary, regulation and local alerts, harvest sharing, a community and Mushroom League challenges. Its publisher listing provides no measured accuracy. [Android listing](https://play.google.com/store/apps/details?id=com.geoticket).

iOS notes add area photos, growth levels, an incubation state, a map legend and Apple Wallet support. The service also offers outdoor bookings and permit-selling tools for authorities and retailers. Forecast duration, map detail, offline use, exports and precise privacy controls remain unknown. The Italian store page was rate-limited, so iOS evidence came from the US publisher listing. Store privacy declarations include tracking or third-party sharing. [iOS listing](https://apps.apple.com/us/app/geoticket/id1475238989?platform=ipad) and [website](https://geoticket.it/).

### P23. Picture Mushroom

Picture Mushroom has Android and iOS apps and a web encyclopedia. It proposes species from photos and provides comparison details, habitat and toxicity information, articles, saved places, local seasonal suggestions, a distribution map, personal collections and sharing. Free download leads to paid offers for unlimited identification, expert consultation and ad-free information. Italian is listed. The distribution map is not established as a weather forecast. [Publisher listing](https://apps.apple.com/us/app/picture-mushroom-identifier/id1474578078) and [website](https://picturemushroom.com/app).

Users can remove saved pictures, save them to their device and share identification results through another app. Bulk export and offline operation remain unverified. The store's detailed privacy declaration includes location, photos, search history and tracking data. [FAQ](https://picturemushroom.com/faq).

### P24. Shroomify

The iOS app offers offline photo assistance, illustrated trait questions, species search, comparison, favorites and a local photo logbook. Release notes add three-photo comparison, export and restore. Its guide advertises over 400 species. A weather preview compares recent and future conditions with seasonal patterns, without harvest counts or habitat comparison. Weather needs a connection. iOS uses a one-time purchase without separate subscriptions or ads. Optional photo contributions and translated content are described. [iOS listing](https://apps.apple.com/us/app/shroomify-mushroom-id-usa/id1490594715).

The Android listing instead documents trait matching, regional datasets, monthly suggestions and in-app purchases. Feature parity must not be assumed. Weather coverage, forecast duration, export format and independent identification accuracy remain unresolved. [Android listing](https://play.google.com/store/apps/details?hl=en_US&id=com.mushroom.shroomify).

### P25. iNaturalist

iNaturalist provides a free worldwide website and mobile apps for observations with photos or sounds, date and position. Computer suggestions and community review help identify them. Accounts synchronize records. Searches filter maps by species, place, date, observer, identification status, project and other details. Projects, journals, forums and followed observations support community work. [Introduction](https://www.inaturalist.org/blog/130697-introduction-to-inaturalist-turn-your-curiosity-into-discovery) and [search guide](https://www.inaturalist.org/pages/search%2Burls).

The newer iPhone app includes live or offline suggestions, batch photo import and multiple-photo observations. Platform differences remain. Observations are public by default, with open, blurred or private location controls and trusted access. The service can obscure vulnerable species. Nearby public records can still reveal a hidden location. [App comparison](https://help.inaturalist.org/en/support/solutions/articles/151000216149-what-s-the-difference-between-inaturalist-and-inaturalist-classic-) and [location privacy](https://help.inaturalist.org/en/support/solutions/articles/151000169938-what-is-geoprivacy-what-does-it-mean-for-an-observation-to-be-obscured-).

CSV export and moderation through flags, hidden content, warnings and account sanctions are documented. Offline maps and trail navigation were not established. [Export guide](https://help.inaturalist.org/en/support/solutions/articles/151000170342-how-can-i-download-data-from-inaturalist-) and [enforcement guide](https://help.inaturalist.org/en/support/solutions/articles/151000232621-community-guidelines-enforcement).

### P26. Mushroom Observer

Mushroom Observer's Android app records mushroom observations and photos without a connection, then uploads them to an account. Its community helps with identification. The publisher declares location, personal information and photo collection, encrypted transfer and a deletion-request option. [Android listing](https://play.google.com/store/apps/details?hl=en_US&id=org.mushroomobserver).

The website currently requires a verified account for nearly all content. Account creation is free, and public links provide data and image downloads. The organization publishes biodiversity records through GBIF. Detailed website tools, location hiding, moderation and native iOS availability remain unverified because the research did not sign in. [Access page](https://mushroomobserver.org/) and [GBIF publisher record](https://www.gbif.org/publisher/b873c239-a68e-4133-ae0b-0c534101f7b5).

### P27. AllTrails

AllTrails is a website and mobile outdoor-navigation service. It offers trail search and filters, maps, favorites, lists, external driving directions, GPS activity recording and public reviews or photos. Editors review submitted trail changes. [Getting started](https://support.alltrails.com/hc/en-us/articles/37200401098516-Getting-started-on-AllTrails).

Paid plans add offline areas, 3D and printed maps, weather and other trail conditions, popular-route maps, device transfer, wrong-turn alerts and live sharing. The higher plan adds map layers, multi-day planning, route editing and camera identification for trees, flowers and insects. Mushroom identification was not established. Older marketing differs from the September 2026 membership guide, which governs the comparison here. [Membership guide](https://support.alltrails.com/hc/en-us/articles/37200882853140-The-benefits-of-AllTrails-premium-membership).

Privacy settings cover public, follower and private content. Users can request account exports. GPX transfer is documented by device partner COROS. AllTrails provides navigation examples, not evidence of porcini prediction. [Privacy](https://support.alltrails.com/hc/en-us/articles/4410205748244-Your-account-privacy-options), [account export](https://support.alltrails.com/hc/en-us/articles/18177547076116-How-to-request-a-copy-of-your-AllTrails-account-data) and [COROS instructions](https://support.coros.com/hc/en-us/articles/37955063572500-Connect-AllTrails-with-COROS).

### Additional leads have narrower evidence

Associazione Meteofunghi is separate from FungoCenter's Meteo Funghi. Its site has a dated growth chart and Google Earth overlays. A municipality list is planned. FungoApp advertises saved areas, offline maps, compass, rain history, three-day weather, calendars and visit statistics. Funghi italiani provides an AMINT species reference and GPS records. These received less investigation than the 27 products above. [Associazione Meteofunghi](https://www.meteofunghi.it/), [FungoApp](https://play.google.com/store/apps/details?id=org.fungoapp.app) and [Funghi italiani](https://apps.apple.com/it/app/funghi-italiani/id1169188181).

Mushroom Map's creator described a US morel habitat and forecast service, but the linked application could not be fetched. ShroomSpy's inspected site was a marketplace with mushroom information, without an established prediction product. Focused searches did not establish relevant products called FungoGo, Fungaiolo or Micodata. These names do not increase the main product count. [Mushroom Map creator post](https://www.reddit.com/r/mushroom_hunting/comments/1js69fw/i_made_a_map_that_forecasts_where_and_when_morels/) and [ShroomSpy](https://shroomspy.com/).

## Similar percentages can describe different promises

ShroomCast defines a regional percentage as the chance of active fruiting on that day. Mondo Funghi instead compares environmental conditions with local seasonal history. Tattis combines habitat, weather and season into a score. The Mycologist separates habitat probability from its daily growth index. These are distinct claims even when they produce similar-looking maps. [ShroomCast](https://shroomcast.net/), [Mondo Funghi](https://mondofunghi.it/funzionalita/), [Tattis](https://tattis.life/en/) and [The Mycologist](https://mappadeifunghi.it/).

The user selected actual growing probability for SporaMeteo. A condition score cannot silently replace that choice. The product PRD defines the area, date, event and experimental status. None of the inspected sources establishes a common test under which a displayed 70 percent consistently corresponds to growing porcini in seven out of ten comparable areas and dates. Competitor wording alone cannot establish that evidence for SporaMeteo. The owner accepts clearly labelled unvalidated estimates for the MVP.

Map detail and weather detail also need separate treatment. A map can draw fine shapes while weather observations cover a much larger area. A live map, a future estimate and a replay of a past date need separate date rules. Likewise, a private favorite, a find record, an unsuccessful search and permission to use records for model improvement are separate choices. The checklist preserves these distinctions.

## Feature selection

Each ID identifies a capability that can be discussed without adopting an entire competitor's package. The example links point to public evidence. They do not certify working software. A row can contain settings within one capability, such as the number of forecast days. Those settings still need decisions if the user selects that row.

`Confirmed` means the user selected the requirement for the MVP. `Later` means it belongs in the description of the single "Features Roadmap" epic, without sub-tickets. Product references retain their platform and evidence limits from the inventory above.

### Growth estimates and dates

| ID | Capability and remaining choice | Public examples | Status |
|---|---|---|---|
| F01 | Show the estimated chance that porcini are growing in an area on the selected day. Define the event and area before interpreting the percentage. | [ShroomCast](https://shroomcast.net/) uses similar regional wording. | Confirmed |
| F02 | Cover all Italy at the MVP launch. Define how unavailable evidence appears within that coverage. | [MyBoletus](https://myboletus.com/it/) advertises all 20 regions. | Confirmed |
| F03 | Offer a separate habitat view showing places where a species can live, apart from daily growth estimates. | [The Mycologist](https://mappadeifunghi.it/). | Later |
| F04 | Show growing-probability estimates for today. | [Meteo Funghi](https://meteofunghi.fungocenter.it/) offers a today view with a different score meaning. | Confirmed |
| F05 | Show growing-probability estimates for the next seven days. Date controls remain a design choice. | [ShroomCast](https://shroomcast.net/), [MushScout](https://play.google.com/store/apps/details?hl=it&id=it.fungofind.app) offer future estimates with different durations. | Confirmed |
| F06 | Replay past dates and show how estimates changed. Distinguish saved predictions from later reconstruction. | [MycoMap](https://mycomap.it/), [ShroomCast](https://shroomcast.net/about/). | Later |
| F07 | Compare areas, rank nearby options or highlight the best day for a saved area. | [Catacapea](https://apps.apple.com/it/app/catacapea/id6817034469), [Meteo Funghi](https://meteofunghi.fungocenter.it/). | Later |
| F08 | Distinguish porcini types or species within the porcini group. | [Mappa dei Porcini](https://play.google.com/store/apps/details?hl=it&id=it.matteoperseoinformatica.mappadeiporcinipremium), [ilCercaFunghi](https://ilcercafunghi.it/funzionalita-mappa). | Later |
| F09 | Add other mushrooms or edible plants as selectable subjects. | [Tattis](https://tattis.life/en/), [Fung.es](https://www.fung.es/instructions/). | Later |
| F10 | Show seasonal calendars and growth stages such as preparation, production and decline. | [ShroomCast](https://apps.apple.com/es/app/shroomcast-mushroom-forecast/id6748039058), [Mappa dei Porcini](https://play.google.com/store/apps/details?hl=it&id=it.matteoperseoinformatica.mappadeiporcinipremium). | Later |
| F11 | Explain which weather or habitat facts raise or lower an estimate. | [Mycoverse](https://mycoverse.app/en/mushroom-app/), [MushScout](https://mushscout.eu/it/premium/). | Confirmed |
| F12 | Show sources, update times, missing data, uncertainty and the real detail supported by the evidence. | [Mondo Funghi](https://mondofunghi.it/funzionalita/), [FungRadar](https://it.fungradar.com/). | Confirmed |
| F82 | Automatically improve the prediction method using new public mushroom observations. | Owner deferred this capability during question 9. | Later |

### Map controls and environmental information

| ID | Capability and remaining choice | Public examples | Status |
|---|---|---|---|
| F13 | Search places, use current position and inspect a clicked point. | [Mondo Funghi](https://mondofunghi.it/funzionalita/). | Confirmed |
| F14 | Choose map backgrounds, control layer visibility and adjust opacity. | [Fung.es](https://www.fung.es/instructions/), [ilCercaFunghi](https://ilcercafunghi.it/). | Confirmed |
| F15 | Inspect elevation, slope, direction, shade and drainage. | [MushScout](https://mushscout.eu/it/premium/). | Later |
| F16 | Inspect forest type, host trees, tree age, density or cover. | [ShroomCast](https://shroomcast.net/about/), [Tattis](https://tattis.life/en/). | Later |
| F17 | Inspect soil acidity, moisture and temperature. | [The Mycologist](https://mappadeifunghi.it/), [ShroomCast](https://shroomcast.net/about/). | Later |
| F18 | Inspect current weather and recent rain over selectable periods, with temperature, drying, frost or hail where available. | [Pilzwetter](https://pilzwetter.at/), [MycoMap](https://mycomap.it/). | Confirmed |
| F19 | Inspect weather stations and historical charts, with downloadable reports if selected. | [Semaforo dei Funghi](https://play.google.com/store/apps/details?id=com.funghimagazine.semaforodeifunghi). | Later |
| F20 | Show protected areas, gathering restrictions and closed days. | [Tattis](https://tattis.life/en/), [Catacapea](https://apps.apple.com/it/app/catacapea/id6817034469). | Later |
| F21 | Overlay published sightings and filter by species, date or identification status. | [iNaturalist](https://www.inaturalist.org/pages/search%2Burls), [Mycel](https://apps.apple.com/it/app/mycel-mappa-dei-funghi/id6771742569). | Later |
| F22 | Let a user draw or select a forest boundary for analysis. | [MushScout](https://play.google.com/store/apps/details?hl=it&id=it.fungofind.app). | Later |

### Personal places and outing records

| ID | Capability and remaining choice | Public examples | Status |
|---|---|---|---|
| F23 | Save private favorite points or areas with names, colors and folders or lists. | [Mondo Funghi](https://mondofunghi.it/faq/), [AllTrails](https://support.alltrails.com/hc/en-us/articles/37200401098516-Getting-started-on-AllTrails). | Confirmed |
| F24 | Keep a find journal with date, location, species, quantity and optional condition details. | [MycoMap](https://mycomap.it/). | Later |
| F25 | Record unsuccessful searches, time spent and possible reasons for finding nothing. | [ShroomCast](https://shroomcast.net/about/), [MushScout](https://play.google.com/store/apps/details?hl=it&id=it.fungofind.app). | Later |
| F26 | Fill records with weather or photo date and position, while allowing corrections. | [FunghiMapp](https://apps.apple.com/it/app/funghimapp/id6749822174), [MycoMap](https://mycomap.it/). | Later |
| F27 | Attach photos, text and voice notes, with bulk import if selected. | [MushScout](https://mushscout.eu/it/), [Mycel](https://apps.apple.com/it/app/mycel-mappa-dei-funghi/id6771742569). | Later |
| F28 | Compare outings with weather or forecasts and summarize seasons, anniversaries and previous years. | [ShroomCast](https://apps.apple.com/es/app/shroomcast-mushroom-forecast/id6748039058), [MushScout](https://mushscout.eu/it/). | Later |
| F29 | Reconstruct past outings from later-entered records or photos. | [MushScout](https://mushscout.eu/it/). | Later |
| F30 | Choose local-only storage, account synchronization or both for personal records. | [Mycel](https://apps.apple.com/it/app/mycel-mappa-dei-funghi/id6771742569), [Mondo Funghi](https://mondofunghi.it/privacy/). | Later |
| F31 | Back up, restore, import, export and delete personal records. Define supported formats and replacement behavior. | [Mondo Funghi](https://mondofunghi.it/faq/), [Shroomify](https://apps.apple.com/us/app/shroomify-mushroom-id-usa/id1490594715). | Later |
| F32 | Monitor places or species and send threshold, rain, season or reminder alerts. Choose email, push or both. | [Meteo Funghi](https://meteofunghi.fungocenter.it/), [MushScout](https://mushscout.eu/it/premium/). | Later |

### Offline use

| ID | Capability and remaining choice | Public examples | Status |
|---|---|---|---|
| F33 | Download map backgrounds and selected terrain or forest layers. | [Mondo Funghi](https://mondofunghi.it/faq/). | Later |
| F34 | Keep estimates or briefings available offline with their date and expiry. | [Fung.es](https://www.fung.es/instructions/), [Mycoverse](https://mycoverse.app/en/mushroom-app/). | Later |
| F35 | Read and create personal records offline, then upload them later if synchronization is selected. | [Mushroom Observer](https://play.google.com/store/apps/details?hl=en_US&id=org.mushroomobserver). | Later |
| F36 | Run identification suggestions or reference tools offline. | [Shroomify](https://apps.apple.com/us/app/shroomify-mushroom-id-usa/id1490594715). | Later |
| F37 | Use downloaded routes or return guidance without a connection. | [Catacapea](https://apps.apple.com/it/app/catacapea/id6817034469), [AllTrails](https://support.alltrails.com/hc/en-us/articles/37200882853140-The-benefits-of-AllTrails-premium-membership). | Later |
| F38 | Show download sizes and provide resume, repair and deletion controls. | [Mondo Funghi](https://mondofunghi.it/faq/). | Later |

### Reaching an area and recording the walk

| ID | Capability and remaining choice | Public examples | Status |
|---|---|---|---|
| F39 | Open a destination in an external driving or navigation app. | [ilCercaFunghi](https://ilcercafunghi.it/funzionalita-mappa). | Confirmed |
| F40 | Show trails, contours, 3D terrain or printable maps for field use. | [AllTrails](https://support.alltrails.com/hc/en-us/articles/37200882853140-The-benefits-of-AllTrails-premium-membership). | Later |
| F41 | Create and edit walking routes, estimate travel time and plan multi-day trips. | [AllTrails](https://support.alltrails.com/hc/en-us/articles/37200882853140-The-benefits-of-AllTrails-premium-membership). | Later |
| F42 | Record a GPS route, duration and distance, including operation with the screen off where supported. | [MushScout](https://mushscout.eu/it/), [Mycoverse](https://mycoverse.app/en/). | Later |
| F43 | Save parking and provide a compass, altitude and return-to-car guidance. | [FcP Map](https://funghichepassione.shop/blog/fcp-map-la-migliore-app-per-andare-a-funghi-in-italia/). | Later |
| F44 | Deliberately share a live outing, last position and expected return. | [Mycoverse](https://mycoverse.app/en/privacy/). | Later |
| F45 | Offer wrong-turn or group-separation alerts, return checks and emergency messages. Each selected function needs explicit limits. | [AllTrails](https://support.alltrails.com/hc/en-us/articles/37200882853140-The-benefits-of-AllTrails-premium-membership), [MushScout](https://play.google.com/store/apps/details?hl=it&id=it.fungofind.app). | Later |
| F46 | Import or export route files and exchange routes or activity with watches. | [COROS and AllTrails](https://support.coros.com/hc/en-us/articles/37955063572500-Connect-AllTrails-with-COROS). | Later |
| F47 | Record finds from a lock-screen control or watch without opening the full app. | [Mycel](https://apps.apple.com/it/app/mycel-mappa-dei-funghi/id6771742569). | Later |

### Privacy, sharing and community

| ID | Capability and remaining choice | Public examples | Status |
|---|---|---|---|
| F48 | Set exact, approximate, trusted-person or private location visibility separately for each kind of record. | [iNaturalist](https://help.inaturalist.org/en/support/solutions/articles/151000169938-what-is-geoprivacy-what-does-it-mean-for-an-observation-to-be-obscured-). | Later |
| F49 | Share a selected place or record by link, QR code or file, with explicit coordinates and optional expiry. | [Mycoverse](https://mycoverse.app/en/privacy/), [Mondo Funghi](https://mondofunghi.it/faq/). | Later |
| F50 | Decide separately whether personal records may improve predictions, and what consent and location precision that requires. | [MycoMap's data use](https://mycomap.it/privacy), [MushScout's optional coarse sharing](https://mushscout.eu/it/). Neither establishes a SporaMeteo consent rule. | Later |
| F51 | Publish community observations or coarse totals and let users search them. | [iNaturalist](https://www.inaturalist.org/pages/search%2Burls), [MushScout](https://mushscout.eu/it/). | Later |
| F52 | Offer invitations, groups, companions, chat, posts, replies or followed activity. | [Mycoverse](https://mycoverse.app/en/), [iNaturalist](https://help.inaturalist.org/en/support/solutions/articles/151000216149-what-s-the-difference-between-inaturalist-and-inaturalist-classic-). | Later |
| F53 | Report and block users or content, with moderation and appeal rules defined before use. | [iNaturalist enforcement](https://help.inaturalist.org/en/support/solutions/articles/151000232621-community-guidelines-enforcement). | Later |
| F54 | Ask other users to suggest or review an identification. | [Mushroom Observer](https://play.google.com/store/apps/details?hl=en_US&id=org.mushroomobserver), [iNaturalist](https://www.inaturalist.org/blog/130697-introduction-to-inaturalist-turn-your-curiosity-into-discovery). | Later |
| F55 | Identify verified experts or trusted contributors with a visible status. | [FcP Map](https://funghichepassione.shop/blog/fcp-map-la-migliore-app-per-andare-a-funghi-in-italia/). | Later |
| F56 | Add achievements, friend challenges, rankings or rubbish-collection records. Decide public and private behavior separately. | [MushScout](https://mushscout.eu/it/), [Geoticket](https://play.google.com/store/apps/details?id=com.geoticket). | Later |
| F57 | Let users export all account data and request account deletion, distinct from deleting a single find. | [Mycoverse](https://mycoverse.app/en/privacy/), [AllTrails export](https://support.alltrails.com/hc/en-us/articles/18177547076116-How-to-request-a-copy-of-your-AllTrails-account-data). | Later |

### Identification and learning

| ID | Capability and remaining choice | Public examples | Status |
|---|---|---|---|
| F58 | Provide species reference cards with names, photos, habitat and season. | [Picture Mushroom](https://apps.apple.com/us/app/picture-mushroom-identifier/id1474578078). | Later |
| F59 | Compare similar species and show dangerous lookalikes. | [Mycel](https://apps.apple.com/it/app/mycel-mappa-dei-funghi/id6771742569), [ShroomCast](https://apps.apple.com/es/app/shroomcast-mushroom-forecast/id6748039058). | Later |
| F60 | Suggest possible species from one or several photos. Define limits and avoid presenting a suggestion as consumption approval. | [Mondo Funghi](https://apps.apple.com/it/app/mondo-funghi/id6764337695), [Picture Mushroom](https://apps.apple.com/us/app/picture-mushroom-identifier/id1474578078). | Later |
| F61 | Guide identification through visible traits and illustrated questions. | [Shroomify](https://play.google.com/store/apps/details?hl=en_US&id=com.mushroom.shroomify). | Later |
| F62 | Offer consultation with a human expert. | [Picture Mushroom](https://apps.apple.com/us/app/picture-mushroom-identifier/id1474578078). | Later |
| F63 | Provide quizzes, practice exams and review of mistakes. | [Mondo Funghi](https://apps.apple.com/it/app/mondo-funghi/id6764337695). | Later |
| F64 | Provide guided field exercises and learning progress. | [Mycoverse](https://mycoverse.app/en/). | Later |
| F65 | Publish guides, growth bulletins, newsletters or embeddable website badges. | [MyBoletus](https://myboletus.com/it/), [FungRadar](https://it.fungradar.com/previsioni). | Later |

### Permits and commercial services

| ID | Capability and remaining choice | Public examples | Status |
|---|---|---|---|
| F66 | Sell permits and retain purchase history or wallet passes. | [Geoticket](https://geoticket.it/download-app). | Later |
| F67 | Store an existing permit's authority, number, receipt, cost and expiry. Expiry alerts would be a separate choice. | [Mondo Funghi](https://mondofunghi.it/faq/) documents records without expiry alerts. | Later |
| F68 | Notify users about local restrictions or changes to gathering rules. | [Geoticket](https://play.google.com/store/apps/details?id=com.geoticket). | Later |
| F69 | Offer outdoor bookings, authority or retailer tools, or member shop benefits. | [Geoticket](https://geoticket.it/), [FcP Map](https://funghichepassione.shop/blog/fcp-map-la-migliore-app-per-andare-a-funghi-in-italia/). | Later |
| F70 | Provide free access without advertising for the MVP. Competitor paid tiers, one-time purchases, species or area packs, trials, gifts and referral rewards remain documented alternatives for a later decision. | [The Mycologist](https://mappadeifunghi.it/mappe-complete/), [Chasseurs gifts](https://www.chasseursdechampignons.com/fr/offrez-une-carte), [MushScout](https://play.google.com/store/apps/details?hl=it&id=it.fungofind.app). | Confirmed |
| F71 | Suggest recipes and routes between ingredient locations. | [Fung.es](https://www.fung.es/instructions/). | Later |

### Website access and supporting choices

| ID | Capability and remaining choice | Public examples | Status |
|---|---|---|---|
| F72 | Provide the growth map as a responsive website for phone and desktop. | [The Mycologist](https://mappadeifunghi.it/) demonstrates browser access across device sizes. | Confirmed |
| F73 | Provide native phone or tablet apps in addition to the website. | [ShroomCast](https://shroomcast.net/). | Later |
| F74 | Let users install the website on a device as an app. | [Fung.es](https://www.fung.es/instructions/). | Later |
| F75 | Offer Italian and English in the first release. | [MyBoletus](https://myboletus.com/it/), [Shroomify](https://apps.apple.com/us/app/shroomify-mushroom-id-usa/id1490594715) document translated content. | Confirmed |
| F76 | Allow useful browsing without registration. Define which capabilities require an account. | [Fung.es](https://www.fung.es/instructions/), [The Mycologist demo](https://mappadeifunghi.it/). | Confirmed |
| F77 | Offer accounts and selected sign-in methods when required by saved data, sharing or paid access. | [Meteo Funghi](https://meteofunghi.fungocenter.it/) documents Google login. | Later |
| F78 | Show outdoor conditions beyond mushroom growth, such as snow, air quality or insect activity. | [AllTrails](https://support.alltrails.com/hc/en-us/articles/37200882853140-The-benefits-of-AllTrails-premium-membership), [FungRadar](https://it.fungradar.com/previsioni). | Later |
| F79 | Accept local weather corrections or structured field measurements. | [MushScout](https://mushscout.eu/it/) documents local rain correction. | Later |
| F80 | Publish how predictions are evaluated, including errors and failed targets. Define the acceptance evidence for percentage claims. | [FungRadar's published evaluation](https://it.fungradar.com/come-verifichiamo). | Later |
| F81 | Deliver a polished, coherent interface on phone and desktop, even with a small feature set. Visual quality is a launch requirement. | Explicit owner requirement during question 6. | Confirmed |

## Existing project patterns can guide implementation after selection

The local Book Corners project supplies concrete technical examples. Its [README](../../book-corners/README.md) describes Django and Django Ninja for the server, PostgreSQL with PostGIS for geographic data, Django templates and HTMX for pages, Tailwind CSS with daisyUI for styling, and Leaflet for maps. Its [dependencies](../../book-corners/requirements.txt) include django-allauth for accounts and database-backed background tasks. Docker Compose supports local development. Dokku and GitHub Actions provide deployment examples.

These are reuse candidates. Their use in Book Corners does not require SporaMeteo to copy every dependency, account feature, hosting service or infrastructure setting. This report does not pin versions. The confirmed website and OpenStreetMap direction should guide later design, while the selected data and interaction requirements determine which existing patterns fit.

The [product PRD](../docs/product_prd.md) records the confirmed MVP and later features. The next planning step is to create complete epics and sub-issues for MVP work, and one "Features Roadmap" epic whose description contains the grouped later features without sub-tickets. The mockup epic will use the selected MVP scope. It will require two alternatives before production UI work, one from Google Stitch using a prepared prompt and one created by the agent. This report does not design those mockups.
