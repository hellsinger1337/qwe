from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from database import SessionLocal
from models import Employee, Organization, BotMessage, OrganizationMessage
from aiogram import Bot
import yaml
import logging
import asyncio
from analyze_points import analyze_points

logger = logging.getLogger(__name__)

def load_config(config_path='config.yaml'):
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

config = load_config()

async def send_survey(org_id):
    logger.info(f"Запуск задачи send_survey для организации ID {org_id}.")
    session = SessionLocal()
    try:
        organization = session.query(Organization).filter(Organization.id==org_id).first()
        if not organization:
            logger.error(f"Организация {org_id} не найдена")
            return
        first_msg = session.query(OrganizationMessage).filter(OrganizationMessage.organization_id==org_id).order_by(OrganizationMessage.order).first()
        if not first_msg:
            logger.info("Нет сообщений для отправки")
            return

        employees = session.query(Employee).filter(Employee.organization_id==org_id).all()
        bot = Bot(token=organization.telegram_bot_token)
        for emp in employees:
            session.query(BotMessage).filter(BotMessage.employee_id==emp.id).delete()
            session.commit()
            await bot.send_message(chat_id=emp.telegram_id, text=first_msg.message_text)
            bm = BotMessage(employee_id=emp.id, message_text=first_msg.message_text)
            session.add(bm)
            session.commit()
    except Exception as e:
        logger.error(f"Ошибка при отправке опроса для org {org_id}: {e}")
    finally:
        session.close()

def run_analyze_points(org_id, days):
    logger.info(f"Запуск analyze_points для org_id {org_id}")
    try:
        analyze_points(org_id=org_id, days=days)
    except Exception as e:
        logger.error(f"Ошибка analyze_points для org {org_id}: {e}")

def start_scheduler():
    scheduler = AsyncIOScheduler()
    session = SessionLocal()
    try:
        orgs = session.query(Organization).all()
        for org in orgs:
            if org.survey_frequency == 'weekly':
                survey_trigger = CronTrigger(day_of_week=org.survey_day_of_week, hour=org.survey_hour, minute=org.survey_minute)
            else:
                # monthly
                survey_trigger = CronTrigger(day=org.survey_day_of_week, hour=org.survey_hour, minute=org.survey_minute)

            scheduler.add_job(send_survey, survey_trigger, args=[org.id])

            days=7
            if org.report_frequency == 'weekly':
                report_trigger = CronTrigger(day_of_week=org.report_day_of_week, hour=org.report_hour, minute=org.report_minute)
            else:
                days=30
                report_trigger = CronTrigger(day=org.report_day_of_week, hour=org.report_hour, minute=org.report_minute)

            scheduler.add_job(run_analyze_points, report_trigger, args=[org.id, days])

        scheduler.start()
        return scheduler
    except Exception as e:
        logger.error(f"Ошибка при инициализации планировщика: {e}")
    finally:
        session.close()