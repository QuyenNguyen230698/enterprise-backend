from io import BytesIO
import unittest

from fastapi import HTTPException
from PIL import Image, ImageDraw

from app.api.v1.profile_route import _scan_signature_to_blue_png


class SignatureScannerTests(unittest.TestCase):
    def _make_signature_image(self) -> bytes:
        image = Image.new("RGB", (640, 220), "white")
        draw = ImageDraw.Draw(image)
        draw.line([(60, 150), (180, 90), (280, 140), (380, 80), (560, 130)], fill="black", width=8)
        out = BytesIO()
        image.save(out, format="PNG")
        return out.getvalue()

    def test_scan_converts_signature_to_blue_png(self):
        processed = _scan_signature_to_blue_png(self._make_signature_image())
        result = Image.open(BytesIO(processed)).convert("RGBA")

        colored_pixels = [px for px in result.getdata() if px[3] > 0]
        self.assertGreater(len(colored_pixels), 200, "Expected detected signature pixels")

        blue_dominant = sum(1 for r, g, b, a in colored_pixels if b >= r and b >= g and a > 0)
        self.assertGreaterEqual(blue_dominant / len(colored_pixels), 0.95)

    def test_scan_rejects_invalid_image_payload(self):
        with self.assertRaises(HTTPException):
            _scan_signature_to_blue_png(b"not-an-image")


if __name__ == "__main__":
    unittest.main()
