from flask import Blueprint, request, jsonify
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time


SUPPORTED_CONTEST_LANGUAGES = {"python", "cpp"}
MAX_CONTEST_TESTS = 40
TEST_TIMEOUT_SECONDS = 4
COMPILE_TIMEOUT_SECONDS = 20


def normalize_program_output(text):
    normalized = str(text or "").replace('\r\n', '\n').replace('\r', '\n')
    lines = [line.rstrip() for line in normalized.split('\n')]
    while lines and lines[-1] == '':
        lines.pop()
    return '\n'.join(lines)


def normalize_expected_output(text):
    normalized = str(text or "").replace('\r\n', '\n').replace('\r', '\n')
    normalized = normalized.replace("```", "").replace("`", "")
    normalized = re.sub(r'(?im)^\s*(output|expected)\s*:\s*', '', normalized)
    lines = []
    for line in normalized.split('\n'):
        cleaned = line.rstrip()
        # Preserve negative numbers that sometimes arrive as "- 998".
        cleaned = re.sub(r'^\s*-\s+(\d+(?:[.,]\d+)?)\s*$', r'-\1', cleaned)
        cleaned = re.sub(r'^\s*[-*]\s+', '', cleaned)
        cleaned = re.sub(r'^\s*\d+\.\s+', '', cleaned)
        lines.append(cleaned)
    while lines and lines[0] == '':
        lines.pop(0)
    while lines and lines[-1] == '':
        lines.pop()
    return '\n'.join(lines)


def find_cpp_compiler():
    compiler_candidates = ("g++", "g++.exe", "clang++", "clang++.exe", "c++", "c++.exe")
    for compiler in compiler_candidates:
        path = shutil.which(compiler)
        if path:
            return path

    if os.name == "nt":
        common_windows_paths = (
            r"C:\msys64\mingw64\bin\g++.exe",
            r"C:\msys64\ucrt64\bin\g++.exe",
            r"C:\msys64\clang64\bin\clang++.exe",
            r"C:\mingw64\bin\g++.exe",
            r"C:\MinGW\bin\g++.exe",
        )
        for path in common_windows_paths:
            if os.path.isfile(path):
                return path

    return None


def run_competitive_code(language, code, tests):
    safe_language = str(language or "").strip().lower()
    if safe_language not in SUPPORTED_CONTEST_LANGUAGES:
        return {
            "success": False,
            "error": "Поддерживаются только Python и C++.",
            "compile_error": "",
            "results": []
        }

    if not isinstance(tests, list) or not tests:
        return {
            "success": False,
            "error": "Список тестов пуст.",
            "compile_error": "",
            "results": []
        }

    limited_tests = tests[:MAX_CONTEST_TESTS]

    with tempfile.TemporaryDirectory(prefix="contest_runner_") as tmp_dir:
        executable_cmd = None

        if safe_language == "python":
            source_path = os.path.join(tmp_dir, "solution.py")
            with open(source_path, "w", encoding="utf-8") as source_file:
                source_file.write(code)
            executable_cmd = [sys.executable, source_path]

        elif safe_language == "cpp":
            compiler_path = find_cpp_compiler()
            if not compiler_path:
                return {
                    "success": False,
                    "error": "Не найден компилятор C++ (g++/clang++). Добавьте компилятор в PATH и попробуйте снова.",
                    "compile_error": "",
                    "results": []
                }

            source_path = os.path.join(tmp_dir, "solution.cpp")
            output_path = os.path.join(tmp_dir, "solution.exe" if os.name == "nt" else "solution.out")
            with open(source_path, "w", encoding="utf-8") as source_file:
                source_file.write(code)

            try:
                compile_cmd = [compiler_path, source_path, "-std=c++17", "-O2", "-o", output_path]
                compiler_name = os.path.basename(compiler_path).lower()
                if "g++" in compiler_name:
                    compile_cmd.extend(["-finput-charset=UTF-8", "-fexec-charset=UTF-8"])
                compile_process = subprocess.run(
                    compile_cmd,
                    capture_output=True,
                    text=True,
                    cwd=tmp_dir,
                    timeout=COMPILE_TIMEOUT_SECONDS
                )
            except subprocess.TimeoutExpired:
                return {
                    "success": False,
                    "error": "Компиляция заняла слишком много времени.",
                    "compile_error": f"Превышен лимит компиляции ({COMPILE_TIMEOUT_SECONDS}с).",
                    "results": []
                }
            if compile_process.returncode != 0:
                return {
                    "success": False,
                    "error": "Ошибка компиляции.",
                    "compile_error": (compile_process.stderr or compile_process.stdout or "").strip(),
                    "results": []
                }
            executable_cmd = [output_path]

        results = []
        passed_count = 0

        failed_test_index = None
        failed_status = ""

        for index, test in enumerate(limited_tests, start=1):
            input_data = str((test or {}).get("input", ""))
            expected_output = normalize_expected_output((test or {}).get("output", ""))
            test_note = str((test or {}).get("note", "")).strip()
            started_at = time.perf_counter()

            try:
                process = subprocess.run(
                    executable_cmd,
                    input=input_data,
                    capture_output=True,
                    text=True,
                    cwd=tmp_dir,
                    timeout=TEST_TIMEOUT_SECONDS
                )
                duration_ms = int((time.perf_counter() - started_at) * 1000)

                if process.returncode != 0:
                    results.append({
                        "index": index,
                        "passed": False,
                        "status": "runtime_error",
                        "input": input_data,
                        "expected": expected_output,
                        "actual": (process.stdout or "").rstrip(),
                        "note": test_note,
                        "stderr": (process.stderr or "").strip(),
                        "time_ms": duration_ms
                    })
                    failed_test_index = index
                    failed_status = "runtime_error"
                    break

                actual_output = process.stdout or ""
                is_passed = normalize_program_output(actual_output) == normalize_program_output(expected_output)
                if is_passed:
                    passed_count += 1

                results.append({
                    "index": index,
                    "passed": is_passed,
                    "status": "ok" if is_passed else "wrong_answer",
                    "input": input_data,
                    "expected": expected_output,
                    "actual": actual_output.rstrip(),
                    "note": test_note,
                    "stderr": "",
                    "time_ms": duration_ms
                })
                if not is_passed:
                    failed_test_index = index
                    failed_status = "wrong_answer"
                    break

            except subprocess.TimeoutExpired:
                duration_ms = int((time.perf_counter() - started_at) * 1000)
                results.append({
                    "index": index,
                    "passed": False,
                    "status": "timeout",
                    "input": input_data,
                    "expected": expected_output,
                    "actual": "",
                    "note": test_note,
                    "stderr": f"Превышено время выполнения ({TEST_TIMEOUT_SECONDS}с).",
                    "time_ms": duration_ms
                })
                failed_test_index = index
                failed_status = "timeout"
                break

        return {
            "success": True,
            "error": "",
            "compile_error": "",
            "passed": passed_count,
            "total": len(limited_tests),
            "checked": len(results),
            "failed_test": failed_test_index,
            "verdict": "ok" if failed_test_index is None else failed_status,
            "results": results
        }


def create_contest_blueprint(model, save_contest_callback=None, current_user_id_callback=None):
    contest_bp = Blueprint("contest", __name__)

    @contest_bp.route('/api/contest', methods=['POST'])
    def generate_contest():
        data = request.get_json(silent=True) or {}
        description = str(data.get('description', '')).strip()
        difficulty_raw = str(data.get('difficulty', '5')).strip().lower()
        topics = data.get('topics', [])

        try:
            tasks_count = int(data.get('tasks_count', 3))
        except (TypeError, ValueError):
            tasks_count = 3

        tasks_count = max(1, min(10, tasks_count))
        if not isinstance(topics, list):
            topics = []

        try:
            difficulty_level = int(difficulty_raw)
        except (TypeError, ValueError):
            alias_level_map = {"easy": 2, "medium": 5, "hard": 7, "olymp": 10}
            difficulty_level = alias_level_map.get(difficulty_raw, 5)
        difficulty_level = max(1, min(10, difficulty_level))
        difficulty_labels_ru = {
            1: "очень легкий",
            2: "легкий",
            3: "ниже среднего",
            4: "средний",
            5: "средний+",
            6: "выше среднего",
            7: "сложный",
            8: "очень сложный",
            9: "предолимпиадный",
            10: "олимпиадный",
        }
        difficulty_label = difficulty_labels_ru.get(difficulty_level, "средний")

        user_id = current_user_id_callback() if callable(current_user_id_callback) else None
        if not user_id:
            return jsonify({"error": "Требуется авторизация"}), 401

        try:
            contest_payload = model.create_contest_round(
                description=description,
                difficulty=str(difficulty_level),
                tasks_count=tasks_count,
                topics=topics
            )
            contest_payload["difficulty_label"] = difficulty_label
            if callable(save_contest_callback):
                contest_id = save_contest_callback(
                    user_id=user_id,
                    payload=contest_payload,
                    description=description,
                    difficulty=difficulty_label,
                    tasks_count=tasks_count,
                    duration_minutes=data.get("duration_minutes", 60),
                )
                contest_payload["contest_id"] = int(contest_id)
            return jsonify(contest_payload)
        except Exception as e:
            print(f"Ошибка генерации контеста: {str(e)}")
            return jsonify({
                "error": "Ошибка при генерации контеста. Попробуйте ещё раз."
            }), 500

    @contest_bp.route('/api/contest/run', methods=['POST'])
    def contest_run():
        data = request.get_json(silent=True) or {}
        language = str(data.get('language', '')).strip().lower()
        code = str(data.get('code', ''))
        tests = data.get('tests', [])

        if language not in SUPPORTED_CONTEST_LANGUAGES:
            return jsonify({"success": False, "error": "Выберите язык Python или C++.", "results": []}), 400

        if not code.strip():
            return jsonify({"success": False, "error": "Код не может быть пустым.", "results": []}), 400

        if len(code) > 100_000:
            return jsonify({"success": False, "error": "Код слишком большой.", "results": []}), 400

        run_result = run_competitive_code(language=language, code=code, tests=tests)
        status_code = 200 if run_result.get("success") else 400
        return jsonify(run_result), status_code

    return contest_bp
