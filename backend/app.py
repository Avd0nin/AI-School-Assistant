from flask import Flask, Response
import requests


class Maker: # класс для генерации конспектов
    def __init__(self):
        self.url = "https://api.deepseek.com/v1/chat/completions"
        self.api_key = "sk-338c16a44f21420282495748d4f8b729"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
            }
    def create(self, subject, klass, theme):
        }
        data = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "user", "content": f"отвечай с форматированием html и только по теме вопроса. представь, что ты учитель школьного предмета '{subject}' в {klass} классе. твой ученик хочет подготовится к контрольной работе по теме {theme}. подготовь для него краткий, но ёмкий конспект."}
            ],
            "temperature": 1,  # управление креативностью (0-1)
            "max_tokens": 1000   # ограничение длины ответа
        }

        response = requests.post(self.url, json=data, headers=self.headers)
        return response.json()['choices'][0]['message']['content']


main = Maker()


app = Flask(__name__)


# маршрут главной страницы
@app.route('/')
def home():
    return '''
    <html>
        <head>
            <title>AI School Assistant</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    background: #f4f8fb;
                    color: #222;
                    margin: 0;
                    padding: 0;
                }
                .container {
                    max-width: 600px;
                    margin: 60px auto;
                    background: #fff;
                    border-radius: 12px;
                    box-shadow: 0 4px 16px rgba(0,0,0,0.08);
                    padding: 40px 30px;
                    text-align: center;
                }
                h1 {
                    color: #2a7ae2;
                    margin-bottom: 18px;
                }
                p {
                    font-size: 1.15em;
                    margin-bottom: 10px;
                }
                .help-link {
                    display: inline-block;
                    margin-top: 18px;
                    padding: 10px 22px;
                    background: #2a7ae2;
                    color: #fff;
                    border-radius: 6px;
                    text-decoration: none;
                    font-weight: bold;
                    transition: background 0.2s;
                }
                .help-link:hover {
                    background: #185a9d;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Добро пожаловать!</h1>
                <p>Это сайт-помощник школьникам нового поколения.</p>
                <p>Для получения информации об использовании перейдите по ссылке ниже:</p>
                <a class="help-link" href="/help">Инструкция по использованию</a>
            </div>
        </body>
    </html>
    '''


# тестовый маршрут для генерации изображений, пока что рисует простой квадрат
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
    return 'чтобы получить конспект, отправьте запрос вида /make_summary/<предмет>/<класс>/<тема>'


# основной маршрут для генерации конспекта
@app.route('/make_summary/<string:subject>/<int:klass>/<string:theme>', methods=['GET'])
def question(subject, klass, theme):
    return main.create(subject, klass, theme)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
