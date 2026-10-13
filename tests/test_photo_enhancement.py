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
