import logging
import openai
from aiogram import Router, F, Dispatcher
from aiogram.filters.command import Command
from aiogram.types import Message
from database import SessionLocal
from models import Employee, BotMessage, Response, PositivePoint, NegativePoint, OrganizationMessage
import datetime
import logging

logger = logging.getLogger(__name__)

def create_router():
    router = Router()
    router.message.register(start_command_handler, Command(commands=["start"]))
    router.message.register(message_handler, F.text)
    return router

async def start_command_handler(message: Message, org_id: int):

    session = SessionLocal()
    telegram_id = str(message.from_user.id)
    employee = session.query(Employee).filter(Employee.telegram_id == telegram_id).first()

    if employee:
        if employee.organization_id != org_id:
            employee.organization_id = org_id
            session.commit()
            await message.answer("Ваш аккаунт был перенесен в текущую организацию.")
        else:
            await message.answer("Вы уже зарегистрированы в этой организации.")
        session.close()
        return

    employee = Employee(
        telegram_id=telegram_id,
        name=message.from_user.full_name,
        organization_id=org_id,
    )
    session.add(employee)
    session.commit()
    session.refresh(employee)

    await message.answer(f"Вы успешно зарегистрированы в компании (ID: {org_id}). Спасибо!")
    session.query(BotMessage).filter(BotMessage.employee_id == employee.id).delete()
    session.commit()

    org_messages = session.query(OrganizationMessage).filter(OrganizationMessage.organization_id == org_id).order_by(OrganizationMessage.order).all()
    if org_messages:
        first_msg = org_messages[0]
        await message.answer(first_msg.message_text)
        bot_message = BotMessage(employee_id=employee.id, message_text=first_msg.message_text)
        session.add(bot_message)
        session.commit()
        logger.info(f"Отправлено первое опросное сообщение сотруднику {employee.name}")
    else:
        await message.answer("Пока нет доступных вопросов.")
    session.close()

async def message_handler(message: Message, org_id: int):
    session = SessionLocal()
    telegram_id = str(message.from_user.id)
    employee = session.query(Employee).filter(Employee.telegram_id == telegram_id).first()

    if not employee:
        await message.answer("Вы не зарегистрированы. Введите /start для регистрации.")
        session.close()
        return

    if employee.organization_id != org_id:
        await message.answer("Вы зарегистрированы в другой организации. Введите /start для смены организации.")
        session.close()
        return

    org_messages = session.query(OrganizationMessage).filter(OrganizationMessage.organization_id == org_id).order_by(OrganizationMessage.order).all()
    questions = [m.message_text for m in org_messages]

    last_bot_message = session.query(BotMessage).filter(BotMessage.employee_id==employee.id).order_by(BotMessage.timestamp.desc()).first()

    if not questions:
        await message.answer("Простите, но сейчас у меня нет вопросов для вас!")
        session.close()
        return

    if last_bot_message and last_bot_message.message_text == "Пока вопросы закончились! Спасибо за участие в опросе!":
        await message.answer("Простите, но сейчас у меня нет вопросов для вас!")
        session.close()
        return

    # Определяем текущий и следующий вопрос
    if last_bot_message and last_bot_message.message_text in questions:
        current_index = questions.index(last_bot_message.message_text)
        next_index = current_index + 1
        next_question = questions[next_index] if next_index < len(questions) else None
    else:
        # Если нет последнего вопроса или он не из списка, начинаем с первого
        next_question = questions[0] if questions else None

    # Сохраняем ответ
    response = Response(
        employee_id=employee.id,
        response_text=message.text,
        question=last_bot_message.message_text if last_bot_message else (questions[0] if questions else "")
    )
    session.add(response)
    session.commit()

    # Анализ ответа через OpenAI (код без изменений)
    prompt = (
        "Раздели следующий текст на положительные и отрицательные моменты. "
        "Представь их в виде списка с плюсами и минусами:\n\n"
        f"Вопрос: {response.question}\n"
        f"Ответ: {response.response_text}"
    )
    try:
        completion = await openai.ChatCompletion.acreate(
            model="gpt-4",
            messages=[
                {"role": "system", "content": """
                    Ты — аналитический помощник... (тот же системный промпт)
                """},
                {"role": "user", "content": prompt}
            ],
            temperature=0.5,
            max_tokens=500
        )
        gpt_response = completion.choices[0].message['content']
        pos_points, neg_points = parse_gpt_response(gpt_response)
        for p in pos_points:
            pp = PositivePoint(response_id=response.id, point_text=p)
            session.add(pp)
        for n in neg_points:
            np = NegativePoint(response_id=response.id, point_text=n)
            session.add(np)
        session.commit()
    except Exception as e:
        logger.error(f"Ошибка OpenAI: {e}")
        await message.answer("Произошла ошибка при обработке ответа. Повторите позже.")

    # Переход к следующему вопросу
    if last_bot_message and last_bot_message.message_text in questions:
        # Был предыдущий вопрос
        current_index = questions.index(last_bot_message.message_text)
        next_index = current_index + 1
        if next_index < len(questions):
            next_q = questions[next_index]
            await message.answer(next_q)
            new_msg = BotMessage(employee_id=employee.id, message_text=next_q)
            session.add(new_msg)
        else:
            final_msg = "Пока вопросы закончились! Спасибо за участие в опросе!"
            await message.answer(final_msg)
            new_msg = BotMessage(employee_id=employee.id, message_text=final_msg)
            session.add(new_msg)
        session.commit()
    else:
        # Если это первый ответ без предыдущего вопроса
        if next_question and next_question != response.question:
            await message.answer(next_question)
            new_msg = BotMessage(employee_id=employee.id, message_text=next_question)
            session.add(new_msg)
            session.commit()
        else:
            final_msg = "Пока вопросы закончились! Спасибо за участие!"
            await message.answer(final_msg)
            new_msg = BotMessage(employee_id=employee.id, message_text=final_msg)
            session.add(new_msg)
            session.commit()

    session.close()

def parse_gpt_response(gpt_response):
    positive_points = []
    negative_points = []
    try:
        sections = gpt_response.split("Минусы:")
        positives = sections[0].replace("Плюсы:", "").strip()
        negatives = sections[1].strip() if len(sections) > 1 else ""

        for line in positives.split('\n'):
            if line.strip().startswith(('1.', '2.', '3.', '-', '*')):
                point = line.strip().lstrip('-—–*0123456789. ').strip()
                if point:
                    positive_points.append(point)

        for line in negatives.split('\n'):
            if line.strip().startswith(('1.', '2.', '3.', '-', '*')):
                point = line.strip().lstrip('-—–*0123456789. ').strip()
                if point:
                    negative_points.append(point)
    except Exception as e:
        logger.error(f"Ошибка парсинга GPT: {e}")
    return positive_points, negative_points