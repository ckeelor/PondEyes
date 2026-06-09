# Entry-point. Keeps the top-level script tiny.
import pygame

from radar import config, gui
from radar.logging_setup import setup_logging


def main():
    log = setup_logging()            # rotating file (run-logs/) + stderr; PONDEYES_LOG=DEBUG for detail
    pygame.init()
    cfg = config.load()
    log.info("PondEyes start: %d sensor(s), map=%s",
             len(cfg.get("sensors", [])), cfg.get("map"))
    app = gui.RadarGUI(cfg)
    try:
        app.run()
    finally:
        config.save(cfg)
        log.info("PondEyes exit")


if __name__ == "__main__":
    main()
