"""The made-up world the sandbox runs on.

Every hotel, partner, person and price here is invented. Destinations and seasons are
real places with general knowledge, but nothing here is client material and nothing
should be read as checked travel advice (entry rules in particular are placeholders).
"""

TEAMS = {
    "asia": ("Team Asia", ["thailand", "vietnam", "japan", "indonesia", "sri-lanka"]),
    "africa": ("Team Africa", ["south-africa", "tanzania"]),
    "americas": ("Team Americas", ["costa-rica"]),
}

DESTINATIONS = {
    "thailand": {
        "name": "Thailand", "nl": "Thailand", "airport": "BKK", "flight_pp": 820,
        "best": "november tot en met april", "rain": "juni tot en met oktober, vooral aan de westkust",
        "stops": [
            ("Bangkok", 3, ["Riverside Lotus Hotel", "Sukhumvit Family Suites"], ["Fietstocht door Thonburi", "Long tail boot over de klongs", "Kookles voor kinderen"]),
            ("Kanchanaburi", 2, ["River Kwai Raft Lodge"], ["Erawan watervallen", "Olifanten opvang (alleen observeren)"]),
            ("Chiang Mai", 3, ["Old City Teak House", "Mae Rim Valley Resort"], ["Kookschool op de boerderij", "Jungle zipline (vanaf 8 jaar)", "Doi Suthep tempel"]),
            ("Khao Sok", 2, ["Khao Sok Treehouse Camp"], ["Kanotocht op de rivier", "Overnachting op het meer"]),
            ("Koh Yao Noi", 5, ["Yao Bay Bungalows", "Koh Yao Family Beach Resort"], ["Kajakken langs de kalkrotsen", "Snorkeltrip naar Hong eilanden"]),
            ("Koh Lanta", 5, ["Lanta Sands Family Resort"], ["Snorkelen bij Koh Rok", "Mangrove kajaktocht"]),
        ],
        "partner": ("Siam Family Journeys", "local_agent"),
    },
    "vietnam": {
        "name": "Vietnam", "nl": "Vietnam", "airport": "HAN", "flight_pp": 860,
        "best": "maart tot en met mei en september tot en met november", "rain": "per regio anders; het midden heeft regen van oktober tot december",
        "stops": [
            ("Hanoi", 3, ["Old Quarter Lantern Hotel"], ["Streetfood tour op de fiets", "Waterpoppentheater"]),
            ("Ninh Binh", 2, ["Tam Coc Rice Field Homestay"], ["Bootje door Trang An", "Fietsen langs de rijstvelden"]),
            ("Halong Bay", 2, ["Bai Tu Long Family Junk"], ["Kajakken in de baai", "Grotbezoek"]),
            ("Hoi An", 4, ["Hoi An Garden Villas"], ["Lantaarns maken", "Kookles met marktbezoek", "Strand van An Bang"]),
            ("Ho Chi Minhstad", 2, ["Saigon Courtyard Hotel"], ["Mekong delta dagtocht", "Cu Chi tunnels (vanaf 10 jaar)"]),
        ],
        "partner": ("Lotus Road Vietnam", "local_agent"),
    },
    "japan": {
        "name": "Japan", "nl": "Japan", "airport": "NRT", "flight_pp": 1150,
        "best": "maart tot en met mei en oktober tot en met november", "rain": "juni en juli (regenseizoen), tyfoons kunnen in augustus en september",
        "stops": [
            ("Tokio", 4, ["Asakusa Family Ryokan", "Shinjuku Compact Suites"], ["Ghibli museum (vooraf reserveren)", "Teamlab digitaal museum", "Sumo training bekijken"]),
            ("Hakone", 2, ["Hakone Onsen Guesthouse"], ["Rondje Hakone met kabelbaan en boot", "Openluchtmuseum"]),
            ("Kyoto", 4, ["Gion Machiya House"], ["Fushimi Inari vroeg in de ochtend", "Samurai les voor kinderen", "Arashiyama bamboebos"]),
            ("Nara", 1, ["Nara Park Inn"], ["Herten in Nara park", "Todai-ji tempel"]),
            ("Osaka", 2, ["Osaka Bay Family Hotel"], ["Aquarium Kaiyukan", "Streetfood in Dotonbori"]),
        ],
        "partner": ("Sakura Trails Japan", "local_agent"),
    },
    "indonesia": {
        "name": "Indonesie", "nl": "Indonesie", "airport": "DPS", "flight_pp": 900,
        "best": "april tot en met oktober", "rain": "november tot en met maart",
        "stops": [
            ("Ubud", 4, ["Ubud Rice Terrace Villas"], ["Rijstterrassen wandeling", "Balinese dansles", "Apenbos"]),
            ("Munduk", 2, ["Munduk Cloud Lodge"], ["Watervallen wandeling", "Koffieplantage"]),
            ("Pemuteran", 3, ["Pemuteran Reef Bungalows"], ["Snorkelen bij Menjangan", "Schildpaddenproject"]),
            ("Nusa Lembongan", 3, ["Lembongan Coral Cottages"], ["Mantarog snorkeltocht (vanaf 8 jaar)", "Mangrove peddelen"]),
            ("Sanur", 2, ["Sanur Beach Family Hotel"], ["Fietsen over de boulevard"]),
        ],
        "partner": ("Island Spirit Bali", "local_agent"),
    },
    "sri-lanka": {
        "name": "Sri Lanka", "nl": "Sri Lanka", "airport": "CMB", "flight_pp": 880,
        "best": "december tot en met april voor het zuiden en westen", "rain": "mei tot en met september aan de zuidwestkust",
        "stops": [
            ("Negombo", 1, ["Lagoon Edge Hotel"], ["Vismarkt in de ochtend"]),
            ("Sigiriya", 3, ["Sigiriya Jungle Lodge"], ["Leeuwenrots beklimmen", "Jeep safari Minneriya"]),
            ("Kandy", 2, ["Kandy Hillside Bungalow"], ["Tempel van de Tand", "Botanische tuin"]),
            ("Ella", 3, ["Ella Tea Estate Cottage"], ["Treinrit door de theeplantages", "Little Adams Peak"]),
            ("Yala", 2, ["Yala Safari Tents"], ["Safari in Yala"]),
            ("Mirissa", 4, ["Mirissa Palm Beach Resort"], ["Walvissen spotten (december tot april)", "Surfles voor kinderen"]),
        ],
        "partner": ("Ceylon Family Tours", "local_agent"),
    },
    "south-africa": {
        "name": "Zuid-Afrika", "nl": "Zuid-Afrika", "airport": "CPT", "flight_pp": 980,
        "best": "oktober tot en met april voor de Kaap, mei tot en met september voor safari", "rain": "winterregen in Kaapstad van juni tot en met augustus",
        "stops": [
            ("Kaapstad", 4, ["Bo-Kaap Family Lofts", "Camps Bay Guesthouse"], ["Tafelberg met de kabelbaan", "Pinguins bij Boulders Beach", "Fietsen langs de wijngaarden"]),
            ("Hermanus", 2, ["Walker Bay Cottages"], ["Walvissen kijken vanaf de kust"]),
            ("Tuinroute", 4, ["Knysna Lagoon Lodge", "Plettenberg Family Chalets"], ["Kanoen op de Keurbooms rivier", "Olifantenpark"]),
            ("Addo", 2, ["Addo Bush Camp"], ["Safari in Addo Elephant Park"]),
            ("Kruger", 3, ["Kruger Riverside Camp"], ["Game drive met ranger", "Bushwalk (vanaf 12 jaar)"]),
        ],
        "partner": ("Cape Horizon Travel", "local_agent"),
    },
    "tanzania": {
        "name": "Tanzania", "nl": "Tanzania", "airport": "JRO", "flight_pp": 1050,
        "best": "juni tot en met oktober en januari tot en met februari", "rain": "maart tot en met mei (lange regentijd)",
        "stops": [
            ("Arusha", 1, ["Arusha Coffee Lodge Garden"], ["Koffieplantage bezoek"]),
            ("Tarangire", 2, ["Tarangire Baobab Camp"], ["Game drive tussen de baobabs"]),
            ("Ngorongoro", 2, ["Crater Rim Family Lodge"], ["Krater safari"]),
            ("Serengeti", 3, ["Serengeti Family Tented Camp"], ["Game drives", "Ballonvaart (vanaf 7 jaar)"]),
            ("Zanzibar", 5, ["Zanzibar Palm Family Resort"], ["Stone Town wandeling", "Specerijentour", "Snorkelen bij Mnemba"]),
        ],
        "partner": ("Kilima Family Safaris", "local_agent"),
    },
    "costa-rica": {
        "name": "Costa Rica", "nl": "Costa Rica", "airport": "SJO", "flight_pp": 1020,
        "best": "december tot en met april", "rain": "mei tot en met november, vaak alleen in de middag",
        "stops": [
            ("San Jose", 1, ["Escazu Garden Hotel"], ["Koffietour"]),
            ("Tortuguero", 2, ["Tortuguero Canal Lodge"], ["Kanoen door de kanalen", "Schildpadden kijken (juli tot oktober)"]),
            ("Arenal", 3, ["Arenal Volcano View Lodge"], ["Hangbruggen wandeling", "Warmwaterbronnen", "Canyoning (vanaf 10 jaar)"]),
            ("Monteverde", 2, ["Cloud Forest Family Cabins"], ["Nachtwandeling", "Zipline (vanaf 8 jaar)"]),
            ("Manuel Antonio", 4, ["Manuel Antonio Jungle Villas"], ["Nationaal park met gids", "Kajakken bij de mangroven"]),
        ],
        "partner": ("Pura Vida Family Travel", "local_agent"),
    },
}

FIRST_NAMES = ["Anouk", "Bas", "Daan", "Eva", "Femke", "Floor", "Gijs", "Hanna", "Iris", "Jesse", "Joris", "Julia",
               "Koen", "Lisa", "Lotte", "Maarten", "Marit", "Merel", "Noor", "Olivier", "Pim", "Roos", "Sem", "Sophie",
               "Thijs", "Tim", "Vera", "Wouter", "Yara", "Zoe"]
SURNAMES = ["Bakker", "Visser", "Smit", "Meijer", "Mulder", "Bos", "Vos", "Peters", "Hendriks", "Brouwer",
            "Kok", "Jacobs", "Vermeulen", "Schouten", "Willems", "Hoekstra", "Koster", "Prins", "Huisman", "Kuipers",
            "Veenstra", "Kramer", "Postma", "Timmermans", "Wolters", "Groen", "Sanders", "Bosman", "Verbeek"]
CITIES = ["Utrecht", "Amersfoort", "Haarlem", "Leiden", "Zwolle", "Nijmegen", "Den Bosch", "Delft", "Groningen",
          "Breda", "Arnhem", "Hilversum", "Amsterdam", "Rotterdam", "Eindhoven"]

WISHES = ["veel natuur", "niet te veel reizen", "strand aan het eind", "iets met dieren", "actief: fietsen en kanoen",
          "cultuur, maar kindvriendelijk", "zwembad bij elk hotel", "lokale ervaringen", "geen lange autoritten",
          "huisje met eigen keuken", "snorkelen", "rustig tempo"]

# Fictional staff. 20 specialists, 6 back office, 3 team leads.
STAFF = {
    "asia": {"lead": "Marloes Kuiper", "specialists": ["Sanne de Vries", "Ilse Vermeer", "Bram Hofman", "Lieke Jansen",
                                                         "Niels Dijkstra", "Fleur van Dam", "Tessa Boer", "Ruud Martens",
                                                         "Esther Pauw", "Kim van Leeuwen"]},
    "africa": {"lead": "Hans Brink", "specialists": ["Mirjam Sluis", "Jeroen Vink", "Annelies Kroon", "Dirk Hoogland",
                                                       "Saskia Mol"]},
    "americas": {"lead": "Paula Rietveld", "specialists": ["Joost Haan", "Laura Wijn", "Martijn Eekhof", "Nadia Bouma",
                                                             "Rick Bloem"]},
}
BACK_OFFICE = ["Ruben Stam", "Carla Doorn", "Wim Teunissen", "Mila Brandsma", "Gerda Lans", "Sven Akkerman"]
