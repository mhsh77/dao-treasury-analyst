import asyncio
import json
import pathlib
import sys

from playwright.async_api import async_playwright

comp = pathlib.Path(sys.argv[1]).resolve()


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": 1920, "height": 1080})
        await pg.goto(comp.as_uri())
        await pg.evaluate("window.__ready")
        ev = await pg.evaluate("window.__events()")
        (comp.parent / "events.json").write_text(json.dumps(ev, indent=1))
        print(len(ev["events"]), "events")
        await b.close()


asyncio.run(main())
