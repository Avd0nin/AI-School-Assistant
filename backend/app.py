from flask import Flask, Response, request, redirect, render_template, url_for
import requests
import time


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


main = Maker()


app = Flask(__name__)

# домашняя страницы
@app.route('/', methods=['GET'])
def home():
    return render_template('home.html')
               

# маршрут страницы с генерацией конспекта
@app.route('/make_summary', methods=['GET'])
def generate():
    return render_template('generate_summary.html')


# тестовый маршрут для генерации изображений
@app.route('/square', methods=['GET'])
def square():
    svg = '''
    <svg width="200" height="200" xmlns="http://www.w3.org/2000/svg">
        <rect width="150" height="150" fill="lightblue" stroke="black" stroke-width="3"/>
    </svg>
    '''
    return Response(svg, mimetype='image/svg+xml')


# маршрут по консультации использования
@app.route('/help', methods=['GET'])
def info():
    return render_template('help.html')



# основной маршрут для генерации конспекта
@app.route('/api/make_summary/<subject>/<klass>/<theme>', methods=['GET'])
def question(subject, klass, theme):
        result = main.create(subject, klass, theme)
        return result
    

@app.route('/api/summary')
def action():
    subject, klass, theme = request.args.get('subject'), int(request.args.get('class')), request.args.get('theme')
    if klass < 1 or klass > 11:
        return f"Некорректный класс (должен быть от 1 до 11), у вас {klass}", 400
    return main.create(subject, klass, theme).lstrip('```html\n').rstrip('\n```')
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
    app.run(host='0.0.0.0', port=5000)
