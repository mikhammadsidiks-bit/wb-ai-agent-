import logging
import os
import time
from datetime import datetime, timezone

import requests

API = "https://feedbacks-api.wildberries.ru"
POSITIVE = "Спасибо большое за такой приятный отзыв! ❤️ Очень рады, что вы остались довольны качеством товара и нашей работой. Пользуйтесь с удовольствием! Будем рады видеть вас снова 🥰"
NEGATIVE = "Спасибо за отзыв. Жаль, что впечатление осталось негативным. Напишите, пожалуйста, в поддержку Wildberries — постараемся разобраться в ситуации."

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

def run():
    token = os.environ.get("WB_API_TOKEN", "").strip()
    start_date = os.environ.get("START_DATE", "").strip()
    if not token:
        raise RuntimeError("WB_API_TOKEN is not configured in GitHub Secrets")
    if not start_date:
        raise RuntimeError("START_DATE is not configured in GitHub Variables (YYYY-MM-DD)")

    start = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    params = {
        "isAnswered": "false",
        "take": 100,
        "skip": 0,
        "order": "dateAsc",
        "dateFrom": int(start.timestamp()),
    }
    headers = {"Authorization": token, "Accept": "application/json"}
    sent = 0
    session = requests.Session()

    # Each successful reply removes one item from the unanswered list.
    # Re-read from skip=0 after each batch so pagination cannot skip reviews.
    while sent < 500:
        response = session.get(
            f"{API}/api/v1/feedbacks",
            headers=headers,
            params=params,
            timeout=30,
        )
        if response.status_code != 200:
            raise RuntimeError(f"WB list request failed: HTTP {response.status_code}: {response.text[:500]}")

        payload = response.json()
        feedbacks = (payload.get("data") or {}).get("feedbacks") or []
        if not feedbacks:
            break

        batch_sent = 0
        for feedback in feedbacks:
            feedback_id = feedback.get("id")
            rating = feedback.get("productValuation")
            if not feedback_id or not isinstance(rating, int) or rating < 1 or rating > 5:
                logging.warning("Skipping review with missing ID or invalid rating")
                continue

            text = POSITIVE if rating >= 4 else NEGATIVE
            result = session.post(
                f"{API}/api/v1/feedbacks/answer",
                headers={**headers, "Content-Type": "application/json"},
                json={"id": feedback_id, "text": text},
                timeout=30,
            )
            if result.status_code != 204:
                # Stop on the first failure; never spin on a review that WB did not accept.
                raise RuntimeError(
                    f"WB reply failed for review {feedback_id}: "
                    f"HTTP {result.status_code}: {result.text[:500]}"
                )
            sent += 1
            batch_sent += 1
            logging.info("Replied to review %s (%s stars)", feedback_id, rating)
            time.sleep(0.4)  # Personal token limit: max 3 requests/second.

        if batch_sent == 0:
            break

    logging.info("Finished. Replies sent: %d", sent)

if __name__ == "__main__":
    run()
