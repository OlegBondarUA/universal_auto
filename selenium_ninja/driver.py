import base64
import csv
import json
import os
import time
from datetime import datetime
import re
from urllib.parse import urlparse

import redis
from selenium.webdriver.common.proxy import ProxyType
from selenium.webdriver.support import expected_conditions as ec
import requests
from django.utils import timezone
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver import DesiredCapabilities, Proxy
from selenium.common import TimeoutException, NoSuchElementException, InvalidArgumentException

from app.models import FleetOrder, Vehicle, FleetsDriversVehiclesRate, UberService, UberSession, \
    UaGpsService, NewUklonService, ParkSettings, Driver
from app.uklon_sync import UklonRequest
from auto import settings
from auto_bot.handlers.order.utils import check_vehicle
from auto_bot.main import bot
from scripts.redis_conn import get_logger, redis_instance
from selenium_ninja.synchronizer import AuthenticationError, InfinityTokenError


class SeleniumTools:
    def __init__(self, partner=None, remote=True, driver=True, sleep=4):
        self.partner = partner
        self.remote = remote
        self.sleep = sleep
        self.logger = get_logger()
        if driver:
            if self.remote:
                self.driver = self.build_remote_driver()
            else:
                self.driver = self.build_driver()

    @staticmethod
    def build_driver():
        options = webdriver.ChromeOptions()
        options.add_experimental_option("prefs", {
            "download.default_directory": os.path.join(os.getcwd(), "LastDownloads"),
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing_for_trusted_sources_enabled": False,
        })
        options.add_argument("--disable-infobars")
        options.add_argument("--enable-file-cookies")
        options.add_argument('--allow-profiles-outside-user-dir')
        options.add_argument('--enable-profile-shortcut-manager')
        options.add_argument('--headless=new')
        options.add_argument('--disable-gpu')
        options.add_argument("--no-sandbox")
        options.add_argument("--screen-size=1920,1080")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--start-maximized")
        options.add_argument("--disable-extensions")
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('''user-agent=Mozilla/5.0
         (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/104.0.0.0 Safari/537.36''')

        driver = webdriver.Chrome(options=options, port=9514)
        return driver

    @staticmethod
    def build_remote_driver():
        options = Options()
        options.add_argument("--disable-infobars")
        options.add_argument("--enable-file-cookies")
        options.add_argument('--allow-profiles-outside-user-dir')
        options.add_argument('--enable-profile-shortcut-manager')
        options.enable_downloads = True
        options.add_argument('--disable-gpu')
        options.add_argument("--no-sandbox")
        options.add_argument("--start-maximized")
        options.add_argument("--disable-extensions")
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('''--user-agent=Mozilla/5.0
         (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/104.0.0.0 Safari/537.36''')
        proxy = Proxy()
        proxy.proxy_type = ProxyType.MANUAL
        proxy.http_proxy = ParkSettings.get_value("SELENIUM_PROXY")
        capabilities = DesiredCapabilities.CHROME.copy()
        capabilities['acceptInsecureCerts'] = True
        proxy.add_to_capabilities(capabilities)

        driver = webdriver.Remote(
            os.environ['SELENIUM_HUB_HOST'],
            desired_capabilities=capabilities,
            options=options
        )
        return driver

    @staticmethod
    def download_from_bucket(path, filename):
        response = requests.get(path)
        local_path = os.path.join(os.getcwd(), f"Temp/{filename}.jpg")
        with open(local_path, "wb") as file:
            file.write(response.content)
        return local_path

    def quit(self):
        if hasattr(self, 'driver'):
            self.driver.quit()
            self.driver = None

    def get_downloaded_files(self, driver):
        if not self.driver.current_url.startswith("chrome://downloads"):
            self.driver.get("chrome://downloads/")

        return self.driver.execute_script(
            "return  document.querySelector('downloads-manager')  "
            " .shadowRoot.querySelector('#downloadsList')         "
            " .items.filter(e => e.state === 'COMPLETE')          "
            " .map(e => e.filePath || e.file_path || e.fileUrl || e.file_url); ")

    def get_file_content(self, path):
        try:
            elem = self.driver.execute_script(
                "var input = window.document.createElement('INPUT'); "
                "input.setAttribute('type', 'file'); "
                "input.hidden = true; "
                "input.onchange = function (e) { e.stopPropagation() }; "
                "return window.document.documentElement.appendChild(input); ")
            elem._execute('sendKeysToElement', {'value': [path], 'text': path})
            result = self.driver.execute_async_script(
                "var input = arguments[0], callback = arguments[1]; "
                "var reader = new FileReader(); "
                "reader.onload = function (ev) { callback(reader.result) }; "
                "reader.onerror = function (ex) { callback(ex.message) }; "
                "reader.readAsDataURL(input.files[0]); "
                "input.remove(); ", elem)
            if not result.startswith('data:'):
                raise Exception("Failed to get file content: %s" % result)
            return base64.b64decode(result[result.find('base64,') + 7:])
        finally:
            pass

    def get_last_downloaded_file_from_remote(self, save_as=None):
        try:
            files = WebDriverWait(self.driver, 30, 1).until(lambda driver: self.get_downloaded_files(driver))
        except TimeoutException:
            return
        content = self.get_file_content(files[0])
        if len(files):
            filename = os.path.basename(files[0]) if save_as is None else save_as
            with open(os.path.join(os.getcwd(), filename), 'wb') as f:
                f.write(content)

    def get_uber_session(self):
        return UberSession.objects.filter(partner=self.partner).latest('created_at')

    def get_cookies(self):
        cookies = [
            {
                'name': 'sid',
                'value': self.get_uber_session().session,
                'domain': '.uber.com',
                'path': '/',
            },
            {
                'name': 'csid',
                'value': self.get_uber_session().cook_session,
                'domain': '.uber.com',
                'path': '/',
            },

        ]
        return cookies

    def get_ecofactor_token(self):
        url = "https://operator.ecofactor.eu/"
        self.driver.get(url)
        time.sleep(self.sleep)
        input_login = WebDriverWait(self.driver, self.sleep).until(
            ec.presence_of_element_located((By.XPATH, '//input[@name="username"]')))
        click_and_clear(input_login)
        input_login.send_keys(ParkSettings.get_value("ECO_LOGIN"))
        input_pass = WebDriverWait(self.driver, self.sleep).until(
            ec.presence_of_element_located((By.XPATH, '//input[@name="password"]')))
        click_and_clear(input_pass)
        input_pass.send_keys(ParkSettings.get_value("ECO_PASSWORD"))
        WebDriverWait(self.driver, self.sleep).until(
            ec.element_to_be_clickable((By.XPATH, '//button[@class="auth0-lock-submit"]'))).click()
        time.sleep(self.sleep)
        token = self.driver.execute_script('return window.localStorage.getItem("@@auth0spajs@@::R9l9zluJUz3nDRlYCvW9ShmJ9SxvBRBv::https://cpo.charging123.com/api/v1/::openid manage:cpo")')
        token_dict = json.loads(token)
        redis_instance().set("eco_token", token_dict['body']['access_token'])
        self.quit()

    def create_uber_session(self, login, password):
        self.driver.get(UberService.get_value('UBER_LOGIN_URL'))
        time.sleep(self.sleep)
        input_login = WebDriverWait(self.driver, self.sleep).until(
            ec.presence_of_element_located((By.XPATH, UberService.get_value('UBER_LOGIN_1'))))
        click_and_clear(input_login)
        input_login.send_keys(login)
        WebDriverWait(self.driver, self.sleep).until(
            ec.element_to_be_clickable((By.XPATH, UberService.get_value('UBER_LOGIN_2')))).click()
        try:
            self.password_form(password)
        except TimeoutException:
            try:
                WebDriverWait(self.driver, self.sleep).until(
                    ec.presence_of_element_located((By.XPATH, UberService.get_value('UBER_LOGIN_4')))).click()
                self.password_form(password)
            except TimeoutException:
                try:
                    bot.send_message(chat_id=ParkSettings.get_value("DEVELOPER_CHAT_ID"),
                                     text=f"Solve Puzzle Uber {os.environ.get('SELENIUM_URL')}"
                                     )
                    WebDriverWait(self.driver, 600).until(
                        ec.presence_of_element_located((By.XPATH, UberService.get_value('UBER_LOGIN_5')))).click()
                    WebDriverWait(self.driver, self.sleep).until(
                        ec.presence_of_element_located((By.XPATH, UberService.get_value('UBER_LOGIN_6')))).click()
                    self.password_form(password)
                except TimeoutException:
                    raise AuthenticationError("Uber login or password invalid")
        time.sleep(self.sleep)

        self.driver.get(UberService.get_value('BASE_URL'))
        time.sleep(self.sleep)
        self.save_uber()
        self.quit()

    def save_uber(self):
        url = self.driver.current_url
        uuid_pattern = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
        uuid_list = re.findall(uuid_pattern, url)
        sid = None
        csid = None
        if uuid_list:
            uuid = uuid_list[0]
            for cookie in self.driver.get_cookies():
                if cookie['name'] == 'sid':
                    sid = cookie['value']
                elif cookie['name'] == 'csid':
                    csid = cookie['value']
            if sid and csid:
                UberSession.objects.create(session=sid,
                                           cook_session=csid,
                                           uber_uuid=uuid,
                                           partner_id=self.partner
                                           )
                return sid
            else:
                raise AuthenticationError(f"Uber cookie error {sid}, {csid}")
        else:
            raise Exception(f"{url}  uber url without uuid")

    def password_form(self, password):
        input_password = WebDriverWait(self.driver, self.sleep).until(
            ec.presence_of_element_located((By.ID, UberService.get_value('UBER_LOGIN_3'))))
        click_and_clear(input_password)
        input_password.send_keys(password)
        WebDriverWait(self.driver, self.sleep).until(
            ec.element_to_be_clickable((By.XPATH, UberService.get_value('UBER_LOGIN_2')))).click()

    # def create_gps_session(self, login, password, url):
    #     try:
    #         session = None
    #         self.driver.get(url)
    #         time.sleep(self.sleep)
    #         user_field = WebDriverWait(self.driver, self.sleep).until(
    #             ec.presence_of_element_located((By.ID, UaGpsService.get_value('UAGPS_LOGIN_1'))))
    #         click_and_clear(user_field)
    #         user_field.send_keys(login)
    #         pass_field = self.driver.find_element(By.ID, UaGpsService.get_value('UAGPS_LOGIN_2'))
    #         click_and_clear(pass_field)
    #         pass_field.send_keys(password)
    #         self.driver.find_element(By.ID, UaGpsService.get_value('UAGPS_LOGIN_3')).click()
    #         time.sleep(self.sleep)
    #         cookies = self.driver.get_cookies()
    #     except (NoSuchElementException, InvalidArgumentException):
    #         return False
    #     for cookie in cookies:
    #         if cookie.get('name') == 'sessions':
    #             session = cookie.get('value')
    #         else:
    #             session = "5150a0c1025fda8440f78839971d5b73"
    #     self.quit()
    #     if session:
    #         params = {
    #             'sid': session,
    #             'svc': 'token/list',
    #             'params': json.dumps({})
    #         }
    #         wialon_url = "https://hst-api.wialon.eu/" if url == "https://gps.antenor.online/" else url
    #         response = requests.get(f"{wialon_url}wialon/ajax.html", params=params)
    #         tokens_list = response.json()
    #         for token in tokens_list:
    #             if not token.get('dur'):
    #                 infinity_token = token['h']
    #                 break
    #         else:
    #             raise InfinityTokenError
    #     else:
    #         raise AuthenticationError(f"Gps login or password incorrect.")
    #     return infinity_token

    @staticmethod
    def report_file_name(pattern):
        filenames = os.listdir(os.curdir)
        for file in filenames:
            if re.search(pattern, file):
                return file

    def payments_order_file_name(self, start, end):
        return self.report_file_name(self.file_pattern(start, end))

    def file_pattern(self, start, end, fleet="Uber"):
        sd, sy, sm = start.strftime("%d"), start.strftime("%Y"), start.strftime("%m")
        ed, ey, em = end.strftime("%d"), end.strftime("%Y"), end.strftime("%m")
        return f'{fleet} {sy}{sm}{sd}-{ey}{em}{ed}-{self.partner}.csv'

    def click_uber_calendar(self, month, year, day):
        self.driver.find_element(By.XPATH, UberService.get_value("UBER_CALENDAR_3")).click()
        self.driver.find_element(By.XPATH,
                                 f'{UberService.get_value("UBER_CALENDAR_2")}{year}")]]').click()
        self.driver.find_element(By.XPATH, UberService.get_value('UBER_CALENDAR_1')).click()
        self.driver.find_element(By.XPATH,
                                 f'{UberService.get_value("UBER_CALENDAR_2")}{month}")]]').click()
        self.driver.find_element(By.XPATH,
                                 f'{UberService.get_value("UBER_CALENDAR_4")}{day}]').click()

    def generate_payments_order(self, start, end):
        url = f"{UberService.get_value('UBER_GENERATE_PAYMENTS_ORDER_1')}{str(self.get_uber_session().uber_uuid)}/reports"
        xpath = UberService.get_value('UBER_GENERATE_PAYMENTS_ORDER_2')
        self.driver.get(UberService.get_value('BASE_URL'))
        for cook in self.get_cookies():
            self.driver.add_cookie(cook)
        self.driver.get(url)
        WebDriverWait(self.driver, 10).until(ec.presence_of_element_located((By.XPATH, xpath))).click()
        try:
            xpath = UberService.get_value('UBER_GENERATE_TRIPS_1')
            WebDriverWait(self.driver, self.sleep).until(ec.presence_of_element_located((By.XPATH, xpath))).click()
        except TimeoutException:
            xpath = UberService.get_value('UBER_GENERATE_TRIPS_2')
            WebDriverWait(self.driver, self.sleep).until(ec.presence_of_element_located((By.XPATH, xpath))).click()
        self.driver.find_element(By.XPATH, UberService.get_value('UBER_GENERATE_PAYMENTS_ORDER_4')).click()
        self.click_uber_calendar(start.strftime("%B"),
                                 start.strftime("%Y"),
                                 start.day)
        self.click_uber_calendar(end.strftime("%B"),
                                 end.strftime("%Y"),
                                 end.day)
        self.driver.find_element(By.XPATH, UberService.get_value('UBER_GENERATE_PAYMENTS_ORDER_5')).click()
        return f'{self.payments_order_file_name(start, end)}'

    def download_payments_order(self, start, end):
        if os.path.exists(f'{self.payments_order_file_name(start, end)}'):
            self.logger.info('Report already downloaded')
            return

        self.generate_payments_order(start, end)
        download_button = f"{UberService.get_value('UBER_DOWNLOAD_PAYMENTS_ORDER_1')}"
        try:
            in_progress_text = f"{UberService.get_value('UBER_DOWNLOAD_PAYMENTS_ORDER_2')}"
            WebDriverWait(self.driver, 10).until(ec.presence_of_element_located((By.XPATH, in_progress_text)))
            WebDriverWait(self.driver, 200).until_not(ec.presence_of_element_located((By.XPATH, in_progress_text)))
        except TimeoutException:
            self.driver.refresh()
        WebDriverWait(self.driver, 60).until(ec.element_to_be_clickable((By.XPATH, download_button))).click()
        time.sleep(self.sleep)
        self.get_last_downloaded_file_from_remote(self.file_pattern(start, end))

    def save_trips_report(self, start, end):
        states = {"completed": FleetOrder.COMPLETED,
                  "delivery_failed": FleetOrder.SYSTEM_CANCEL,
                  "rider_cancelled": FleetOrder.CLIENT_CANCEL,
                  "driver_cancelled": FleetOrder.DRIVER_CANCEL
                  }

        self.logger.info(self.file_pattern(start, end))
        file_path = self.payments_order_file_name(start, end)
        calendar_errors = {}
        if file_path is not None:
            with open(file_path, encoding="utf-8") as file:
                reader = csv.reader(file)
                next(reader)
                rows = [row for row in reader]
                existing_ids = FleetOrder.objects.filter(order_id__in=[str(row[0]) for row in rows],
                                                         fleet="Uber",
                                                         partner=self.partner).values_list('order_id', flat=True)
                orders = [row for row in rows if row[0] not in existing_ids]
                for order in orders:
                    try:
                        finish = timezone.make_aware(datetime.strptime(order[8], "%Y-%m-%d %H:%M:%S"))
                    except ValueError:
                        finish = None
                    driver_order = Driver.objects.filter(
                        fleetsdriversvehiclesrate__driver_external_id=order[1],
                        fleetsdriversvehiclesrate__fleet__name="Uber", partner=self.partner).first()
                    calendar_vehicle = check_vehicle(driver_order)
                    vehicle = Vehicle.objects.get(licence_plate=order[5])
                    if calendar_vehicle != vehicle and not calendar_errors.get(driver_order.pk):
                        calendar_errors[driver_order.pk] = vehicle.licence_plate
                    data = {"order_id": order[0],
                            "driver": driver_order,
                            "fleet": "Uber",
                            "from_address": order[9],
                            "destination": order[10],
                            "accepted_time": timezone.make_aware(datetime.strptime(order[7], "%Y-%m-%d %H:%M:%S")),
                            "finish_time": finish,
                            "state": states.get(order[12]),
                            "vehicle": vehicle,
                            "partner_id": self.partner,
                            "date_order": timezone.make_aware(datetime.strptime(order[7], "%Y-%m-%d %H:%M:%S"))}
                    FleetOrder.objects.create(**data)
                os.remove(file_path)
        return calendar_errors

    def add_driver(self, job_application):
        uklon_id = UklonRequest.objects.filter(partner=self.partner).uklon_id()
        url = NewUklonService.get_value('NEWUKLON_ADD_DRIVER_1')
        self.driver.get(url)
        WebDriverWait(self.driver, self.sleep).until(
            ec.element_to_be_clickable((By.XPATH, NewUklonService.get_value('NEWUKLON_ADD_DRIVER_2')))).click()
        WebDriverWait(self.driver, self.sleep).until(
            ec.presence_of_element_located((By.XPATH, NewUklonService.get_value('NEWUKLON_ADD_DRIVER_3')))).click()
        WebDriverWait(self.driver, self.sleep).until(
            ec.element_to_be_clickable((By.XPATH, NewUklonService.get_value('NEWUKLON_ADD_DRIVER_4')))).click()
        form_phone_number = self.driver.find_element(By.XPATH, NewUklonService.get_value('NEWUKLON_ADD_DRIVER_5'))
        click_and_clear(form_phone_number)
        form_phone_number.send_keys(job_application.phone_number[4:])
        WebDriverWait(self.driver, self.sleep).until(
            ec.element_to_be_clickable((By.XPATH, NewUklonService.get_value('NEWUKLON_ADD_DRIVER_4')))).click()

        # 2FA
        code = self.wait_otp_code(f'{job_application.phone_number} code')
        digits = self.driver.find_elements(By.XPATH, NewUklonService.get_value('NEWUKLON_ADD_DRIVER_6'))
        for i, element in enumerate(digits):
            element.send_keys(code[i])
        WebDriverWait(self.driver, self.sleep).until(
            ec.element_to_be_clickable((By.XPATH, NewUklonService.get_value('NEWUKLON_ADD_DRIVER_4')))).click()
        if self.sleep:
            time.sleep(self.sleep)
        self.driver.find_element(By.XPATH, NewUklonService.get_value('NEWUKLON_ADD_DRIVER_7')).click()
        WebDriverWait(self.driver, self.sleep).until(
            ec.element_to_be_clickable((By.XPATH, NewUklonService.get_value('NEWUKLON_ADD_DRIVER_4')))).click()
        if self.sleep:
            time.sleep(self.sleep)
        registration_fields = {"firstName": job_application.first_name,
                               "lastName": job_application.last_name,
                               "email": job_application.email,
                               "password": job_application.password}
        for field, value in registration_fields.items():
            element = self.driver.find_element(By.ID, field)
            click_and_clear(element)
            element.send_keys(value)
        WebDriverWait(self.driver, self.sleep).until(
            ec.element_to_be_clickable((By.XPATH, NewUklonService.get_value('NEWUKLON_ADD_DRIVER_4')))).click()

        file_paths = [
            f"{settings.MEDIA_URL}{job_application.photo}",
            f"{settings.MEDIA_URL}{job_application.driver_license_front}",
            f"{settings.MEDIA_URL}{job_application.driver_license_back}",

        ]
        for i, file_path in enumerate(file_paths):
            if self.sleep:
                time.sleep(self.sleep)
            local_path = self.download_from_bucket(file_path, i)
            photo_input = self.driver.find_element(By.XPATH, NewUklonService.get_value('NEWUKLON_ADD_DRIVER_8'))
            photo_input.send_keys(local_path)
            WebDriverWait(self.driver, self.sleep).until(
                ec.element_to_be_clickable((By.XPATH, NewUklonService.get_value('NEWUKLON_ADD_DRIVER_9')))).click()
            time.sleep(1)
            WebDriverWait(self.driver, self.sleep).until(
                ec.element_to_be_clickable((By.XPATH, NewUklonService.get_value('NEWUKLON_ADD_DRIVER_9')))).click()
            WebDriverWait(self.driver, self.sleep).until(
                ec.element_to_be_clickable((By.XPATH, NewUklonService.get_value('NEWUKLON_ADD_DRIVER_4')))).click()
        fleet_code = WebDriverWait(self.driver, self.sleep).until(
            ec.presence_of_element_located((By.ID, NewUklonService.get_value('NEWUKLON_ADD_DRIVER_10'))))
        click_and_clear(fleet_code)
        fleet_code.send_keys(uklon_id)
        WebDriverWait(self.driver, self.sleep).until(
            ec.element_to_be_clickable((By.XPATH, NewUklonService.get_value('NEWUKLON_ADD_DRIVER_4')))).click()
        job_application.status_uklon = datetime.now().date()
        job_application.save()
        self.quit()

    def wait_otp_code(self, key):
        p = redis_instance().pubsub()
        p.subscribe(key)
        p.ping()
        while True:
            try:
                otp = p.get_message()
                if otp:
                    otpa = list(f'{otp["data"]}')
                    otpa = list(filter(lambda d: d.isdigit(), otpa))
                    digits = [s.isdigit() for s in otpa]
                    if not digits or (not all(digits)) or len(digits) != 4:
                        continue
                    break
            except redis.ConnectionError as e:
                self.logger.error(str(e))
                p = redis_instance().pubsub()
                p.subscribe('code')
            time.sleep(1)
        return otpa


def click_and_clear(element):
    element.click()
    element.clear()
