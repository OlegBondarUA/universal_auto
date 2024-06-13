import asyncio
import logging
import os
import re
import asyncpg
from asgiref.sync import sync_to_async
from auto.tasks import raw_gps_handler
from django.utils.timezone import now


logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.DEBUG)
logger = logging.getLogger(__name__)

HOST, PORT = '0.0.0.0', 44300
PACKAGE_SIZE = 1024*8


class PackageHandler:
    pattern = r'#(.*?)#(.*?)\r\n'
    answer_login = '#AL#1\r\n'
    answer_bad_login = '#AL#0\r\n'
    answer_data = '#AD#1\r\n'
    answer_bad_data = '#AD#-1\r\n'
    answer_ping = '#AP#\r\n'

    def __init__(self):
        self.imei = ''


    async def _l_handler(self, **kwargs):
        imei = kwargs['msg'].split(';')[0]
        if imei:
            self.imei = imei
            return self.answer_login
        else:
            return self.answer_bad_login

    async def _d_handler(self, **kwargs):
        if self.imei and kwargs['msg']:
            imei,  client_ip, client_port = self.imei, kwargs['addr'][0], kwargs['addr'][1]
            data, created_at = kwargs['msg'], await sync_to_async(now)()
            database_url = os.environ.get('DATABASE_URL')
            db_conn = await asyncpg.connect(dsn=database_url)
            try:
                query = """
                            INSERT INTO app_rawgps (imei, client_ip, client_port, data, created_at)
                            VALUES ($1, $2, $3, $4, $5)
                        """
                await db_conn.execute(query, imei, client_ip, client_port, data, created_at)
                return self.answer_data
            except (Exception, asyncpg.PostgresError) as error:
                print("Error inserting GPS data:", error)
                return self.answer_bad_data
            finally:
                db_conn.close()
        else:
            return self.answer_bad_data

    async def _p_handler(self, **kwargs):
        return self.answer_ping

    async def process_package(self, addr, message):
        try:
            message_ = re.sub(r'\r\n', '', message)
            logging.info(msg=f"Received from {addr}: {message_[:100]}...")
            handlers = {
                'L': self._l_handler,
                'D': self._d_handler,
                'P': self._p_handler,
            }
            res = ''
            match = re.findall(self.pattern, message)
            for item in match:
                func = handlers[item[0]]
                res += await func(addr=addr, msg=item[1])
            if len(res):
                return res
            else:
                return self.answer_bad_data
        except Exception:
            return self.answer_bad_data


async def handle_connection(reader, writer):
    addr = writer.get_extra_info("peername")
    logging.info(msg=f"Connected by {addr}")
    ph = PackageHandler()
    while True:
        # Receive
        try:
            data = await reader.read(PACKAGE_SIZE)
            # logging.info(msg=f"{data}")
        except ConnectionError:
            logging.info(msg=f"Client suddenly closed while receiving from {addr}")
            break
        if not data:
            break
        answer = await ph.process_package(addr, data.decode('utf-8'))
        # logging.info(msg=f"{answer}")
        try:
            writer.write(answer.encode('utf-8'))
        except ConnectionError:
            logging.info(msg=f"Client suddenly closed, cannot send")
            break
    writer.close()
    logging.info(msg=f"Disconnected by {addr}")


async def main(host, port):
    server = await asyncio.start_server(handle_connection, host, port)
    async with server:
        await server.serve_forever()


def run():
    asyncio.run(main(HOST, PORT))
