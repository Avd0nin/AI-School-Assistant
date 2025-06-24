from flask import Flask, Response, request, redirect, render_template, url_for
import requests


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
                {"role": "user", "content": f"отвечай с форматированием html в фиолетовом стиле и только по теме вопроса (чистый, абсолютно без постороннего контента, без побочных надписей). представь, что ты учитель школьного предмета '{subject}' в {klass} классе. твой ученик хочет подготовится к контрольной работе по теме {theme}. подготовь для него краткий, но ёмкий конспект."}
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
    return '''
    <html>
        <head>
            <title>Помощь</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    max-width: 800px;
                    margin: 0 auto;
                    padding: 20px;
                    line-height: 1.6;
                }
                h1 {
                    color: #2a7ae2;
                }
                .back-link {
                    display: inline-block;
                    margin-top: 20px;
                    color: #2a7ae2;
                    text-decoration: none;
                    font-weight: bold;
                }
                .back-link:hover {
                    text-decoration: underline;
                }
            </style>
        </head>
        <body>
            <h1>Инструкция по использованию</h1>
            <p>Этот сервис помогает школьникам готовиться к контрольным работам, генерируя краткие конспекты по заданным темам.</p>
            
            <h2>Как использовать:</h2>
            <ol>
                <li>На главной странице заполните форму:
                    <ul>
                        <li>Укажите школьный предмет (например, "Математика")</li>
                        <li>Выберите класс (от 1 до 11)</li>
                        <li>Введите тему для конспекта (например, "Квадратные уравнения")</li>
                    </ul>
                </li>
                <li>Нажмите кнопку "Сгенерировать конспект"</li>
                <li>Система создаст для вас структурированный конспект по указанной теме</li>
            </ol>
            
            <h2>Примеры запросов:</h2>
            <ul>
                <li>Предмет: История, Класс: 8, Тема: Отечественная война 1812 года</li>
                <li>Предмет: Биология, Класс: 9, Тема: Деление клетки</li>
                <li>Предмет: Физика, Класс: 10, Тема: Законы Ньютона</li>
            </ul>
            
            <a href="/" class="back-link">Вернуться на главную</a>
        </body>
    </html>
    '''



# основной маршрут для генерации конспекта
@app.route('/api/make_summary/<subject>/<klass>/<theme>', methods=['GET'])
def question(subject, klass, theme):
        result = main.create(subject, klass, theme)
        return result
    

@app.route('/api/make_summary_load', methods=['POST'])
def action():
    try:
        subject, klass, theme = request.form.get('subject'), int(request.form.get('klass')), request.form.get('theme')
        # Проверяем корректность класса
        if klass < 1 or klass > 11:
            return f"Некорректный класс (должен быть от 1 до 11), у вас {klass}", 400
        return render_template('summary_loading.html', subject=subject, klass=klass, theme=theme)
    except Exception as e:
        return f"Внутренняя ошибка сервера: {str(e)}", 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
