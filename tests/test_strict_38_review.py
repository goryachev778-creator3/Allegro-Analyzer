from strict_38_review import review_38_piece

def offer(title):
    return {"Название предложения": title, "Цена brutto PLN": 45, "Ссылка Allegro": "https://allegro.pl/oferta/demo"}

def test_only_explicit_thirty_eight():
    yes, no, maybe = review_38_piece([
        offer("zestaw ściągacze tapicerki 38EL"),
        offer("ściągacze do tapicerki 20 elementów"),
        offer("narzędzia tapicerki 43EL"),
        offer("ściągacze do demontażu tapicerki XL"),
    ])
    assert (len(yes), len(no), len(maybe)) == (1, 2, 1)
    assert "38" in yes[0]["Liczba elementów (z tytułu)"]

def test_no_saving_or_new_scraping():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "strict_38_review.py").read_text()
    assert "save_analysis(" not in src
    assert "urlopen(" not in src
