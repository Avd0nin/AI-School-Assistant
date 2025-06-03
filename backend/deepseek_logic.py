import requests

url = "https://api.deepseek.com/v1/chat/completions"  # предположительный эндпоинт
api_key = "sk-338c16a44f21420282495748d4f8b729"

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

data = {
    "model": "deepseek-chat",  # или другая модель
    "messages": [
        {"role": "user", "content": "отвечай не используя форматирование и смайлы, только по делу. представь, что ты учитель геометрии в 8 классе. твой ученик хочет подготовится к контрольной работе по темем тригонометрические функции. подготовь для него краткий но ёмкий конспект."}
    ],
    "temperature": 1,  # управление креативностью (0-1)
    "max_tokens": 1000   # ограничение длины ответа
}

response = requests.post(url, json=data, headers=headers)
print(response.json()['choices'][0]['message']['content'])