"""Refresh the exact-name, browser-verified mabimobi.life icon URLs in the manifest.

New names must first be verified against the site's visible item name and image.
Never derive filenames from guessed names or silently use a similar item's icon.
"""
import json
import urllib.request
from pathlib import Path

def main():
    root = Path(__file__).resolve().parents[1] / 'app/dashboard/assets/item_icons'
    entries = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    for entry in {v['file']: v for v in entries.values()}.values():
        url = entry['url']
        if not url.startswith('https://cdn.mabimobi.life/image/item/'):
            raise ValueError('Unexpected icon source')
        data = urllib.request.urlopen(url, timeout=30).read()
        if not data.startswith(b'\x89PNG\r\n\x1a\n'):
            raise ValueError('Not a PNG: ' + entry['name'])
        target = root / Path(entry['file']).name
        pending = target.with_suffix('.tmp')
        pending.write_bytes(data)
        pending.replace(target)
    print(f'Refreshed icons for {len(entries)} exact names.')

if __name__ == '__main__': main()
