from __future__ import annotations

import uuid

import pandas as pd

from config.settings import CANONICAL_COLUMNS


def empty_contacts_dataframe() -> pd.DataFrame:
    return pd.DataFrame(columns=CANONICAL_COLUMNS)


def new_contact_row_dict() -> dict[str, str]:
    row = {column: "" for column in CANONICAL_COLUMNS}
    row["contact_id"] = str(uuid.uuid4())
    return row
