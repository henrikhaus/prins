"""The note is a 312x216 black and white pixel grid. Everything that draws on it lives here."""

from .canvas import HEIGHT, WIDTH, Canvas, DesignError, bitmap_to_image, image_to_bitmap

__all__ = ["WIDTH", "HEIGHT", "Canvas", "DesignError", "bitmap_to_image", "image_to_bitmap"]
