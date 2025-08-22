from flask import Flask, Response, request, redirect, render_template, url_for
import requests
import time
from flask import jsonify
import json


class AICore:  # класс для генерации конспектов
    def __init__(self):
        self.url = "https://api.deepseek.com/v1/chat/completions"
        self.api_key = "sk-338c16a44f21420282495748d4f8b729"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def generaty_summary(self, subject, klass, theme):
        data = {
                    "model": "deepseek-chat",
                    "messages": [
                        {"role": "user", "content": None}
                    ],
                    "temperature": 1,  # управление креативностью (0-1)
                    "max_tokens": 2000   # ограничение длины ответа
                }
        data['messages'][0]['content'] = f'отвечай с форматированием html (оставь только body) и только по теме вопроса (абсолютно без постороннего контента, без побочных надписей). представь, что ты учитель школьного предмета "{subject}" в {klass} классе. твой ученик хочет подготовится к контрольной работе по теме {theme}. подготовь для него краткий, но ёмкий конспект.'
        response = requests.post(self.url, json=data, headers=self.headers)
        print(response.json()['choices'][0]['message']['content'])
        return response.json()['choices'][0]['message']['content']
    
    def answer_question(self, subject, klass, theme, question, history):
        data = {
                    "model": "deepseek-chat",
                    "messages": [
                        {"role": "user", "content": None}
                    ] + history,
                    "temperature": 1,  # управление креативностью (0-1)
                    "max_tokens": 2000   # ограничение длины ответа
                }
        data['messages'][0]['content'] = f'отвечай только по теме вопроса (без постороннего контента, без побочных надписей) а также абсолютно без форматирования (исключительно пробелы и переносы строк). представь, что ты учитель школьного предмета "{subject}" в {klass} классе. у твоего ученика есть вопрос по теме "{theme}": {question}. ответь на вопрос ученика подробно и озабочено.'
        response = requests.post(self.url, json=data, headers=self.headers)
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



model = AICore()


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

# маршрут по консультации использования
@app.route('/help', methods=['GET'])
def info():
    return render_template('help.html')

# API для генерации конспекта

@app.route('/chat', methods=['GET'])
def chat():
    return render_template('chat.html')

# маршрут страницы с генерацией тестов
@app.route('/make_test', methods=['GET'])
def make_test():
    return render_template('generate_test.html')

@app.route('/api/question', methods=['POST'])
def asking():
    data = request.get_json()
    subject, klass, theme, question, history = data['subject'], int(data['klass']), data['theme'], data['question'], data['message_history']
    print(data['message_history'])
    #subject, klass, theme, question = request.args.get('subject'), int(request.args.get('klass')), request.args.get('theme'), request.args.get('question')
    #return 'ыыыыыыыыыыыыыыыыыыыыыыыыыыыыыыыыыыыыыыыыыыыыыыыыыыыыыыыыыыыыыыыыыыыыыыыы'
    return model.answer_question(subject, klass, theme, question, history)

# API для генерации теста
@app.route('/api/test')
def generate_test():
    subject, klass, theme = request.args.get('subject'), int(
        request.args.get('class')), request.args.get('theme')
    if klass < 1 or klass > 11:
        return f"Некорректный класс (должен быть от 1 до 11), у вас {klass}", 400
    return model.create_test(subject, klass, theme).lstrip('```html\n').rstrip('\n```')

# API для проверки ответов в тестах
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

        # Используем API ключ из класса AICore
        headers = {
            "Authorization": f"Bearer {model.api_key}",
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
        Не пиши, что требуются исправления.
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


    

@app.route('/api/summary')
def action():
    subject, klass, theme = request.args.get('subject'), int(request.args.get('klass')), request.args.get('theme')
    if klass < 1 or klass > 11:
        return f"Некорректный класс (должен быть от 1 до 11), у вас {klass}", 400
    return model.generaty_summary(subject, klass, theme).lstrip('```html\n').rstrip('\n```')
    print(subject, klass, theme)
    time.sleep(1)
    return '''
    <div style="font-family: Arial, sans-serif; color: #800080; background-color: #f0e6ff; padding: 15px; border-radius: 8px; max-width: 600px; margin: auto;">
    <h2 style="text-align: center; color: #4b0082;">Конспект по теме "Дроби"</h2>
    
    <h3 style="color: #6a0dad;">1. Основные понятия</h3>
    <p><strong>Дробь</strong> — число вида <span style="font-weight: bold;">a/b</span>, где:</p>
    <ul>
        <li><strong>a</strong> — числитель (сколько частей взяли),</li>
        <li><strong>b</strong> — знаменатель (на сколько частей разделили целое).</li>
    </ul>
    
    <h3 style="color: #6a0dad;">2. Виды дробей</h3>
    <ul>
        <li><strong>Правильная</strong> — числитель меньше знаменателя (пример: 2/5).</li>
        <li><strong>Неправильная</strong> — числитель больше или равен знаменателю (пример: 7/4).</li>
        <li><strong>Смешанная</strong> — целая часть + дробь (пример: 1 3/4).</li>
    </ul>
    
    <h3 style="color: #6a0dad;">3. Действия с дробями</h3>
    <p><strong>Сложение/вычитание:</strong></p>
    <ul>
        <li>Приводим к общему знаменателю.</li>
        <li>Складываем/вычитаем числители.</li>
    </ul>
    <p>Пример: <br> 1/4 + 1/6 = 3/12 + 2/12 = <strong>5/12</strong></p>
    
    <p><strong>Умножение:</strong></p>
    <ul>
        <li>Умножаем числители и знаменатели.</li>
    </ul>
    <p>Пример: <br> 2/3 × 3/5 = <strong>6/15</strong> = 2/5 (сократили).</p>
    
    <p><strong>Деление:</strong></p>
    <ul>
        <li>Умножаем на дробь, обратную делителю.</li>
    </ul>
    <p>Пример: <br> 4/7 ÷ 2/3 = 4/7 × 3/2 = <strong>12/14</strong> = 6/7.</p>
    
    <h3 style="color: #6a0dad;">4. Сокращение дробей</h3>
    <p>Делим числитель и знаменатель на их НОД.</p>
    <p>Пример: <br> 8/12 = (8÷4)/(12÷4) = <strong>2/3</strong>.</p>
    
    <h3 style="color: #6a0dad;">5. Перевод дробей</h3>
    <p><strong>Неправильную → смешанную:</strong></p>
    <p>Пример: <br> 7/3 = 2 1/3 (7÷3=2 и остаток 1).</p>
    
    <p><strong>Смешанную → неправильную:</strong></p>
    <p>Пример: <br> 1 2/5 = (1×5 + 2)/5 = <strong>7/5</strong>.</p>
    
    <p style="text-align: center; font-style: italic; color: #4b0082;">Успехов на контрольной! 😊</p>
    </div>'''


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=4000, debug=True)
