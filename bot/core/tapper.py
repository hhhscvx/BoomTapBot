import asyncio
from urllib.parse import unquote

from aiohttp import ClientSession
import aiohttp
from aiohttp_proxy import ProxyConnector
from better_proxy import Proxy
from pyrogram import Client
from pyrogram.errors import Unauthorized, UserDeactivated, AuthKeyUnregistered
from pyrogram.raw.functions.messages import RequestWebView
from pyrogram.errors import FloodWait

from bot.utils import logger
from bot.config import InvalidSession
from .headers import headers
from bot.config import settings


class Tapper:
    def __init__(self, tg_client: Client) -> None:
        self.session_name = tg_client.name
        self.tg_client = tg_client
        self.device = "Linux"

    async def get_tg_web_data(self, proxy: str | None) -> str:
        if proxy:
            proxy: Proxy = Proxy.from_str(proxy)
            proxy_dict = dict(
                scheme=proxy.protocol,
                hostname=proxy.host,
                port=proxy.port,
                username=proxy.login,
                password=proxy.password
            )
        else:
            proxy_dict = None

        self.tg_client.proxy = proxy_dict

        try:
            with_tg = True

            if not self.tg_client.is_connected:
                with_tg = False
                try:
                    await self.tg_client.connect()
                except (Unauthorized, UserDeactivated, AuthKeyUnregistered):
                    raise InvalidSession(self.session_name)

            while True:
                try:
                    peer = await self.tg_client.resolve_peer('boom')
                    break
                except FloodWait as fl:
                    fls = fl.value

                    logger.warning(f"{self.session_name} | FloodWait {fl}")
                    logger.info(f"{self.session_name} | Sleep {fls}s")

                    await asyncio.sleep(fls + 3)

            web_view = await self.tg_client.invoke(RequestWebView(
                peer=peer,
                bot=peer,
                platform='android',
                from_bot_menu=False,
                url='https://bot.backend-boom.com/'
            ))

            auth_url = web_view.url
            query = unquote(string=auth_url.split('tgWebAppData=')[1].split('&tgWebAppVersion')[0])

            self.user_id = (await self.tg_client.get_me()).id

            if with_tg is False:
                await self.tg_client.disconnect()

            return query

        except InvalidSession as error:
            raise error

        except Exception as error:
            logger.error(f"{self.session_name} | Unknown error during Authorization: {error}")
            await asyncio.sleep(delay=3)

    async def login(self, http_client: ClientSession, tg_web_data: str) -> str:
        """token"""
        try:
            response = await http_client.post(url='https://api-bot.backend-boom.com/api/v1/auth',
                                              json={"data": tg_web_data,
                                                    "device": self.device}
                                              )
            resp_json = await response.json()
            response.raise_for_status()

            return resp_json
        except Exception as error:
            logger.error(f"{self.session_name} | Unknown error while Login: {error}")
            await asyncio.sleep(delay=3)

    async def get_me(self, http_client: ClientSession, access_token: str) -> dict:
        """coins"""
        try:
            response = await http_client.get(url=f'https://api-bot.backend-boom.com/api/v1/me?access_token={access_token}')
            resp_json = await response.json()
            response.raise_for_status()

            return resp_json
        except Exception as error:
            logger.error(f"{self.session_name} | Unknown error when Get user data: {error}")
            await asyncio.sleep(delay=3)
