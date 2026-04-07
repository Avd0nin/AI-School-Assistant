from flask import Flask, Response, request, redirect, render_template, url_for
import requests
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
        test_format_html = render_template('test_format_snippet.html')
        prompt = f"""
                Сгенерируй тест по предмету '{subject}' для {klass} класса по теме '{theme}'.
                (10 разных вопросов)
                Формат HTML должен быть строго следующим:
                
                {test_format_html}
                
                Правила:
                1. Добавляй кнопку 'Проверить ответ' после каждого вопроса
                2. Добавляй div для отображения результата проверки
                3. Для вопросов с выбором: правильный вариант помечай value="correct"
                4. Для открытых вопросов просто добавляй текстовое поле
                5. Не добавляй никаких дополнительных комментариев
                """
        data = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "user", "content": prompt}
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
    try:
        return model.generaty_summary(subject, klass, theme).lstrip('```html\n').rstrip('\n```')
    except Exception:
        return render_template('summary_example_snippet.html')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=4000, debug=True)
