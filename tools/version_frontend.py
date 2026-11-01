#!/usr/bin/env python3
"""Refresh content hashes in static HTML before committing/publishing docs/."""
import argparse
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / 'docs'


def versioned(url):
    path = urlsplit(url).path
    if not path.startswith('./'):
        raise ValueError(f'Expected a site-relative URL: {url}')
    source = SITE / path[2:]
    digest = hashlib.sha256(source.read_bytes()).hexdigest()[:12]
    return f'{path}?v={digest}'


def updated_html(page):
    html = page.read_text()
    # Canonical aliases keep dynamic imports (including diagnostics) on the same
    # module instance as the versioned entry point and its static dependencies.
    def importmap(match):
        mapping = json.loads(match.group(2))
        imports = mapping.setdefault('imports', {})
        for key, value in list(imports.items()):
            if not value.endswith('/'):
                imports[key] = versioned(value)
        for module in sorted((SITE / 'js').glob('*.js')):
            key = './' + module.relative_to(SITE).as_posix()
            imports[key] = versioned(key)
        addons = SITE / 'vendor/three/addons'
        for module in sorted(addons.rglob('*.js')):
            key = 'three/addons/' + module.relative_to(addons).as_posix()
            imports[key] = versioned('./' + module.relative_to(SITE).as_posix())
        return match.group(1) + '\n    ' + json.dumps(mapping, separators=(',', ':')) + '\n  ' + match.group(3)

    html = re.sub(r'(<script\s+type="importmap">)(.*?)(</script>)', importmap, html, flags=re.S)
    html = re.sub(r'(<script\b[^>]*\bsrc=")([^"?]+\.js)(?:\?[^\"]*)?("[^>]*>)',
                  lambda m: m.group(1) + versioned(m.group(2)) + m.group(3), html)
    html = re.sub(r'(<link\b[^>]*\bhref=")([^"?]+\.(?:css|svg))(?:\?[^\"]*)?("[^>]*>)',
                  lambda m: m.group(1) + versioned(m.group(2)) + m.group(3), html)
    return html


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Fail if generated URL hashes are stale.')
    args = parser.parse_args()
    stale = []
    for page in sorted(SITE.glob('*.html')):
        expected = updated_html(page)
        if expected != page.read_text():
            stale.append(page.relative_to(ROOT).as_posix())
            if not args.check:
                page.write_text(expected)
    if args.check and stale:
        parser.exit(1, 'Stale frontend URLs: ' + ', '.join(stale) + '\nRun: python3 tools/version_frontend.py\n')
    print('Frontend URL hashes current.' if not stale else 'Versioned: ' + ', '.join(stale))


if __name__ == '__main__':
    main()
