import pandas as pd
import pytest
from apify_verified_prices import apply_verified, build_review_rows

def frame():
    rows=[]
    for n in range(1,109):
        rows.append({
            "_position_id": f"item-{n}",
            "Товар":f"Товар {n}", "Produkt":f"Produkt {n}", "Wariant":"red",
            "Закупка PLN": 29.99, "Цена Allegro PLN": 0.0, "Комиссия %":0.0,
            "Комиссия PLN":0.0, "Фото Komertia": "original",
        })
    return pd.DataFrame(rows)

def valid_record():
    return {
        "№": 70, "_position_id": "item-70",
        "Ссылка Allegro": "https://allegro.pl/oferta/zestaw-tapicerki-123",
        "Цена продажи PLN": 58.24, "Комиссия %": 11.5,
        "Товар, комплект и категория проверены": True,
        "Комиссия проверена по тарифу Allegro": True,
    }

def test_only_verified_row_and_columns_change():
    original=frame()
    result,count=apply_verified(original,[valid_record()])
    assert len(original)==len(result)==108 and count==1
    assert result.loc[69, "Цена Allegro PLN"]==58.24
    assert result.loc[69, "Комиссия %"]==11.5
    assert result.loc[69, "Закупка PLN"]==29.99
    assert result["Фото Komertia"].eq("original").all()
    assert original.loc[69, "Цена Allegro PLN"]==0
    assert result.loc[68, "Цена Allegro PLN"]==0

def test_refuses_unverified_and_missing_commission():
    decision=valid_record()
    decision["Комиссия проверена по тарифу Allegro"]=False
    with pytest.raises(ValueError):
        apply_verified(frame(),[decision])
    decision["Комиссия проверена по тарифу Allegro"]=True
    decision["Комиссия %"]=None
    with pytest.raises(ValueError):
        apply_verified(frame(),[decision])

def test_refuses_stale_position_and_existing_prices():
    wrong=valid_record()
    wrong["_position_id"]="different"
    with pytest.raises(ValueError):
        apply_verified(frame(),[wrong])
    existing=frame()
    existing.loc[69, "Цена Allegro PLN"]=40
    with pytest.raises(ValueError):
        apply_verified(existing,[valid_record()])

def test_refuses_wrong_row_count():
    with pytest.raises(ValueError):
        apply_verified(frame().iloc[:-1], [valid_record()])

def test_cannot_auto_accept_search_result():
    original=frame()
    raw=[{"Группа товара":70,"Статус":"ПРЕДВАРИТЕЛЬНЫЙ КАНДИДАТ",
          "Цена конкурента brutto PLN":58.24,"Предложение Allegro":"Zestaw 38 elementów",
          "Ссылка Allegro":"https://allegro.pl/oferta/test"}]
    targets=[{"№ в базе":70,"Товар":"Zestaw","Вариант":"red"}]
    review=build_review_rows(original, raw, targets)
    assert len(review)==1
    assert review[0]["Цена продажи PLN"] is None
    assert review[0]["Комиссия %"] is None
    assert review[0]["Товар, комплект и категория проверены"] is False
