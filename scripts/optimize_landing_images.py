"""Encode responsive landing assets from retained originals (Pillow with AVIF/WebP)."""
from pathlib import Path
from PIL import Image, ImageOps
import json
ROOT = Path(__file__).resolve().parents[1] / 'marketing' / 'assets'
SOURCES = {
 'landing-hero-clean': ('landing-hero-clean.png', [640, 960, 1376]),
 'learning-together': ('student-learning-together.png', [480, 768, 1024]),
 'teacher-workspace': ('sunlit-teacher-workspace.png', [640, 1024, 1672]),
 'mobile-phones': ('sisu-three-phones.png', [640, 1024, 1536]),
}
def optimize_book_covers():
 report = {}
 for source in sorted((ROOT / 'Book Cover').glob('*/*.png')):
  image = ImageOps.exif_transpose(Image.open(source)).convert('RGB')
  target = source.with_suffix('.webp')
  image.save(target, quality=90, method=6)
  report[str(target.relative_to(ROOT))] = dict(original_bytes=source.stat().st_size, bytes=target.stat().st_size)
 return report

def main():
 report = {}
 for name, (source, widths) in SOURCES.items():
  original = ImageOps.exif_transpose(Image.open(ROOT / source)).convert('RGB')
  outputs = {}
  for width in widths:
   im = original if width == original.width else original.resize((width, round(original.height * width / original.width)), Image.Resampling.LANCZOS)
   for ext, options in [('avif', dict(quality=85, speed=6)), ('webp', dict(quality=92, method=6))]:
    target = ROOT / f'{name}-{width}.{ext}'
    im.save(target, **options)
    outputs[target.name] = target.stat().st_size
  report[name] = dict(original_bytes=(ROOT / source).stat().st_size, files=outputs)
 sprite = Image.open(ROOT / 'testimonial-portraits.png').convert('RGB')
 sprite.thumbnail((832,416),Image.Resampling.LANCZOS)
 sprite.save(ROOT / 'testimonial-portraits.webp', quality=90,method=6)
 report['book_covers'] = optimize_book_covers()
 print(json.dumps(report,indent=2))
if __name__ == '__main__':
 main()
