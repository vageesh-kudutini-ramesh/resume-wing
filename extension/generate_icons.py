"""
generate_icons.py
─────────────────
Generates the three PNG icons required by Chrome extensions (16×16, 48×48, 128×128)
using only Python's built-in `struct` and `zlib` modules — no Pillow or any
third-party dependency required.

The icons are solid indigo squares (#4f46e5) matching the ResumeWing colour palette.

Run once from the extension/ directory:
    python generate_icons.py

Output:
    icons/icon16.png
    icons/icon48.png
    icons/icon128.png
"""

import struct
import zlib
import os


def _make_png(size: int, rgb: tuple = (79, 70, 229)) -> bytes:
    """
    Create a minimal, valid solid-colour square PNG.

    PNG structure: signature + IHDR + IDAT + IEND.
    Each row is a filter byte (0 = None) followed by the RGB pixel data.
    """
    r, g, b = rgb

    def chunk(name: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(name + data) & 0xFFFFFFFF
        return struct.pack('>I', len(data)) + name + data + struct.pack('>I', crc)

    signature = b'\x89PNG\r\n\x1a\n'

    # IHDR: width, height, bit depth, colour type (2=RGB), compress, filter, interlace
    ihdr = chunk(b'IHDR', struct.pack('>IIBBBBB', size, size, 8, 2, 0, 0, 0))

    # Raw image data: one filter byte (0) per row + RGB pixels
    raw_rows = b''
    row_pixels = bytes([r, g, b]) * size
    for _ in range(size):
        raw_rows += b'\x00' + row_pixels

    idat = chunk(b'IDAT', zlib.compress(raw_rows, level=9))
    iend = chunk(b'IEND', b'')

    return signature + ihdr + idat + iend


def main():
    os.makedirs('icons', exist_ok=True)

    # Indigo: #4f46e5 = RGB(79, 70, 229)
    COLOR = (79, 70, 229)

    for size in (16, 48, 128):
        path = os.path.join('icons', f'icon{size}.png')
        with open(path, 'wb') as f:
            f.write(_make_png(size, COLOR))
        print(f'  Created {path}  ({size}×{size}px)')

    print('\nDone. Icons are in the icons/ folder.')
    print('You can replace them with a proper logo later — just keep the same file names.')


if __name__ == '__main__':
    main()
