import datetime
import argparse
import openai
import os
from email.message import EmailMessage
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import SessionLocal
from models import PositivePoint, NegativePoint, Organization, Response, Employee
import yaml
import pandas as pd
import smtplib
import logging
import re
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def load_config(config_path='config.yaml'):
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)
        
config = load_config()
openai.api_key = config['openai']['api_key']

def send_to_gpt4(positive_text, negative_text, activity):
    prompt = f"""
Привет!

У меня есть анализ позитивных и негативных моментов, высказанных сотрудниками за последнюю неделю. Организация занимается следующей деятельностью: {activity}.

Пожалуйста, сформируй ответ в формате JSON с тремя секциями: "positive", "negative" и "main", в каждой из которых не более 5 аспектов. Каждый аспект должен содержать следующие поля: "aspect" (название аспекта), "count" (количество встретившихся раз) и "comment" (краткий комментарий).

Учти, что похожие поинты ты должен соединить, то есть например 3 раза встретившийся поинт хороший коллектив и 2 раза встретившийся поинт приятные коллеги -- это 5 раз встретившийся поин хороший коллектив!

Ты сначала получаешь новый список поинтов, объединив похожие. Потом сортируешь от самых часто встречающихся к самым редко встречающимся и выбираешь первые 5 из списков! 

В секции "main" должны быть основные негативные моменты основанные на деятельности

Используй следующие данные:

**Позитивные Поинты:**
{positive_text}

**Негативные Поинты:**
{negative_text}

Спасибо!
"""
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "Ты помощник, который формирует ответ в формате JSON."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1500,
            temperature=0.3,
        )
        return response['choices'][0]['message']['content'].strip()
    except Exception as e:
        print(f'Ошибка при обращении к GPT-4 API: {e}')
        return None

def parse_gpt4_response(response_text):
    try:
        response_json = json.loads(response_text)
        
        # Получаем данные
        top_positive_data = response_json.get('positive', [])
        top_negative_data = response_json.get('negative', [])
        main_aspects_data = response_json.get('main', [])
        
        # Сортировка по полю 'count' во всех списках
        top_positive_data = sorted(top_positive_data, key=lambda x: x.get('count', 0), reverse=True)
        top_negative_data = sorted(top_negative_data, key=lambda x: x.get('count', 0), reverse=True)
        main_aspects_data = sorted(main_aspects_data, key=lambda x: x.get('count', 0), reverse=True)
        
        return top_positive_data, top_negative_data, main_aspects_data
    
    except json.JSONDecodeError as e:
        logger.error(f'Ошибка при разборе JSON ответа от GPT-4: {e}')
        return [], [], []

def send_email(org, excel_file_path, brief_excel_file_path):
    smtp_config = config['smtp']
    msg = EmailMessage()
    msg['Subject'] = f"Еженедельный отчёт для {org.name}"
    msg['From'] = smtp_config['from_email']
    msg['To'] = ', '.join([email.email_address for email in org.emails])
    msg.set_content(f"Здравствуйте,\n\nВо вложении вы найдёте еженедельный отчёт для организации {org.name}.\n\nС уважением,\nВаш бот.")
    try:
        with open(excel_file_path, 'rb') as f:
            file_data = f.read()
            file_name = os.path.basename(excel_file_path)
            msg.add_attachment(file_data, maintype='application', subtype='vnd.openxmlformats-officedocument.spreadsheetml.sheet', filename=file_name)
    except Exception as e:
        logger.error(f'Ошибка при прикреплении Excel-файла: {e}')
        return
    try:
        with open(brief_excel_file_path, 'rb') as f:
            file_data = f.read()
            file_name = os.path.basename(brief_excel_file_path)
            msg.add_attachment(file_data, maintype='application', subtype='vnd.openxmlformats-officedocument.spreadsheetml.sheet', filename=file_name)
    except Exception as e:
        logger.error(f'Ошибка при прикреплении краткого Excel-файла: {e}')
        return
    try:
        with smtplib.SMTP_SSL(smtp_config['server'], smtp_config['port']) as server:
            server.login(smtp_config['username'], smtp_config['password'])
            server.send_message(msg)
            server.quit()
            logger.info(f'Письмо успешно отправлено всем email-адресам организации {org.name}.')
    except smtplib.SMTPAuthenticationError:
        logger.error('Ошибка аутентификации: Проверьте ваш логин и пароль приложения.')
    except smtplib.SMTPConnectError:
        logger.error('Ошибка соединения: Не удалось подключиться к SMTP-серверу.')
    except smtplib.SMTPException as e:
        logger.error(f'SMTP ошибка: {e}')
    except Exception as e:
        logger.error(f'Неизвестная ошибка при отправке письма: {e}')

def generate_excel_report(org_id, start_date, end_date, top_positive_counts, top_negative_counts):
    session = SessionLocal()
    try:
        # Извлекаем все ответы сотрудников за указанный период
        responses = (
            session.query(Response)
            .join(Response.employee)
            .filter(
                Response.timestamp >= start_date,
                Response.timestamp <= end_date,
                Employee.organization_id == org_id
            )
            .all()
        )
        
        if not responses:
            logger.info("Нет данных для формирования Excel-отчёта.")
            return None
        
        data = []
        for response in responses:
            # Используем вопрос из базы данных
            question = response.question  # Вопрос теперь извлекается из поля question в таблице Response
            data.append({
                'Сотрудник': response.employee.name,
                'Вопрос': question,
                'Текст ответа': response.response_text,
                'Дата и время': response.timestamp.strftime('%Y-%m-%d %H:%M:%S')
            })
        
        df_responses = pd.DataFrame(data)
        df_top_positives = pd.DataFrame(top_positive_counts, columns=['Позитивный Поинт', 'Количество'])
        df_top_negatives = pd.DataFrame(top_negative_counts, columns=['Негативный Поинт', 'Количество'])
        
        excel_file_path = f'employee_reports_org_{org_id}.xlsx'
        
        with pd.ExcelWriter(excel_file_path) as writer:
            df_responses.to_excel(writer, sheet_name='Ответы сотрудников', index=False)
            df_top_positives.to_excel(writer, sheet_name='Топ-5 Позитивных', index=False)
            df_top_negatives.to_excel(writer, sheet_name='Топ-5 Негативных', index=False)
        
        logger.info(f'Excel-отчёт успешно сформирован и сохранен в "{excel_file_path}".')
        return excel_file_path
    except Exception as e:
        logger.error(f'Ошибка при формировании Excel-отчёта: {e}')
        return None
    finally:
        session.close()


def generate_brief_excel_report(org_id, top_positive_data, top_negative_data, main_aspects_data):
    brief_excel_file_path = f'brief_report_org_{org_id}.xlsx'
    try:
        with pd.ExcelWriter(brief_excel_file_path) as writer:
            data_written = False
            if top_positive_data:
                df_top_positives = pd.DataFrame(top_positive_data)
                df_top_positives.to_excel(writer, sheet_name='Топ-5 Позитивных', index=False)
                data_written = True
            else:
                logger.info('Нет данных для Топ-5 Позитивных Аспектов.')
            if top_negative_data:
                df_top_negatives = pd.DataFrame(top_negative_data)
                df_top_negatives.to_excel(writer, sheet_name='Топ-5 Негативных', index=False)
                data_written = True
            else:
                logger.info('Нет данных для Топ-5 Негативных Аспектов.')
            if main_aspects_data:
                df_main_aspects = pd.DataFrame(main_aspects_data)
                df_main_aspects.to_excel(writer, sheet_name='Главные Аспекты', index=False)
                data_written = True
            else:
                logger.info('Нет данных для Главных Аспектов.')
            if not data_written:
                df_empty = pd.DataFrame({'Сообщение': ['Нет данных для отображения.']})
                df_empty.to_excel(writer, sheet_name='Отчёт отсутствует', index=False)
        logger.info(f'Краткий Excel-отчёт успешно сформирован и сохранен в "{brief_excel_file_path}".')
        return brief_excel_file_path
    except Exception as e:
        logger.error(f'Ошибка при формировании краткого Excel-отчёта: {e}')
        return None

def analyze_points(org_id, days=7):
    end_date = datetime.datetime.utcnow()
    start_date = end_date - datetime.timedelta(days=days)
    session = SessionLocal()
    try:
        organization = session.query(Organization).filter(Organization.id == org_id).first()
        if not organization:
            logger.error(f'Ошибка: Организация с ID "{org_id}" не найдена в базе данных.')
            return
        activity = organization.activity
        positive_counts = (
            session.query(
                PositivePoint.point_text,
                func.count(PositivePoint.id).label('count')
            )
            .join(PositivePoint.response)
            .join(Response.employee)
            .filter(
                Response.timestamp >= start_date,
                Response.timestamp <= end_date,
                Employee.organization_id == org_id
            )
            .group_by(PositivePoint.point_text)
            .order_by(func.count(PositivePoint.id).desc())
            .all()
        )
        negative_counts = (
            session.query(
                NegativePoint.point_text,
                func.count(NegativePoint.id).label('count')
            )
            .join(NegativePoint.response)
            .join(Response.employee)
            .filter(
                Response.timestamp >= start_date,
                Response.timestamp <= end_date,
                Employee.organization_id == org_id
            )
            .group_by(NegativePoint.point_text)
            .order_by(func.count(NegativePoint.id).desc())
            .all()
        )
        if not positive_counts and not negative_counts:
            logger.info("Нет данных для анализа за указанный период и организацию.")
            return
        positive_text = ""
        for point_text, count in positive_counts:
            positive_text += f'- {point_text}: {count}\n'
        negative_text = ""
        for point_text, count in negative_counts:
            negative_text += f'- {point_text}: {count}\n'
        logger.info("Отправка данных в GPT-4 для формирования отчета...")
        top_positive_counts = positive_counts[:5]
        top_negative_counts = negative_counts[:5]
        gpt_response = send_to_gpt4(positive_text, negative_text, activity)
        if gpt_response:
            top_positive_data, top_negative_data, main_aspects_data = parse_gpt4_response(gpt_response)
        else:
            logger.error('Не удалось получить ответ от GPT-4.')
            return
        excel_file_path = generate_excel_report(org_id, start_date, end_date, top_positive_counts, top_negative_counts)
        if not excel_file_path:
            logger.error('Не удалось сформировать Excel-отчет.')
            return
        brief_excel_file_path = generate_brief_excel_report(org_id, top_positive_data, top_negative_data, main_aspects_data)
        if not brief_excel_file_path:
            logger.error('Не удалось сформировать краткий Excel-отчет.')
            return
        send_email(org=organization, excel_file_path=excel_file_path, brief_excel_file_path=brief_excel_file_path)
    except Exception as e:
        logger.error(f'Произошла ошибка: {e}')
    finally:
        session.close()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Анализ позитивных и негативных поинтов за указанный период и организацию, формирование отчета и отправка email.')
    parser.add_argument('--org_id', type=int, required=True, help='Идентификатор организации для анализа.')
    parser.add_argument('--days', type=int, default=7, help='Количество дней для анализа (по умолчанию: 7)')
    args = parser.parse_args()
    analyze_points(org_id=args.org_id, days=args.days)