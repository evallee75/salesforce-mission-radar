"""Point d'entrée : `python -m radar` lance un scan complet et régénère le site.
`python -m radar --publish-only` régénère le site sans scanner (après l'analyse IA)."""
from __future__ import annotations

import logging
import sys

from .digest import send_digest
from .pipeline import load_config, run


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if "--publish-only" in sys.argv:
        run(publish_only=True)
        return
    result = run()
    send_digest(result["offers"], result["new_ids"], load_config().get("site_url") or "")


if __name__ == "__main__":
    main()
