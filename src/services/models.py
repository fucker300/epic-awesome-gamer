# -*- coding: utf-8 -*-
# Time       : 2023/8/14 17:04
# Author     : QIN2DIM
# Github     : https://github.com/QIN2DIM
# Description:
from __future__ import annotations

import abc
import inspect
import json
import time
from abc import ABC
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Awaitable, List, Any, Dict
from typing import Literal

import httpx
from hcaptcha_challenger.agents.playwright.tarnished import Malenia
from loguru import logger
from playwright.async_api import async_playwright

from settings import config, project


@dataclass
class EpicCookie:
    cookies: Dict[str, str] = field(default_factory=dict)
    """
    cookies in the Request Header
    """

    URL_VERIFY_COOKIES = "https://www.epicgames.com/account/personal"

    @classmethod
    def from_state(cls, fp: Path) -> EpicCookie:
        """Jsonify cookie from Playwright"""
        cookies = {}
        try:
            data = json.loads(fp.read_text())["cookies"]
            cookies = {ck["name"]: ck["value"] for ck in data}
        except (FileNotFoundError, KeyError):
            pass
        return cls(cookies=cookies)

    def is_available(self) -> bool | None:
        if not self.cookies:
            return
        with suppress(httpx.ConnectError):
            headers = {
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36 Edg/115.0.1901.203",
                "origin": "https://store.epicgames.com/zh-CN/p/orwell-keeping-an-eye-on-you",
            }
            resp = httpx.get(self.URL_VERIFY_COOKIES, headers=headers, cookies=self.cookies)
            return resp.status_code == 200

    def reload(self, fp: Path):
        try:
            data = json.loads(fp.read_text())["cookies"]
            self.cookies = {ck["name"]: ck["value"] for ck in data}
        except (FileNotFoundError, KeyError):
            pass


class Ring(Malenia):
    @staticmethod
    async def patch_cookies(context):
        five_days_ago = datetime.now() - timedelta(days=5)
        cookie = {
            "name": "OptanonAlertBoxClosed",
            "value": five_days_ago.isoformat(),
            "domain": ".epicgames.com",
            "path": "/",
        }
        await context.add_cookies([cookie])

    async def execute(
        self,
        sequence: Callable[..., Awaitable[...]] | List,
        *,
        parameters: Dict[str, Any] = None,
        headless: bool = False,
        locale: str = "en-US",
        **kwargs,
    ):
        async with async_playwright() as p:
            context = await p.firefox.launch_persistent_context(
                user_data_dir=self._user_data_dir,
                headless=headless,
                locale=locale,
                record_video_dir=self._record_dir,
                record_har_path=self._record_har_path,
                args=["--hide-crash-restore-bubble"],
                **kwargs,
            )
            await self.apply_stealth(context)
            await self.patch_cookies(context)

            if not isinstance(sequence, list):
                sequence = [sequence]
            for container in sequence:
                logger.info("execute task", name=container.__name__)
                kws = {}
                params = inspect.signature(container).parameters
                if parameters and isinstance(parameters, dict):
                    for name in params:
                        if name != "context" and name in parameters:
                            kws[name] = parameters[name]
                if not kws:
                    await container(context)
                else:
                    await container(context, **kws)
            await context.close()


@dataclass
class Player(ABC):
    email: str
    password: str
    """
    Player's account
    """

    mode: Literal["epic-games", "unreal", "gog", "apg", "xbox"]
    """
    Game Platform
    """

    user_data_dir: Path = project.user_data_dir
    """
    Mount user cache
    - database
    - user_data_dir
        - games@email # runtime user_data_dir
            - context
            - record
                - captcha.mp4
                - eg-record.har
            - ctx_cookie.json
            - ctx_store.json
            - order_history.json
        - unreal@email
            - context
            - record
                - captcha.mp4
                - eg-record.har
        - gog@alice
        - xbox@alice
    """

    def __post_init__(self):
        namespace = f"{self.mode}@{self.email.split('@')[0]}"
        self.user_data_dir = self.user_data_dir.joinpath(namespace)
        for ck in ["browser_context", "record"]:
            ckp = self.user_data_dir.joinpath(ck)
            ckp.mkdir(parents=True, exist_ok=True)

    @classmethod
    @abc.abstractmethod
    def from_account(cls, *args, **kwargs):
        raise NotImplementedError

    @property
    def browser_context_dir(self) -> Path:
        return self.user_data_dir.joinpath("browser_context")

    @property
    def record_dir(self) -> Path:
        return self.user_data_dir.joinpath("record")

    @property
    def record_har_path(self) -> Path:
        return self.record_dir.joinpath(f"eg-{int(time.time())}.har")

    @property
    def ctx_cookie_path(self) -> Path:
        return self.user_data_dir.joinpath("ctx_cookie.json")

    def build_agent(self):
        return Ring(
            user_data_dir=self.browser_context_dir,
            record_dir=self.record_dir,
            record_har_path=self.record_har_path,
            state_path=self.ctx_cookie_path,
        )


@dataclass
class EpicPlayer(Player):
    _ctx_cookies: EpicCookie = None

    def __post_init__(self):
        super().__post_init__()
        self._ctx_cookies = EpicCookie.from_state(fp=self.ctx_cookie_path)

    @classmethod
    def from_account(cls):
        return cls(email=config.epic_email, password=config.epic_password, mode="epic-games")

    @property
    def ctx_store_path(self) -> Path:
        return self.user_data_dir.joinpath("ctx_store.json")

    @property
    def order_history_path(self) -> Path:
        return self.user_data_dir.joinpath("order_history.json")

    @property
    def ctx_cookies(self) -> EpicCookie:
        return self._ctx_cookies

    @property
    def cookies(self) -> Dict[str, str]:
        return self._ctx_cookies.cookies

    @cookies.setter
    def cookies(self, cookies: Dict[str, str]):
        self._ctx_cookies.cookies = cookies
