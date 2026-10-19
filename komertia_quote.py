"""Parse actual Komertia HTML/WebArchive quotes locally; never fetch remote URLs."""
import base64
import hashlib
import io
import json
import plistlib
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from datetime import date
from urllib.parse import urljoin, urlsplit, parse_qs
from uuid import NAMESPACE_URL, uuid5, UUID
from lxml import html
from PIL import Image
from analyzer import INPUTS
from komertia_details import PHOTO, FULL_NAME

MAX_UPLOAD = 25 * 1024 * 1024
MAX_IMAGES = 35 * 1024 * 1024


class QuoteError(ValueError):
    pass


def decimal(text):
    try:
        value = Decimal(str(text).replace('zł', '').replace('PLN', '').replace('\xa0', '').replace(' ', '').replace(',', '.'))
    except InvalidOperation:
        raise QuoteError('Некорректное число в выценке') from None
    if not value.is_finite() or value < 0:
        raise QuoteError('Отрицательные или бесконечные значения в выценке')
    return value


def safe_url(value):
    u = urlsplit(value)
    return value if u.scheme == 'https' and u.hostname and not u.username and not u.password else ''


def text(cell):
    return ' '.join(cell.text_content().split())


@dataclass
class Quote:
    order_id: str
    batch: str
    records: list
    report: dict
    digest: str


def parse_quote(payload, filename, batch, order_url=''):
    if not payload or len(payload) > MAX_UPLOAD:
        raise QuoteError('Максимальный размер файла — 25 МБ')
    resources = {}
    if filename.lower().endswith('.webarchive'):
        try:
            archive = plistlib.loads(payload)
            main = archive['WebMainResource']
            content = main['WebResourceData']
            order_url = main.get('WebResourceURL', '')
            resources = {r.get('WebResourceURL'): r for r in archive.get('WebSubresources', [])}
        except (ValueError, TypeError, KeyError, plistlib.InvalidFileException):
            raise QuoteError('Не удалось прочитать веб-архив Safari') from None
    elif filename.lower().endswith(('.html', '.htm')):
        content = payload
    else:
        raise QuoteError('Поддерживаются исходные .webarchive и .html выцены Komertia')
    match = re.fullmatch(r'https://(?:www\.)?komertia\.com/client/orders/([a-fA-F0-9-]{36})/?', order_url)
    if not match:
        raise QuoteError('Нужна исходная ссылка Komertia /client/orders/<UUID>')
    order = match[1]
    try:
        UUID(order)
        date.fromisoformat(batch)
    except ValueError:
        raise QuoteError('Некорректная дата партии или идентификатор заказа') from None
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', batch):
        raise QuoteError('Дата партии должна иметь формат ГГГГ-ММ-ДД')
    try:
        root = html.fromstring(content, parser=html.HTMLParser(no_network=True, encoding="utf-8"))
    except (ValueError, TypeError):
        raise QuoteError('Некорректный HTML выцены') from None
    nodes = root.xpath('//tr[starts-with(@id,"product-row-")]')
    if not nodes or len(nodes) > 500:
        raise QuoteError('Не найдены строки таблицы Komertia (product-row-*)')
    table = nodes[0].getparent()
    while table.tag != 'table' and table.getparent() is not None:
        table = table.getparent()
    headers = [text(c) for c in table.xpath('.//th')]
    if 'Cena szt.' not in headers:
        raise QuoteError('В выценке нет окончательной цены Cena szt.')
    footer = next((r for r in table.xpath('.//tr') if r.xpath('./td') and text(r.xpath('./td')[0]).casefold() == 'razem'), None)
    if footer is None:
        raise QuoteError('Нет контрольной итоговой строки Razem')
    foot = []
    for cell in footer.xpath('./td'):
        foot.extend([cell] * int(cell.get('colspan', 1)))
    if len(foot) != 16:
        raise QuoteError('Неизвестная структура итоговой строки')
    expected_qty, first, second, total = (decimal(text(foot[i])) for i in (4, 8, 13, 14))
    if first + second != total:
        raise QuoteError('Первая и вторая оплаты не совпадают с итогом выцены')
    records, pending, ids = [], {}, set()
    units, cost, zero, embedded_bytes, missing_photos = 0, Decimal(0), 0, 0, 0
    variants, source_first = [], Decimal(0)
    grouped_second = {}
    source_signature = []
    for node in nodes:
        cells, carry = {}, {}
        for col, (cell, remaining, group) in pending.items():
            cells[col] = (cell, group)
            if remaining > 1:
                carry[col] = (cell, remaining-1, group)
        col = 0
        for cell in node.xpath('./td'):
            while col in cells:
                col += 1
            group = node.get('id') + ':' + str(col)
            cells[col] = (cell, group)
            span = int(cell.get('rowspan', 1))
            if not 1 <= span <= 500:
                raise QuoteError('Некорректное объединение строк')
            if span > 1:
                carry[col] = (cell, span-1, group)
            col += 1
        pending = carry
        if len(cells) != 16:
            raise QuoteError('Неполная строка товара Komertia')
        qty = decimal(text(cells[4][0]))
        if qty != int(qty):
            raise QuoteError('Количество товара должно быть целым')
        source_first += decimal(text(cells[8][0]))
        grouped_second[cells[13][1]] = decimal(text(cells[13][0]))
        if not qty:
            zero += 1
            continue
        product, variant = text(cells[2][0]), text(cells[3][0])
        links = cells[2][0].xpath('.//a/@href')
        if not product or not links:
            raise QuoteError('Нет названия или исходного идентификатора карточки')
        source = urljoin(order_url, links[0])
        product_match = re.fullmatch(r'https://(?:www\.)?komertia\.com/product/(\d+)/?', source)
        if not product_match:
            raise QuoteError('Неизвестная ссылка карточки товара')
        source_id = product_match[1] + ':' + hashlib.sha256(variant.encode()).hexdigest()[:20]
        identity = str(uuid5(NAMESPACE_URL, f'komertia:{order}:{source_id}'))
        if identity in ids:
            raise QuoteError('Дубли одного product ID и варианта в исходной выценке; импорт остановлен')
        ids.add(identity)
        unit = decimal(text(cells[15][0]))
        record = dict.fromkeys(INPUTS, 0)
        record.update({'Товар': product, 'Produkt': product, 'Wariant': variant, 'SKU': '',
                       'Закупка PLN': float(unit), 'Цена Allegro PLN': None, 'Комиссия %': None,
                       'Ilość': int(qty), 'Партия': batch, 'source_order': batch,
                       'source_order_id': order, 'source_product_id': source_id,
                       'source_row': int(text(cells[0][0])), '_position_id': identity,
                       'source_url': source, FULL_NAME: product,
                       '_komertia_final_cost': True, '_landed_purchase_analysis': True,
                       '_archived_no_allegro_price': False, '_commission_unverified': True,
                       '_variant_source_truncated': '...' in variant or '…' in variant})
        images = cells[1][0].xpath('.//img/@src')
        photo, original = '', ''
        if images:
            proxy = urljoin(order_url, images[0])
            original = safe_url(parse_qs(urlsplit(proxy).query).get('url', [proxy])[0])
            resource = resources.get(proxy) or resources.get(original)
            if resource:
                blob = resource.get('WebResourceData', b'')
                if len(blob) > 5 * 1024 * 1024:
                    raise QuoteError('Исходное фото превышает 5 МБ')
                try:
                    with Image.open(io.BytesIO(blob)) as img:
                        size, fmt = img.size, img.format
                        if max(size) > 12000 or size[0]*size[1] > 40000000:
                            raise QuoteError('Слишком большое разрешение фотографии')
                        img.verify()
                except (OSError, Image.DecompressionBombError):
                    raise QuoteError('Повреждён оригинал фотографии') from None
                mime = {'JPEG': 'jpeg', 'PNG': 'png', 'WEBP': 'webp'}.get(fmt)
                if not mime:
                    raise QuoteError('Неподдерживаемый формат оригинала фото')
                embedded_bytes += len(blob)
                if embedded_bytes > MAX_IMAGES:
                    raise QuoteError('Суммарный размер фото превышает 35 МБ')
                photo = f'data:image/{mime};base64,' + base64.b64encode(blob).decode()
                record['_source_photo_sha256'] = hashlib.sha256(blob).hexdigest()
                record['_source_photo_dimensions'] = list(size)
        record[PHOTO] = photo or original
        record['_source_photo_url'] = original
        if not record[PHOTO]:
            missing_photos += 1
        if record['_variant_source_truncated']:
            variants.append(record['source_row'])
        records.append(record)
        units += int(qty)
        cost += unit * qty
        source_signature.append((identity, int(qty), str(unit), product, variant, record.get('_source_photo_sha256', original)))
    if units != expected_qty or not records:
        raise QuoteError('Количество строк не совпадает с итоговым количеством')
    delta = total - cost
    if abs(delta) > Decimal('.005') * (units+1):
        raise QuoteError('Расхождение стоимости превышает допустимое округление Cena szt.')
    if abs(source_first-first) > Decimal('.005')*(len(nodes)+1) or abs(sum(grouped_second.values())-second) > Decimal('.005')*(len(nodes)+1):
        raise QuoteError('Построчные платежи не совпадают с итогами за пределами округления')
    if missing_photos:
        raise QuoteError('У активных товаров отсутствуют исходные фотографии')
    report = {'order_id': order, 'batch': batch, 'source_positions': len(nodes), 'active_positions': len(records),
              'zero_positions': zero, 'quantity': units, 'first_payment': str(first), 'second_payment': str(second),
              'quote_total': str(total), 'unit_price_total': str(cost), 'rounding_difference': str(delta),
              'incomplete_variant_lps': variants, 'embedded_photo_bytes': embedded_bytes,
              'remote_photos': sum(not r[PHOTO].startswith('data:') for r in records)}
    digest = hashlib.sha256(json.dumps([order, batch, sorted(source_signature), str(first), str(second), str(total)], ensure_ascii=False).encode()).hexdigest()
    return Quote(order, batch, records, report, digest)
