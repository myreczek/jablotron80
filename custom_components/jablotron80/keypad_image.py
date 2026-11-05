"""Reading a picture for the keypad logo (options flow upload)."""

from typing import List

from homeassistant.core import HomeAssistant

from .jablotron import JablotronKeypadImage


def load_pixels(path: str) -> List[List[bool]]:
    """Rows of pixels (True = dark) from an image file, with OLink's threshold."""
    from PIL import Image

    with Image.open(path) as image:
        rgb = image.convert("RGB")
        width, height = rgb.size
        if width > JablotronKeypadImage.WIDTH or height > JablotronKeypadImage.HEIGHT:
            raise ValueError(
                f"the image is {width}x{height}, the keypad takes at most "
                f"{JablotronKeypadImage.WIDTH}x{JablotronKeypadImage.HEIGHT} pixels"
            )
        return [[JablotronKeypadImage.is_dark(*rgb.getpixel((x, y))) for x in range(width)] for y in range(height)]


def load_uploaded(hass: HomeAssistant, file_id: str) -> List[List[bool]]:
    """Pixels of a file uploaded through a form's file selector (executor only)."""
    from homeassistant.components.file_upload import process_uploaded_file

    with process_uploaded_file(hass, file_id) as path:
        return load_pixels(str(path))
