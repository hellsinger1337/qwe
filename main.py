import asyncio
import logging
from sqlalchemy.orm import sessionmaker
from database import engine
from models import Base, Organization, Email, OrganizationMessage
from handlers import create_router
from aiogram import Dispatcher
from aiogram.client.bot import Bot, DefaultBotProperties
import sys
from scheduler import start_scheduler

def load_config(config_path='config.yaml'):
    import yaml
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def setup_organization():
    config = load_config()
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    organizations_data = config.get('organizations', [])

    for org_data in organizations_data:
        org_name = org_data.get('name')
        org_activity = org_data.get('activity')
        org_emails = org_data.get('emails', [])
        telegram_bot_token = org_data.get('telegram_bot_token')
        org_messages = org_data.get('messages', [])

        survey_schedule = org_data.get('survey_schedule', {})
        survey_day_of_week = survey_schedule.get('day_of_week', 1)
        survey_hour = survey_schedule.get('hour', 9)
        survey_minute = survey_schedule.get('minute', 0)
        survey_frequency = survey_schedule.get('frequency', 'weekly')

        report_schedule = org_data.get('report_schedule', {})
        report_day_of_week = report_schedule.get('day_of_week', 2)
        report_hour = report_schedule.get('hour', 17)
        report_minute = report_schedule.get('minute', 0)
        report_frequency = report_schedule.get('frequency', 'weekly')

        if not org_name or not telegram_bot_token:
            continue

        organization = session.query(Organization).filter(Organization.name == org_name).first()
        if organization:
            # обновляем
            organization.activity = org_activity
            organization.survey_day_of_week = survey_day_of_week
            organization.survey_hour = survey_hour
            organization.survey_minute = survey_minute
            organization.survey_frequency = survey_frequency
            organization.report_day_of_week = report_day_of_week
            organization.report_hour = report_hour
            organization.report_minute = report_minute
            organization.report_frequency = report_frequency
            organization.telegram_bot_token = telegram_bot_token
        else:
            # создаем
            organization = Organization(
                name=org_name,
                activity=org_activity,
                survey_day_of_week=survey_day_of_week,
                survey_hour=survey_hour,
                survey_minute=survey_minute,
                survey_frequency=survey_frequency,
                report_day_of_week=report_day_of_week,
                report_hour=report_hour,
                report_minute=report_minute,
                report_frequency=report_frequency,
                telegram_bot_token=telegram_bot_token
            )
            session.add(organization)
            session.commit()

        # emails
        session.query(Email).filter(Email.organization_id == organization.id).delete()
        session.commit()
        for email_address in org_emails:
            email = Email(email_address=email_address, organization=organization)
            session.add(email)
        session.commit()

        # messages
        session.query(OrganizationMessage).filter(OrganizationMessage.organization_id == organization.id).delete()
        session.commit()
        for i, msg_text in enumerate(org_messages):
            om = OrganizationMessage(organization_id=organization.id, message_text=msg_text, order=i)
            session.add(om)
        session.commit()

    session.close()

async def main():
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    setup_organization()
    scheduler = start_scheduler()

    Session = sessionmaker(bind=engine)
    session = Session()
    orgs = session.query(Organization).all()
    session.close()

    tasks = []
    for org in orgs:
        bot = Bot(
            token=org.telegram_bot_token, 
            default=DefaultBotProperties(parse_mode="HTML")
        )
        dp = Dispatcher()
        dp.include_router(create_router())
        
        tasks.append(dp.start_polling(bot, stop_signals=None, org_id=org.id))

    if tasks:
        await asyncio.gather(*tasks)
    else:
        logger.info("Нет организаций для запуска ботов.")

if __name__ == "__main__":
    if sys.platform.startswith('win'):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())