"""Encode responsive landing assets from retained originals (Pillow with AVIF/WebP).

After replacing a source PNG in marketing/assets, re-run for that image, e.g.
  python scripts/optimize_landing_images.py student-learning-together
With no names, every landing image, the testimonial sprite and the book covers are re-encoded.
"""
from pathlib import Path
from PIL import Image, ImageOps
import json
import sys
ROOT = Path(__file__).resolve().parents[1] / 'marketing' / 'assets'
SOURCES = {
 'teacher-workspace': ('sunlit-teacher-workspace.png', [640, 1024, 1672]),
 # Output names follow the source file so a replaced PNG never pairs with copies of an older picture.
 'student-learning-together': ('student-learning-together.png', [480, 768, 1024]),
 'sisu-three-phones': ('sisu-three-phones.png', [640, 1024, 1536]),
 'sisu-academy-learning-studio': ('Sisu Academy Learning Studio.png', [480, 960, 1671]),
 'hero': ('HERO.jpg', [640, 960, 1376]),
 'hero-mobile': ('Hero mobile 3x2.jpg', [480, 720, 896]),
}


def outputs(name):
 return [ROOT / f'{name}-{w}.{ext}' for w in SOURCES[name][1] for ext in ('avif', 'webp')]


def stale():
 """Names whose source PNG is newer than (or missing) any of its encoded copies."""
 result = []
 for name, (source, _) in SOURCES.items():
  src = ROOT / source
  # 2 s slack: a git checkout writes a PNG and its copies within the same moment, in any order
  if src.exists() and any(not o.exists() or o.stat().st_mtime < src.stat().st_mtime - 2 for o in outputs(name)):
   result.append(name)
 return result


def optimize_book_covers():
 report = {}
 for source in sorted((ROOT / 'Book Cover').glob('*/*.png')):
  image = ImageOps.exif_transpose(Image.open(source)).convert('RGB')
  target = source.with_suffix('.webp')
  image.save(target, quality=90, method=6)
  report[str(target.relative_to(ROOT))] = dict(original_bytes=source.stat().st_size, bytes=target.stat().st_size)
 return report

def main(names=None):
 unknown = set(names or []) - set(SOURCES)
 if unknown:
  raise SystemExit(f'Unknown image name(s): {", ".join(sorted(unknown))}. Known: {", ".join(SOURCES)}')
 report = {}
 for name, (source, widths) in SOURCES.items():
  if names and name not in names:
   continue
  original = ImageOps.exif_transpose(Image.open(ROOT / source))
  # keep transparency: flattening faded edges to RGB shows them as a dark box against the page
  original = original.convert('RGBA' if 'A' in original.getbands() else 'RGB')
  files = {}
  for width in widths:
   im = original if width == original.width else original.resize((width, round(original.height * width / original.width)), Image.Resampling.LANCZOS)
   for ext, options in [('avif', dict(quality=85, speed=6)), ('webp', dict(quality=92, method=6))]:
    target = ROOT / f'{name}-{width}.{ext}'
    im.save(target, **options)
    files[target.name] = target.stat().st_size
  report[name] = dict(original_bytes=(ROOT / source).stat().st_size, files=files)
 if not names:
  sprite = Image.open(ROOT / 'testimonial-portraits.png').convert('RGB')
  sprite.thumbnail((832,416),Image.Resampling.LANCZOS)
  sprite.save(ROOT / 'testimonial-portraits.webp', quality=90,method=6)
  report['book_covers'] = optimize_book_covers()
 print(json.dumps(report,indent=2))
if __name__ == '__main__':
 main(sys.argv[1:])
