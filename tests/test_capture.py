import numpy as np

from changedetector.capture import is_probably_blank, encode_png


class TestIsProbablyBlank:
    def test_all_black_is_blank(self):
        assert is_probably_blank(np.zeros((50, 50, 3), dtype=np.uint8)) is True

    def test_uniform_color_is_blank(self):
        assert is_probably_blank(np.full((50, 50, 3), 100, dtype=np.uint8)) is True

    def test_varied_content_is_not_blank(self):
        rng = np.arange(50 * 50 * 3, dtype=np.uint8).reshape(50, 50, 3)
        assert is_probably_blank(rng) is False


class TestEncodePng:
    def test_returns_png_bytes(self):
        frame = np.zeros((8, 8, 3), dtype=np.uint8)
        frame[..., 0] = 255  # red
        data = encode_png(frame)
        assert isinstance(data, (bytes, bytearray))
        assert data[:8] == b"\x89PNG\r\n\x1a\n"  # PNG magic number

    def test_grayscale_2d_frame_encodes(self):
        frame = np.full((8, 8), 128, dtype=np.uint8)
        data = encode_png(frame)
        assert data[:8] == b"\x89PNG\r\n\x1a\n"
