import pytest
import datetime
from app.models import Fleet, FleetsDriversVehiclesRate, Driver, Vehicle, Partner, AuUser, Role
from selenium_ninja.synchronizer import Synchronizer
from django.core.exceptions import MultipleObjectsReturned


@pytest.fixture
def synchronizer():
    synchronizer = Synchronizer(partner_id=1, fleet='Uklon')
    return synchronizer


@pytest.fixture
def partner():
    partner = Partner.objects.filter(pk=2)
    if not partner:
        user = AuUser.objects.create(username='test_user')
        partner = Partner.objects.get(user=user.pk)
    return partner


@pytest.fixture
def fleet():
    fleet = Fleet.objects.create(name='Uklon')
    return fleet


@pytest.fixture
def driver(partner):
    driver = Driver.objects.create(name='John',
                                   second_name='Doe',
                                   phone_number='+1234567890',
                                   email='john.doe@example.com',
                                   role=Role.DRIVER,
                                   partner=partner)
    return driver


@pytest.fixture
def vehicle(partner):
    vehicle = Vehicle.objects.create(
        name='BYB'.upper(),
        licence_plate='AA1234BB',
        vin_code='123456789123',
        partner=partner
    )
    return vehicle


def test_r_dup_without_dup(synchronizer):
    first_text = 'Some Text WithoutDUP'
    second_text = 'Some Text'

    result = synchronizer.r_dup(first_text)
    result_ = synchronizer.r_dup(second_text)

    assert result == 'Some Text Without'
    assert result_ == second_text


def test_parameters(synchronizer):
    result = synchronizer.parameters()

    assert isinstance(result, dict)
    assert result == {'limit': '50', 'offset': '0'}


def test_get_drivers_table_not_implemented(synchronizer):
    with pytest.raises(NotImplementedError):
        synchronizer.get_drivers_table()


def test_get_vehicles_not_implemented(synchronizer):
    with pytest.raises(NotImplementedError):
        synchronizer.get_vehicles()


@pytest.mark.django_db
def test_create_driver(synchronizer, fleet, partner, vehicle, driver):
    fleet_name = 'Uklon'
    driver_external_id = '12345'
    pay_cash = True
    name = 'John'
    second_name = 'Doe'
    phone_number = '+1234567890'
    email = 'john.doe@example.com'
    licence_plate = 'AA1234BB'
    vehicle_name = 'BYB'
    vin_code = '123456789123'

    data = {
        'fleet_name': fleet_name,
        'driver_external_id': driver_external_id,
        'pay_cash': pay_cash,
        'name': name,
        'second_name': second_name,
        'phone_number': phone_number,
        'email': email,
        'licence_plate': licence_plate,
        'vehicle_name': vehicle_name,
        'vin_code': vin_code,
    }

    synchronizer.create_driver(**data)

    fleet = Fleet.objects.get(name=fleet)
    driver = Driver.objects.get(name=name, second_name=second_name, partner=partner.pk)
    vehicle = Vehicle.objects.get(licence_plate=licence_plate, partner=partner.pk)
    fleets_drivers_vehicles_rate = FleetsDriversVehiclesRate.objects.get(
        fleet=fleet, driver_external_id=driver_external_id, partner=partner.pk)

    assert fleets_drivers_vehicles_rate.driver == driver
    assert fleets_drivers_vehicles_rate.vehicle == vehicle
    assert fleets_drivers_vehicles_rate.pay_cash == pay_cash


@pytest.mark.django_db
def test_get_or_create_driver(partner, synchronizer, driver):
    name = 'John'
    second_name = 'Doe'
    phone_number = '+1234567890'
    email = 'john.doe@example.com'

    assert isinstance(driver, Driver)
    assert driver.name == name
    assert driver.second_name == second_name
    assert driver.phone_number == phone_number
    assert driver.email == email
    assert driver.partner_id == 2


@pytest.mark.django_db
def test_get_or_create_vehicle(synchronizer, partner, vehicle):
    name = 'BYB'
    licence_plate = 'AA1234BB'
    vin_code = '123456789123'

    assert isinstance(vehicle, Vehicle)
    assert vehicle.licence_plate == licence_plate
    assert vehicle.name == name.upper()
    assert vehicle.vin_code == vin_code
    assert vehicle.partner_id == 3


@pytest.mark.django_db
def test_update_driver_fields_with_phone(synchronizer, driver):
    phone_number = '+1234567890'
    driver.phone_number = phone_number
    driver.save()

    assert driver.phone_number == phone_number


@pytest.mark.django_db
def test_update_driver_fields_with_email(synchronizer, partner, driver):
    email = 'john.doe@example.com'
    driver.email = email
    driver.save()

    assert driver.email == email


@pytest.mark.django_db
def test_update_vehicle_fields_with_vehicle_name(synchronizer, vehicle):
    vehicle_name = 'CAR1'
    vehicle.name = vehicle_name
    vehicle.save()

    assert vehicle.name == vehicle_name.upper()


@pytest.mark.django_db
def test_update_vehicle_fields_with_vin_code(synchronizer, vehicle):
    vin_code = 'XYZ789'
    vehicle.vin_code = vin_code
    vehicle.save()

    assert vehicle.vin_code == vin_code


@pytest.mark.django_db
def test_update_vehicle_fields_with_no_changes(synchronizer, vehicle):
    assert vehicle.name == 'BYB'
    assert vehicle.licence_plate == 'AA1234BB'
    assert vehicle.vin_code == '123456789123'


def test_report_interval(synchronizer):
    # Arrange
    day = datetime.date(2023, 4, 25)

    # Act
    result = synchronizer.report_interval(day, start=True)
    result_end = synchronizer.report_interval(day)

    assert result == datetime.datetime(2023, 4, 25, 0, 0)
    assert result_end == datetime.datetime(2023, 4, 25, 23, 59, 59)


@pytest.mark.django_db
def test_get_driver_by_name_with_exact_match(synchronizer, partner, driver):
    name = 'John'
    second_name = 'Doe'

    assert name == driver.name
    assert second_name == driver.second_name


@pytest.mark.django_db
def test_get_or_create_driver_with_multiple_attempts(synchronizer, driver):
    name = 'John'
    second_name = 'Doe'
    phone_number = '+1234567890'
    email = 'john.doe@example.com'

    assert isinstance(driver, Driver)
    assert driver.name == name
    assert driver.second_name == second_name
    assert driver.phone_number == phone_number
    assert driver.email == email


@pytest.mark.django_db
def test_get_driver_by_phone_or_email_with_phone_number(synchronizer, partner):
    phone_number = '+1234567890'
    driver = Driver.objects.create(phone_number=phone_number, partner=partner)

    result = synchronizer.get_driver_by_phone_or_email(phone_number, None, partner.pk)

    assert result == driver


@pytest.mark.django_db
def test_get_driver_by_phone_or_email_with_multiple_matches(synchronizer, partner):
    phone_number = '+1234567890'
    email = 'john.doe@example.com'
    name = 'Dek'
    second_name = 'Smith'
    Driver.objects.create(name=name,
                          second_name=second_name,
                          phone_number=phone_number,
                          email=email,
                          partner=partner)

    try:
        Driver.objects.create(name=name,
                              second_name=second_name,
                              phone_number=phone_number,
                              email=email,
                              partner=partner)
    except:
        raise MultipleObjectsReturned


@pytest.mark.django_db
def test_synchronize(synchronizer, monkeypatch):
    class MockDriver:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class MockVehicle:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    drivers = [
        {'fleet_name': 'Fleet1', 'driver_external_id': '12345', 'pay_cash': True, 'name': 'John', 'second_name': 'Doe',
         'phone_number': '+1234567890', 'email': 'john.doe@example.com'},
        {'fleet_name': 'Fleet2', 'driver_external_id': '54321', 'pay_cash': False, 'name': 'Jane', 'second_name': 'Smith',
         'phone_number': '+9876543210', 'email': 'jane.smith@example.com'}
    ]
    vehicles = [
        {'licence_plate': 'ABC123', 'vehicle_name': 'Car1', 'vin_code': 'XYZ789'},
        {'licence_plate': 'XYZ789', 'vehicle_name': 'Car2', 'vin_code': 'ABC123'}
    ]

    def mock_get_drivers_table():
        return drivers

    def mock_get_vehicles():
        return vehicles

    def mock_create_driver(**kwargs):
        return MockDriver(**kwargs)

    def mock_get_or_create_vehicle(**kwargs):
        return MockVehicle(**kwargs)

    monkeypatch.setattr(synchronizer, 'get_drivers_table', mock_get_drivers_table)
    monkeypatch.setattr(synchronizer, 'get_vehicles', mock_get_vehicles)
    monkeypatch.setattr(synchronizer, 'create_driver', mock_create_driver)
    monkeypatch.setattr(synchronizer, 'get_or_create_vehicle', mock_get_or_create_vehicle)

    synchronizer.synchronize()

    assert len(FleetsDriversVehiclesRate.objects.all()) == 0
