"""Image invariants tested with synthetic pictures and mocked model output."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main


class SplitImageTests(unittest.IsolatedAsyncioTestCase):
    def test_square_padding_round_trip_keeps_pixels(self):
        image = main.Image.new("RGBA", (25, 12), (20, 40, 60, 180))
        square, inner = main.split_square_pad(image)
        self.assertEqual(square.size, (25, 25))
        restored = main.split_unpad(square, inner)
        self.assertEqual(restored.tobytes(), image.tobytes())

    def test_alpha_clamp_does_not_modify_source(self):
        image = main.Image.new("RGBA", (16, 16), (20, 40, 60, 180))
        result = main.split_clamp_alpha(image, (4, 4, 12, 12))
        self.assertEqual(image.getpixel((0, 0))[3], 180)
        self.assertEqual(result.getpixel((0, 0))[3], 0)
        self.assertEqual(result.getpixel((5, 5)), image.getpixel((5, 5)))

    async def test_opaque_model_crop_does_not_expand_subject_alpha(self):
        source = main.Image.new("RGBA", (160, 128), (20, 40, 60, 255))
        plate = source.copy()
        alpha = main.Image.new("L", source.size, 0)
        alpha.paste(200, (65, 50, 90, 78))
        alpha.paste(255, (66, 51, 89, 77))
        plate.putalpha(alpha)
        original = plate.tobytes()
        with patch.object(main, "split_call_image_model", return_value="/output/generated.png"), \
                patch.object(main, "output_file_from_url", return_value="generated.png"), \
                patch.object(main.Image, "open", return_value=main.Image.new("RGBA", (384, 384), (240, 0, 0, 255))):
            result, note = await main.split_ai_repair(
                SimpleNamespace(), source, 160, 128,
                {"id": "subject", "bbox": [65, 50, 25, 28]}, plate,
                {"kind": "edge"}, main.SplitLayersBudget(1))
        self.assertIsNotNone(result, note)
        self.assertEqual(result.getchannel("A").tobytes(), alpha.tobytes())
        self.assertEqual(result.getpixel((0, 0))[3], 0)
        self.assertGreater(result.getpixel((75, 60))[0], source.getpixel((75, 60))[0])
        self.assertEqual(plate.tobytes(), original)

    async def test_background_repair_keeps_every_pixel_outside_mask(self):
        source = main.Image.new("RGBA", (64, 64), (20, 40, 60, 255))
        mask = main.Image.new("L", source.size, 0)
        mask.paste(255, (24, 24, 40, 40))
        original = source.tobytes()
        with patch.object(main, "split_call_image_model", return_value="/output/generated.png"), \
                patch.object(main, "output_file_from_url", return_value="generated.png"), \
                patch.object(main.Image, "open", return_value=main.Image.new("RGBA", (384, 384), (240, 0, 0, 255))):
            result = await main.split_erase_elements(
                SimpleNamespace(), source, 64, 64, None, mask=mask,
                budget=main.SplitLayersBudget(1))
        self.assertIsNotNone(result)
        for y in range(64):
            for x in range(64):
                if not mask.getpixel((x, y)):
                    self.assertEqual(result.getpixel((x, y)), source.getpixel((x, y)), (x, y))
        self.assertGreater(result.getpixel((32, 32))[0], source.getpixel((32, 32))[0])
        self.assertEqual(source.tobytes(), original)


if __name__ == "__main__":
    unittest.main()