from flask import Flask, Response, request, redirect, render_template, url_for
import requests
import time
from flask import jsonify
import json


class Maker:  # класс для генерации конспектов
    def __init__(self):
        self.url = "https://api.deepseek.com/v1/chat/completions"
        self.api_key = "sk-338c16a44f21420282495748d4f8b729"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def create(self, subject, klass, theme):
        data = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "user", "content": f"отвечай с форматированием html (оставь только body) и только по теме вопроса (абсолютно без постороннего контента, без побочных надписей). представь, что ты учитель школьного предмета '{subject}' в {klass} классе. твой ученик хочет подготовится к контрольной работе по теме {theme}. подготовь для него краткий, но ёмкий конспект."}
            ],
            "temperature": 1,  # управление креативностью (0-1)
            "max_tokens": 2000   # ограничение длины ответа
        }

        response = requests.post(self.url, json=data, headers=self.headers)
        print(response.json()['choices'][0]['message']['content'])
        return response.json()['choices'][0]['message']['content']

    def create_test(self, subject, klass, theme):
        data = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "user", "content": f"""
                Сгенерируй тест по предмету '{subject}' для {klass} класса по теме '{theme}'.
                (10 разных вопросов)
                Формат HTML должен быть строго следующим:
                
                <div class="test-container">
                    <!-- Для вопросов с выбором ответа -->
                    <div class="question-block">
                        <div class="question-text">1. Текст вопроса?</div>
                        <ul class="options-list">
                            <li class="option-item">
                                <input type="radio" name="q1" id="q1_1">
                                <label for="q1_1">Вариант 1</label>
                            </li>
                            <li class="option-item">
                                <input type="radio" name="q1" id="q1_2" value="correct">
                                <label for="q1_2">Вариант 2 (правильный)</label>
                            </li>
                        </ul>
                        <button class="check-btn">Проверить ответ</button>
                        <div class="feedback" style="display: none;"></div>
                    </div>
                    
                    <!-- Для вопросов с открытым ответом -->
                    <div class="question-block">
                        <div class="question-text">2. Текст открытого вопроса?</div>
                        <div class="open-question">
                            <textarea class="answer-input" placeholder="Введите ваш ответ..."></textarea>
                            <button class="check-btn">Проверить ответ</button>
                            <div class="feedback" style="display: none;"></div>
                        </div>
                    </div>
                </div>
                
                Правила:
                1. Добавляй кнопку 'Проверить ответ' после каждого вопроса
                2. Добавляй div для отображения результата проверки
                3. Для вопросов с выбором: правильный вариант помечай value="correct"
                4. Для открытых вопросов просто добавляй текстовое поле
                5. Не добавляй никаких дополнительных комментариев
                """}
            ],
            "temperature": 0.7,
            "max_tokens": 4000
        }

        response = requests.post(self.url, json=data, headers=self.headers)
        content = response.json()['choices'][0]['message']['content']
        return content.replace('```html', '').replace('```', '').strip()


main = Maker()


app = Flask(__name__)

# Главная страница


@app.route('/')
def home():
    return render_template('home.html')

# Генерация конспекта


@app.route('/make_summary')
def make_summary():
    return render_template('generate_summary.html')

# Генерация теста


@app.route('/make_test')
def make_test():
    return render_template('generate_test.html')

# Тестовый маршрут для изображений


@app.route('/square')
def square():
    svg = '''
    <svg width="200" height="200" xmlns="http://www.w3.org/2000/svg">
        <rect width="150" height="150" fill="lightblue" stroke="black" stroke-width="3"/>
    </svg>
    '''
    return Response(svg, mimetype='image/svg+xml')

# Страница помощи


@app.route('/help')
def help():
    return render_template('help.html')

# API для генерации конспекта


@app.route('/api/make_summary/<subject>/<klass>/<theme>')
def generate_summary(subject, klass, theme):
    result = main.create(subject, klass, theme)
    return result

# API для генерации теста


@app.route('/api/test')
def generate_test():
    subject, klass, theme = request.args.get('subject'), int(
        request.args.get('class')), request.args.get('theme')
    if klass < 1 or klass > 11:
        return f"Некорректный класс (должен быть от 1 до 11), у вас {klass}", 400
    return main.create_test(subject, klass, theme).lstrip('```html\n').rstrip('\n```')

# Альтернативный API для генерации конспекта


@app.route('/api/summary')
def api_summary():
    subject, klass, theme = request.args.get('subject'), int(
        request.args.get('class')), request.args.get('theme')
    if klass < 1 or klass > 11:
        return f"Некорректный класс (должен быть от 1 до 11), у вас {klass}", 400
    return main.create(subject, klass, theme).lstrip('```html\n').rstrip('\n```')

# Отладочный маршрут для проверки всех URL


@app.route('/debug-routes')
def debug_routes():
    routes = []
    for rule in app.url_map.iter_rules():
        routes.append(f"{rule.endpoint}: {rule.methods} → {rule}")
    return '<br>'.join(routes)


@app.route('/api/check_answer', methods=['POST'])
def check_answer():
    try:
        data = request.get_json()
        question = data.get('question', '').strip()
        user_answer = data.get('answer', '').strip()
        subject = data.get('subject', '').strip()

        if not question or not user_answer:
            return jsonify({
                "is_correct": False,
                "feedback": "Вопрос и ответ не могут быть пустыми",
                "correct_answer": ""
            })

        # Используем API ключ из класса Maker
        maker = Maker()
        headers = {
            "Authorization": f"Bearer {maker.api_key}",
            "Content-Type": "application/json"
        }

        prompt = f"""
        Ты - учитель {subject}. Проанализируй ответ ученика строго по критериям:
        1. Фактическая точность
        2. Полнота ответа
        3. Соответствие вопросу

        Вопрос: {question}
        Ответ ученика: {user_answer}

        Верни JSON в формате:
        {{
            "is_correct": bool,
            "feedback": str,
            "correct_answer": str
        }}

        Если ответ частично правильный, считай его правильным.
        Не ппиши, что требуються исправления.
        Фидбек должен быть полезным и конкретным (1-2 предложения).
        """

        response = requests.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers=headers,
            json={
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 500,
                "response_format": {"type": "json_object"}
            },
            timeout=15
        )

        result = response.json()
        checked_answer = json.loads(result['choices'][0]['message']['content'])

        # Валидация ответа
        if not all(key in checked_answer for key in ['is_correct', 'feedback', 'correct_answer']):
            raise ValueError("Некорректный формат ответа API")

        return jsonify(checked_answer)

    except Exception as e:
        print(f"Ошибка проверки ответа: {str(e)}")
        # Возвращаем ответ, который можно проверить вручную
        return jsonify({
            "is_correct": False,
            "feedback": "Ошибка проверки. Пожалуйста, проверьте ответ по учебнику.",
            "correct_answer": "Не удалось получить автоматическую проверку"
        })


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
