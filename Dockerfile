# Используем официальный образ Python
FROM python:3.13-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем зависимости и устанавливаем их
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем исходный код и HTML-файлы
COPY backend/app.py .
COPY backend/templates/ ./templates/
COPY backend/static ./static
# Указываем порт, который будет использоваться Flask
EXPOSE 5000

# Запускаем приложение
CMD ["python", "app.py"]
