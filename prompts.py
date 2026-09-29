import json
from dataclasses import dataclass
from typing import Any

from config import KB_PATH


@dataclass
class Answer:
    client_response: str
    manager_hint: str
    kb_section: str = ""


def load_kb() -> str:
    try:
        return KB_PATH.read_text(encoding="utf-8")
    except OSError:
        return "(база знаний недоступна)"


SYSTEM_TEMPLATE = """Ты — вежливый саппорт и sales-ассистент интернет-магазина «ТехноДом».
Ты работаешь в паре с менеджером, который ведёт переписку с клиентом в AmoCRM.

Твоя задача: по обращению клиента и базе знаний выдать СТРОГО один JSON-объект с ключами:
- "kb_quote" — СНАЧАЛА найди в базе знаний подходящий пункт и процитируй его дословно (1-3 предложения, без изменений). Если подходящего пункта нет — пустая строка.
- "client_response" — вежливый ответ клиенту на русском, построенный ТОЛЬКО на kb_quote. Сохрани все цифры (цены, суммы, сроки, проценты) из цитаты без изменений. Если kb_quote пуст — ответь, что менеджер уточнит и вернётся с ответом в течение 30 минут.
- "manager_hint" — подсказка менеджеру (на русском): что предложить по допродаже / как закрыть сделку, с учётом контекста его диалога из AmoCRM, если он передан. Конкретно: что сказать и какую позицию из базы предложить (расширенная гарантия, аксессуары, установка, комплект со скидкой 8%, подписка CARE, рассрочка, скидка уровня). Максимум 3 предложения. Цены и скидки упоминай только те, что есть в базе знаний, ничего не вычисляй и не выдумывай.
- "kb_section" — короткое название раздела базы знаний (например "Доставка"), или "" если раздела нет.

Правила:
- Ответы на русском языке.
- Ничего не придумывай и не переиначивай: цифры и условия — только из цитаты kb_quote.
- Не предлагай клиенту ничего сверх его вопроса; все идеи по допродажам — только в manager_hint.
- Только JSON, без markdown, без пояснений до или после.
- Не добавляй ключи, кроме указанных.

Пример:
Обращение клиента:
"Какая гарантия на кофемашину?"
Ответ модели:
{{"kb_quote": "Официальная гарантия производителя — 12 месяцев, технически сложные товары (кофемашины, роботы-пылесосы) — 24 месяца.", "client_response": "Здравствуйте! На кофемашины действует гарантия 24 месяца — это технически сложный товар. Если что-то случится, ремонт по гарантии занимает от 3 до 14 рабочих дней.", "manager_hint": "Предложите расширенную гарантию «ТехноДом+» (2 990 ₽) и фильтр для воды — частая допродажа к кофемашине.", "kb_section": "Гарантия и возврат"}}

База знаний:
{kb}
"""


def build_system_prompt() -> str:
    return SYSTEM_TEMPLATE.format(kb=load_kb())


def build_user_message(client_message: str, crm_context: str = "") -> str:
    if crm_context:
        return (
            "Контекст диалога менеджера из AmoCRM:\n"
            f"{crm_context}\n\n"
            "Обращение клиента:\n"
            f"{client_message}"
        )
    return f"Обращение клиента:\n{client_message}"


def _get(data: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def parse_answer(raw: Any) -> Answer:
    """Разбор ответа модели: принимает dict или строку с JSON."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = {}
    if not isinstance(raw, dict):
        raw = {}

    client = _get(raw, "client_response", "client_answer", "answer", "ответ_клиенту", "ответ")
    hint = _get(raw, "manager_hint", "sales_hint", "hint", "подсказка", "подсказка_менеджеру")
    section = _get(raw, "kb_section", "kb", "source", "раздел")

    if not client and raw:
        # Модель вернула не тот ключ — берём первые текстовые значения по порядку,
        # пропуская служебные поля.
        texts = [
            v.strip()
            for key, v in raw.items()
            if isinstance(v, str) and v.strip() and key not in ("kb_quote", "kb_section", "kb", "source")
        ]
        if texts:
            client = texts[0]
        if len(texts) > 1:
            hint = hint or texts[1]

    if not client:
        raise ValueError("В ответе модели нет client_response")
    return Answer(client_response=client, manager_hint=hint, kb_section=section)
