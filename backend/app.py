from flask import Flask, Response, request, redirect
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
                {"role": "user", "content": f"отвечай с форматированием html и только по теме вопроса. представь, что ты учитель школьного предмета '{subject}' в {klass} классе. твой ученик хочет подготовится к контрольной работе по теме {theme}. подготовь для него краткий, но ёмкий конспект."}
            ],
            "temperature": 1,  # управление креативностью (0-1)
            "max_tokens": 2000   # ограничение длины ответа
        }

        response = requests.post(self.url, json=data, headers=self.headers)
        return response.json()['choices'][0]['message']['content']


main = Maker()


app = Flask(__name__)


# домашняя страницы
@app.route('/', methods=['GET'])
def index():
    return '''
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>AI-School-Assistant</title>
        <style>
            body {
                font-family: 'Arial', sans-serif;
                margin: 0;
                padding: 0;
                background-color: #f8f5ff;
                color: #333;
            }
            
            header {
                background: linear-gradient(to right, #6a11cb, #8e44ad);
                color: white;
                padding: 20px 0;
                text-align: center;
                box-shadow: 0 2px 5px rgba(0,0,0,0.1);
            }
            
            .logo {
                font-size: 2.5em;
                font-weight: bold;
                margin-bottom: 10px;
            }
            
            nav {
                background-color: #5d3f8a;
                padding: 10px 0;
            }
            
            nav ul {
                list-style-type: none;
                margin: 0;
                padding: 0;
                text-align: center;
            }
            
            nav ul li {
                display: inline;
                margin: 0 15px;
            }
            
            nav ul li a {
                color: white;
                text-decoration: none;
                font-size: 1.1em;
                transition: color 0.3s;
            }
            
            nav ul li a:hover {
                color: #d1c4e9;
            }
            
            main {
                max-width: 1200px;
                margin: 20px auto;
                padding: 20px;
                min-height: calc(100vh - 200px);
            }
            
            footer {
                background-color: #4a235a;
                color: white;
                text-align: center;
                padding: 20px 0;
                margin-top: 20px;
            }
            
            .footer-content {
                max-width: 1200px;
                margin: 0 auto;
            }
            
            .footer-links {
                margin-bottom: 15px;
            }
            
            .footer-links a {
                color: #d1c4e9;
                margin: 0 10px;
                text-decoration: none;
            }
            
            .footer-links a:hover {
                text-decoration: underline;
            }
        </style>
    </head>
    <body>
        <header>
            <div class="logo">AI-School-Assistant</div>
        </header>
        
        <nav>
            <ul>
                <li><a href="/">Главная</a></li>
                <li><a href="help.html">Помощь</a></li>
                <li><a href="about.html">О нас</a></li>
                <li><a href="contact.html">Контакты</a></li>
            </ul>
        </nav>
        
        <main>
            <!-- Здесь будет основное содержимое страницы -->
            <h1>Добро пожаловать в AI-School-Assistant</h1>
            <p>Ваш умный помощник в образовательном процессе.</p>
        </main>
        
        <footer>
            <div class="footer-content">
                <div class="footer-links">
                    <a href="privacy.html">Политика конфиденциальности</a>
                    <a href="terms.html">Условия использования</a>
                    <a href="faq.html">FAQ</a>
                </div>
                <p>&copy; 2023 AI-School-Assistant. Все права защищены.</p>
            </div>
        </footer>
    </body>
    </html>'''
               

# маршрут страницы с генерацией конспекта
@app.route('/make_summary', methods=['GET'])
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
                .summary-form {
                    display: flex;
                    flex-direction: column;
                    gap: 20px;
                    margin-top: 30px;
                }
                .form-group {
                    display: flex;
                    flex-direction: column;
                    gap: 8px;
                    text-align: left;
                }
                .form-group label {
                    font-weight: bold;
                    color: #333;
                }
                .form-group input {
                    padding: 12px 15px;
                    border: 1px solid #ddd;
                    border-radius: 6px;
                    font-size: 16px;
                }
                .submit-btn {
                    margin-top: 15px;
                    padding: 14px 20px;
                    background: #2a7ae2;
                    color: white;
                    border: none;
                    border-radius: 6px;
                    font-size: 16px;
                    font-weight: bold;
                    cursor: pointer;
                    transition: background 0.2s;
                }
                .submit-btn:hover {
                    background: #185a9d;
                }
                .help-link {
                    display: inline-block;
                    margin-top: 25px;
                    color: #2a7ae2;
                    text-decoration: none;
                    font-weight: bold;
                }
                .help-link:hover {
                    text-decoration: underline;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Генератор конспектов</h1>
                <form action="/make_summary" method="get" class="summary-form">
                    <div class="form-group">
                        <label for="subject">Предмет:</label>
                        <input type="text" id="subject" name="subject" required placeholder="Например: Математика">
                    </div>
                    
                    <div class="form-group">
                        <label for="klass">Класс:</label>
                        <input type="number" id="klass" name="klass" min="1" max="11" required placeholder="От 1 до 11">
                    </div>
                    
                    <div class="form-group">
                        <label for="theme">Тема:</label>
                        <input type="text" id="theme" name="theme" required placeholder="Например: Квадратные уравнения">
                    </div>
                    
                    <button type="submit" class="submit-btn">Сгенерировать конспект</button>
                </form>
                <a href="/help" class="help-link">Инструкция по использованию</a>
            </div>
        </body>
    </html>
    '''


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


# обработчик формы
@app.route('/api/make_summary', methods=['GET'])
def handle_form():
    subject = request.args.get('subject')
    klass = request.args.get('klass')
    theme = request.args.get('theme')

    if not all([subject, klass, theme]):
        return "Все поля должны быть заполнены", 400

    try:
        klass_int = int(klass)
        if klass_int < 1 or klass_int > 11:
            return "Класс должен быть числом от 1 до 11", 400
    except (ValueError, TypeError):
        return "Класс должен быть числом", 400

    return redirect(f'/make_summary/{subject}/{klass_int}/{theme}')


# основной маршрут для генерации конспекта
@app.route('/api/make_summary/<string:subject>/<int:klass>/<string:theme>', methods=['GET'])
def question(subject, klass, theme):
    try:
        # Проверяем корректность класса
        if klass < 1 or klass > 11:
            return f"Некорректный класс (должен быть от 1 до 11), у вас {klass}", 400
        # Проверяем, что тема не пустая
        if not theme.strip():
            return "Тема не может быть пустой", 400
        result = main.create(subject, klass, theme)
        return result
    except Exception as e:
        return f"Внутренняя ошибка сервера: {str(e)}", 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
