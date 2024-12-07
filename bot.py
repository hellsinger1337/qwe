from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)
from database import SessionLocal
from models import Employee, Response, PositivePoint, NegativePoint,Organization,BotMessage
import yaml
import logging
import openai

logger = logging.getLogger(__name__)

def load_config(config_path='config.yaml'):
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

config = load_config()

openai.api_key = config['openai']['api_key']

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Привет! Я бот для сбора обратной связи.')
    logger.info(f"Пользователь {update.effective_user.full_name} выполняет регистрацию.")
    session = SessionLocal()
    telegram_id = str(update.effective_user.id)

    employee = session.query(Employee).filter(Employee.telegram_id == telegram_id).first()
    if employee:
        await update.message.reply_text(
            "Вы уже зарегистрированы в системе. Спасибо за использование бота!"
        )
        logger.info(f"Пользователь {employee.name} пытался повторно зарегистрироваться.")
        session.close()
        return

    employee = Employee(
        telegram_id=telegram_id,
        name=update.effective_user.full_name,
        organization_id=1,
    )
    session.add(employee)
    session.commit()
    session.refresh(employee)

    await update.message.reply_text(
        f"Вы успешно зарегистрированы в компании. Спасибо!"
    )
    session.query(BotMessage).filter(BotMessage.employee_id == employee.id).delete()
    session.commit()
    survey_text = config['messages'][0]
    await update.message.reply_text(survey_text)
    logger.info(f"Отправлено опросное сообщение сотруднику {employee.name} (Telegram ID: {employee.telegram_id}).")
    bot_message = BotMessage(
                    employee_id=employee.id,
                    message_text=survey_text
                )
    session.add(bot_message)
    session.commit()

    logger.info(f"Новый сотрудник зарегистрирован: {employee.name} (ID: {employee.id})")
    session.close()
    logger.info(f"Пользователь {update.effective_user.full_name} начал взаимодействие с ботом.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработка входящего сообщения от пользователя.
    Проверяет, зарегистрирован ли пользователь, и предлагает регистрацию, если не зарегистрирован.
    """
    logger.info(f"Получено сообщение от пользователя {update.effective_user.full_name}.")
    session = SessionLocal()
    telegram_id = str(update.effective_user.id)
    employee = session.query(Employee).filter(Employee.telegram_id == telegram_id).first()

    if not employee:
        await update.message.reply_text(
            "Вы не зарегистрированы в системе.\n"
            "Пожалуйста, зарегистрируйтесь, введя команду:\n"
            "/register"
        )
        logger.info(f"Пользователь {telegram_id} не зарегистрирован.")
    else:
        logger.info(f"Сохранение ответа от сотрудника {employee.name}.")
        
        last_bot_message = session.query(BotMessage).filter(BotMessage.employee_id == employee.id).order_by(BotMessage.timestamp.desc()).first()
        print(last_bot_message)
        next_question = False
        if last_bot_message:
            if last_bot_message.message_text == "Пока вопросы закончились! Спасибо за участие в опросе!":
                await update.message.reply_text("Простите, но сейчас у меня нет вопросов для вас! Вернусь со следующим вопросом.")
                logger.info(f"Пользователь {employee.name} не имеет новых вопросов.")
                return

            questions = config['messages']
            if last_bot_message.message_text in questions:
                next_question_index = questions.index(last_bot_message.message_text) + 1
                if next_question_index < len(questions):
                    next_question = questions[next_question_index]
                    bot_message = BotMessage(
                        employee_id=employee.id,
                        message_text=next_question 
                    )
                    session.add(bot_message)
                    logger.info(f"Отправлен следующий вопрос: {next_question}")
                else:
                    await update.message.reply_text("Пока вопросы закончились! Спасибо за участие в опросе!")
                    logger.info(f"Пользователь {employee.name} завершил опрос.")
                    bot_message = BotMessage(
                        employee_id=employee.id,
                        message_text="Пока вопросы закончились! Спасибо за участие в опросе!"
                    )
                    session.add(bot_message)
            else:
                await update.message.reply_text("Простите, но сейчас у меня нет вопросов для вас! Вернусь со следующим вопросом.")


        else:
            await update.message.reply_text("Простите, но сейчас у меня нет вопросов для вас! Вернусь со следующим вопросом.")

        response = Response(
            employee_id=employee.id,
            response_text=update.message.text,
            question=last_bot_message.message_text if last_bot_message else config['messages'][0]  
        )
        session.add(response)
        session.commit()
        
        logger.info(f"Ответ от {employee.name}: {response.response_text}")

        try:
            prompt = (
                "Раздели следующий текст на положительные и отрицательные моменты. "
                "Представь их в виде списка с плюсами и минусами:\n\n"
                f"Вопрос: {response.question}\n"
                f"Ответ: {response.response_text}"
            )
            completion = await openai.ChatCompletion.acreate(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": """
                        Ты — аналитический помощник, специализирующийся на анализе отзывов сотрудников о работе в компании. Твоя задача — выделить и стандартизировать плюсы и минусы из предоставленного отзыва. Пожалуйста, ответь в следующем формате: 
                        Плюсы: 
                        1. 
                        2.
                        Минусы: 
                        1. 
                        2. 
                        Учти следующее: - В разделе "Плюсы" перечисли только положительные аспекты работы в компании. - В разделе "Минусы" укажи только негативные аспекты, которые можно улучшить. - Стандартизируй формулировки, чтобы схожие моменты описывались одинаково (например, "гибкий график работы" и "флексибельные часы" должны быть представлены одинаково). - Используй краткие и четкие фразы для каждого пункта. - Придерживайся нумерованного списка для удобства последующего анализа. - Избегай личных оценок и субъективных суждений.
                    """},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.5,
                max_tokens=500
            )
            gpt_response = completion.choices[0].message['content']
            logger.info(f"Ответ от OpenAI: {gpt_response}")

            positive_points, negative_points = parse_gpt_response(gpt_response)

            for point in positive_points:
                positive = PositivePoint(
                    response_id=response.id,
                    point_text=point.strip()
                )
                session.add(positive)

            for point in negative_points:
                negative = NegativePoint(
                    response_id=response.id,
                    point_text=point.strip()
                )
                session.add(negative)

            session.commit()
            logger.info(f"Сохранены плюсы: {positive_points} и минусы: {negative_points} для ответа ID {response.id}")
        except Exception as e:
            logger.error(f"Ошибка при обработке ответа через OpenAI: {e}")
            await update.message.reply_text('Произошла ошибка при обработке вашего ответа. Пожалуйста, попробуйте позже.')
        if next_question: 
            await update.message.reply_text(next_question)

    session.close()

def parse_gpt_response(gpt_response):
    """
    Функция для парсинга ответа от GPT и извлечения плюсов и минусов.
    Предполагается, что GPT отвечает в следующем формате:

    Плюсы:
    1. Плюс 1
    2. Плюс 2

    Минусы:
    1. Минус 1
    2. Минус 2
    """
    positive_points = []
    negative_points = []

    try:
        sections = gpt_response.split("Минусы:")
        positives = sections[0].replace("Плюсы:", "").strip()
        negatives = sections[1].strip() if len(sections) > 1 else ""

        for line in positives.split('\n'):
            if line.strip().startswith(('-', '—', '–', '*', '1.', '2.', '3.')):
                point = line.strip().lstrip('-—–*0123456789. ').strip()
                if point:
                    positive_points.append(point)

        for line in negatives.split('\n'):
            if line.strip().startswith(('-', '—', '–', '*', '1.', '2.', '3.')):
                point = line.strip().lstrip('-—–*0123456789. ').strip()
                if point:
                    negative_points.append(point)

    except Exception as e:
        logger.error(f"Ошибка при парсинге ответа от GPT: {e}")

    return positive_points, negative_points

def setup_bot():
    application = ApplicationBuilder().token(config['telegram_bot_token']).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("register", register))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    return application
