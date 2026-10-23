"""Minute-0 check: one BigQuery query and one Gemini call with the pinned model IDs."""

from app.config import get_settings


def main() -> None:
    from google import genai
    from google.cloud import bigquery

    settings = get_settings()
    rows = bigquery.Client(project=settings.gcp_project).query(
        "SELECT COUNT(*) AS n FROM `bigquery-public-data.thelook_ecommerce.orders`"
    ).result()
    print("BigQuery orders:", next(iter(rows))["n"])

    client = genai.Client()
    for model in (settings.model_sql, settings.model_lite):
        reply = client.models.generate_content(model=model, contents="Reply with the single word: ok")
        print(f"Gemini {model}:", (reply.text or "").strip())


if __name__ == "__main__":
    main()
