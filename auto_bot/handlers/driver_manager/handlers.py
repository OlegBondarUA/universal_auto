# Create driver and other
import json
from datetime import datetime, timedelta, time
from celery.signals import task_postrun
from django.db.models import F, Value
from django.db.models.functions import Concat
from django.utils import timezone
from telegram import ReplyKeyboardRemove, ParseMode, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest

from app.models import Manager, Vehicle, User, Driver, FleetsDriversVehiclesRate, Fleet, JobApplication, \
    Payments, ParkSettings, VehicleSpending, Partner, CustomUser
from auto_bot.handlers.driver.keyboards import back_to_payment
from auto_bot.handlers.driver.static_text import BROKEN
from auto_bot.handlers.driver_job.static_text import driver_job_name
from auto_bot.handlers.driver_manager.keyboards import create_user_keyboard, role_keyboard, fleets_keyboard, \
    fleet_job_keyboard, drivers_status_buttons, inline_driver_paid_kb, inline_earning_report_kb, \
    inline_efficiency_report_kb, inline_partner_vehicles, inline_partner_drivers, inline_func_with_driver_kb, \
    inline_statistic_kb, inline_driver_eff_kb, inline_func_with_vehicle_kb, vehicle_spending_kb
from auto_bot.handlers.driver_manager.static_text import *
from auto_bot.handlers.driver_manager.utils import get_daily_report, validate_date, get_efficiency, \
    generate_message_report, get_driver_efficiency_report, validate_sum, generate_report_period
from auto_bot.handlers.main.keyboards import markup_keyboard, markup_keyboard_onetime, inline_manager_kb
from auto.tasks import send_on_job_application_on_driver, manager_paid_weekly, fleets_cash_trips, \
    update_driver_data, send_efficiency_report, send_driver_efficiency, \
    generate_rent_message_driver
from auto_bot.handlers.order.utils import check_vehicle
from auto_bot.main import bot
from auto_bot.utils import send_long_message, edit_long_message
from scripts.redis_conn import redis_instance
from auto_bot.handlers.main.keyboards import back_to_main_menu


def cache_queryset(query):
    user = CustomUser.get_by_chat_id(query.from_user.id)
    drivers = Driver.objects.get_active(manager=user, schema__isnull=False) if user.is_manager() else\
        Driver.objects.get_active(partner=user, schema__isnull=False)
    driver_name_id = drivers.order_by('second_name').annotate(
        full_name=Concat(
            F("user_ptr__second_name"),
            Value(" "),
            F("user_ptr__name")
        )
    ).values('id', 'full_name')
    driver_data_list = list(driver_name_id)
    driver_data_json = json.dumps(driver_data_list)
    redis_instance().hset(str(query.from_user.id), 'driver_data', driver_data_json)


def retrieve_records(page_number, chat_id):
    drivers = redis_instance().hget(chat_id, 'driver_data')
    driver_data = json.loads(drivers)
    if driver_data:
        start_index = (page_number - 1) * records_per_page
        end_index = min(start_index + records_per_page, len(driver_data))
        return driver_data[start_index:end_index]
    else:
        return []


def generate_buttons_for_page(page_number, chat_id):
    records = retrieve_records(page_number, chat_id)
    buttons = []
    for obj in records:
        buttons.append([InlineKeyboardButton(text=obj['full_name'], callback_data=f"Generate_rent_{obj['id']}")])
    return buttons


def generate_pagination_buttons(page_number, chat_id):
    drivers = redis_instance().hget(chat_id, 'driver_data')
    driver_data = json.loads(drivers)
    buttons = []
    total_records = len(driver_data) if driver_data else 0
    total_pages = (total_records // records_per_page) + 1 if total_records % records_per_page != 0 else total_records // records_per_page
    if total_pages != 1:
        page_chunks = [list(range(start, min(start + max_buttons_in_row, total_pages + 1))) for start in range(1, total_pages + 1, max_buttons_in_row)]

        for chunk in page_chunks:
            row_buttons = [
                InlineKeyboardButton(text=f"{i}", callback_data=f"Page_{i}")
                for i in chunk
            ]
            buttons.append(row_buttons)
    return buttons


def get_driver_rent_info(update, context):
    query = update.callback_query
    cache_queryset(query)
    page_number = 1
    buttons = generate_buttons_for_page(page_number, str(query.from_user.id))
    buttons.extend(generate_pagination_buttons(page_number, str(query.from_user.id)))
    reply_markup = InlineKeyboardMarkup(buttons)
    query.edit_message_text("Оберіть водія:", reply_markup=reply_markup)


def handle_page_button_click(update, context):
    query = update.callback_query
    page_number = int(query.data.split('_')[-1])
    buttons = generate_buttons_for_page(page_number, str(query.from_user.id))
    buttons.extend(generate_pagination_buttons(page_number, str(query.from_user.id)))
    reply_markup = InlineKeyboardMarkup(buttons)
    try:
        query.edit_message_reply_markup(reply_markup=reply_markup)
    except BadRequest as e:
        if "Message is not modified" in str(e):
            pass


def start_rent_info_task(update, context):
    query = update.callback_query
    driver_id = int(query.data.split('_')[-1])
    query.edit_message_text(waiting_task_text)
    generate_rent_message_driver.apply_async(args=[driver_id, query.from_user.id,
                                                   query.message.message_id])



@task_postrun.connect
def send_rent_drivers(sender=None, **kwargs):
    if sender == generate_rent_message_driver:
        result = kwargs.get('retval')
        reply_markup = back_to_payment(result[3]) if result[3] else inline_manager_kb()
        edit_long_message(chat_id=result[0], text=result[1], message_id=result[2], keyboard=reply_markup)


@task_postrun.connect
def remove_cash_driver(sender=None, **kwargs):
    if sender == manager_paid_weekly:
        partner_pk = kwargs.get('retval')
        for manager in Manager.objects.filter(managers_partner=partner_pk):
            for driver in Driver.objects.filter(manager=manager):
                bot.send_message(chat_id=manager.chat_id, text=ask_driver_paid(driver),
                                 reply_markup=inline_driver_paid_kb(driver.id))


def functions_with_drivers(update, context):
    query = update.callback_query
    query.edit_message_text(choose_func_text)
    query.edit_message_reply_markup(inline_func_with_driver_kb())


def functions_with_vehicles(update, context):
    query = update.callback_query
    query.edit_message_text(choose_func_text)
    query.edit_message_reply_markup(inline_func_with_vehicle_kb())


def statistic_functions(update, context):
    query = update.callback_query
    query.edit_message_text(choose_func_text)
    query.edit_message_reply_markup(inline_statistic_kb())


def choose_spending_category(update, context):
    query = update.callback_query
    redis_instance().hset(str(update.effective_chat.id), 'vehicle', query.data.split()[1])
    query.edit_message_text(choose_category_text)
    query.edit_message_reply_markup(vehicle_spending_kb('Spending_car'))


def ask_spending_sum(update, context):
    query = update.callback_query
    data = {
        'category': query.data.split()[0],
        'state': SPENDING_CAR
    }
    redis_instance().hmset(str(update.effective_chat.id), data)
    query.edit_message_text(ask_spend_sum_text)


def save_car_spending(update, context):
    spending = update.message.text
    chat_id = str(update.effective_chat.id)
    if validate_sum(spending):
        user_data = redis_instance().hgetall(chat_id)
        vehicle = Vehicle.objects.get(pk=int(user_data['vehicle']))
        data = {'category': user_data['category'],
                'vehicle': vehicle,
                'amount': round(int(spending), 2)}
        VehicleSpending.objects.create(**data)
        redis_instance().delete(chat_id)
        context.bot.send_message(chat_id=update.effective_chat.id,
                                 text=spending_saved_text,
                                 reply_markup=inline_manager_kb())
    else:
        update.message.reply_text(wrong_sum_type)


@task_postrun.connect
def update_drivers(sender=None, **kwargs):
    if sender == update_driver_data:
        if kwargs.get('retval'):
            bot.send_message(chat_id=kwargs.get('retval'), text=update_finished, reply_markup=inline_manager_kb())


def remove_cash_by_manager(update, context):
    query = update.callback_query
    data = query.data.split(' ')
    driver = Driver.objects.filter(id=int(data[2])).first()
    fleets_cash_trips.apply_async(kwargs= {"partner_pk": driver.partner.id,
                                           "driver_id": int(data[2]), "enable": data[1]})
    query.edit_message_text(remove_cash_text(driver, data[1]))


def get_drivers_from_fleets(update, context):
    query = update.callback_query
    manager = Manager.get_by_chat_id(query.from_user.id)
    partner_id = manager.managers_partner_id if manager else Partner.get_by_chat_id(query.from_user.id).pk
    update_driver_data.apply_async(kwargs={"partner_pk": partner_id, "manager_id": query.from_user.id})
    query.edit_message_text(get_drivers_text)


def get_earning_report(update, context):
    query = update.callback_query
    user = CustomUser.get_by_chat_id(update.effective_chat.id)
    drivers = Driver.objects.filter(manager=user) if user.is_manager() else Driver.objects.filter(partner=user)
    if drivers:
        query.edit_message_text(choose_period_text)
        query.edit_message_reply_markup(inline_earning_report_kb('Get_statistic'))
    else:
        query.edit_message_text(no_manager_drivers)
        query.edit_message_reply_markup(back_to_main_menu())


def get_efficiency_report(update, context):
    query = update.callback_query
    query.edit_message_text(choose_period_text)
    query.edit_message_reply_markup(inline_efficiency_report_kb('Get_statistic'))


def get_drivers_statistics(update, context):
    query = update.callback_query
    query.edit_message_text(choose_period_text)
    query.edit_message_reply_markup(inline_driver_eff_kb('Get_statistic'))


def get_efficiency_for_drivers(update, context):
    query = update.callback_query
    if query.data == "Driver_custom":
        query.edit_message_text(start_report_text)
        redis_instance().hset(str(update.effective_chat.id), 'state', START_DRIVER_EFF)
    else:
        query.edit_message_text(generate_text)
        result, start, end = get_driver_efficiency_report(manager_id=query.from_user.id)
        if result:
            message = f"Статистика з {start.strftime('%d.%m')} по {end.strftime('%d.%m')}\n"
            for k, v in result.items():
                message += f"{k}\n" + "".join(v) + "\n"
        else:
            message = no_drivers_report_text
        try:
            query.edit_message_text(message)
            query.edit_message_reply_markup(reply_markup=inline_manager_kb())
        except BadRequest:
            send_long_message(update.effective_chat.id, message, inline_manager_kb())


def get_period_driver_eff(update, context):
    data = update.message.text
    if validate_date(data):
        redis_instance().hset(str(update.effective_chat.id), 'start', data)
        update.message.reply_text(end_report_text)
        redis_instance().hset(str(update.effective_chat.id), 'state', END_DRIVER_EFF)
    else:
        redis_instance().hset(str(update.effective_chat.id), 'state', START_DRIVER_EFF)
        context.bot.send_message(chat_id=update.message.chat_id, text=invalid_data_text)
        update.message.reply_text(start_report_text)


def create_driver_eff(update, context):
    data = update.message.text
    if validate_date(data):
        redis_instance().hdel(str(update.effective_chat.id), 'state')
        start_date = redis_instance().hget(str(update.effective_chat.id), "start")
        start = datetime.strptime(start_date, '%d.%m.%Y')
        end = datetime.strptime(data, '%d.%m.%Y')
        if start > end:
            start, end = end, start
        msg = update.message.reply_text(generate_text)
        result, start_stats, end_stats = get_driver_efficiency_report(update.message.chat_id, start_time=start, end_time=end)
        if result:
            message = f"Статистика з {start_stats.strftime('%d.%m')} по {end_stats.strftime('%d.%m')}\n"
            for k, v in result.items():
                message += f"{k}\n" + "".join(v) + "\n"
        else:
            message = no_drivers_report_text
        try:
            bot.edit_message_text(chat_id=update.effective_chat.id, text=message,
                                  message_id=msg.message_id, reply_markup=inline_manager_kb())
        except BadRequest:
            send_long_message(update.effective_chat.id, message, inline_manager_kb())
    else:
        redis_instance().hset(str(update.effective_chat.id), 'state', END_DRIVER_EFF)
        context.bot.send_message(chat_id=update.message.chat_id, text=invalid_end_data_text)


def get_weekly_report(update, context):
    query = update.callback_query
    query.edit_message_text(generate_text)
    daily = True if query.data == "Daily_payment" else False
    messages = generate_message_report(query.from_user.id, daily=daily)
    owner_message = messages.get(str(query.from_user.id))
    if owner_message:
        edit_long_message(chat_id=update.effective_chat.id, text=owner_message,
                          message_id=query.message.message_id, keyboard=back_to_main_menu())
    else:
        query.edit_message_text(no_drivers_report_text)
        query.edit_message_reply_markup(back_to_main_menu())


def get_report(update, context):
    query = update.callback_query
    message = ''
    if query.data == "Custom_report":
        query.edit_message_text(start_report_text)
        redis_instance().hset(str(update.effective_chat.id), 'state', START_EARNINGS)
    else:
        query.edit_message_text(generate_text)
        result = get_daily_report(manager_id=query.from_user.id)
        for key in result[0]:
            if result[0][key]:
                message += "{}\nКаса: {:.2f} (+{:.2f})\nОренда: {:.2f}км (+{:.2f})\n\n".format(
                    key, result[0][key], result[1].get(key, 0), result[2].get(key, 0), result[3].get(key, 0))
        try:
            query.edit_message_text(message)
        except BadRequest as e:
            if "Message text is empty" in str(e):
                query.edit_message_text(no_drivers_report_text)
        query.edit_message_reply_markup(reply_markup=inline_manager_kb())


def get_report_period(update, context):
    data = update.message.text
    if validate_date(data):
        user_data = {'start': data,
                     'state': END_EARNINGS}
        update.message.reply_text(end_report_text)
        redis_instance().hmset(str(update.effective_chat.id), user_data)
    else:
        redis_instance().hset(str(update.effective_chat.id), 'state', START_EARNINGS)
        context.bot.send_message(chat_id=update.message.chat_id, text=invalid_data_text)
        update.message.reply_text(start_report_text)


def create_period_report(update, context):
    date = update.message.text
    if validate_date(date):
        redis_instance().hdel(str(update.effective_chat.id), 'state')
        start_date = redis_instance().hget(str(update.effective_chat.id), "start")
        start = datetime.strptime(start_date, '%d.%m.%Y')
        end = datetime.strptime(date, '%d.%m.%Y')
        if start > end:
            start, end = end, start
        msg = update.message.reply_text(generate_text)
        report = generate_report_period(update.effective_chat.id, start, end)
        bot.edit_message_text(chat_id=update.effective_chat.id, text=report,
                              message_id=msg.message_id, reply_markup=inline_manager_kb())
    else:
        redis_instance().hset(str(update.effective_chat.id), 'state', END_EARNINGS)
        context.bot.send_message(chat_id=update.message.chat_id, text=invalid_end_data_text)


def get_efficiency_auto(update, context):
    query = update.callback_query
    message = ''
    if query.data == "Efficiency_custom":
        query.edit_message_text(start_report_text)
        redis_instance().hset(str(update.effective_chat.id), 'state', START_EFFICIENCY)
    else:
        query.edit_message_text(generate_text)
        result = get_efficiency(manager_id=query.from_user.id)
        for k, v in result.items():
            message += f"{k}\n" + "".join(v) + "\n"
        try:
            query.edit_message_text(message)
        except BadRequest as e:
            if "Message text is empty" in str(e):
                query.edit_message_text(no_vehicles_text)
        query.edit_message_reply_markup(reply_markup=inline_manager_kb())


def get_efficiency_period(update, context):
    data = update.message.text
    if validate_date(data):
        redis_instance().hset(str(update.effective_chat.id), 'start', data)
        update.message.reply_text(end_report_text)
        redis_instance().hset(str(update.effective_chat.id), 'state', END_EFFICIENCY)
    else:
        redis_instance().hset(str(update.effective_chat.id), 'state', START_EFFICIENCY)
        context.bot.send_message(chat_id=update.message.chat_id, text=invalid_data_text)
        update.message.reply_text(start_report_text)


def create_period_efficiency(update, context):
    data = update.message.text
    if validate_date(data):
        redis_instance().hdel(str(update.effective_chat.id), 'state')
        start_date = redis_instance().hget(str(update.effective_chat.id), "start")
        start = datetime.strptime(start_date, '%d.%m.%Y')
        end = datetime.strptime(data, '%d.%m.%Y')
        if start > end:
            start, end = end, start
        msg = update.message.reply_text(generate_text)
        result = get_efficiency(update.message.chat_id, start, end)
        message = ''
        for k, v in result.items():
            message += f"{k}\n" + "".join(v) + "\n"
        try:
            context.bot.edit_message_text(chat_id=update.effective_chat.id, text=message,
                                          message_id=msg.message_id, reply_markup=inline_manager_kb())
        except BadRequest as e:
            if "Message text is empty" in str(e):
                context.bot.edit_message_text(chat_id=update.effective_chat.id, text=no_vehicles_text,
                                              message_id=msg.message_id, reply_markup=inline_manager_kb())
    else:
        redis_instance().hset(str(update.effective_chat.id), 'state', END_EFFICIENCY)
        context.bot.send_message(chat_id=update.message.chat_id, text=invalid_end_data_text)


@task_postrun.connect
def send_into_group(sender=None, **kwargs):
    yesterday = timezone.make_aware(datetime.combine(timezone.localtime() - timedelta(days=1), time.max))
    if sender == send_driver_efficiency:
        messages, drivers_messages = kwargs.get('retval')
        for partner, message in messages.items():
            if message:
                send_long_message(chat_id=ParkSettings.get_value('DRIVERS_CHAT',
                                  default=Partner.objects.get(pk=partner).chat_id,
                                  partner=partner), text=message)
        for pk, message in drivers_messages.items():
            vehicle = check_vehicle(pk, yesterday)
            if vehicle:
                if vehicle.chat_id and message:
                    try:
                        bot.send_message(chat_id=vehicle.chat_id, text=message)
                    except BadRequest:
                        pass


@task_postrun.connect
def send_vehicle_efficiency(sender=None, **kwargs):
    if sender == send_efficiency_report:
        messages = kwargs.get('retval')
        for partner, message in messages.items():
            if message:
                send_long_message(chat_id=ParkSettings.get_value('DRIVERS_CHAT',
                                  default=Partner.objects.get(pk=partner).chat_id,
                                  partner=partner), text=message)


def get_partner_vehicles(update, context):
    query = update.callback_query
    user = CustomUser.get_by_chat_id(query.from_user.id)
    vehicles = Vehicle.objects.filter(manager=user) if user.is_manager() else Vehicle.objects.filter(partner=user)
    if vehicles:
        if query.data == "Pin_vehicle_to_driver":
            callback = 'select_vehicle'
            back_step = "Setup_drivers"
        else:
            callback = 'Spending_vehicle'
            back_step = 'Setup_vehicles'
        query.edit_message_text(partner_vehicles)
        query.edit_message_reply_markup(reply_markup=inline_partner_vehicles(vehicles, callback, back_step))
    else:
        query.edit_message_text(no_manager_vehicles)


def get_partner_drivers(update, context):
    query = update.callback_query
    pk_vehicle = query.data.split()[1]
    user = CustomUser.get_by_chat_id(query.from_user.id)
    drivers = Driver.objects.get_active(manager=user) if user.is_manager() else Driver.objects.get_active(partner=user)
    if drivers:
        query.edit_message_text(partner_drivers)
        query.edit_message_reply_markup(reply_markup=inline_partner_drivers(pin_vehicle_callback, drivers,
                                                                            'Pin_vehicle_to_driver', pk_vehicle,))
    else:
        query.edit_message_text(no_manager_drivers)


def pin_partner_vehicle_to_driver(update, context):
    query = update.callback_query
    data = query.data.split()
    driver_pk, vehicle_pk = data[1], data[2]
    driver_obj = Driver.objects.get(pk=driver_pk)
    vehicle_obj = Vehicle.objects.get(pk=vehicle_pk)
    driver_obj.vehicle = vehicle_obj
    driver_obj.save()
    query.edit_message_text(pin_vehicle_to_driver(driver_obj, vehicle_obj))
    query.edit_message_reply_markup(back_to_main_menu())


# Add users and vehicle to db and others
def add(update, context):
    chat_id = update.message.chat.id
    driver_manager = Manager.get_by_chat_id(chat_id)
    if driver_manager is not None:
        context.user_data['role'] = driver_manager
        update.message.reply_text('Оберіть опцію, кого ви бажаєте створити',
                                  reply_markup=markup_keyboard([create_user_keyboard]))
    else:
        update.message.reply_text(not_manager_text)


def create(update, context):
    update.message.reply_text('Оберіть, якого користувача ви бажаєте створити',
                              reply_markup=markup_keyboard([role_keyboard]))


def name(update, context):
    context.user_data['manager_state'] = NAME
    context.user_data['role'] = update.message.text
    update.message.reply_text("Введіть Ім`я:", reply_markup=ReplyKeyboardRemove())


def second_name(update, context):
    new_name = update.message.text
    new_name = User.name_and_second_name_validator(name=new_name)
    if new_name is not None:
        context.user_data['name'] = new_name
        update.message.reply_text("Введіть Прізвище:")
        context.user_data['manager_state'] = SECOND_NAME
    else:
        update.message.reply_text('Ім`я занадто довге. Спробуйте ще раз')


def email(update, context):
    second_name = update.message.text
    second_name = User.name_and_second_name_validator(name=second_name)
    if second_name is not None:
        context.user_data['second_name'] = second_name
        update.message.reply_text("Введіть електронну адресу:")
        context.user_data['manager_state'] = EMAIL
    else:
        update.message.reply_text('Прізвище занадто довге. Спробуйте ще раз')


def phone_number(update, context):
    email = update.message.text
    email = User.email_validator(email=email)
    if email is not None:
        context.user_data['email'] = email
        update.message.reply_text("Введіть телефонний номер:")
        context.user_data['manager_state'] = PHONE_NUMBER
    else:
        update.message.reply_text('Eлектронна адреса некоректна. Спробуйте ще раз')


def create_user(update, context):
    phone_number = update.message.text
    chat_id = update.message.chat.id
    phone_number = User.phone_number_validator(phone_number=phone_number)
    if phone_number is not None:
        if context.user_data['role'] == USER_DRIVER:
            driver = Driver.objects.create(
                name=context.user_data['name'],
                second_name=context.user_data['second_name'],
                email=context.user_data['email'],
                phone_number=phone_number)

            manager = Manager.get_by_chat_id(chat_id)
            manager.driver_id.add(driver.id)
            manager.save()
            update.message.reply_text('Водія було добавленно в базу данних')
        elif context.user_data['role'] == USER_MANAGER_DRIVER:
            Manager.objects.create(
                name=context.user_data['name'],
                second_name=context.user_data['second_name'],
                email=context.user_data['email'],
                phone_number=phone_number)

            update.message.reply_text('Менеджера водія було добавленно в базу данних')
        context.user_data['manager_state'] = None
    else:
        update.message.reply_text('Телефонний номер некоректний')


# Viewing broken car
def broken_car(update, context):
    chat_id = update.message.chat.id
    driver_manager = Manager.get_by_chat_id(chat_id)
    if driver_manager is not None:
        vehicle = Vehicle.objects.filter(car_status=f'{BROKEN}')
        report = ''
        result = [f'{i.licence_plate}' for i in vehicle]
        if len(result) == 0:
            update.message.reply_text("Немає зламаних авто")
        else:
            for i in result:
                report += f'{i}\n'
            update.message.reply_text(f'{report}')
    else:
        update.message.reply_text(not_manager_text)


# Viewing status driver
def driver_status(update, context):
    chat_id = update.message.chat.id
    driver_manager = Manager.get_by_chat_id(chat_id)
    if driver_manager is not None:
        context.user_data['manager_state'] = STATUS
        context.bot.send_message(chat_id=update.effective_chat.id, text='Оберіть статус',
                                 reply_markup=markup_keyboard_onetime(drivers_status_buttons))
    else:
        update.message.reply_text(not_manager_text)


def viewing_status_driver(update, context):
    status = update.message.text
    status = status[2:]
    driver = Driver.objects.filter(driver_status=status)
    report = ''
    result = [f'{i.name} {i.second_name}' for i in driver]
    if len(result) == 0:
        update.message.reply_text('Зараз немає водіїв з таким статусом', reply_markup=ReplyKeyboardRemove())
    else:
        for i in result:
            report += f'{i}\n'
    update.message.reply_text(f'{report}', reply_markup=ReplyKeyboardRemove())
    context.user_data['manager_state'] = None


# Add Vehicle to driver
def get_list_drivers(update, context):
    chat_id = update.message.chat.id
    driver_manager = Manager.get_by_chat_id(chat_id)
    if driver_manager is not None:
        drivers = {i.id: f'{i.name } {i.second_name}' for i in Driver.objects.all()}
        if len(drivers) == 0:
            update.message.reply_text('Кількість зареєстрованих водіїв 0')
        else:
            drivers_keys = sorted(drivers)
            drivers = {i: drivers[i] for i in drivers_keys}
            report_list_drivers = ''
            for k, v in drivers.items():
                report_list_drivers += f'{k}: {v}\n'
            update.message.reply_text(f'{report_list_drivers}')
            context.user_data['manager_state'] = DRIVER
            update.message.reply_text('Укажіть номер водія, якому хочете добавити авто.')
    else:
        update.message.reply_text(not_manager_text)


def get_list_vehicle(update, context):
    id_driver = update.message.text
    try:
        id_driver = int(id_driver)
        context.user_data['driver'] = Driver.objects.get(id=id_driver)
    except:
        update.message.reply_text('Не вдалось обробити ваше значення, або переданий номер водія виявився недійсним. Спробуйте ще раз')
    vehicles = {i.id: i.licence_plate for i in Vehicle.objects.all()}
    if len(vehicles) == 0:
        update.message.reply_text('Кількість зареєстрованих траспортних засобів 0')
    else:
        if context.user_data['driver'] is not None:
            report_list_vehicles = ''
            for k, v in vehicles.items():
                report_list_vehicles += f'{k}: {v}\n'
            update.message.reply_text(f'{report_list_vehicles}')
            context.user_data['manager_state'] = CAR_NUMBERPLATE
            update.message.reply_text('Укажіть номер авто, який ви хочете прикріпити до водія')


def get_fleet(update, context):
    id_vehicle = update.message.text
    try:
        id_vehicle = int(id_vehicle)
        context.user_data['vehicle'] = Vehicle.objects.get(id=id_vehicle)
    except:
        update.message.reply_text('Не вдалось обробити ваше значення, або переданий номер автомобільного номера виявився недійсним. Спробуйте ще раз')
    if context.user_data['vehicle'] is not None:

        context.bot.send_message(chat_id=update.effective_chat.id,
                                 text='Оберіть автопарк. Для прикріплення автомобіля водію',
                                 reply_markup=markup_keyboard(fleets_keyboard))


def get_driver_external_id(update, context):
    fleet = update.message.text
    context.user_data['fleet'] = fleet
    try:
        response = FleetsDriversVehiclesRate.objects.get(
            fleet=Fleet.objects.get(name=fleet),
            driver=context.user_data['driver'],
            vehicle=context.user_data['vehicle'])
        response = str(response)
    except:
        try:
            driver = str(context.user_data['driver'])
            driver = driver.split()
            driver = f'{driver[1]} {driver[0]}'
            driver_external_id = Payments.objects.get(full_name=driver, vendor_name=fleet)
            driver_external_id = driver_external_id.driver_id
        except:
            pass
        try:
            context.user_data['driver_external_id'] = driver_external_id
        except:
            context.user_data['driver_external_id'] = 'pass'

        drivers_rate = {key: round(key * 0.05, 2) for key in range(1, 21)}
        rate = ''
        for k, v in drivers_rate.items():
            rate += f'{k}: {v}\n'

        context.user_data['rate'] = drivers_rate
        update.message.reply_text(f"{rate}",  reply_markup=ReplyKeyboardRemove())
        update.message.reply_text(f"Укажіть номер рейтингу, який ви хочете встановити для {context.user_data['driver']}"
                                  f" в автопарку {context.user_data['fleet']}")
        context.user_data['manager_state'] = RATE
    try:
        if isinstance(response, str):
            update.message.reply_text('Для даного водія вже прикріплене данне авто та автопарк. Спробуйте спочатку')
            context.user_data['manager_state'] = None
    except:
        pass


def add_information_to_driver(update, context):
    id_rate = update.message.text
    try:
        id_rate = int(id_rate)
        rate = context.user_data['rate']
        rate = rate[id_rate]
    except:
        update.message.reply_text('Не вдалось обробити ваше значення, або переданий номер рейтингу не є дійсним. Спробуйте ще раз')
    if isinstance(rate, float):
        FleetsDriversVehiclesRate.objects.create(
                fleet=Fleet.objects.get(name=context.user_data['fleet']),
                driver=context.user_data['driver'],
                vehicle=context.user_data['vehicle'],
                driver_external_id=context.user_data['driver_external_id'],
                rate=rate)
        update.message.reply_text(f"Ви добавили водію машину та рейтинг в автопарк {context.user_data['fleet']}")
        if context.user_data['driver_external_id'] == 'pass':
            update.message.reply_text(f"Водія {context.user_data['driver']} збереженно зі значенням driver_external_id = \
                        {context.user_data['driver_external_id']}. Ви можете його змінити власноруч, через панель адміністратора")
        context.user_data['manager_state'] = None


# Push job application to fleets
def get_list_job_application(update, context):
    chat_id = update.message.chat.id
    driver_manager = Manager.get_by_chat_id(chat_id)
    if driver_manager is not None:
        applications = {i.id: f'{i}' for i in JobApplication.objects.all() if (i.role == driver_job_name and i.status_bolt == False)}
        if len(applications) == 0:
            update.message.reply_text('Заявок на роботу водія поки немає')
        else:
            report_list_applications = ''
            for k, v in applications.items():
                report_list_applications += f'{k}: {v}\n'
            update.message.reply_text(report_list_applications)
            update.message.reply_text('Укажіть номер користувача, заявку якого ви бажаєте відправити')
            context.user_data['manager_state'] = JOB_APPLICATION
    else:
        update.message.reply_text('Зареєструйтесь як менеджер водіїв')


def get_fleet_for_job_application(update, context):
    id_job_application = update.message.text
    try:
        id_job_application = int(id_job_application)
        context.user_data['job_application'] = JobApplication.objects.get(id=id_job_application)

        context.bot.send_message(chat_id=update.effective_chat.id,
                                 text='Ви дійсно бажаєте подати заявку?',
                                 reply_markup=markup_keyboard(fleet_job_keyboard))
        context.user_data['manager_state'] = None
    except:
        update.message.reply_text('Не вдалось обробити ваше значення. Спробуйте ще раз')


def add_job_application_to_fleet(update, context):
    data = context.user_data['job_application']
    send_on_job_application_on_driver.delay(data.id)
    update.message.reply_text('Заявки додано в Uklon та Bolt.Користувачу потрібно зареєструватись на сайті Uber як водій')


# Add vehicle to db
def name_vehicle(update, context):
    update.message.reply_text('Введіть назву авто:', reply_markup=ReplyKeyboardRemove())
    context.user_data['manager_state'] = NAME_VEHICLE


def get_name_vehicle(update, context):
    name_vehicle = update.message.text
    name_vehicle = Vehicle.name_validator(name=name_vehicle)
    if name_vehicle is not None:
        context.user_data['name_vehicle'] = name_vehicle
        update.message.reply_text('Введіть модель авто:')
        context.user_data['manager_state'] = MODEL_VEHICLE
    else:
        update.message.reply_text('Назва занадто довга. Спробуйте ще раз')


def get_model_vehicle(update, context):
    model_vehicle = update.message.text
    model_vehicle = Vehicle.model_validator(model=model_vehicle)
    if model_vehicle is not None:
        context.user_data['model_vehicle'] = model_vehicle
        update.message.reply_text('Введіть автомобільний номер:')
        context.user_data['manager_state'] = LICENCE_PLATE_VEHICLE
    else:
        update.message.reply_text('Назва занадто довга. Спробуйте ще раз')


def get_licence_plate_vehicle(update, context):
    licence_plate_vehicle = update.message.text
    licence_plate_vehicle = Vehicle.licence_plate_validator(licence_plate=licence_plate_vehicle)
    if licence_plate_vehicle is not None:
        context.user_data['licence_plate_vehicle'] = licence_plate_vehicle
        update.message.reply_text('Введіть vin_code для машини (максимальна кількість символів 17)')
        context.user_data['manager_state'] = VIN_CODE_VEHICLE
    else:
        update.message.reply_text('Номерний знак занадто довгий. Спробуйте ще раз')


def get_vin_code_vehicle(update, context):
    vin_code = update.message.text
    vin_code = Vehicle.vin_code_validator(vin_code=vin_code)
    if vin_code is not None:
        Vehicle.objects.create(
            name=context.user_data['name_vehicle'],
            model=context.user_data['model_vehicle'],
            licence_plate=context.user_data['licence_plate_vehicle'],
            vin_code=vin_code)
        update.message.reply_text('Машину додано до бази даних')
        context.user_data['manager_state'] = None
    else:
        update.message.reply_text('Vin code занадто довгий. Спробуйте ще раз')


def get_licence_plate_for_gps_imei(update, context):
    chat_id = update.message.chat.id
    driver_manager = Manager.get_by_chat_id(chat_id)
    vehicles = {i.id: i.licence_plate for i in Vehicle.objects.all()}
    vehicles = {k: vehicles[k] for k in sorted(vehicles)}
    report_list_vehicles = ''
    if driver_manager is not None:
        if vehicles:
            for k, v in vehicles.items():
                report_list_vehicles += f'{k}: {v}\n'
            update.message.reply_text(f'{report_list_vehicles}')
            update.message.reply_text(f'Укажіть номер машини від 1-{len(vehicles)}, для якого ви бажаєте добавити gps_imei')
            context.user_data['manager_state'] = V_GPS
        else:
            update.message.reply_text("Не здайдено жодного авто у автопарку")
    else:
        update.message.reply_text('Зареєструйтесь як менеджер водіїв')


def get_n_vehicle(update, context):
    id_vehicle = update.message.text
    try:
        id_vehicle = int(id_vehicle)
        context.user_data['vehicle'] = Vehicle.objects.get(id=id_vehicle)
        update.message.reply_text('Введіть gps_imei для данного авто')
        context.user_data['manager_state'] = V_GPS_IMEI
    except:
        update.message.reply_text('Не вдалось обробити ваше значення, або переданий номер автомобільного'
                                  ' номера виявився недійсним. Спробуйте ще раз')


def get_gps_imea(update, context):
    gps_imei = update.message.text
    gps_imei = Vehicle.gps_imei_validator(gps_imei=gps_imei)
    if gps_imei is not None:
        context.user_data['vehicle'].gps_imei = gps_imei
        context.user_data['vehicle'].save()
        update.message.reply_text('Ми встановили GPS imei до авто, яке ви вказали')
        context.user_data['manager_state'] = None
    else:
        update.message.reply_text("Задовге значення. Спробуйте ще раз")
