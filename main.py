# main.py
import asyncio
import logging
from sqlalchemy.orm import sessionmaker
from bot import setup_bot
from scheduler import start_scheduler
from database import engine
from models import Base,Organization, Email
import sys
import yaml

def main():
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    logger = logging.getLogger(__name__)  

    scheduler = start_scheduler()

    app = setup_bot()
    
    loop = asyncio.get_event_loop()
    
    loop.create_task(app.run_polling())
    
    try:
        loop.run_forever()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Программа остановлена вручную.")
    finally:
        pending = asyncio.all_tasks(loop=loop)
        for task in pending:
            task.cancel()
        try:
            loop.run_until_complete(asyncio.gather(*pending))
        except Exception:
            pass
        loop.close()

def setup_organization():
    def load_config(config_path='config.yaml'):
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    Base.metadata.create_all(bind=engine)

    config = load_config()
    Session = sessionmaker(bind=engine)
    session = Session()

    org_data = config.get('organization', {})
    org_name = org_data.get('name')
    org_activity = org_data.get('activity')
    org_emails = org_data.get('emails', [])

    survey_schedule = org_data.get('survey_schedule', {})
    survey_day_of_week = survey_schedule.get('day_of_week', 1)
    survey_hour = survey_schedule.get('hour', 9)
    survey_minute = survey_schedule.get('minute', 0)
    survey_frequency = survey_schedule.get('frequency', 'weekly')  # Чтение частоты отчета

    report_schedule = org_data.get('report_schedule', {})
    report_day_of_week = report_schedule.get('day_of_week', 2)
    report_hour = report_schedule.get('hour', 17)
    report_minute = report_schedule.get('minute', 0)
    report_frequency = report_schedule.get('frequency', 'weekly')  # Чтение частоты отчета

    if not org_name:
        return

    organization = session.query(Organization).first()

    if organization:
        organization.name = org_name
        organization.activity = org_activity
        organization.survey_day_of_week = survey_day_of_week
        organization.survey_hour = survey_hour
        organization.survey_minute = survey_minute
        organization.survey_frequency = survey_frequency  # Обновление частоты опроса

        organization.report_day_of_week = report_day_of_week
        organization.report_hour = report_hour
        organization.report_minute = report_minute
        organization.report_frequency = report_frequency  # Обновление частоты отчета
    else:
        organization = Organization(
            name=org_name,
            activity=org_activity,
            survey_day_of_week=survey_day_of_week,
            survey_hour=survey_hour,
            survey_minute=survey_minute,
            survey_frequency=survey_frequency,  # Устанавливаем частоту опроса
            report_day_of_week=report_day_of_week,
            report_hour=report_hour,
            report_minute=report_minute,
            report_frequency=report_frequency  # Устанавливаем частоту отчета
        )
        session.add(organization)


    session.query(Email).filter(Email.organization_id == organization.id).delete()
    session.commit()


    for email_address in org_emails:
        email = Email(email_address=email_address, organization=organization)
        session.add(email)


    session.commit()
    session.close()

if __name__ == "__main__":
    if sys.platform.startswith('win'):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    setup_organization()
    main()
    