from io import BytesIO
import pytest
from PIL import Image
from photo_enhancement import enhance_photo


def image_bytes(mode='RGB', color=(20,80,120), size=(20,10)):
    stream=BytesIO()
    Image.new(mode,size,color).save(stream,format='PNG')
    return stream.getvalue()


def test_upscale_preserves_original_aspect_and_uniform_color():
    source=image_bytes()
    original=source[:]
    result,size,_=enhance_photo(source,2)
    assert size==(40,20)
    assert source==original
    image=Image.open(BytesIO(result))
    assert image.getpixel((20,10))==(20,80,120)


def test_white_background_only_transparency_and_no_cropping():
    image=Image.new('RGBA',(20,10),(0,0,0,0))
    image.putpixel((10,5),(250,30,60,255))
    stream=BytesIO();image.save(stream,format='PNG')
    result,size,transparent=enhance_photo(stream.getvalue(),1,False,False,True)
    out=Image.open(BytesIO(result))
    assert out.getpixel((0,0))==(255,255,255)
    assert out.getpixel((10,5))==(250,30,60)
    assert transparent and size==(20,10)
    opaque=image_bytes()
    result,_,transparent=enhance_photo(opaque,1,False,False,True)
    assert Image.open(BytesIO(result)).getpixel((0,0))==(20,80,120)
    assert not transparent


def test_invalid_or_excessive_output_rejected():
    with pytest.raises(ValueError): enhance_photo(b'invalid')
    with pytest.raises(ValueError): enhance_photo(image_bytes(size=(1100,1100)),4)


def test_batch_26_images_zip_progress_and_originals_unchanged():
    import pandas as pd
    import base64,zipfile,json
    from photo_enhancement import enhance_all_photos
    from komertia_details import PHOTO
    source=image_bytes()
    photo='data:image/png;base64,' + base64.b64encode(source).decode()
    frame=pd.DataFrame([{'_position_id':f'item-{i}','Produkt':'Produkt','Wariant':str(i),PHOTO:photo,'Закупка PLN':12.5} for i in range(26)])
    before=frame.copy(deep=True)
    progress=[]
    result=enhance_all_photos(frame,lambda x,y:progress.append((x,y)))
    assert result['saved']==26 and result['missing']==0 and not result['errors']
    assert progress==[(i,26) for i in range(1,27)]
    pd.testing.assert_frame_equal(frame,before)
    with zipfile.ZipFile(BytesIO(result['zip'])) as archive:
        names=[n for n in archive.namelist() if n.endswith('.png')]
        assert len(names)==len(set(names))==26
        assert all(Image.open(BytesIO(archive.read(n))).size==(40,20) for n in names)
        report=json.loads(archive.read('photos-report.json'))
        assert report['saved']==26


def test_batch_missing_bad_photo_and_order_total_are_handled():
    import pandas as pd,base64
    from photo_enhancement import enhance_all_photos
    from komertia_details import PHOTO
    photo='data:image/png;base64,'+base64.b64encode(image_bytes()).decode()
    frame=pd.DataFrame([{'_position_id':'good','Produkt':'Produkt',PHOTO:photo},{'_position_id':'none',PHOTO:''},{'_position_id':'bad',PHOTO:'data:image/png;base64,invalid'},{'_position_id':'total','Produkt':'ИТОГО A1632',PHOTO:photo}])
    result=enhance_all_photos(frame)
    assert result['saved']==1 and result['missing']==1 and result['total']==2
    assert len(result['errors'])==1
