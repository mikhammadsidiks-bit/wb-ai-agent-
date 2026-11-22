import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone

import requests

API = "https://feedbacks-api.wildberries.ru"
POSITIVE = "Спасибо большое за такой приятный отзыв! ❤️ Очень рады, что вы остались довольны качеством товара и нашей работой. Пользуйтесь с удовольствием! Будем рады видеть вас снова 🥰"
NEGATIVE = "Спасибо за отзыв. Жаль, что впечатление осталось негативным. Напишите, пожалуйста, в поддержку Wildberries — постараемся разобраться в ситуации."

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("wb-autoreply")


def request_with_retry(session, method, url, *, max_attempts=5, **kwargs):
    """Retry temporary API/network failures without logging credentials."""
    for attempt in range(max_attempts):
        try:
            response = session.request(method, url, timeout=30, **kwargs)
        except requests.RequestException:
            if attempt == max_attempts - 1:
                raise
            time.sleep(min(2 ** attempt, 30))
            continue

        if response.status_code == 429 or response.status_code >= 500:
            if attempt == max_attempts - 1:
                return response
            retry_after = response.headers.get("Retry-After", "")
            try:
                delay = max(1, min(int(retry_after), 60))
            except (TypeError, ValueError):
                delay = min(2 ** attempt, 30)
            time.sleep(delay)
            continue
        return response
    raise RuntimeError("Request retry loop ended unexpectedly")


def configured_stores():
    """Read store tokens from Actions secrets exposed as environment variables."""
    stores = []
    primary = os.environ.get("WB_API_TOKEN", "").strip()
    if primary:
        stores.append((os.getenv("WB_STORE_NAME", "Магазин 1"), primary))

    numbered = []
    for key, value in os.environ.items():
        match = re.fullmatch(r"WB_API_TOKEN_(\d+)", key)
        if match and value.strip():
            numbered.append((int(match.group(1)), key, value.strip()))

    for number, key, token in sorted(numbered):
        name = os.getenv(f"WB_STORE_NAME_{number}", f"Магазин {number}")
        stores.append((name, token))

    if not stores:
        raise RuntimeError(
            "Add WB_API_TOKEN (and optionally WB_API_TOKEN_2, "
            "WB_API_TOKEN_3, ...) in GitHub Actions repository secrets."
        )
    return stores


def run_store(store_name, token, lookback_days):
    date_from = int(
        (datetime.now(timezone.utc) - timedelta(days=lookback_days)).timestamp()
    )
    headers = {"Authorization": token, "Accept": "application/json"}
    session = requests.Session()
    sent = 0

    log.info("[%s] Checking unanswered reviews.", store_name)

    # Successful replies disappear from the unanswered list, so keep reading
    # from skip=0 until no unanswered reviews remain on the first page.
    while sent < 500:
        params = {
            "isAnswered": "false",
            "take": 100,
            "skip": 0,
            "order": "dateAsc",
            "dateFrom": date_from,
        }
        response = request_with_retry(
            session, "GET", f"{API}/api/v1/feedbacks",
            headers=headers, params=params,
        )
        if response.status_code != 200:
            raise RuntimeError(
                f"[{store_name}] WB review-list request failed: "
                f"HTTP {response.status_code}. Check token permissions "
                "and WB API availability."
            )

        payload = response.json()
        feedbacks = (payload.get("data") or {}).get("feedbacks") or []
        if not feedbacks:
            break

        batch_sent = 0
        for feedback in feedbacks:
            feedback_id = feedback.get("id")
            rating = feedback.get("productValuation")
            if not feedback_id or not isinstance(rating, int) or not 1 <= rating <= 5:
                log.warning("[%s] Skipped a review with missing ID or invalid rating.", store_name)
                continue

            answer_text = POSITIVE if rating >= 4 else NEGATIVE
            result = request_with_retry(
                session,
                "POST",
                f"{API}/api/v1/feedbacks/answer",
                headers={**headers, "Content-Type": "application/json"},
                json={"id": feedback_id, "text": answer_text},
            )
            if result.status_code != 204:
                raise RuntimeError(
                    f"[{store_name}] WB reply request failed: "
                    f"HTTP {result.status_code}. Check token write permissions "
                    "and WB API availability."
                )

            sent += 1
            batch_sent += 1
            log.info("[%s] Successfully replied to a review (%s stars).", store_name, rating)
            time.sleep(0.4)  # Stay below the personal-token request limit.

        if batch_sent == 0:
            log.warning(
                "[%s] No replies were sent from the current page; stopping "
                "to avoid reprocessing the same unanswered reviews.",
                store_name,
            )
            break

    log.info("[%s] Run finished. Replies sent: %d", store_name, sent)
    return sent


def run():
    lookback_days = int(os.getenv("REVIEW_LOOKBACK_DAYS", "100"))
    if not 1 <= lookback_days <= 365:
        raise RuntimeError("REVIEW_LOOKBACK_DAYS must be between 1 and 365.")

    stores = configured_stores()
    total_sent = 0
    failures = []

    log.info("Starting review processing for %d store(s).", len(stores))
    for store_name, token in stores:
        try:
            total_sent += run_store(store_name, token, lookback_days)
        except Exception as exc:
            # Exception text contains status/error details, never request headers.
            log.error("[%s] Store processing failed: %s", store_name, exc)
            failures.append(store_name)

    log.info("All stores finished. Total replies sent: %d", total_sent)
    if failures:
        raise RuntimeError("Processing failed for store(s): " + ", ".join(failures))


if __name__ == "__main__":
    run()
