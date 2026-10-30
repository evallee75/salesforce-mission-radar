"""Point d'entrée : `python -m radar` lance un scan complet et régénère le site."""
from __future__ import annotations

import logging

from .digest import send_digest
from .pipeline import load_config, run


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    result = run()
    send_digest(result["offers"], result["new_ids"], load_config().get("site_url") or "")


if __name__ == "__main__":
    main()
