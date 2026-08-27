# symmetrical-funicular

Бот, который берёт новости из RSS-ленты англоязычного крипто-СМИ (по умолчанию
[Unchained Crypto](https://unchainedcrypto.com)), переводит заголовок и краткое
описание на русский язык и публикует их в Telegram-канал. Публикуется только
перевод + ссылка на оригинал — без копирования полного текста статьи.

Работает по расписанию через GitHub Actions, без своего сервера.

## Как это устроено

- `fetch_feed.py` — читает RSS-ленту источника.
- `translate.py` — переводит заголовок/описание. Если задан `ANTHROPIC_API_KEY`,
  используется Claude (лучше справляется с крипто-терминологией); иначе —
  бесплатный Google Translate через `deep-translator`.
- `telegram_post.py` — публикует сообщение в канал через Telegram Bot API.
- `state.py` / `data/seen_ids.json` — хранит id уже опубликованных новостей,
  чтобы не дублировать посты. При самом первом запуске текущие записи ленты
  помечаются как "уже виденные" без публикации — так канал не заваливает
  разом всем архивом источника.
- `.github/workflows/post_news.yml` — запускает бота каждые 30 минут.

## Настройка

1. **Создайте Telegram-бота**: напишите [@BotFather](https://t.me/BotFather),
   команда `/newbot`, сохраните токен.
2. **Добавьте бота администратором** в ваш канал (с правом публиковать сообщения).
3. **Узнайте chat_id канала**: проще всего через `@username` канала (если он
   публичный) — тогда `TELEGRAM_CHAT_ID` = `@your_channel`. Для приватного
   канала chat_id можно получить, переслав любое сообщение из канала боту
   [@getidsbot](https://t.me/getidsbot) или через `getUpdates` Bot API.
4. В настройках репозитория **Settings → Secrets and variables → Actions**
   добавьте secrets:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - `ANTHROPIC_API_KEY` (опционально, для перевода через Claude)
5. По желанию задайте **variables**:
   - `FEED_URL` — RSS другого источника (по умолчанию
     `https://unchainedcrypto.com/feed/`)
   - `SOURCE_NAME` — подпись источника в посте (по умолчанию `Unchained Crypto`)
6. Запустите workflow вручную (вкладка Actions → Post translated crypto news
   to Telegram → Run workflow) для первого "посева" состояния, затем он
   будет тикать сам каждые 30 минут.

## Локальный запуск

```bash
pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN=...
export TELEGRAM_CHAT_ID=@your_channel
python main.py
```

## Важно про авторские права

Публикуется только переведённый заголовок, краткое описание (не более ~500
символов исходного текста) и ссылка на оригинал статьи — это соответствует
обычной практике агрегаторов новостей. Копировать и переводить статьи целиком
без разрешения источника не стоит.
