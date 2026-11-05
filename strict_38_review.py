"""Strictly classify title-only 38-piece trim-removal kit results.

No Actor calls, database mutations, automatic pricing or fees.
"""
import re

COUNT = re.compile(r"(?<!\d)(\d{1,3})\s*(?:[- ]?(?:element(?:ów|y)?|el\.?|szt(?:uk|\.)?|części|cz\.?))(?!\w)",re.I)
CAR_WORDS = re.compile(r"tapicer|demontaż|sciagacz|ściągacz|plastik|radio|spinek|wyjmaki", re.I)


def review_38_piece(offers):
    accepted, excluded, uncertain = [], [], []
    for offer in offers:
        title = str(offer.get("Название предложения", ""))
        counts = {int(x) for x in COUNT.findall(title)}
        data = dict(offer)
        data["Liczba elementów (z tytułu)"] = ", ".join(str(v) for v in sorted(counts)) or "brak"
        if not CAR_WORDS.search(title):
            data["Decyzja"] = "ODRZUĆ — inny typ produktu"
            excluded.append(data)
        elif counts and 38 in counts and len(counts) == 1:
            data["Decyzja"] = "KANDYDAT 38 szt. — zweryfikuj zdjęcie, materiał i zestaw"
            accepted.append(data)
        elif counts and 38 not in counts:
            data["Decyzja"] = "ODRZUĆ — inna liczba elementów"
            excluded.append(data)
        else:
            data["Decyzja"] = "BRAK POTWIERDZENIA 38 szt. w tytule"
            uncertain.append(data)
    return accepted, excluded, uncertain
