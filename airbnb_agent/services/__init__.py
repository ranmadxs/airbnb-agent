"""Servicios de Airbnb Agent"""
from .airbnb_calendar import CalendarService, AirbnbCalendarService
from .database import DatabaseService

# Alias legacy: AirbnbCalendarService == CalendarService (3.0.0 multi-calendario)
AirbnbCalendarService = CalendarService
