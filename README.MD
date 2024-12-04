# Запуск проекта

1. Скопируйте файл `config.yaml.example` и переименуйте его в `config.yaml`.
2. Откройте `config.yaml` и заполните свои креды.
3. Создайте виртуальное окружение:
```
python -m venv venv
```
4. Активируйте виртуальное окружение:
- Для Windows:
  ```
  venv\Scripts\activate
  ```
- Для macOS/Linux:
  ```
  source venv/bin/activate
  ```
5. Установите зависимости:
```
pip install -r requirements.txt
```
6. Запустите проект:
```
python main.py
```