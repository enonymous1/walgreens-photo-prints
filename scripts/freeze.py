"""Render the demo web app to a static site for GitHub Pages.

This script builds its own demo app and takes no credentials
argument, so real data cannot be frozen by accident: every page
comes from the fictional demo transport in ``demo.py``. The output
is a browsable, click-through demo, not the live app: forms are
disabled and a static-demo banner is added, because Pages is
static and cannot submit forms, upload files, or call the API.

Output goes to ``freeze-site/`` by default, which is gitignored
and never committed; the Pages workflow builds it fresh.
"""

import argparse
import re
import shutil
from pathlib import Path

from walgreens_photo_prints.webapp import create_app

ROUTES = [
    ("/", "index.html"),
    ("/products", "products.html"),
    ("/stores", "stores.html"),
    ("/coupon", "coupon.html"),
    ("/upload", "upload.html"),
    ("/submit", "submit.html"),
    ("/status", "status.html"),
]

# Absolute Flask paths -> flat frozen files, so the site works
# under a project Pages subpath as well as at a domain root.
LINK_REWRITES = {
    'href="/"': 'href="index.html"',
    'href="/products"': 'href="products.html"',
    'href="/stores"': 'href="stores.html"',
    'href="/coupon"': 'href="coupon.html"',
    'href="/upload"': 'href="upload.html"',
    'href="/submit"': 'href="submit.html"',
    'href="/status"': 'href="status.html"',
    'href="/static/style.css"': 'href="static/style.css"',
    'action="/products"': 'action="products.html"',
    'action="/stores"': 'action="stores.html"',
    'action="/coupon"': 'action="coupon.html"',
    'action="/upload"': 'action="upload.html"',
    'action="/submit"': 'action="submit.html"',
    'action="/status"': 'action="status.html"',
}

STATIC_BANNER = (
    '<p class="banner static-banner">Static demo — forms are disabled. '
    "Run the Flask app locally for live use.</p>"
)


def disable_forms(html):
    """Disable every form control in a rendered page."""
    return re.sub(r"<(input|button|select|textarea)(?=[\s>])", r"<\1 disabled", html)


def freeze_page(html):
    for old, new in LINK_REWRITES.items():
        html = html.replace(old, new)
    html = disable_forms(html)
    html = html.replace("<main>", f"<main>\n{STATIC_BANNER}", 1)
    return html


def build_freeze(output_dir):
    """Build the frozen demo site into ``output_dir`` and return its file list."""
    app = create_app(demo=True)
    # Guardrail: the frozen app must be the demo app, never a live one.
    assert app.config["WPP_DEMO"], "Freeze requires the demo app."
    output = Path(output_dir)
    if output.exists():
        shutil.rmtree(output)
    (output / "static").mkdir(parents=True)
    client = app.test_client()
    written = []
    for route, filename in ROUTES:
        response = client.get(route)
        assert response.status_code == 200, f"{route} returned {response.status_code}"
        html = freeze_page(response.get_data(as_text=True))
        assert "demo-api-key" not in html, "Demo freeze leaked a credential placeholder."
        assert "Static demo" in html and "disabled" in html
        (output / filename).write_text(html, encoding="utf-8")
        written.append(filename)
    package_static = (
        Path(__file__).resolve().parent.parent
        / "src"
        / "walgreens_photo_prints"
        / "static"
        / "style.css"
    )
    # When run from an installed package, static files live with the package.
    import walgreens_photo_prints

    installed_static = (
        Path(walgreens_photo_prints.__file__).resolve().parent / "static" / "style.css"
    )
    source = installed_static if installed_static.exists() else package_static
    shutil.copyfile(source, output / "static" / "style.css")
    written.append("static/style.css")
    (output / ".nojekyll").write_text("", encoding="utf-8")
    written.append(".nojekyll")
    return written


def main():
    parser = argparse.ArgumentParser(description="Freeze the demo web app to a static site.")
    parser.add_argument("--output", default="freeze-site", help="Output directory.")
    args = parser.parse_args()
    for filename in build_freeze(args.output):
        print(filename)


if __name__ == "__main__":
    main()
