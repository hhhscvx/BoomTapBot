import asyncio
from time import time
from urllib.parse import unquote

from aiohttp import ClientSession, ClientTimeout
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

    async def login(self, http_client: ClientSession, tg_web_data: str) -> dict:
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

    async def claim(self, http_client: ClientSession, access_token: str) -> dict:
        try:
            response = await http_client.get(url=f'https://api-bot.backend-boom.com/api/v1/daily/claim?access_token={access_token}')
            resp_json = await response.json()
            response.raise_for_status()

            return resp_json
        except Exception as error:
            logger.error(f"{self.session_name} | Unknown error when claim: {error}")
            await asyncio.sleep(delay=3)
        
        

    async def check_proxy(self, http_client: ClientSession, proxy: Proxy) -> None:
        try:
            response = await http_client.get(url='https://httpbin.org/ip', timeout=ClientTimeout(5))
            ip = (await response.json()).get('origin')
            logger.info(f"{self.session_name} | Proxy IP: {ip}")
        except Exception as error:
            logger.error(f"{self.session_name} | Proxy: {proxy} | Error: {error}")


    async def run(self, proxy: str | None) -> None:
        # TODO: проверить, экспайрится ли токен: 85c45142-7f01-4242-b9c4-d2832e178a67
        last_claimed_time = 0

        proxy_conn = ProxyConnector().from_url(proxy) if proxy else None

        async with aiohttp.ClientSession(headers=headers, connector=proxy_conn) as http_client:
            if proxy:
                await self.check_proxy(http_client=http_client, proxy=proxy)

            tg_web_data = await self.get_tg_web_data(proxy=proxy)
            login = await self.login(http_client=http_client, tg_web_data=tg_web_data)
            access_token = login["token"]

            while True:
                try:
                    if (time() - last_claimed_time > 3600 * 8) or last_claimed_time == 0:
                        claimed = await self.claim(http_client, access_token=access_token)
                        logger.info(f"Try to claim.. {claimed}")
                        if len(claimed) > 0:
                            logger.success(f"Claimed +{claimed[0]['value']} coins")
                        

                    me = await self.get_me(http_client=http_client, access_token=access_token)

                    logger.success(f"Successfully Login! Balance: {me['coins']}")
                    
                except InvalidSession as error:
                    raise error

                except Exception as error:
                    logger.error(f"{self.session_name} | Unknown error: {error}")
                    await asyncio.sleep(delay=3)
                
                else:
                    logger.info(f"Start sleep on {settings.SLEEP_BETWEEN_CLAIM}s..")
                    await asyncio.sleep(delay=settings.SLEEP_BETWEEN_CLAIM + 5)


async def run_tapper(tg_client: Client, proxy: str | None):
    try:
        await Tapper(tg_client=tg_client).run(proxy=proxy)
    except InvalidSession:
        logger.error(f"{tg_client.name} | Invalid Session")
