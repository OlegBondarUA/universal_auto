import json
import os
import re
from datetime import datetime

from django.db.models import F
from telegram import ReplyKeyboardRemove,  LabeledPrice, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest

from app.models import Order, Driver, Client, FleetOrder, ReportTelegramPayments, Manager, UserBank
from auto.tasks import get_distance_trip, order_create_task, send_map_to_client, fleet_order
from auto_bot.handlers.main.keyboards import markup_keyboard, back_to_main_menu
from auto_bot.handlers.order.keyboards import inline_spot_keyboard, inline_route_keyboard, inline_finish_order, \
    inline_repeat_keyboard, inline_reject_order, inline_increase_price_kb, inline_search_kb, inline_start_order_kb, \
    share_location, inline_location_kb, inline_payment_kb, inline_comment_for_client, inline_choose_date_kb, \
    inline_add_info_kb, user_duty, personal_order_start_kb, personal_order_time_kb, \
    personal_order_end_kb, personal_order_back_kb
from auto_bot.handlers.order.utils import buttons_addresses, text_to_client, validate_text, get_geocoding_address, \
    save_location_to_redis, check_vehicle
from auto_bot.main import bot
from scripts.conversion import get_address, get_location_from_db, get_route_price
from auto_bot.handlers.order.static_text import *
from scripts.redis_conn import redis_instance, get_logger
from app.portmone.portmone import Portmone


def personal_driver_info(update, context):
    query = update.callback_query
    query.edit_message_text(choose_action)
    query.edit_message_reply_markup(personal_order_start_kb())


def personal_order_info(update, context):
    query = update.callback_query
    query.edit_message_text(personal_order_text)
    query.edit_message_reply_markup(personal_order_back_kb())


def personal_order_terms(update, context):
    query = update.callback_query
    query.edit_message_text(personal_terms_text)
    query.edit_message_reply_markup(personal_order_back_kb())


def get_personal_time(update, context):
    query = update.callback_query
    chat_id = update.effective_chat.id
    if query:
        query.edit_message_text(pd_time_text)
        query.edit_message_reply_markup(personal_order_time_kb())
    else:
        context.bot.send_message(chat_id=chat_id, text=pd_time_text, reply_markup=personal_order_time_kb())


def finish_personal_driver(update, context):
    query = update.callback_query
    order_id = int(query.data.split()[1])
    order = Order.objects.get(pk=order_id)
    order.status_order = Order.COMPLETED
    order.partner = order.driver.partner
    order.save()
    client_msg = redis_instance().hget(str(order.chat_id_client), "client_msg")
    driver_msg = redis_instance().hget(str(order.driver.chat_id), "driver_msg")
    context.bot.edit_message_text(chat_id=order.driver.chat_id,
                                  message_id=driver_msg, text=driver_complete_text(order.sum))
    text_to_client(order, complete_order_text, delete_id=client_msg, button=inline_comment_for_client())
    fleet_order(order)
    redis_instance().delete(str(order.chat_id_client))
    redis_instance().delete(str(order.driver.chat_id))


def not_continue_personal_order(update, context):
    query = update.callback_query
    order_id = int(query.data.split()[1])
    order = Order.objects.get(pk=order_id)
    redis_instance().hset(str(update.effective_chat.id), "finish", order_id)
    query.edit_message_text(client_finish_personal_order)
    text_to_client(order, complete_order_text, button=inline_comment_for_client())


def update_personal_order(update, context):
    query = update.callback_query
    order_id = int(query.data.split()[1])
    query.edit_message_text(pd_update_time)
    query.edit_message_reply_markup(personal_order_time_kb(order_id))


def payment_personal_order(update, context):
    query = update.callback_query
    chat_id = update.effective_chat.id
    data = query.data.split()
    hours, pk = int(data[2]), data[0]
    redis_instance().hset(str(chat_id), 'hours', hours)
    price = hours * int(ParkSettings.get_value('AVERAGE_DISTANCE_PER_HOUR')) * int(
        ParkSettings.get_value('TARIFF_IN_THE_CITY'))
    edit_text = complete_personal_order(price) if pk == "None" else add_hours_text(price)
    query.edit_message_text(edit_text)
    payload = f"{chat_id} {query.message.message_id} {price}"
    payment_request(chat_id,
                    chat_id,
                    payload,
                    price)


def back_step_to_finish_personal(update, context):
    query = update.callback_query
    order_id = int(query.data.split()[0])
    query.edit_message_text(back_time_route_end)
    query.edit_message_reply_markup(personal_order_end_kb(order_id, pre_finish=True))


def continue_order(update, context):
    query = update.callback_query
    chat_id = update.effective_chat.id
    order = Order.objects.filter(chat_id_client=chat_id,
                                 status_order__in=[Order.ON_TIME, Order.WAITING],
                                 type_order=Order.STANDARD_TYPE)
    if order:
        query.edit_message_text(already_ordered)
    else:
        redis_instance().hdel(str(chat_id), 'location_button')
        redis_instance().hset(str(chat_id), 'state', START_TIME_ORDER)
        query.edit_message_text(price_info(ParkSettings.get_value('TARIFF_IN_THE_CITY'),
                                           ParkSettings.get_value('TARIFF_OUTSIDE_THE_CITY')))
    query.edit_message_reply_markup(inline_start_order_kb())


def get_location(update, context):
    chat_id = str(update.effective_chat.id)
    if update.message:
        location = update.message.location
        data = {
            'state': 0,
            'location_button': 1,
            'latitude': location.latitude,
            'longitude': location.longitude
        }
        redis_instance().hmset(str(chat_id), data)
        latitude = redis_instance().hget(chat_id, 'latitude')
        longitude = redis_instance().hget(chat_id, 'longitude')
        address = get_address(latitude, longitude,
                              ParkSettings.get_value('GOOGLE_API_KEY'))
        if address is not None:
            redis_instance().hdel(str(chat_id), 'location_button')
            redis_instance().hset(chat_id, 'location_address', address)
            update.message.reply_text(text=f'Ваша адреса: {address}', reply_markup=ReplyKeyboardRemove())
            update.message.reply_text(text=ask_spot_text, reply_markup=inline_location_kb())
        else:
            update.message.reply_text(text=no_location_text)
            from_address(update, context)


def from_address(update, context):
    query = update.callback_query
    chat_id = update.effective_chat.id
    redis_instance().hset(str(chat_id), 'state', FROM_ADDRESS)
    location_button = redis_instance().hget(str(chat_id), 'location_button')
    if not location_button:
        reply_markup = markup_keyboard(share_location)
        if query:
            query.edit_message_text(info_address_text)
        else:
            context.bot.send_message(chat_id=chat_id, text=info_address_text)
        context.bot.send_message(chat_id=chat_id, text=from_address_text, reply_markup=reply_markup)
    else:
        query.edit_message_text(from_address_text)


def to_the_address(update, context):
    query = update.callback_query
    chat_id = update.effective_chat.id
    state = redis_instance().hget(str(chat_id), 'state')
    if state and state == str(FROM_ADDRESS):
        buttons = [[InlineKeyboardButton(f'{NOT_CORRECT_ADDRESS}', callback_data='From_address 0')], ]
        address = update.message.text
        addresses = buttons_addresses(address)
        if addresses is not None:
            for no, key in enumerate(addresses.keys(), 1):
                buttons.append([InlineKeyboardButton(key, callback_data=f'From_address {no}')])
            buttons.append([InlineKeyboardButton(order_inline_buttons[6], callback_data="On_time_order")])
            reply_markup = InlineKeyboardMarkup(buttons)
            redis_instance().hset(str(chat_id), 'addresses_first', json.dumps(addresses))
            context.bot.send_message(chat_id=chat_id, text=from_address_search, reply_markup=ReplyKeyboardRemove())
            context.bot.send_message(chat_id=chat_id, text=choose_from_address_text, reply_markup=reply_markup)
        else:
            context.bot.send_message(chat_id=chat_id, text=wrong_address_request, reply_markup=ReplyKeyboardRemove())
            from_address(update, context)
    elif redis_instance().hget(str(chat_id), 'personal_flag'):
        payment_method(update, context)
        return
    else:
        if query:
            query.edit_message_text(arrival_text)
        else:
            context.bot.send_message(chat_id=chat_id, text=arrival_text)
        redis_instance().hset(str(chat_id), 'state', TO_THE_ADDRESS)


def payment_method(update, context):
    query = update.callback_query
    chat_id = update.effective_chat.id
    state = redis_instance().hget(str(chat_id), 'state')
    if state and state == str(TO_THE_ADDRESS):
        address = update.message.text
        buttons = [[InlineKeyboardButton(f'{NOT_CORRECT_ADDRESS}', callback_data='To_the_address 0')], ]
        addresses = buttons_addresses(address)
        if addresses is not None:
            for no, key in enumerate(addresses.keys(), 1):
                buttons.append([InlineKeyboardButton(key, callback_data=f'To_the_address {no}')])
            buttons.append([InlineKeyboardButton(order_inline_buttons[6], callback_data="Wrong_place")])
            reply_markup = InlineKeyboardMarkup(buttons)
            redis_instance().hset(str(chat_id), 'addresses_second', json.dumps(addresses))
            context.bot.send_message(chat_id=chat_id,
                                     text=choose_to_address_text,
                                     reply_markup=reply_markup)
        else:
            context.bot.send_message(chat_id=chat_id, text=wrong_address_request)
            to_the_address(update, context)
    else:
        back_step = "Wrong_place" if redis_instance().hget(str(chat_id), 'personal_flag') else "Right_place"
        query.edit_message_text(add_info_text)
        query.edit_message_reply_markup(inline_add_info_kb(back_step))
        redis_instance().hdel(str(chat_id), 'state')


def add_info_to_order(update, context):
    query = update.callback_query
    query.edit_message_text(ask_info_text)
    redis_instance().hset(str(update.effective_chat.id), 'state', ADD_INFO)


def get_additional_info(update, context):
    query = update.callback_query
    chat_id = update.effective_chat.id
    personal_order = redis_instance().hget(str(chat_id), 'personal_flag')
    if personal_order:
        get_personal_time(update, context)
        return
    if query:
        query.edit_message_text(payment_text)
        query.edit_message_reply_markup(inline_payment_kb())
    else:
        if validate_text(update.message.text):
            redis_instance().hdel(str(update.effective_chat.id), 'state')
            redis_instance().hset(str(chat_id), 'info', update.message.text)
            context.bot.send_message(chat_id=chat_id, text=payment_text, reply_markup=inline_payment_kb())
        else:
            redis_instance().hset(str(update.effective_chat.id), 'state', ADD_INFO)
            context.bot.send_message(chat_id=chat_id, text=too_long_text)


def second_address_check(update, context):
    query = update.callback_query
    chat_id = update.effective_chat.id
    data = int(query.data.split(' ')[1])
    response = query.message.reply_markup.inline_keyboard[data][0].text
    if data:
        data_ = {
            'to_the_address': response,
            'state': 0
        }
        redis_instance().hmset(str(chat_id), data_)
        payment_method(update, context)
    else:
        to_the_address(update, context)


def first_address_check(update, context):
    query = update.callback_query
    chat_id = update.effective_chat.id
    data = int(query.data.split(' ')[1])
    response = query.message.reply_markup.inline_keyboard[data][0].text
    if data:
        data_ = {
            'from_address': response,
            'state': 0
        }
        redis_instance().hmset(str(chat_id), data_)

        to_the_address(update, context)
    else:
        from_address(update, context)


def payment_request(chat_id_client, start_parameter, payload, price: int):
    prices = [LabeledPrice(label=payment_price, amount=int(price) * 100)]

    # Sending a request for payment
    bot.send_invoice(chat_id=chat_id_client,
                     title=payment_title,
                     description=payment_description,
                     payload=payload,
                     start_parameter=start_parameter,
                     provider_token=os.environ["PAYMENT_TOKEN"],
                     currency=payment_currency,
                     prices=prices,
                     photo_url=os.environ["BOT_URL_IMAGE_TAXI"],
                     need_shipping_address=False,
                     photo_width=615,
                     photo_height=512,
                     photo_size=50000,
                     is_flexible=False)


def order_create(update, context):
    query = update.callback_query

    data = int(query.data.split()[1])
    button_text = query.message.reply_markup.inline_keyboard[data][0].text
    payment = button_text.split()[1]
    user = Client.get_by_chat_id(update.effective_chat.id)
    query.edit_message_text(creating_order_text)
    redis_instance().hset(user.chat_id, 'client_msg', query.message.message_id)
    save_location_to_redis(user.chat_id)
    destination_lat, destination_long = get_geocoding_address(user.chat_id, 'addresses_second', 'to_the_address')

    order_data = {
        'from_address': redis_instance().hget(user.chat_id, 'from_address'),
        'latitude': redis_instance().hget(user.chat_id, 'latitude'),
        'longitude': redis_instance().hget(user.chat_id, 'longitude'),
        'to_the_address': redis_instance().hget(user.chat_id, 'to_the_address'),
        'to_latitude': destination_lat,
        'to_longitude': destination_long,
        'phone_number': user.phone_number,
        'chat_id_client': user.chat_id,
        'payment_method': payment,
    }
    if redis_instance().hexists(user.chat_id, 'info'):
        order_data.update({'info': redis_instance().hget(user.chat_id, 'info')}),
    if not redis_instance().hexists(user.chat_id, 'time_order'):
        order_data['status_order'] = Order.WAITING
    else:
        order_data['status_order'] = Order.ON_TIME
        order_time = redis_instance().hget(user.chat_id, 'time_order')
        order_data['order_time'] = datetime.fromisoformat(order_time)

    distance_price = get_route_price(order_data['latitude'], order_data['longitude'],
                                     order_data['to_latitude'], order_data['to_longitude'],
                                     ParkSettings.get_value('GOOGLE_API_KEY'))

    order_data['sum'] = distance_price[0] if \
        distance_price[0] > int(ParkSettings.get_value('MINIMUM_PRICE_FOR_ORDER')) else \
        int(ParkSettings.get_value('MINIMUM_PRICE_FOR_ORDER'))
    order_data['distance_google'] = round(distance_price[1], 2)
    if order_data['payment_method'] == price_inline_buttons[5].split()[1]:
        query.edit_message_text(accept_order(order_data['sum']))
        del order_data['order_time']
        redis_instance().hmset(f"{order_data['chat_id_client']}_", order_data)
        payment_request(order_data['chat_id_client'],
                        order_data['chat_id_client'],
                        order_data['chat_id_client'],
                        order_data['sum'])
    else:
        order_create_task.delay(order_data)


def increase_search_radius(update, context):
    query = update.callback_query
    data = int(query.data.split()[1])
    query.edit_message_text(increase_radius_text)
    query.edit_message_reply_markup(inline_increase_price_kb(data))


def ask_client_action(update, context):
    query = update.callback_query
    data = int(query.data.split()[1])
    query.edit_message_text(no_driver_in_radius)
    query.edit_message_reply_markup(inline_search_kb(data))


def increase_order_price(update, context):
    query = update.callback_query
    chat_id = query.from_user.id
    order = Order.objects.filter(chat_id_client=chat_id,
                                 status_order=Order.WAITING).last()
    if query.data != "Continue_search":
        order.car_delivery_price += int(query.data)
        order.sum += int(query.data)
    order.checked = False
    order.save()


def choose_date_order(update, context):
    query = update.callback_query
    chat_id = update.effective_chat.id
    duty = UserBank.get_duty(chat_id)
    if query.data == "Personal_order":
        redis_instance().hset(str(update.effective_chat.id), 'personal_flag', query.data)
        query.edit_message_text(order_date_text)
        query.edit_message_reply_markup(inline_choose_date_kb("Personal_driver"))
    elif duty.duty >= int(ParkSettings.get_value('USER_DUTY')):
        query.edit_message_text(duty_of_user)
        query.edit_message_reply_markup(user_duty())
    else:
        order = Order.objects.filter(chat_id_client=chat_id,
                                     status_order__in=[Order.ON_TIME, Order.WAITING],
                                     type_order=Order.STANDARD_TYPE).count()
        if order >= 1:
            query.edit_message_text(order_not_payment)
        else:
            query.edit_message_text(order_date_text)
            query.edit_message_reply_markup(inline_choose_date_kb("Back_to_main"))


def time_order(update, context):
    query = update.callback_query
    chat_id = str(update.effective_chat.id)
    if query.data in ("Today_order", "Tomorrow_order"):
        redis_instance().hset(chat_id, 'time_order', query.data)
    redis_instance().hset(chat_id, 'state', TIME_ORDER)
    query.edit_message_text(text=ask_time_text)


def order_on_time(update, context):
    chat_id = str(update.message.chat.id)
    pattern = r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$'
    user_time, user = update.message.text, Client.get_by_chat_id(chat_id)
    if re.match(pattern, user_time):
        format_time = timezone.datetime.strptime(user_time, '%H:%M').time()
        if redis_instance().hget(chat_id, 'time_order') == "Tomorrow_order":
            tomorrow = datetime.now() + timedelta(days=1)
            order_time = datetime.combine(tomorrow.date(), format_time)
        else:
            order_time = datetime.combine(datetime.now().date(), format_time)
        time_difference = order_time - datetime.now()
        if time_difference.total_seconds() / 60 > int(ParkSettings.get_value('TIME_ORDER_MIN', 60)):
            redis_instance().hdel(chat_id, 'state')
            if not redis_instance().hexists(chat_id, 'time_order'):
                order = Order.objects.filter(chat_id_client=user.chat_id,
                                             status_order=Order.WAITING).last()
                try:
                    client_msg = redis_instance().hget(order.chat_id_client, 'client_msg')
                    context.bot.delete_message(chat_id=order.chat_id_client, message_id=client_msg)
                    redis_instance().hdel(order.chat_id_client, 'client_msg')
                except BadRequest:
                    pass
                order.status_order = Order.ON_TIME
                order.order_time, order.checked = timezone.make_aware(order_time), False
                order.save()
            else:
                redis_instance().hset(chat_id, 'time_order', timezone.make_aware(order_time).isoformat())
                from_address(update, context)
        else:
            update.message.reply_text(small_time_delta(timezone.localtime(),
                                                       int(ParkSettings.get_value('TIME_ORDER_MIN')) + 5))
            redis_instance().hset(chat_id, 'state', TIME_ORDER)
    else:
        update.message.reply_text(wrong_time_format)
        redis_instance().hset(chat_id, 'state', TIME_ORDER)


def cancel_order_report(response, report, cancel):
    if isinstance(response, list):
        report_for_client = f'{return_money_from_system} {get_money} {cancel}{report.currency}'
    else:
        bad_response = bad_response_portmone(ParkSettings.get_value("NINJA_PHONE"),
                                             ParkSettings.get_value("NINJA_EMAIL"),
                                             ParkSettings.get_value("NINJA_ADDRESS"),
                                             report.provider_payment_charge_id
                                             )
        report_for_client = f'{bad_response}\n' \
                            f'{get_money} {cancel}{report.currency}'
    return report_for_client


def client_reject_order(update, context):
    query = update.callback_query
    order = Order.objects.filter(pk=int(query.data.split()[1])).first()
    if order.driver:
        fleet_order(order, FleetOrder.CLIENT_CANCEL)
        driver_msg = redis_instance().hget(str(order.driver.chat_id), 'driver_msg')
        bot.delete_message(chat_id=order.driver.chat_id, message_id=driver_msg)
        bot.send_message(
            chat_id=order.driver.chat_id,
            text=f'Вибачте, замовлення за адресою {order.from_address} відхилено клієнтом.'
        )
        cancel = int(ParkSettings.get_value('CANCEL_ORDER'))
        report = ReportTelegramPayments.objects.filter(order=order.pk).first()

        if order.payment_method == price_inline_buttons[4].split()[1]:
            duty = UserBank.get_duty(order.chat_id_client)
            duty.duty += cancel
            report_for_client = f'{get_money} {cancel}UAH. {put_on_bank}'
            duty.save()
        else:
            portmone = Portmone()
            total_amount = report.total_amount
            dif_sum = total_amount - cancel
            response = portmone.return_amount(dif_sum, report.provider_payment_charge_id, return_money)
            report_for_client = cancel_order_report(response, report, cancel)
            report.total_amount = dif_sum
            report.save()

        text_to_client(order=order,
                       text=report_for_client)
        driver_msg = redis_instance().hget(str(order.driver.chat_id), 'driver_msg')
        bot.delete_message(chat_id=order.driver.chat_id, message_id=driver_msg)
    else:
        if order.payment_method == price_inline_buttons[5].split()[1]:
            report = ReportTelegramPayments.objects.filter(order=order.pk).first()
            portmone = Portmone()
            response = portmone.return_amount(report.total_amount, report.provider_payment_charge_id, return_money)
            if isinstance(response, list):
                report_for_client = f'{return_money_from_system}'
            else:
                report_for_client = f'{bad_response_portmone}{report.provider_payment_charge_id}\n'
            text_to_client(order=order,
                           text=report_for_client)
            report.total_amount = 0
            report.save()
        try:
            group_msg = redis_instance().hget('group_msg', order.pk)
            context.bot.delete_message(chat_id=ParkSettings.get_value('ORDER_CHAT'),
                                       message_id=group_msg)
            redis_instance().hdel('group_msg', order.pk)
        except BadRequest as e:
            get_logger().error(e)
    order.status_order = Order.CANCELED
    order.finish_time = timezone.localtime()
    order.save()
    redis_instance().delete(order.chat_id_client)

    try:
        for i in range(3):
            context.bot.delete_message(chat_id=order.chat_id_client,
                                       message_id=query.message.message_id + i)
    except BadRequest as e:
        get_logger().error(e)
    text_to_client(order=order,
                   text=client_cancel,
                   button=inline_comment_for_client())


def handle_callback_order(update, context):
    query = update.callback_query
    data = query.data.split(' ')
    driver = Driver.get_by_chat_id(chat_id=query.from_user.id)
    vehicle = check_vehicle(driver)
    order = Order.objects.filter(pk=int(data[1])).first()
    if order.status_order in (Order.COMPLETED, Order.IN_PROGRESS):
        query.edit_message_text(text=already_accepted)
        return
    if order.status_order == Order.ON_TIME:
        if driver and vehicle:
            order.driver = driver
            order.save()
            group_msg = redis_instance().hget('group_msg', order.pk)
            context.bot.delete_message(chat_id=ParkSettings.get_value('ORDER_CHAT'),
                                       message_id=group_msg)
            redis_instance().hdel('group_msg', order.pk)
            for manager in Manager.objects.exclude(chat_id__isnull=True):
                if redis_instance().hexists(str(manager.chat_id), f'personal {order.id}'):
                    context.bot.send_message(chat_id=manager.chat_id,
                                             text=f"Замовлення {order.id} прийнято")
                    redis_instance().hdel(str(manager.chat_id), f'personal {order.id}')
            report_for_client = client_order_text(driver, vehicle.name, vehicle.licence_plate,
                                                  driver.phone_number, order.sum)
            message_info = redis_instance().hget(str(order.chat_id_client), 'client_msg')
            client_msg = text_to_client(order, report_for_client, delete_id=message_info,
                                        button=inline_reject_order(order.pk))
            redis_instance().hset(str(order.chat_id_client), 'client_msg', client_msg)
            driver_msg = context.bot.send_message(
                chat_id=driver.chat_id,
                text=time_order_accepted(order.from_address, timezone.localtime(order.order_time).time()))
            context.bot.send_message(chat_id=order.chat_id_client,
                                     text=order_complete)
            redis_instance().hset(str(driver.chat_id), 'driver_msg', driver_msg.message_id)
        else:
            context.bot.send_message(chat_id=query.from_user.id, text=add_many_auto_text)

    else:
        order.driver = driver
        order.save()
        markup = inline_spot_keyboard(order.latitude, order.longitude, pk=order.id)
        query.edit_message_text(text=order_info(order))
        query.edit_message_reply_markup(reply_markup=markup)
        report_for_client = client_order_text(driver, vehicle.name, vehicle.licence_plate,
                                              driver.phone_number, order.sum)
        client_msg = redis_instance().hget(str(order.chat_id_client), 'client_msg')
        text_to_client(order, report_for_client, button=inline_reject_order(order.pk), message_id=client_msg)
        redis_instance().hset(str(query.from_user.id), 'driver_msg', query.message.message_id)
        order.status_order, order.accepted_time = Order.IN_PROGRESS, timezone.localtime()
        order.save()
        if order.chat_id_client:
            lat, long = get_location_from_db(vehicle.licence_plate)
            bot.send_message(chat_id=order.chat_id_client, text=order_customer_text)
            message = bot.sendLocation(order.chat_id_client, latitude=lat, longitude=long, live_period=1800)
            send_map_to_client.delay(order.id, vehicle.licence_plate, message.message_id, message.chat_id)


def cash_order(update, query, order, sum, default=True):
    query.edit_message_reply_markup(reply_markup=None)
    bot.send_message(text=driver_complete_text(sum) if default else driver_duty(sum, client=False),
                     chat_id=order.driver.chat_id)
    bot.send_message(text=driver_complete_text(sum) if default else driver_duty(sum),
                     chat_id=order.chat_id_client)
    text_to_client(order, complete_order_text, button=inline_comment_for_client())
    order.status_order = Order.COMPLETED
    order.partner = order.driver.partner
    order.save()
    fleet_order(order)
    redis_instance().delete(str(update.effective_chat.id))


def second_payment_portmone(response, first_payment, total):
    if isinstance(response, list):
        report_for_client = f'{return_money_from_system} {sum_return}{abs(total)}{first_payment.currency}'
    else:
        report_for_client = f'{bad_response_portmone}{first_payment.provider_payment_charge_id}\n' \
                            f'{sum_return}{abs(total)}{first_payment.currency}'
    return report_for_client


def handle_order(update, context):
    query = update.callback_query
    data = query.data.split()
    chat_id = str(update.effective_chat.id)
    driver = Driver.get_by_chat_id(chat_id=query.from_user.id)
    order = Order.objects.filter(pk=int(data[1])).first()
    if data[0] == 'Reject_order':
        query.edit_message_text(client_decline)
        client_msg = redis_instance().hget(order.chat_id_client, 'client_msg')
        context.bot.edit_message_reply_markup(chat_id=order.chat_id_client,
                                              message_id=client_msg,
                                              )
        fleet_order(order, FleetOrder.DRIVER_CANCEL)
        text_to_client(order, driver_cancel)
        order.status_order, order.driver, order.checked = Order.WAITING, None, False
        order.save()
    elif data[0] == "Client_on_site":
        try:
            context.bot.delete_message(order.chat_id_client, message_id=data[2])
            context.bot.delete_message(order.chat_id_client, message_id=int(data[2])-1)
        except BadRequest as e:
            get_logger().error(e)
        query.edit_message_text(order_info(order))

        reply_markup = inline_finish_order(order.to_latitude,
                                           order.to_longitude,
                                           pk=order.id)
        query.edit_message_reply_markup(reply_markup=reply_markup)
    elif data[0] == "End_trip":
        reply_markup = inline_route_keyboard(order.id)
        query.edit_message_text(text=route_trip_text)
        query.edit_message_reply_markup(reply_markup=reply_markup)
    elif data[0] in ("Along_the_route", "Off_route"):
        redis_instance().hset(chat_id, 'recheck', data[0])
        query.edit_message_text(order_info(order))
        query.edit_message_reply_markup(reply_markup=inline_repeat_keyboard(order.id))
    elif data[0] == "Accept":
        if redis_instance().hget(chat_id, 'recheck') == "Off_route":
            query.edit_message_text(text=calc_price_text)
            start_route = redis_instance().hget(chat_id, 'start_route')
            s, e = int(start_route), int(timezone.localtime().timestamp())
            vehicle = check_vehicle(driver)
            get_distance_trip.delay(data[1], query.message.message_id, s, e, vehicle.gps_id)
        else:
            if redis_instance().hexists(chat_id, 'delivary_price_duty'):
                bank = UserBank.get_duty(chat_id)
                bank.duty = 0
                bank.save()
            if order.payment_method == price_inline_buttons[4].split()[1]:
                cash_order(update, query, order, order.sum)
            else:
                query.edit_message_reply_markup(reply_markup=None)
                text_to_client(order, complete_order_text, button=inline_comment_for_client())
                bot.send_message(text=trip_paymented, chat_id=order.driver.chat_id)
                order.status_order = Order.COMPLETED
                order.partner = order.driver.partner
                order.save()
                fleet_order(order)
                redis_instance().delete(str(update.effective_chat.id))
    elif data[0] == 'Second_cash_payment':
        if order.payment_method == price_inline_buttons[4].split()[1]:   # first cash second cash
            cash_order(update, query, order, order.sum)
        else:
            first_payment = ReportTelegramPayments.objects.get(order=order.pk).first()  # first card second cash
            total = order.sum - first_payment.total_amount
            if total >= 0:
                cash_order(update, query, order, total, default=False)
            else:
                query.edit_message_reply_markup(reply_markup=None)
                portmone = Portmone()
                first_payment.total_amount += total
                response = portmone.return_amount(abs(total), first_payment.provider_payment_charge_id, return_money)
                report_for_client = second_payment_portmone(response, first_payment, total)
                bot.send_message(text=trip_paymented,
                                 chat_id=order.driver.chat_id)
                bot.send_message(text=report_for_client,
                                 chat_id=order.chat_id_client)
                first_payment.save()
                text_to_client(order, complete_order_text, button=inline_comment_for_client())
                order.status_order = Order.COMPLETED
                order.partner = order.driver.partner
                order.save()
                fleet_order(order)
                redis_instance().delete(str(update.effective_chat.id))
    elif data[0] == 'Second_card_payment':
        query.edit_message_reply_markup(reply_markup=None)
        if order.payment_method == price_inline_buttons[5].split()[1]:   # first card second card
            first_payment = ReportTelegramPayments.objects.get(order=order.pk)
            total = order.sum - first_payment.total_amount
            if total >= 0:
                if total == 0:
                    order.status_order = Order.COMPLETED
                    order.partner = order.driver.partner
                    order.save()
                    fleet_order(order)
                    context.bot.send_message(chat_id=order.driver.chat_id, text=trip_paymented)
                    text_to_client(order, complete_order_text, button=inline_comment_for_client())
                    redis_instance().delete(chat_id)
                else:
                    payment_request(order.chat_id_client,
                                    f'{order.pk} {query.message.message_id}',
                                    total)
            else:
                portmone = Portmone()
                response = portmone.return_amount(abs(total), first_payment.provider_payment_charge_id, return_money)
                report_for_client = second_payment_portmone(response, first_payment, total)
                context.bot.send_message(chat_id=order.chat_id_client, text=report_for_client)
                context.bot.send_message(chat_id=order.driver.chat_id, text=trip_paymented)
                text_to_client(order, complete_order_text, button=inline_comment_for_client())
                first_payment.total_amount += total
                first_payment.save()
                order.status_order = Order.COMPLETED
                order.partner = order.driver.partner
                order.save()
                fleet_order(order)
                redis_instance().delete(chat_id)
        else:                                       # first cash second card
            payment_request(order.chat_id_client,
                            order.chat_id_client,
                            f'{order.pk} {query.message.message_id}',
                            order.sum)


def payment_duty(update, context):
    chat_id = str(update.effective_chat.id)
    duty = UserBank.get_duty(chat_id)
    payment_request(chat_id,
                    chat_id,
                    chat_id,
                    duty.duty)
    redis_instance().hset(chat_id, 'duty', 1)


def precheckout_callback(update, context):
    query = update.pre_checkout_query
    chat_id = query.from_user.id
    redis_instance().hset(chat_id, 'payload_data', query.invoice_payload)
    query.answer(ok=True)


def create_report_payment(successful_payment, order=None):
    report_payment_data = {
        'provider_payment_charge_id': successful_payment.provider_payment_charge_id,
        'telegram_payment_charge_id': successful_payment.telegram_payment_charge_id,
        'currency': successful_payment.currency,
        'total_amount': successful_payment.total_amount / 100,
    }

    if order is not None:
        report_payment_data['order'] = order

    report = ReportTelegramPayments.objects.create(**report_payment_data)
    return report


def successful_payment(update, context):
    chat_id = str(update.message.chat.id)
    personal_order = redis_instance().hget(chat_id, 'personal_flag')
    successful_payment = update.message.successful_payment
    payload_data = redis_instance().hget(chat_id, 'payload_data')
    list_payload = payload_data.split()
    order = Order.objects.filter(chat_id_client=chat_id, status_order=Order.IN_PROGRESS).last()
    if redis_instance().hexists(chat_id, 'duty'):
        bank = UserBank.get_duty(chat_id)
        bank.duty = 0
        bank.save()
        context.bot.send_message(chat_id=chat_id, text=success_duty, reply_markup=back_to_main_menu())
        order = Order.objects.filter(chat_id_client=chat_id, status_order=Order.CANCELED, type_order=Order.STANDARD_TYPE,
                                     payment_method=price_inline_buttons[4].split()[1]).last()
        create_report_payment(successful_payment, order)
    if order:
        if order.type_order == Order.STANDARD_TYPE:
            fleet_order(order)
            context.bot.send_message(chat_id=order.driver.chat_id, text=trip_paymented)
            text_to_client(order, complete_order_text, button=inline_comment_for_client())
        elif order.type_order == Order.PERSONAL_TYPE:
            update_hours = int(redis_instance().hget(chat_id, 'hours'))
            order.update(
                payment_hours=F('payment_hours') + update_hours,
                sum=F('sum') + int(list_payload[2])
            )
            context.bot.send_message(chat_id=chat_id,
                                     text=update_hours_text(update_hours))
            try:
                msg = redis_instance().hget(str(order.first().driver.chat_id), "driver_msg")
                context.bot.delete_message(chat_id=order.first().driver.chat_id, message_id=msg)
            except BadRequest as e:
                get_logger().error(e)
            driver_msg = context.bot.send_message(chat_id=order.first().driver.chat_id,
                                                  text=update_hours_driver_text(update_hours))
            redis_instance().hset(str(order.first().driver.chat_id), "driver_msg", driver_msg.message_id)
            create_report_payment(successful_payment, order)
    elif personal_order:
        save_location_to_redis(chat_id)
        user_data = redis_instance().hgetall(chat_id)
        client = Client.get_by_chat_id(chat_id)
        data = {'order_time': datetime.fromisoformat(user_data['time_order']),
                'chat_id_client': chat_id,
                'phone_number': client.phone_number,
                'from_address': user_data['from_address'],
                'latitude': user_data['latitude'],
                'longitude': user_data['longitude'],
                'payment_hours': user_data['hours'],
                'type_order': Order.PERSONAL_TYPE,
                'status_order': Order.ON_TIME,
                'sum': int(list_payload[2])
                }
        if user_data.get('info'):
            data['info'] = user_data['info']
        order = Order.objects.create(**data)
        message = bot.send_message(chat_id=chat_id,
                                   text=client_personal_info(order),
                                   reply_markup=inline_reject_order(order.pk))
        redis_instance().hset(chat_id, 'client_msg', message.message_id)
        create_report_payment(successful_payment, order)
    else:
        order_data = redis_instance().hgetall(f'{chat_id}_')
        order_data['sum'] = int(order_data['sum'])
        order_time = redis_instance().hget(chat_id, 'time_order')
        order_data['order_time'] = datetime.fromisoformat(order_time)
        redis_instance().delete(f'{chat_id}_')
        report = create_report_payment(successful_payment)
        order_create_task.delay(order_data, report.pk)










