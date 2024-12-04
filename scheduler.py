
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from database import SessionLocal
from models import Employee, Organization,BotMessage
from telegram import Bot
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
    """
    Отправляет опросное сообщение сотрудникам конкретной организации.
    """
    logger.info(f"Запуск задачи send_survey для организации ID {org_id}.")
    session = SessionLocal()
    try:
        organization = session.query(Organization).filter(Organization.id == org_id).first()
        if not organization:
            logger.error(f'Организация с ID "{org_id}" не найдена.')
            return

        employees = session.query(Employee).filter(Employee.organization_id == org_id).all()
        bot = Bot(token=config['telegram_bot_token'])
        survey_text = config['messages'][0]

        for employee in employees:
            try:
                session.query(BotMessage).filter(BotMessage.employee_id == employee.id).delete()
                session.commit()


                await bot.send_message(chat_id=employee.telegram_id, text=survey_text)
                logger.info(f"Отправлено опросное сообщение сотруднику {employee.name} (Telegram ID: {employee.telegram_id}).")

                bot_message = BotMessage(
                    employee_id=employee.id,
                    message_text=survey_text
                )
                session.add(bot_message)
                session.commit()

            except Exception as e:
                logger.error(f"Не удалось отправить сообщение сотруднику {employee.name} (Telegram ID: {employee.telegram_id}): {e}")

    except Exception as e:
        logger.error(f"Ошибка при отправке опроса для организации ID {org_id}: {e}")
    finally:
        session.close()
        logger.info(f"Задача send_survey для организации ID {org_id} завершена.")

def run_analyze_points(org_id, days=7):
    """
    Запускает анализ позитивных и негативных поинтов для организации.
    """
    logger.info(f"Запуск analyze_points для организации ID {org_id}.")
    try:
        analyze_points(org_id=org_id, days=days)
        logger.info(f"analyze_points для организации ID {org_id} завершен.")
    except Exception as e:
        logger.error(f"Ошибка при запуске analyze_points для организации ID {org_id}: {e}")

def start_scheduler():
    """
    Инициализирует и запускает планировщик задач на основе настроек из базы данных.
    """
    scheduler = AsyncIOScheduler()
    session = SessionLocal()
    try:
        organizations = session.query(Organization).all()
        for org in organizations:
            
            survey_trigger = CronTrigger(
                day_of_week=org.survey_day_of_week,
                hour=org.survey_hour,
                minute=org.survey_minute
            )
            scheduler.add_job(send_survey, survey_trigger, args=[org.id], name=f"send_survey_org_{org.id}")

            
            report_trigger = CronTrigger(
                day_of_week=org.report_day_of_week,
                hour=org.report_hour,
                minute=org.report_minute
            )
            scheduler.add_job(run_analyze_points, report_trigger, args=[org.id], name=f"run_analyze_points_org_{org.id}")
            
            logger.info(f"Задачи для организации '{org.name}' (ID: {org.id}) добавлены в планировщик.")
    except Exception as e:
        logger.error(f"Ошибка при инициализации планировщика: {e}")
    finally:
        session.close()
    
    scheduler.start()
    logger.info("Планировщик задач запущен.")
    return scheduler