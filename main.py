"""Use the scraper straight from Python — no server needed.

    python main.py

Every call is validated by the same schema the API uses and returns the same
records; results are written to output/*.json.
"""
import json
import os

from schema_fields import load_query
from kmart import api, schemas

os.makedirs("output", exist_ok=True)


def run(schema_cls, fn, **params):
    data, error = load_query(schema_cls, {k: str(v) for k, v in params.items()})
    if error:
        raise ValueError(error)
    return fn(**data)


def save(name, data):
    path = os.path.join("output", name)
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"saved {path}")


if __name__ == "__main__":
    # a keycode or any kmart.com.au product link
    save("product_S169775.json", run(schemas.ProductSchema, api.product_details, product="S169775"))

    # 40 products per page, with facets and per-state stock counts
    save("search_air_fryer.json", run(schemas.ProductsSearchSchema, api.products_search, query="air fryer"))

    # 10 reviews per page, most helpful first
    save("reviews_42725411.json", run(schemas.ProductReviewsSchema, api.product_reviews,
                                      product="42725411", sort="helpful"))
