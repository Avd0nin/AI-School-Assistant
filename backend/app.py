from flask import Flask, request, render_template, jsonify
from ai_core import AICore


model = AICore()
app = Flask(__name__)


@app.route('/')
def home():
    return render_template('home.html')


@app.route('/make_summary')
def make_summary():
    return render_template('generate_summary.html')


@app.route('/help', methods=['GET'])
def info():
    return render_template('help.html')


@app.route('/chat', methods=['GET'])
def chat():
    return render_template('chat.html')


@app.route('/make_test', methods=['GET'])
def make_test():
    return render_template('generate_test.html')


@app.route('/api/question', methods=['POST'])
def asking():
    data = request.get_json()
    subject = (data.get('subject') or '').strip()
    theme = (data.get('theme') or '').strip()
    question = (data.get('question') or '').strip()
    history = data.get('message_history', [])

    try:
        klass = int(data.get('klass', 6))
    except (TypeError, ValueError):
        klass = 6

    try:
        return model.answer_question(subject, klass, theme, question, history)
    except Exception as e:
        print(f"Ошибка чата: {str(e)}")
        return "<p>Ошибка при получении ответа от модели.</p>", 500


@app.route('/api/test')
def generate_test():
    subject = request.args.get('subject')
    theme = request.args.get('theme')

    try:
        klass = int(request.args.get('class'))
    except (TypeError, ValueError):
        return "Некорректный класс", 400

    if klass < 1 or klass > 11:
        return f"Некорректный класс (должен быть от 1 до 11), у вас {klass}", 400

    try:
        return model.create_test(subject, klass, theme).lstrip('```html\n').rstrip('\n```')
    except Exception as e:
        print(f"Ошибка генерации теста: {str(e)}")
        return "<p>Ошибка при генерации теста.</p>", 500


@app.route('/api/check_answer', methods=['POST'])
def check_answer():
    try:
        data = request.get_json()
        question = data.get('question', '').strip()
        user_answer = data.get('answer', '').strip()
        subject = data.get('subject', '').strip()
        theme = data.get('theme', '').strip()

        try:
            klass = int(data.get('klass', 6))
        except (TypeError, ValueError):
            klass = 6

        if not question or not user_answer:
            return jsonify({
                "is_correct": False,
                "feedback": "Вопрос и ответ не могут быть пустыми.",
                "correct_answer": ""
            })

        checked_answer = model.check_answer_with_ai(
            subject, question, user_answer, klass, theme)

        if not all(key in checked_answer for key in ['is_correct', 'feedback', 'correct_answer']):
            raise ValueError("Некорректный формат ответа API")

        return jsonify(checked_answer)

    except Exception as e:
        print(f"Ошибка проверки ответа: {str(e)}")
        return jsonify({
            "is_correct": False,
            "feedback": "Ошибка проверки. Попробуйте ещё раз.",
            "correct_answer": ""
        })


@app.route('/api/summary')
def action():
    subject = request.args.get('subject')
    theme = request.args.get('theme')

    try:
        klass = int(request.args.get('klass'))
    except (TypeError, ValueError):
        return "Некорректный класс", 400

    if klass < 1 or klass > 11:
        return f"Некорректный класс (должен быть от 1 до 11), у вас {klass}", 400

    try:
        return model.generaty_summary(subject, klass, theme)
    except Exception as e:
        print(f"Ошибка генерации конспекта: {str(e)}")
        return render_template('summary_example_snippet.html')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=4000, debug=True)
