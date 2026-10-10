import io
import unittest
from unittest.mock import patch
from PIL import Image, ImageDraw, ImageFont
import take_screenshot as app


class LocalOCRTests(unittest.TestCase):
    def image(self, text):
        font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf', 24)
        image = Image.new('RGB', (180, 44), 'white')
        ImageDraw.Draw(image).text((8, 4), text, font=font, fill='red')
        output = io.BytesIO()
        image.save(output, format='PNG')
        return output.getvalue()

    def test_real_tesseract_amounts(self):
        for text, value in [('123456', 123456), ('908760', 908760), ('1234', 1234)]:
            with self.subTest(text=text):
                self.assertEqual(app.recognize_price(self.image(text), len(text.replace(',', ''))), value)

    def test_missing_digit_rejected(self):
        with self.assertRaises(app.DataError):
            app.recognize_price(self.image('123,456'), 7)

    def test_blank_price_rejected(self):
        with self.assertRaises(app.DataError):
            app.recognize_price(self.image(''), 6)

    def test_low_confidence_rejected(self):
        from subprocess import CompletedProcess
        response = CompletedProcess([], 0, 'header\n5\t1\t1\t1\t1\t1\t0\t0\t10\t10\t15\t123456\n')
        with patch.object(app.subprocess, 'run', return_value=response), self.assertRaises(app.DataError):
            app.recognize_price(self.image('123456'), 6)

    def test_ocr_disagreement_rejected(self):
        from subprocess import CompletedProcess
        responses = [CompletedProcess([], 0, 'header\n5\t1\t1\t1\t1\t1\t0\t0\t10\t10\t95\t123,456\n'),
                     CompletedProcess([], 0, 'header\n5\t1\t1\t1\t1\t1\t0\t0\t10\t10\t95\t123,458\n')]
        with patch.object(app.subprocess, 'run', side_effect=responses), self.assertRaises(app.DataError):
            app.recognize_price(self.image('123,456'), 6)
