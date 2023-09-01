# -*- coding: utf-8 -*-
# Time       : 2023/8/16 5:14
# Author     : QIN2DIM
# GitHub     : https://github.com/QIN2DIM
# Description:
import asyncio
import sys

import hcaptcha_challenger as solver
from loguru import logger
from playwright.async_api import BrowserContext

from services.agents.epic_games import EpicPlayer, EpicGames
from services.agents.epic_games import get_promotions, get_order_history

solver.install(flush_yolo=True)

player = EpicPlayer.from_account()

promotions = []

ctx_cookies_is_available = None


@logger.catch
def prelude():
    global promotions, ctx_cookies_is_available

    logger.info("prelude", action="Checking the operating environment")

    # Prelude context
    if not player.ctx_cookies.is_available():
        return
    ctx_cookies_is_available = True

    # Create tasks
    orders = get_order_history(player.cookies)
    namespaces = [order.namespace for order in orders]
    pros = get_promotions()
    for pro in pros:
        logger.debug("prelude", action="check", title=pro.title, url=pro.url)
    promotions = [p for p in pros if p.namespace not in namespaces]

    if not promotions:
        logger.success(
            "prelude",
            action="Pass claim task",
            reason="All free games of the week are in my library",
        )
        sys.exit()


async def claim_epic_games(context: BrowserContext):
    global promotions

    page = context.pages[0]
    epic = EpicGames.from_player(player, page=page)

    # Authorize
    if not ctx_cookies_is_available:
        logger.info("claim_epic_games", action="Try to flush cookie")
        if await epic.authorize(page):
            await epic.flush_token(context)
        else:
            logger.error(
                "claim_epic_games", action="Exit test case", reason="Failed to flush token"
            )
            return

    # Create tasks
    if not promotions:
        orders = get_order_history(player.cookies)
        namespaces = [order.namespace for order in orders]
        promotions = [p for p in get_promotions() if p.namespace not in namespaces]

    if not promotions:
        logger.success("Pass claim task", reason="All free games of the week are in my library")
        return

    # Execute
    await epic.claim_weekly_games(page, promotions)


async def run():
    prelude()

    # Cookie is unavailable or need to process promotions
    agent = player.build_agent()
    await agent.execute(sequence=[claim_epic_games], headless=True)


if __name__ == "__main__":
    asyncio.run(run())
