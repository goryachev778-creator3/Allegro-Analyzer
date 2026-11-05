"""Prepared Allegro research queries (32 identifiable out of 41 groups).

Based on the user's reviewed CSV. Even "searchable" does not mean the
exact product is known. No inferred sale prices or commission percentages.
"""
SEARCHES = [
  [
    69,
    "zestaw wierteł wykrętaki do uszkodzonych śrub"
  ],
  [
    70,
    "zestaw ściągaczy tapicerki demontaż radia samochodowego 38 elementów"
  ],
  [
    71,
    "szczotka szczelinowa do czyszczenia kuchenki 63 cm"
  ],
  [
    72,
    "samoprzylepny schowek pod szafkę organizer czarny"
  ],
  [
    73,
    "obrotowy organizer na przyprawy kuchenny okrągły"
  ],
  [
    74,
    "silikonowy korek do umywalki z przyssawką"
  ],
  [
    75,
    "wypełniacz szczeliny między fotelami samochodowymi czarny 2 szt"
  ],
  [
    76,
    "listwa uszczelka szczeliny między fotelami samochodowymi 2 szt"
  ],
  [
    77,
    "plecak turystyczny outdoor 20l czarny"
  ],
  [
    78,
    "mata pod ekspres do kawy ociekowa 40x50 cm czarna"
  ],
  [
    80,
    "lampa solarna COB panel słoneczny KS-8002"
  ],
  [
    82,
    "pokrowiec nakładka na kierownicę karbon 38 cm czarny"
  ],
  [
    83,
    "podłokietnik samochodowy organizer z ładowaniem czarny"
  ],
  [
    84,
    "poduszka szyjna do samochodu na pas bezpieczeństwa czarna"
  ],
  [
    85,
    "poduszka pod zagłówek samochodowy szyjna czarna serce"
  ],
  [
    86,
    "pokrowiec na kierownicę czarny 38 cm"
  ],
  [
    87,
    "organizer samochodowy pudełko na chusteczki przy fotelu czarne"
  ],
  [
    88,
    "podkładka chłodząca na fotel samochodowy letnia"
  ],
  [
    90,
    "poduszka lędźwiowa samochodowa regulowana"
  ],
  [
    91,
    "plecak kompresyjny próżniowy B788 czarny"
  ],
  [
    93,
    "suszarka do butów składana elektryczna 8 ramion"
  ],
  [
    95,
    "kompresor samochodowy bezprzewodowy pompka 3668"
  ],
  [
    96,
    "wkrętak elektryczny mini akumulatorowy czarny"
  ],
  [
    98,
    "polerka samochodowa akumulatorowa 21v"
  ],
  [
    99,
    "zestaw narzędzi do usuwania wgnieceń karoserii PDR"
  ],
  [
    100,
    "odkurzacz samochodowy do sierści czarny"
  ],
  [
    102,
    "tłumacz elektroniczny języków S80 Smart czarny"
  ],
  [
    103,
    "robot pies elektroniczny kamera podwójna deluxe"
  ],
  [
    105,
    "sofa piankowa kompresowana 55D"
  ],
  [
    106,
    "kula magnetyczna lewitująca 3 cale zasilacz EU granatowa"
  ],
  [
    107,
    "teleskop astronomiczny High Times HD"
  ],
  [
    108,
    "mikroskop kieszonkowy 50-300x uchwyt na telefon"
  ]
]
NOT_IDENTIFIABLE = [68, 79, 81, 89, 92, 94, 97, 101, 104]
def queries():
    assert len(SEARCHES) == 32
    assert len(NOT_IDENTIFIABLE) == 9
    return [row[1] for row in SEARCHES]
