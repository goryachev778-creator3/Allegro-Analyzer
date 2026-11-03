"""Previously checked Polish queries for a safe 13-item Apify pilot.

Reviewed search text only. This module never starts paid actor runs and
does not change the saved Neon analysis. Only original row positions are keyed.
"""
from urllib.parse import quote

REVIEWED = [[70,"zestaw ściągaczy tapicerki demontaż radia samochodowego 38 elementów","38 szt.; sprawdzić czerwony wariant"],[73,"obrotowy organizer na przyprawy kuchenny okrągły","sprawdzić rozmiar i kształt"],[78,"mata pod ekspres do kawy ociekowa 40x50 cm czarna","40x50 cm, kolor czarny"],[82,"pokrowiec nakładka na kierownicę karbon 38 cm czarny","38 cm; materiał"],[86,"pokrowiec na kierownicę czarny 38 cm","38 cm; odróżnić od pozycji 82"],[90,"poduszka lędźwiowa samochodowa regulowana","mechanizm regulacji"],[91,"plecak kompresyjny próżniowy B788 czarny","model B788 bez poduszki"],[95,"kompresor samochodowy bezprzewodowy pompka 3668","model 3668, akumulator"],[96,"wkrętak elektryczny mini akumulatorowy czarny","sprawdzić liczbę bitów"],[99,"zestaw narzędzi do usuwania wgnieceń karoserii PDR","sprawdzić skład zestawu"],[100,"odkurzacz samochodowy do sierści czarny","sprawdzić szczotki i akcesoria"],[102,"tłumacz elektroniczny języków S80 Smart czarny","model S80"],[108,"mikroskop kieszonkowy 50-300x uchwyt na telefon","50-300x z uchwytem"]]

def pilot_queue(unpriced):
    by_number = {int(row["№ в базе"]): row for row in unpriced}
    result = []
    for position, query, check in REVIEWED:
        row = by_number.get(position)
        if row is None:
            continue
        item = dict(row)
        item["Запрос Allegro"] = query
        item["Поиск Allegro"] = "https://allegro.pl/listing?string=" + quote(query)
        item["Нужно сверить"] = check
        item["Проверка цены"] = "НЕ ПОДТВЕРЖДЕНА"
        result.append(item)
    return result
