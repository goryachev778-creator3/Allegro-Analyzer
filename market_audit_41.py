"""Read-only 41-unique-product Allegro market audit, 2026-11-04.

Competitive examples, NOT identified exact product matches. Missing references
remain blank. Original 82 unpriced rows include duplicate representations
of group numbers 68..108, so only canonical identities are shown.
"""
AUDIT_DATE = "2026-11-04"
# canonical position -> [observed competitor gross PLN, source URL, mismatch warning]
LEADS = {
  "69": [
    21.99,
    "https://allegro.pl/listing?string=rozwiertaki+do+wykr%C4%99cania+urwanych+%C5%9Brub",
    "8-elementowy zestaw; w naszym brak liczby elementów"
  ],
  "70": [
    58.24,
    "https://allegro.pl/oferta/zestaw-do-demontazu-tapicerki-38-elementow-beast-18398685325",
    "38 elementów; trzeba porównać komplet i kolor"
  ],
  "71": [
    14.9,
    "https://allegro.pl/listing?string=szczotka+do+szczelin",
    "Szczotka 70 cm do grzejników, inna konstrukcja od 63 cm"
  ],
  "73": [
    19.19,
    "https://allegro.pl/oferta/organizer-obrotowy-do-kuchni-pietrowy-miska-na-przyprawy-przybornik-okragly-17954885997",
    "organizer piętrowy; sprawdzić średnicę i formę"
  ],
  "74": [
    5.99,
    "https://allegro.pl/listing?string=korek+silikonowy+do+umywalki",
    "zwykły korek silikonowy, typ przyssawki niepotwierdzony"
  ],
  "75": [
    24,
    "https://allegro.pl/listing?string=wype%C5%82niacz+szczeliny+luk+pomi%C4%99dzy+fotelami+w+aucie",
    "piankowe 2 szt., porównać materiał i kształt"
  ],
  "76": [
    19.99,
    "https://allegro.pl/listing?string=pasek+wype%C5%82niaj%C4%85cy+szczelin%C4%99+w+fotelu+samochodowym",
    "2 szt., porównać materiał i profil"
  ],
  "77": [
    44.98,
    "https://allegro.pl/listing?string=plecak+czarny+20+litr%C3%B3w",
    "20–40 l w opisie, niepotwierdzona pojemność dokładnie 20 l"
  ],
  "78": [
    14.99,
    "https://allegro.pl/listing?string=mata+pod+ekspres+do+kawy+50x40",
    "czarna 40x50 cm; porównać materiał"
  ],
  "82": [
    59.99,
    "https://allegro.pl/oferta/pokrowiec-na-kierownice-nakladka-srednica-zew-37-39-cm-skora-karbon-carbon-9253495800",
    "37–39 cm; porównać wzór"
  ],
  "84": [
    28.68,
    "https://allegro.pl/listing?string=poduszka+pasa+bezpiecze%C5%84stwa",
    "poduszka na pas, sprawdzić kształt"
  ],
  "85": [
    22.99,
    "https://allegro.pl/listing?string=poduszka+na+zag%C5%82%C3%B3wek+samochodowy+czarna",
    "poduszka szyjna, niepotwierdzony kształt serca"
  ],
  "86": [
    64.99,
    "https://allegro.pl/listing?string=cover+for+steering+wheel+38cm",
    "38 cm mikrofibra, sprawdzić materiał"
  ],
  "88": [
    145,
    "https://allegro.pl/listing?string=mata+ch%C5%82adzaca+na+fotel+samochodowy",
    "mata wentylowana 12 V; nasz produkt może być bez wentylatora"
  ],
  "93": [
    26.9,
    "https://allegro.pl/listing?string=suszarka+do+butow+elektryczna",
    "suszarka elektryczna rozsuwana 20W, niepotwierdzone 8 ramion"
  ],
  "95": [
    176.99,
    "https://allegro.pl/listing?string=mini+kompresor+bezprzewodowe",
    "akumulatorowy kompresor inny model, nie 3668"
  ],
  "96": [
    69.99,
    "https://allegro.pl/listing?string=mini+%C5%9Brubokr%C4%99t+elektryczny",
    "38 bitów; nasz zestaw może mieć inną liczbę bitów"
  ],
  "98": [
    109.99,
    "https://allegro.pl/listing?string=polerka+akumulatorowa+21v",
    "polerka 21V Verk Group; porównać baterie i średnicę tarczy"
  ],
  "99": [
    56.99,
    "https://allegro.pl/produkt/zestaw-do-usuwania-wgniecen-auto-gamma-7-elementow-pdr-3cb6319a-bd23-4c2a-ab73-d12740ffee30",
    "7-elementowy zestaw; nasz pełny zestaw może być inny"
  ],
  "100": [
    85.35,
    "https://allegro.pl/listing?string=odkurzacz+do+sier%C5%9Bci+i+samochodu",
    "odkurzacz bezprzewodowy 400W; akcesoria niepotwierdzone"
  ],
  "102": [
    249.99,
    "https://allegro.pl/produkt/translator-piashow-s80-776c1a6f-d423-44ba-9134-7a0246b1a468",
    "model S80, marka Piashow; zgodność wersji do sprawdzenia"
  ],
  "106": [
    129.99,
    "https://allegro.pl/listing?string=magnetyczna+kula+lewitujaca",
    "lewitujący globus 3 cale; porównać wygląd i zasilacz EU"
  ]
}
NEEDS_IDENTIFICATION = [68,79,81,89,92,94,97,101,104]
def audit_unpriced(unpriced):
    by_id = {}
    for row in unpriced:
        position = int(row["№ в базе"])
        canonical = position if position >= 68 else position + 41
        # Prefer the full source name (positions 68..108) over abbreviated duplicates.
        if canonical not in by_id or position >= 68:
            by_id[canonical] = row
    results = []
    for canonical in sorted(by_id):
        row = by_id[canonical]
        lead = LEADS.get(str(canonical))
        unknown = canonical in NEEDS_IDENTIFICATION
        results.append({
            "Группа": canonical,
            "№ исходной строки": row["№ в базе"],
            "Товар": row["Товар"],
            "Вариант": row["Вариант"],
            "Закупка PLN (без изменений)": row["Закупка PLN"],
            "Цена конкурента brutto PLN (НЕ цена продажи)": lead[0] if lead else None,
            "Источник Allegro": lead[1] if lead else "",
            "Что не совпало / что требуется": lead[2] if lead else ("Невозможно определить модель по описанию; нужно фото/артикул" if unknown else "Нет подтверждённой цены конкретного комплекта"),
            "Статус": "РЫНОЧНЫЙ ОРИЕНТИР — НЕ ПЕРЕНОСИТЬ" if lead else ("НЕОПОЗНАННЫЙ ТОВАР" if unknown else "ЦЕНА НЕ ПОДТВЕРЖДЕНА"),
            "Дата исследования": AUDIT_DATE,
        })
    return results
