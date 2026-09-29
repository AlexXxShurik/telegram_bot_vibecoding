"""Smoke-тест: парсинг, формат ответа и реальный вызов Ollama.

Запуск: python smoke_test.py
"""
import asyncio
import json

from handlers import format_answer, split_message
from prompts import Answer, build_system_prompt, build_user_message, parse_answer


def test_split_message() -> None:
    ctx, client = split_message("клиент просил скидку\n---\nа если возьму два комплекта?")
    assert ctx == "клиент просил скидку"
    assert client == "а если возьму два комплекта?"
    ctx, client = split_message("сколько стоит доставка?")
    assert ctx == "" and client == "сколько стоит доставка?"
    print("ok: split_message")


def test_parse_answer() -> None:
    raw = json.dumps(
        {"client_response": "Доставка по Москве бесплатно от 5 000 ₽.", "manager_hint": "Предложите фильтр.", "kb_section": "Доставка"}
    )
    answer = parse_answer(raw)
    assert answer.client_response.startswith("Доставка")
    assert answer.kb_section == "Доставка"

    answer = parse_answer({"ответ_клиенту": "Здравствуйте!", "подсказка": "Предложите рассрочку."})
    assert answer.client_response == "Здравствуйте!"

    for bad in ({}, "не json", []):
        try:
            parse_answer(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"ожидали ValueError для {bad!r}")
    print("ok: parse_answer")


def test_format_answer() -> None:
    text = format_answer(Answer(client_response="Ответ <b>", manager_hint="Хинт", kb_section="Гарантия"))
    assert "&lt;b&gt;" in text and "🎯" in text
    print("ok: format_answer")


async def test_ollama() -> None:
    from ollama_client import chat_json, ping

    ok, message = await ping()
    print(("ok: " if ok else "FAIL: ") + message)
    if not ok:
        raise SystemExit(1)

    raw = await chat_json(
        build_system_prompt(),
        build_user_message("Сколько стоит доставка в Москве?", "клиент: бюджет до 10 тысяч"),
    )
    answer = parse_answer(raw)
    print("ok: ollama →", json.dumps(raw, ensure_ascii=False)[:400])
    print("\n--- Формат ответа бота ---\n" + format_answer(answer).replace("<b>", "").replace("</b>", ""))


if __name__ == "__main__":
    test_split_message()
    test_parse_answer()
    test_format_answer()
    asyncio.run(test_ollama())
    print("\nALL PASSED")
