import unittest
from pathlib import Path
import io
from PIL import Image
import take_screenshot as app


class DigitTemplateTests(unittest.TestCase):
    def test_real_site_prices_including_tesseract_misread(self):
        directory = Path(__file__).parent / 'fixtures'
        for amount in (1126291, 576821):
            with self.subTest(amount=amount):
                png = (directory / f'price-{amount}.png').read_bytes()
                self.assertEqual(app.recognize_price(png, len(str(amount))), amount)

    def test_missing_digit_count_rejected(self):
        png = (Path(__file__).parent / 'fixtures' / 'price-576821.png').read_bytes()
        with self.assertRaises(app.DataError):
            app.recognize_price(png, 7)

    def test_unrecognized_glyph_rejected(self):
        png = (Path(__file__).parent / 'fixtures' / 'price-576821.png').read_bytes()
        image = Image.open(io.BytesIO(png)).convert('RGB')
        image.putpixel((10, 7), (0, 0, 0))
        output = io.BytesIO()
        image.save(output, format='PNG')
        with self.assertRaises(app.DataError):
            app.recognize_price(output.getvalue(), 6)

    def test_blank_image_rejected(self):
        output = io.BytesIO()
        Image.new('RGB', (80, 32), 'white').save(output, format='PNG')
        with self.assertRaises(app.DataError):
            app.recognize_price(output.getvalue(), 6)
