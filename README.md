# Jira → Telegram daily report bot

Бот шлёт саммари активности Jira (создал / сменил статус / worklog / комментарии).

## Доступ

- Админ chat id: `404740026` (захардкожен)
- `/add_user Имя` — инвайт-токен
- Пользователь: `/start` → токен → имя из Jira → команды
- `/changename` — сменить Jira-пользователя для `/sum`
- Посторонним бот не отвечает (кроме `/start` → запрос токена)

## Запуск / деплой

Локально: `python bot.py`  
VPS: `python deploy_vps.py` (env `VPS_HOST`, `VPS_USER`, `VPS_PASS`)

Сервис: `systemctl status jira-tg-bot`
