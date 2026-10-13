"""Conservative local photo processing; originals and Neon records are never written."""
import base64
import hashlib
from io import BytesIO
from PIL import Image, ImageOps, ImageFilter
import streamlit as st
from komertia_details import PHOTO, original_label, is_order_total, value

MAX_PIXELS = 16_000_000


def enhance_photo(data, scale=2, denoise=True, sharpen=True, white_background=False):
    if scale not in (1, 2, 4) or len(data) > 5 * 1024 * 1024:
        raise ValueError('Выберите увеличение 1×, 2× или 4× и изображение до 5 МБ.')
    try:
        image = Image.open(BytesIO(data))
        if image.width * image.height * scale * scale > MAX_PIXELS:
            raise ValueError('Результат превышает 16 мегапикселей. Уменьшите увеличение.')
        if image.format not in ('PNG', 'JPEG', 'WEBP') or image.mode not in ('RGB', 'RGBA', 'L', 'LA', 'P'):
            raise ValueError('Используйте PNG, JPEG или WebP в обычном цветовом режиме RGB.')
        image.load()
        profile = image.info.get('icc_profile')
        rgba = ImageOps.exif_transpose(image).convert('RGBA')
    except ValueError:
        raise
    except Exception:
        raise ValueError('Не удалось прочитать фотографию.') from None
    alpha = rgba.getchannel('A')
    rgb = rgba.convert('RGB')
    if denoise:
        # Protect edges and lettering; smooth only nearly uniform image areas.
        edges = rgb.convert('L').filter(ImageFilter.FIND_EDGES).filter(ImageFilter.MaxFilter(3))
        protect = edges.point(lambda p: min(255, p * 12))
        soft = Image.blend(rgb, rgb.filter(ImageFilter.GaussianBlur(.45)), .18)
        rgb = Image.composite(rgb, soft, protect)
    dimensions = (rgba.width * scale, rgba.height * scale)
    rgb = rgb.resize(dimensions, Image.Resampling.LANCZOS)
    alpha = alpha.resize(dimensions, Image.Resampling.LANCZOS)
    if sharpen:
        rgb = rgb.filter(ImageFilter.UnsharpMask(radius=.6, percent=35, threshold=4))
    result = rgb.convert('RGBA')
    result.putalpha(alpha)
    transparent = alpha.getextrema()[0] < 255
    if white_background and transparent:
        background = Image.new('RGBA', dimensions, 'white')
        result = Image.alpha_composite(background, result).convert('RGB')
    elif not transparent:
        result = result.convert('RGB')
    output = BytesIO()
    result.save(output, format='PNG', icc_profile=profile)
    return output.getvalue(), dimensions, transparent


def stored_photo_bytes(photo):
    content = value(photo)
    if not content.startswith(('data:image/png;base64,', 'data:image/jpeg;base64,', 'data:image/webp;base64,')):
        raise ValueError('Для фото по внешней ссылке загрузите исходный файл ниже. Фото в базе не изменится.')
    try:
        return base64.b64decode(content.split(',', 1)[1], validate=True)
    except Exception:
        raise ValueError('Сохранённое фото не удалось прочитать.') from None


def enhance_all_photos(frame, progress=None):
    import json
    import zipfile
    rows = [row for _, row in frame.iterrows() if not is_order_total(row)]
    pending = [row for row in rows if value(row.get(PHOTO)).strip()]
    missing = len(rows) - len(pending)
    output = BytesIO()
    report = []
    success = 0
    total_bytes = 0
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for completed, row in enumerate(pending, start=1):
            item = {'position_id': value(row.get('_position_id')), 'Produkt': value(row.get('Produkt')), 'Wariant': value(row.get('Wariant'))}
            try:
                source = stored_photo_bytes(row.get(PHOTO))
                improved, dimensions, _ = enhance_photo(source, scale=2, denoise=True, sharpen=True, white_background=False)
                if total_bytes + len(improved) > 128 * 1024 * 1024:
                    raise ValueError('Общий размер копий превышает 128 МБ. Используйте обработку одного фото для оставшихся товаров.')
                suffix = hashlib.sha256((item['position_id'] + str(completed)).encode()).hexdigest()[:12]
                filename = f'allegro-photo-{suffix}.png'
                archive.writestr(filename, improved)
                total_bytes += len(improved)
                success += 1
                item.update({'file':filename, 'dimensions':list(dimensions), 'status':'ok'})
            except ValueError as exc:
                item.update({'status':'error','error':str(exc)})
            report.append(item)
            if progress:
                progress(completed, len(pending))
        archive.writestr('photos-report.json', json.dumps({'saved':success,'without_photo':missing,'photos':report}, ensure_ascii=False, indent=2))
    return {'zip':output.getvalue(), 'saved':success, 'missing':missing, 'total':len(pending), 'errors':[item for item in report if item['status']=='error']}


def render_batch_enhancement(rows):
    eligible = rows.loc[~rows.apply(is_order_total, axis=1)]
    missing = int(eligible[PHOTO].map(lambda photo: not value(photo).strip()).sum()) if PHOTO in eligible else len(eligible)
    st.caption(f'Без фотографии: {missing}. Массовая обработка: 2×, мягкое уменьшение шума и повышение резкости. Оригиналы не заменяются.')
    token = hashlib.sha256(str([(value(row.get('_position_id')), value(row.get(PHOTO))) for _, row in eligible.iterrows()]).encode()).hexdigest()
    if st.button('Улучшить все фотографии', disabled=missing == len(eligible), key='enhance_all_photos'):
        total = len(eligible) - missing
        bar = st.progress(0, text=f'Обработано 0 из {total}')
        def update(done, count):
            bar.progress(done/count, text=f'Обработано {done} из {count}')
        result = enhance_all_photos(eligible, update)
        result['token'] = token
        st.session_state['enhanced_photo_batch'] = result
    result = st.session_state.get('enhanced_photo_batch')
    if result and result['token'] == token:
        st.success(f"Улучшено фото: {result['saved']} · без фотографии: {result['missing']} · ошибок: {len(result['errors'])}")
        if result['errors']:
            with st.expander('Необработанные фотографии'):
                for item in result['errors']:
                    st.write(' · '.join([item['Produkt'], item['Wariant']]))
                    st.caption(item['error'])
        if result['saved']:
            st.download_button('Скачать ZIP со всеми улучшенными фото', result['zip'], 'allegro-photos-improved.zip', 'application/zip', key='download_enhanced_zip')


def render_enhancement(frame):
    with st.expander('Улучшить фото для Allegro'):
        rows = frame.loc[~frame.apply(is_order_total, axis=1)]
        if rows.empty:
            st.info('Нет товаров для выбора фотографии.')
            return
        render_batch_enhancement(rows)
        st.divider()
        st.caption('Обработка одного фото')
        ids = rows['_position_id'].tolist()
        labels = {row['_position_id']: original_label(row) for _, row in rows.iterrows()}
        position = st.selectbox('Фото товара для улучшения', ids, format_func=lambda item: labels[item], key='enhancement_product')
        upload = st.file_uploader('Или загрузите исходное фото', type=['png','jpg','jpeg','webp'], key='enhancement_upload')
        row = rows.loc[rows['_position_id'].eq(position)].iloc[0]
        try:
            source = upload.getvalue() if upload is not None else stored_photo_bytes(row.get(PHOTO))
        except ValueError as exc:
            st.caption(str(exc))
            return
        scale = st.selectbox('Увеличение разрешения', [2,4,1], format_func=lambda n: f'{n}×', key='enhancement_scale')
        denoise = st.checkbox('Мягкое уменьшение шума', value=True, key='enhancement_noise')
        sharp = st.checkbox('Мягкое повышение резкости', value=True, key='enhancement_sharp')
        white = st.checkbox('Белый фон в прозрачных областях', value=False, key='enhancement_white')
        st.caption('Без перерисовки, изменения формы, надписей или комплектации. Непрозрачный фон не удаляется; оригинал и данные Neon остаются неизменными. Проверьте мелкие детали перед публикацией.')
        token = hashlib.sha256(source + str((position,scale,denoise,sharp,white)).encode()).hexdigest()
        if st.button('Улучшить фотографию', key='enhance_photo'):
            try:
                output, dimensions, transparency = enhance_photo(source, scale, denoise, sharp, white)
                st.session_state['enhanced_photo_result'] = {'token':token,'data':output,'dimensions':dimensions,'transparency':transparency}
            except ValueError as exc:
                st.error(str(exc))
        result = st.session_state.get('enhanced_photo_result')
        if result and result['token'] == token:
            left,right = st.columns(2)
            left.image(source, caption='Оригинал', width='stretch')
            right.image(result['data'], caption=f"Улучшенная копия · {result['dimensions'][0]} × {result['dimensions'][1]}", width='stretch')
            if white and not result['transparency']:
                st.caption('Фото непрозрачное: исходный фон сохранён, чтобы не затронуть товар.')
            st.download_button('Скачать улучшенное фото для Allegro', result['data'], 'allegro-photo-improved.png', 'image/png', key='download_enhanced_photo')
            st.download_button('Скачать неизменённый оригинал', source, 'komertia-original.' + ('jpg' if source[:2] == b'\xff\xd8' else 'webp' if source[:4] == b'RIFF' else 'png'), key='download_original_photo')
