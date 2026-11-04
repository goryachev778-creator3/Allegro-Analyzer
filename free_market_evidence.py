"""Manually researched public market snapshots (4 Nov 2026).

These are competitors, NOT verified exact equivalents. No scraping or Neon writes.
Prices are snapshots and must not be used as live quotes.
"""
from datetime import date

SNAPSHOT_DATE = "2026-11-04"
LEADS = [
    (70, "Zestaw do demontażu tapicerki BEAST 38 elementów", 58.24, "https://allegro.pl/oferta/zestaw-do-demontazu-tapicerki-38-elementow-beast-18398685325", "38 elementów, inna marka; porównać kolor i komplet"),
    (70, "Ściągacze narzędzia do tapicerki EinParts 38 elementów", 59.99, "https://allegro.pl/oferta/sciagacze-klucze-lyzki-narzedzia-do-demontazu-tapicerki-radia-plastikow-x38-15437648672", "38 elementów; sprawdzić identyczność zestawu"),
    (73, "Organizer obrotowy piętrowy na przyprawy Verk Group", 19.19, "https://allegro.pl/oferta/organizer-obrotowy-do-kuchni-pietrowy-miska-na-przyprawy-przybornik-okragly-17954885997", "dwupoziomowy, biały, 25 cm; sprawdzić wariant"),
    (82, "Nakładka na kierownicę karbon skóra 37–39 cm", 59.99, "https://allegro.pl/oferta/pokrowiec-na-kierownice-nakladka-srednica-zew-37-39-cm-skora-karbon-carbon-9253495800", "37–39 cm; sprawdzić wzór i materiał"),
    (99, "Zestaw PDR Auto Gamma 7 elementów", 56.99, "https://allegro.pl/produkt/zestaw-do-usuwania-wgniecen-auto-gamma-7-elementow-pdr-3cb6319a-bd23-4c2a-ab73-d12740ffee30", "7-elementowy wariant; NIE porównywać bez składu zestawu"),
    (99, "Zestaw PDR Super PDR z pullerem i młotkiem", 235.22, "https://allegro.pl/oferta/zestaw-do-usuwania-wgniecen-puller-pdr-xxl-wyciaganie-wgniotek-podluznych-14176256374", "większy zestaw; NIE porównywać bez składu zestawu"),
]
# Allegro /produkt is a valid detail page but intentionally not accepted by
# the automatic /oferta parser. These links are human research references.
def market_leads(unpriced):
    positions = {int(r["№ в базе"]): r for r in unpriced}
    result = []
    for number, name, price, url, warning in LEADS:
        product = positions.get(number)
        if product is None:
            continue
        result.append({
            "№ в базе": number,
            "Наш товар": product["Товар"],
            "Предложение конкурента": name,
            "Цена brutto PLN": price,
            "Allegro": url,
            "Дата проверки": SNAPSHOT_DATE,
            "Что проверить": warning,
            "Статус": "ОРИЕНТИР — НЕ ПОДТВЕРЖДЕНО",
        })
    return result
