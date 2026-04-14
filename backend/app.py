from flask import Flask, request, render_template, jsonify
from openai import OpenAI
import json
import re


class AICore:
    def __init__(self):
        self.client = OpenAI(
            base_url="https://neuroapi.host/v1",
            api_key="sk-G7cp4Eaxd5qxGrslE4PJEVXoiWfsGufoSG5eEr9nbYLPyy0q"
        )
        self.model = "gpt-4.1-mini"

    def _chat(self, messages, temperature=0.7, max_tokens=2000):
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )
        return response.choices[0].message.content.strip()

    def normalize_summary_html(self, html):
        if not html:
            return html

        cleaned = html.replace('```html', '').replace('```', '').strip()
        cleaned = re.sub(r'(?im)^\s*-{2,}\s*$', '', cleaned)
        cleaned = re.sub(r'(?is)<p>\s*-{2,}\s*</p>', '', cleaned)
        cleaned = re.sub(r'(?is)<div>\s*-{2,}\s*</div>', '', cleaned)
        cleaned = re.sub(
            r'(<h1[^>]*>\s*)Краткий\s+конспект\s+по\s+теме\s*',
            r'\1',
            cleaned,
            flags=re.IGNORECASE
        )
        return cleaned.strip()

    def normalize_html(self, html):
        if not html:
            return ""

        cleaned = html.replace('```html', '').replace('```', '').strip()
        cleaned = re.sub(r'^\s*<html[^>]*>\s*<body[^>]*>\s*', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s*</body>\s*</html>\s*$', '', cleaned, flags=re.IGNORECASE)
        return cleaned

    def generaty_summary(self, subject, klass, theme):
        messages = [
            {"role": "user", "content": None}
        ]

        messages[0]["content"] = (
            f'отвечай с форматированием html (оставь только body) и только по теме вопроса '
            f'(абсолютно без постороннего контента, без побочных надписей). '
            f'все математические формулы пиши строго в latex-нотации в разделителях '
            f'\\( ... \\) для строковых формул и \\[ ... \\] для блочных '
            f'(без двойных экранирований). представь, что ты учитель школьного предмета '
            f'"{subject}" в {klass} классе. твой ученик хочет подготовиться к контрольной '
            f'работе по теме {theme}. пиши максимально понятно, подробно и структурированно. '
            f'сделай конспект длинным и полноценным, чтобы по нему реально можно было готовиться: '
            f'раскрой тему последовательно, не сжимай объяснения до пары фраз, '
            f'чаще используй короткие списки, подзаголовки и блок «самое важное» '
            f'(когда это уместно), добавляй несколько коротких примеров с пояснением, '
            f'обязательно объясняй основные термины, правила, типичные ошибки и важные нюансы по теме. '
            f'если тема большая, разбей её на несколько логических разделов. '
            f'делай больше визуальных выносок отдельными блоками (не называй их "самое важное"): '
            f'для определений, правил, типичных ошибок и советов. '
            f'для таких блоков используй div с классом summary-callout и дополнительным классом: '
            f'summary-callout-definition / summary-callout-rule / summary-callout-warning / summary-callout-tip. '
            f'формулы в эти выноски не помещай — формулы оставляй отдельно обычным текстом/блоками. '
            f'заголовок h1 начинай сразу с темы и класса, без слов «краткий конспект по теме».'
        )

        raw_content = self._chat(
            messages=messages,
            temperature=1,
            max_tokens=4000
        )

        print(raw_content)
        return self.normalize_summary_html(raw_content)

    def answer_question(self, subject, klass, theme, question, history):
        safe_subject = (subject or "").strip()
        safe_theme = (theme or "").strip()
        safe_question = (question or "").strip()

        messages = [
            {
                "role": "system",
                "content": (
                    "Ты дружелюбный, умный и понятный AI-помощник. "
                    "Отвечай естественно, по-человечески и по делу. "
                    "Ты умеешь быть хорошим наставником в учёбе, но не обязан превращать каждый диалог в школьный урок. "
                    "Если пользователь просто здоровается, задаёт обычный вопрос или говорит на свободную тему — отвечай нормально как полезный собеседник. "
                    "Если вопрос учебный, объясняй как сильный учитель: понятно, структурированно, без воды, с примерами. "
                    "Если уместно, возвращай HTML-фрагмент без тегов html/head/body: можно использовать h2, h3, p, ul, ol, li, strong, em, blockquote. "
                    "Не используй script, style, iframe. "
                    "Если есть формулы, пиши их в LaTeX: \\( ... \\) или \\[ ... \\]. "
                    "Не придумывай лишнюю тему, если пользователь её не задавал."
                )
            }
        ]

        if history and isinstance(history, list):
            for item in history:
                if isinstance(item, dict) and item.get("role") and item.get("content"):
                    messages.append({
                        "role": item["role"],
                        "content": item["content"]
                    })

        context_parts = []
        if safe_subject:
            context_parts.append(f"Предмет: {safe_subject}.")
        if klass:
            context_parts.append(f"Класс: {klass}.")
        if safe_theme:
            context_parts.append(f"Текущая тема: {safe_theme}.")

        context_text = " ".join(context_parts)

        user_prompt = (
            f"{context_text}\n"
            f"Сообщение пользователя: {safe_question}\n\n"
            f"Правила ответа:\n"
            f"- если это обычное приветствие или обычный разговорный вопрос, ответь естественно и кратко;\n"
            f"- если это учебный вопрос, ответь понятно, структурированно и полезно;\n"
            f"- не навязывай школьную тему, если пользователь о ней не просил;\n"
            f"- если форматирование помогает, используй HTML-фрагмент."
        )

        content = self._chat(
            messages=messages + [{"role": "user", "content": user_prompt}],
            temperature=0.7,
            max_tokens=1800
        )

        return self.normalize_html(content)

    def create_test(self, subject, klass, theme):
        test_format_html = render_template('test_format_snippet.html')

        prompt = f"""
Сгенерируй тест по предмету "{subject}" для {klass} класса по теме "{theme}".

Нужно:
- ровно 10 вопросов;
- уровень сложности должен соответствовать {klass} классу;
- вопросы не должны быть слишком примитивными;
- задания должны реально проверять понимание темы, а не только очевидные факты;
- всегда делай 4 варианта ответа в вопросах с выбором;
- у каждого вопроса с выбором должно быть ровно 4 варианта;
- только один правильный вариант;
- неправильные варианты должны быть правдоподобными, а не абсурдными;
- чередуй типы вопросов: в основном тестовые с 4 вариантами, но можно добавить 2-3 открытых вопроса;
- не делай тест слишком лёгким;
- не добавляй комментарии вне HTML.

Формат HTML должен быть максимально близок к этому шаблону:
{test_format_html}

Дополнительные правила:
1. После каждого вопроса должна быть кнопка "Проверить ответ"
2. Должен быть div для результата проверки
3. Для вопросов с выбором правильный вариант обязан иметь value="correct"
4. Для неправильных вариантов используй value="wrong"
5. Для открытых вопросов добавляй текстовое поле
6. Верни только HTML без markdown-обёртки
"""

        content = self._chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,
            max_tokens=4000
        )

        return self.normalize_html(content)

    def check_answer_with_ai(self, subject, question, user_answer, klass=None, theme=None):
        safe_subject = (subject or "предмет").strip()
        safe_theme = (theme or "").strip()

        prompt = f"""
Ты строгий, но справедливый преподаватель по предмету "{safe_subject}".

Проверь ответ ученика на вопрос.

Контекст:
- Класс: {klass if klass else "не указан"}
- Тема: {safe_theme if safe_theme else "не указана"}

Вопрос:
{question}

Ответ ученика:
{user_answer}

Твои правила проверки:
1. Оцени строго по смыслу ответа.
2. Верни только два варианта итоговой оценки: true или false.
3. Если ответ верный по сути — is_correct = true.
4. Если ответ неверный, неполный по сути или уходит от вопроса — is_correct = false.
5. Если is_correct = false, НЕ ПИШИ правильный ответ.
6. Если is_correct = false, объясни кратко и понятно, почему ответ не засчитан.
7. Если is_correct = true, объясни кратко, почему ответ засчитан.
8. Не пиши "примерно правильно".
9. Не раскрывай эталонный ответ при ошибке.
10. Верни строго JSON и ничего кроме JSON.

Формат ответа:
{{
  "is_correct": true,
  "feedback": "краткое объяснение, почему да или почему нет",
  "correct_answer": ""
}}
"""

        content = self._chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=500
        )

        content = content.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(content)

        if "is_correct" not in parsed:
            parsed["is_correct"] = False
        if "feedback" not in parsed:
            parsed["feedback"] = "Не удалось корректно проверить ответ."
        if "correct_answer" not in parsed:
            parsed["correct_answer"] = ""

        # Жёстко убираем правильный ответ, если ответ неверный
        if parsed["is_correct"] is False:
            parsed["correct_answer"] = ""

        return parsed


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

        checked_answer = model.check_answer_with_ai(subject, question, user_answer, klass, theme)

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
