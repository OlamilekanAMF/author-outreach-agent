import io
from PIL import Image, ImageDraw, ImageFont
import logging

logger = logging.getLogger(__name__)

class ImageGenerator:
    def __init__(self):
        # Try to load a generic sans-serif font, or fallback to default
        self.font_large = self._get_font(40)
        self.font_medium = self._get_font(24)
        self.font_small = self._get_font(18)

    def _get_font(self, size):
        try:
            # On windows
            return ImageFont.truetype("arial.ttf", size)
        except:
            try:
                # On linux
                return ImageFont.truetype("DejaVuSans.ttf", size)
            except:
                return ImageFont.load_default()

    def generate_spotlight_card(self, author_name: str, book_title: str) -> bytes:
        try:
            # Create a background image (e.g. dark blue/slate)
            width, height = 800, 400
            img = Image.new('RGB', (width, height), color=(15, 23, 42))
            draw = ImageDraw.Draw(img)

            # Draw a subtle gradient or border
            draw.rectangle([20, 20, width-20, height-20], outline=(37, 99, 235), width=4)

            # Add Text
            # We need to wrap text if it's too long, but we'll keep it simple for now
            title = "Rejoicebookclub Author Spotlight"
            
            # Simple centering logic
            def draw_centered_text(text, font, y_pos, color):
                # get text length
                text_bbox = draw.textbbox((0, 0), text, font=font)
                text_width = text_bbox[2] - text_bbox[0]
                x_pos = (width - text_width) / 2
                draw.text((x_pos, y_pos), text, font=font, fill=color)

            draw_centered_text(title, self.font_small, 60, (148, 163, 184))
            draw_centered_text(author_name, self.font_large, 150, (255, 255, 255))
            
            book_str = book_title[:50] + "..." if len(book_title) > 50 else book_title
            draw_centered_text(f'"{book_str}"', self.font_medium, 220, (191, 219, 254))
            
            draw_centered_text("We'd love to feature your work.", self.font_small, 320, (148, 163, 184))

            # Save to bytes
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='PNG')
            return img_byte_arr.getvalue()
            
        except Exception as e:
            logger.error(f"Failed to generate spotlight image: {e}")
            return b""

image_generator = ImageGenerator()
