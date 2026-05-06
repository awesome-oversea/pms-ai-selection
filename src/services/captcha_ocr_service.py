from __future__ import annotations

import base64
import io
import re
from typing import Any

try:
    from PIL import Image, ImageOps
    _PIL_AVAILABLE = True
except Exception:
    Image = None  # type: ignore[assignment]
    ImageOps = None  # type: ignore[assignment]
    _PIL_AVAILABLE = False


class CaptchaOCRService:
    _CHAR_PATTERNS: dict[str, tuple[str, ...]] = {
        "0": ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
        "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
        "2": ("01110", "10001", "00001", "00010", "00100", "01000", "11111"),
        "3": ("11110", "00001", "00001", "01110", "00001", "00001", "11110"),
        "4": ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
        "5": ("11111", "10000", "10000", "11110", "00001", "00001", "11110"),
        "6": ("01110", "10000", "10000", "11110", "10001", "10001", "01110"),
        "7": ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
        "8": ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
        "9": ("01110", "10001", "10001", "01111", "00001", "00001", "01110"),
        "A": ("00100", "01010", "10001", "10001", "11111", "10001", "10001"),
        "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
        "C": ("01110", "10001", "10000", "10000", "10000", "10001", "01110"),
        "D": ("11100", "10010", "10001", "10001", "10001", "10010", "11100"),
        "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
        "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
        "G": ("01110", "10001", "10000", "10111", "10001", "10001", "01110"),
        "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
        "J": ("00111", "00010", "00010", "00010", "10010", "10010", "01100"),
        "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
        "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
        "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
        "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
        "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
        "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
        "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
        "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
        "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
        "V": ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
        "W": ("10001", "10001", "10001", "10101", "10101", "11011", "10001"),
        "X": ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
        "Y": ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
        "Z": ("11111", "00001", "00010", "00100", "01000", "10000", "11111"),
    }

    def recognize(self, *, image_base64: str | None = None, image_text_hint: str | None = None) -> dict[str, Any]:
        if image_text_hint:
            normalized = re.sub(r"[^A-Za-z0-9]", "", image_text_hint).upper()
            return {
                "recognized_text": normalized[:8],
                "mode": "hint-normalized",
                "confidence": 0.99,
            }
        if image_base64:
            return self._recognize_from_image_base64(image_base64)
        return {
            "recognized_text": "",
            "mode": "empty",
            "confidence": 0.0,
        }

    def _recognize_from_image_base64(self, image_base64: str) -> dict[str, Any]:
        raw = image_base64.split(",", 1)[-1]
        try:
            image_bytes = base64.b64decode(raw, validate=False)
        except Exception:
            return {
                "recognized_text": "",
                "mode": "invalid-image",
                "confidence": 0.0,
            }

        if not _PIL_AVAILABLE:
            return {
                "recognized_text": "",
                "mode": "simple-ocr-unavailable",
                "confidence": 0.0,
            }

        try:
            image = Image.open(io.BytesIO(image_bytes))
        except Exception:
            return {
                "recognized_text": "",
                "mode": "invalid-image",
                "confidence": 0.0,
            }

        gray = ImageOps.grayscale(image)
        bw = gray.point(lambda x: 255 if x > 160 else 0, mode="1")
        chars = self._segment_characters(bw)
        if not chars:
            return {
                "recognized_text": "",
                "mode": "simple-ocr-no-segments",
                "confidence": 0.0,
            }

        recognized: list[str] = []
        scores: list[float] = []
        for char_img in chars[:8]:
            text, score = self._match_character(char_img)
            recognized.append(text)
            scores.append(score)

        confidence = round(sum(scores) / len(scores), 4) if scores else 0.0
        return {
            "recognized_text": "".join(recognized),
            "mode": "simple-template-ocr",
            "confidence": confidence,
            "char_count": len(recognized),
        }

    def _segment_characters(self, image: Image.Image) -> list[Image.Image]:
        width, height = image.size
        pixels = image.load()
        active_columns: list[bool] = []
        for x in range(width):
            has_ink = any(pixels[x, y] == 0 for y in range(height))
            active_columns.append(has_ink)

        segments: list[tuple[int, int]] = []
        start: int | None = None
        for index, active in enumerate(active_columns):
            if active and start is None:
                start = index
            elif not active and start is not None:
                if index - start >= 2:
                    segments.append((start, index - 1))
                start = None
        if start is not None and width - start >= 2:
            segments.append((start, width - 1))

        chars: list[Image.Image] = []
        for left, right in segments:
            cropped = image.crop((left, 0, right + 1, height))
            bbox = cropped.getbbox()
            if bbox is None:
                continue
            cropped = cropped.crop(bbox)
            chars.append(cropped)
        return chars

    def _normalize_char_image(self, image: Image.Image) -> tuple[str, ...]:
        resized = ImageOps.fit(image.convert("1"), (5, 7), method=Image.Resampling.NEAREST)
        pixels = resized.load()
        rows: list[str] = []
        for y in range(7):
            row = "".join("1" if pixels[x, y] == 0 else "0" for x in range(5))
            rows.append(row)
        return tuple(rows)

    def _match_character(self, image: Image.Image) -> tuple[str, float]:
        normalized = self._normalize_char_image(image)
        best_char = "?"
        best_score = -1.0
        total_cells = 35
        for char, pattern in self._CHAR_PATTERNS.items():
            matches = 0
            for y in range(7):
                for x in range(5):
                    if normalized[y][x] == pattern[y][x]:
                        matches += 1
            score = matches / total_cells
            if score > best_score:
                best_char = char
                best_score = score
        return best_char, round(best_score, 4)
