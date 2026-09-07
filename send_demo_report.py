"""Одноразовая отправка демо-отчёта (данные из Jira MCP)."""

from datetime import date

from report import IssueRow, build_report, send_telegram

activity = {
    "created": [
        IssueRow(
            "PROMO-1904",
            "Не срабатывает блокировка api_bonus при переборе бонусных карт",
            "К выполнению",
            "https://eda1-lifemart-goulash.atlassian.net/browse/PROMO-1904",
        ),
    ],
    "transitioned": [
        IssueRow(
            "AUTO-628",
            "E2E - Поле промокода не пропускает недопустимы символы",
            "Готово",
            "https://eda1-lifemart-goulash.atlassian.net/browse/AUTO-628",
        ),
        IssueRow(
            "AUTO-624",
            "E2E Просмотр карточки гостя без прав на просмотр",
            "Готово",
            "https://eda1-lifemart-goulash.atlassian.net/browse/AUTO-624",
        ),
        IssueRow(
            "AUTO-644",
            "Е2е Отмена акции при использовании бонусов",
            "Готово",
            "https://eda1-lifemart-goulash.atlassian.net/browse/AUTO-644",
        ),
        IssueRow(
            "PROMO-1767",
            "Статистика рекламных рассылок",
            "Публикация (ожидание)",
            "https://eda1-lifemart-goulash.atlassian.net/browse/PROMO-1767",
        ),
        IssueRow(
            "PROMO-1712",
            "Повторное начисление бонусов за отписку от e-mail",
            "Тестирование",
            "https://eda1-lifemart-goulash.atlassian.net/browse/PROMO-1712",
        ),
        IssueRow(
            "PROMO-1887",
            "cafenf - превышено кол-во авторизаций",
            "Доработка после тестирования",
            "https://eda1-lifemart-goulash.atlassian.net/browse/PROMO-1887",
        ),
    ],
    "worklogged": [],
    "commented": [],
}

if __name__ == "__main__":
    send_telegram(build_report(date(2026, 7, 22), activity))
    print("demo report sent")
