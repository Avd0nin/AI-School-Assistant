from flask import Flask, jsonify, request
import requests


class Maker:
    def __init__(self):
        # предположительный эндпоинт
        self.url = "https://api.deepseek.com/v1/chat/completions"
        self.api_key = "sk-338c16a44f21420282495748d4f8b729"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
# OKKAKKK

    def create(self, klass, theme):
        data = {
            "model": "deepseek-chat",  # или другая модель
            "messages": [
                {"role": "user", "content": f"отвечай не используя форматирование и смайлы, только по делу. представь, что ты учитель геометрии в {klass} классе. твой ученик хочет подготовится к контрольной работе по теме {theme}. подготовь для него краткий но ёмкий конспект."}
            ],
            "temperature": 1,  # управление креативностью (0-1)
            "max_tokens": 1000   # ограничение длины ответа
        }

        response = requests.post(self.url, json=data, headers=self.headers)
        return response.json()['choices'][0]['message']['content']


main = Maker()
# окак
app = Flask(__name__)

# Маршрут для главной страницы


@app.route('/')
def home():
    return "Окак."



@app.route('/question', methods=['GET'])
def info():
    return 'Укажите класс и тему'


@app.route('/question/<int:klass>/<string:theme>', methods=['GET'])
def question(klass, theme):
    return main.create(klass, theme)


if __name__ == '__main__':
    app.run(debug=True)
